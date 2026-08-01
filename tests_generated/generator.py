import ast
import asyncio
import csv
import json
import os
import re
import subprocess
import sys
from typing import Optional

import httpx
from dotenv import load_dotenv
from openai import OpenAI  # Use OpenRouter via OpenAI-compatible SDK

# ---------------------------------------------------------------------------
# Load .env and set OpenRouter client
# ---------------------------------------------------------------------------
load_dotenv()

# OpenRouter utilizes its own API key structure
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print(
        "OPENROUTER_API_KEY is not set; using committed generated-test fallback."
    )

# Use OpenRouter's identifier for Gemini models
# Valid options include: "google/gemini-2.5-flash" or "google/gemini-2.5-pro"
MODEL_NAME = os.getenv("GEMINI_MODEL", "google/gemini-2.5-flash")
if OPENROUTER_API_KEY:
    print(f"Using OpenRouter Gemini model: {MODEL_NAME}")

# Initialize OpenAI client pointed directly to OpenRouter's endpoint
client = (
    OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    if OPENROUTER_API_KEY
    else None
)

SERVER_URL = "http://localhost:8000"

# Max tokens per generation request. OpenRouter free/low-credit accounts cap
# total tokens-affordable-per-request (your account is currently capped
# around ~1100). Keep this comfortably under that ceiling - override via
# the MAX_TOKENS env var once you add credits and want richer test bodies.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))


def sanitized_pytest_env() -> dict[str, str]:
    """Do not expose LLM or CI credentials to generated test code."""
    env = os.environ.copy()
    secret_markers = (
        "API_KEY",
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "PRIVATE_KEY",
        "CREDENTIAL",
    )
    for key in list(env):
        upper_key = key.upper()
        if upper_key.startswith(("GITHUB_", "ACTIONS_", "RUNNER_")) or any(
            marker in upper_key for marker in secret_markers
        ):
            env.pop(key, None)
    return env


def write_csv(path: str, rows: list[dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id", "status", "duration", "message"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def generated_results_path() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "..", "reports", "generated_test_results.csv")


def run_committed_generated_tests(reason: str) -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "generated_test.py")
    csv_path = generated_results_path()
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    print(f"{reason} Running committed generated tests instead.")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                output_path,
                "--cov=main",
                "--cov-report=term-missing",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                f"--csv={csv_path}",
                "--csv-columns=id,status,duration,message",
            ],
            capture_output=False,
            text=True,
            env=sanitized_pytest_env(),
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("Committed generated-test fallback timed out after 300 seconds.")
        return 124
    print(f"Wrote CSV report to {csv_path}")
    return result.returncode


# ---------------------------------------------------------------------------
# Step 1 - Fetch OpenAPI spec
# ---------------------------------------------------------------------------
async def fetch_openapi():
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.get(f"{SERVER_URL}/openapi.json")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Step 1b - Build a plausible request body from a JSON Schema (best-effort)
# ---------------------------------------------------------------------------
def _resolve_schema(schema: dict, components: dict) -> dict:
    """Resolve a single level of $ref against components.schemas."""
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return components.get("schemas", {}).get(ref_name, {})
    return schema


def _sample_value_for_property(name: str, prop: dict):
    """Generate a small, schema-valid placeholder value for one field."""
    p_type = prop.get("type")
    if "minimum" in prop:
        return prop["minimum"]
    if p_type == "integer":
        return 1
    if p_type == "number":
        return 1.0
    if p_type == "boolean":
        return True
    if p_type == "array":
        return []
    if p_type == "string":
        fmt = prop.get("format")
        if fmt == "email" or "email" in name.lower():
            return "sample@example.com"
        min_len = prop.get("minLength", 1)
        return ("sample text " * 3)[: max(min_len, len("sample"))] or "sample"
    return "sample"


def build_sample_body(operation: dict, spec: dict) -> Optional[dict]:
    """Build a minimal valid JSON body from requestBody schema, if any."""
    req_body = operation.get("requestBody", {})
    if not req_body:
        return None
    content = req_body.get("content", {}).get("application/json", {})
    schema = content.get("schema", {})
    schema = _resolve_schema(schema, spec.get("components", {}))
    properties = schema.get("properties", {})
    if not properties:
        return None
    return {
        name: _sample_value_for_property(name, prop)
        for name, prop in properties.items()
    }


def build_sample_path(path: str) -> str:
    """Replace {param} placeholders in a path with a safe sample value (1)."""
    return re.sub(r"\{[^}]+\}", "1", path)


# ---------------------------------------------------------------------------
# Step 1c - Call the live server once per endpoint to get a REAL response.
#
# This is the fix for hallucinated response shapes: instead of asking the
# LLM to guess field names from a possibly-empty OpenAPI response schema,
# we show it one real, ground-truth JSON response from the running server.
# Best-effort only - if the call fails (e.g. needs a real existing ID),
# we fall back to "no sample available" and the LLM uses the spec alone.
# ---------------------------------------------------------------------------
async def fetch_sample_response(
    http_client: httpx.AsyncClient, path: str, method: str, operation: dict, spec: dict
) -> Optional[dict]:
    sample_path = build_sample_path(path)
    url = f"{SERVER_URL}{sample_path}"
    try:
        if method.lower() == "get":
            resp = await http_client.get(url, timeout=5.0)
        elif method.lower() == "delete":
            # Never actually delete data while sampling - skip live-fetch for DELETE.
            return None
        elif method.lower() in ("post", "put"):
            body = build_sample_body(operation, spec)
            # Don't let a sampling call mutate state in ways that break later
            # tests (e.g. don't POST /api/posts for real). Only sample safe,
            # idempotent-ish endpoints; skip mutating writes.
            if path.rstrip("/") in ("/api/reset", "/api/seed", "/api/error-injection"):
                return None
            resp = await http_client.request(
                method.upper(), url, json=body, timeout=5.0
            )
        else:
            return None

        if resp.status_code >= 500:
            return None
        try:
            return {"status_code": resp.status_code, "json": resp.json()}
        except ValueError:
            return {"status_code": resp.status_code, "json": None}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Step 2 - Build LLM prompt
# ---------------------------------------------------------------------------
def build_prompt(path, method, operation, sample_response: Optional[dict] = None):
    params = operation.get("parameters", [])
    req_body = operation.get("requestBody", {})
    responses = operation.get("responses", {})
    summary = operation.get("summary", "")
    description = operation.get("description", "")

    if sample_response is not None:
        sample_block = f"""
Real Live Response (ground truth - fetched from the running server just now,
status {sample_response["status_code"]}):
{json.dumps(sample_response["json"], indent=2)}

This is the ACTUAL response shape. Base your assertions on these exact keys
and structure - do NOT assume different field names than what is shown here.
"""
    else:
        sample_block = """
No live sample response was available for this endpoint (e.g. it mutates
state or requires an existing resource). Rely on the OpenAPI schema below,
and keep structural assertions conservative (e.g. assert response.json() is
a dict/list) rather than asserting specific field names you are not sure of.
"""

    prompt = f"""You are an expert QA engineer writing pytest-asyncio tests for a FastAPI backend.

Endpoint:
- Path: {path}
- Method: {method.upper()}
- Summary: {summary}
- Description: {description}

Parameters:
{json.dumps(params, indent=2)}

Request Body (if any):
{json.dumps(req_body, indent=2)}

Expected Responses (OpenAPI spec):
{json.dumps(responses, indent=2)}
{sample_block}
CRITICAL - exact path string: use the path EXACTLY as
"{path}" (with parameter values substituted) for every request you make to
this endpoint, including in any setup/arrange step. Do NOT add or remove a
trailing slash - "{path}" and "{path}/" are different routes and the wrong
one returns 307, not the response you expect.

CRITICAL - numeric validation boundaries: when the Request Body schema above
specifies "minimum"/"maximum" (or ge/le) on a numeric field, an "invalid"
test value must be strictly outside that range (e.g. minimum - 1 or
maximum + 1), not just any number you guess. Re-read the schema's
minimum/maximum values above before writing the invalid-payload test case.

Write a **single** pytest-asyncio test function that:
- Takes `client` as its only parameter - this is an async httpx.AsyncClient fixture provided by the project's conftest.py. Do not define or import it yourself.
- Covers the happy path and the main error cases (404, 422 validation errors) ONLY if they are actually applicable to this specific endpoint based on the spec above. Skip inapplicable cases silently - do not write comments explaining why a case doesn't apply.
- For GET: test a valid ID and an invalid/nonexistent ID, if the endpoint takes an ID.
- For POST: test valid creation, invalid payload (blank/too long/out-of-range per the boundary rule above), and user not found, if applicable.
- For PUT: test update, 404, validation errors, if applicable.
- For DELETE: test deletion, then 404 on second attempt, if applicable.
- Asserts status codes, and asserts response structure using ONLY the keys shown in the Real Live Response above (if provided) - do not invent field names.
- Contains NO comments and NO explanatory prose - only executable code. Every line must be a statement, not a note.
- Uses only relative API paths beginning with `/` through the provided `client` fixture.
- Contains no imports, decorators, skips/xfails, filesystem/process/environment access, external URLs, dynamic execution, or nested functions/classes.

Name the function: `test_{method}_api_{path.replace("/", "_").strip("_")}`

Return **only the Python code**, no markdown fences, no extra text.
"""
    return prompt


# ---------------------------------------------------------------------------
# Step 3a - Extract code from a model response and validate it
# ---------------------------------------------------------------------------
def _extract_code(text: str) -> str:
    """Pull code out of a ```python ... ``` / ``` ... ``` fence if present.

    Using a regex here (rather than fixed-width slicing on startswith) is
    robust to variations like ```py, ```Python, a fence with no trailing
    newline, or stray prose the model added despite being told not to.
    """
    text = text.strip()
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # No fences found - assume the whole response is already raw code.
    return text


def _is_valid_python(code: str) -> bool:
    """Quick syntax check so we never write unparseable code to disk."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _is_statically_truthy_assertion(node: ast.AST) -> bool:
    """Evaluate only literal-only assertion forms; never execute generated code."""
    try:
        if isinstance(node, ast.Constant):
            return bool(node.value)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return bool(node.elts)
        if isinstance(node, ast.Dict):
            return bool(node.keys)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not bool(ast.literal_eval(node.operand))
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
            if ast.dump(node.left, include_attributes=False) == ast.dump(
                node.comparators[0], include_attributes=False
            ) and isinstance(node.ops[0], (ast.Eq, ast.Is, ast.LtE, ast.GtE)):
                return True
            left = ast.literal_eval(node.left)
            right = ast.literal_eval(node.comparators[0])
            operator = node.ops[0]
            if isinstance(operator, ast.Eq):
                return left == right
            if isinstance(operator, ast.NotEq):
                return left != right
            if isinstance(operator, ast.Is):
                return left is right
            if isinstance(operator, ast.IsNot):
                return left is not right
            if isinstance(operator, ast.In):
                return left in right
            if isinstance(operator, ast.NotIn):
                return left not in right
            if isinstance(operator, ast.Lt):
                return left < right
            if isinstance(operator, ast.LtE):
                return left <= right
            if isinstance(operator, ast.Gt):
                return left > right
            if isinstance(operator, ast.GtE):
                return left >= right
    except (TypeError, ValueError, SyntaxError):
        return False
    return False


def _bound_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in target.elts:
            names.update(_bound_names(item))
        return names
    return set()


def _is_client_request_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "client"
        and node.func.attr in {"get", "post", "put", "patch", "delete", "request"}
    )


def _is_direct_client_response(node: ast.AST) -> bool:
    """Return True only when an expression is exactly a fixture request result."""
    value = node.value if isinstance(node, ast.Await) else node
    return _is_client_request_call(value)


def _is_http_status_comparison(node: ast.AST, derived_names: set[str]) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    left = node.left
    if not (
        isinstance(left, ast.Attribute)
        and left.attr == "status_code"
        and isinstance(left.value, ast.Name)
        and left.value.id in derived_names
    ):
        return False
    right = node.comparators[0]
    if isinstance(node.ops[0], ast.Eq):
        return (
            isinstance(right, ast.Constant)
            and isinstance(right.value, int)
            and 100 <= right.value <= 499
        )
    if isinstance(node.ops[0], ast.In) and isinstance(right, (ast.Tuple, ast.List, ast.Set)):
        values = [item.value for item in right.elts if isinstance(item, ast.Constant)]
        return len(values) == len(right.elts) and bool(values) and all(
            isinstance(value, int) and 100 <= value <= 499 for value in values
        )
    return False


def _generated_test_validation_error(code: str) -> Optional[str]:
    """Return a deterministic safety-policy error, or None for an allowed test."""
    try:
        module = ast.parse(code)
    except SyntaxError as error:
        return f"syntax error: {error}"

    if len(module.body) != 1 or not isinstance(module.body[0], ast.AsyncFunctionDef):
        return "output must contain exactly one async test function"
    function = module.body[0]
    if not function.name.startswith("test_"):
        return "function name must start with test_"
    if function.decorator_list:
        return "generated functions may not add decorators"
    args = function.args
    if (
        args.posonlyargs
        or len(args.args) != 1
        or args.args[0].arg != "client"
        or args.vararg
        or args.kwarg
        or args.kwonlyargs
        or args.defaults
        or args.kw_defaults
        or args.args[0].annotation is not None
        or function.returns is not None
        or function.type_comment is not None
        or getattr(function, "type_params", [])
    ):
        return "generated function signature must be exactly (client)"
    if not any(isinstance(node, ast.Assert) for node in ast.walk(function)):
        return "generated tests must contain an assertion"

    forbidden_nodes = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.Global,
        ast.Nonlocal,
        ast.Lambda,
        ast.Yield,
        ast.YieldFrom,
        ast.Delete,
        ast.NamedExpr,
        ast.AugAssign,
        ast.IfExp,
        ast.Return,
        ast.Break,
        ast.Continue,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.TryStar,
        ast.Match,
        ast.With,
        ast.AsyncWith,
    )
    forbidden_names = {
        "AsyncClient",
        "Client",
        "aiohttp",
        "httpx",
        "os",
        "pathlib",
        "pytest",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "urllib",
        "open",
        "eval",
        "exec",
        "compile",
        "__import__",
        "input",
        "breakpoint",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "exit",
        "quit",
        "any",
        "all",
    }
    forbidden_calls = {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "input",
        "breakpoint",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "exit",
        "quit",
    }
    forbidden_attributes = {
        "system",
        "popen",
        "Popen",
        "run",
        "call",
        "check_call",
        "check_output",
        "unlink",
        "rmdir",
        "rmtree",
        "write_text",
        "write_bytes",
        "read_text",
        "read_bytes",
        "chmod",
        "chown",
        "remove",
        "write",
        "writelines",
        "read",
        "readline",
        "readlines",
        "send",
        "connect",
        "clear",
        "pop",
        "popitem",
        "setdefault",
        "update",
        "append",
        "extend",
        "insert",
        "sort",
        "reverse",
    }

    relative_client_calls = 0
    for node in ast.walk(function):
        if isinstance(node, forbidden_nodes):
            return f"forbidden construct: {type(node).__name__}"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not function:
            return "nested functions are forbidden"
        if isinstance(node, ast.Name) and (
            node.id.startswith("__") or node.id in forbidden_names
        ):
            return f"forbidden name: {node.id}"
        if (
            isinstance(node, ast.Name)
            and node.id == "client"
            and isinstance(node.ctx, ast.Store)
        ):
            return "the provided client fixture may not be reassigned"
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("_") or node.attr in forbidden_attributes
        ):
            return f"forbidden attribute: {node.attr}"
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
            node.ctx, ast.Store
        ):
            return "mutation of attributes or response containers is forbidden"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                return f"forbidden call: {node.func.id}"
            if isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_attributes:
                return f"forbidden call: {node.func.attr}"
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "client"
                and node.func.attr in {"get", "post", "put", "patch", "delete", "request"}
            ):
                relative_client_calls += 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if "://" in value or value.startswith("//"):
                return "external URLs are forbidden"
            if value.startswith("/") and not value.startswith("/api/"):
                return "requests must target a relative /api/ path"
        if isinstance(node, ast.Assert) and _is_statically_truthy_assertion(node.test):
            return "trivially true assertions are forbidden"

    if relative_client_calls == 0:
        return "generated tests must call the provided client fixture"
    # Track response provenance in source order.  Using the final set of derived
    # names would let an assertion over fabricated data be "validated" by a real
    # request that only occurs later in the function.
    derived_names: set[str] = set()
    direct_response_names: set[str] = set()
    request_seen = False
    has_status_assertion = False
    for statement in function.body:
        assigned_names: set[str] = set()
        assigned_value: ast.AST | None = None
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                assigned_names.update(_bound_names(target))
            assigned_value = statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            assigned_names = _bound_names(statement.target)
            assigned_value = statement.value

        if assigned_value is not None and assigned_names:
            value_names = {
                child.id
                for child in ast.walk(assigned_value)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            }
            from_client = any(
                _is_client_request_call(child) for child in ast.walk(assigned_value)
            )
            direct_response = _is_direct_client_response(assigned_value)
            remains_derived = from_client or bool(
                value_names.intersection(derived_names)
            )
            derived_names.difference_update(assigned_names)
            direct_response_names.difference_update(assigned_names)
            if remains_derived:
                derived_names.update(assigned_names)
            if direct_response:
                direct_response_names.update(assigned_names)
            request_seen = request_seen or from_client
        else:
            request_seen = request_seen or any(
                _is_client_request_call(child) for child in ast.walk(statement)
            )

        if not isinstance(statement, ast.Assert):
            continue
        assertion = statement
        assertion_names = {
            child.id
            for child in ast.walk(assertion.test)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
        }
        direct_client_call = any(
            _is_client_request_call(child) for child in ast.walk(assertion.test)
        )
        if (
            not request_seen
            or (
                not direct_client_call
                and not assertion_names.intersection(derived_names)
            )
        ):
            return "every assertion must reference data derived from the client response"
        if any(
            _is_http_status_comparison(child, direct_response_names)
            for child in ast.walk(assertion.test)
        ):
            has_status_assertion = True
        for child in ast.walk(assertion.test):
            if isinstance(child, ast.BoolOp) and isinstance(child.op, ast.Or):
                return "boolean OR is forbidden in generated assertions"
    if not has_status_assertion:
        return "generated tests must assert a client response status_code"

    return None


# ---------------------------------------------------------------------------
# Step 3 - Call OpenRouter (non-streaming), with validation + one retry
# ---------------------------------------------------------------------------
async def generate_test(prompt, retries: int = 1):
    last_invalid_code = None

    for attempt in range(retries + 1):
        try:
            # Offload the synchronous OpenAI/OpenRouter client call to an async thread pool
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                # 800 tokens is too tight for a function covering happy-path +
                # 404 + 422 + structure assertions - truncation mid-function
                # is the most common cause of "syntax/indentation errors".
                # Capped via MAX_TOKENS to also respect OpenRouter credit limits.
                max_tokens=MAX_TOKENS,
                extra_headers={
                    "HTTP-Referer": "https://localhost:8000",  # Optional OpenRouter leaderboard tracking
                    "X-Title": "FastAPI Test Generator",
                },
            )

            raw = response.choices[0].message.content.strip()
            code = _extract_code(raw)

            validation_error = _generated_test_validation_error(code)
            if validation_error is None:
                return code

            last_invalid_code = code
            remaining = retries - attempt
            print(
                f"   Attempt {attempt + 1} produced a rejected test "
                f"({validation_error}) - {'retrying' if remaining > 0 else 'giving up'}."
            )

        except Exception as e:
            err_str = str(e)
            if "402" in err_str or "more credits" in err_str.lower():
                print(
                    "OpenRouter rejected the request for insufficient "
                    "credits/budget at the current max_tokens "
                    f"({MAX_TOKENS}). Lower MAX_TOKENS, or add credits at "
                    "https://openrouter.ai/settings/credits."
                )
            else:
                print(f"OpenRouter Gemini call failed: {e}")
            return None

    # All retries exhausted and still invalid - skip rather than corrupt the file.
    if last_invalid_code is not None:
        print("   Skipping this test: could not get valid Python after retries.")
    return None


# ---------------------------------------------------------------------------
# Step 4 - Write generated tests to file and run them
# ---------------------------------------------------------------------------
async def main():
    if client is None:
        sys.exit(
            run_committed_generated_tests(
                "OPENROUTER_API_KEY is missing."
            )
        )

    print("Fetching OpenAPI spec...")
    spec = await fetch_openapi()
    print(f"Found {len(spec['paths'])} endpoints.")

    operations = [
        (path, method, operation)
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
        if method.lower() in {"get", "post", "put", "delete"}
    ]
    all_tests = []
    async with httpx.AsyncClient() as http_client:
        for path, method, operation in operations:
            print(f"Generating test for {method.upper()} {path} ...")
            sample_response = await fetch_sample_response(
                http_client, path, method, operation, spec
            )
            if sample_response is not None:
                print(
                    f"   Got live sample response (status {sample_response['status_code']})"
                )
            else:
                print("   No live sample available - falling back to spec only")
            prompt = build_prompt(path, method, operation, sample_response)
            code = await generate_test(prompt)
            if code:
                all_tests.append(code)
            else:
                print(f"Skipping {method.upper()} {path} due to generation error.")

    if len(all_tests) != len(operations):
        sys.exit(
            run_committed_generated_tests(
                f"LLM generated {len(all_tests)} of {len(operations)} required tests; "
                "partial output will not replace the committed suite."
            )
        )

    # Dynamically locate the script's directory (tests_generated/)
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_PATH = os.path.join(SCRIPT_DIR, "generated_test.py")

    header = (
        "import pytest\n\n"
        "# ---------------------------------------------------------------------------\n"
        "# Generated tests - review before committing\n"
        "# The `client` and `reset_db` fixtures come from the project-root\n"
        "# conftest.py (auto-discovered by pytest) - no import needed here.\n"
        "# ---------------------------------------------------------------------------\n\n"
    )
    full_file_contents = header + "\n\n".join(all_tests)

    # Defense in depth: each function was validated individually, but verify
    # the fully concatenated file too, in case of duplicate function names or
    # other interaction effects between generations.
    full_file_valid = _is_valid_python(full_file_contents)
    if full_file_valid:
        generated_tree = ast.parse(full_file_contents)
        generated_names = [
            node.name
            for node in generated_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        full_file_valid = len(generated_names) == len(set(generated_names))
    if not full_file_valid:
        print(
            "The concatenated test file is invalid or has duplicate function "
            "names. Preserving and running the committed fallback instead."
        )
        sys.exit(run_committed_generated_tests("Generated candidate was rejected."))

    # Save the file using the absolute output path
    with open(OUTPUT_PATH, encoding="utf-8", mode="w") as f:
        f.write(full_file_contents)

    print(f"Wrote {len(all_tests)} tests to {OUTPUT_PATH}")

    # -----------------------------------------------------------------------
    # Step 5 - Run pytest with coverage, and emit a CSV report
    # -----------------------------------------------------------------------
    print("\nRunning generated tests with coverage...\n")
    REPORTS_DIR = os.path.join(SCRIPT_DIR, "..", "reports")
    os.makedirs(REPORTS_DIR, exist_ok=True)
    CSV_PATH = os.path.join(REPORTS_DIR, "generated_test_results.csv")

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                OUTPUT_PATH,  # Use the dynamic path here too!
                "--cov=main",
                "--cov-report=term-missing",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                f"--csv={CSV_PATH}",
                "--csv-columns=id,status,duration,message",
            ],
            capture_output=False,
            text=True,
            env=sanitized_pytest_env(),
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("Generated tests timed out after 300 seconds.")
        sys.exit(124)
    print(f"Wrote CSV report to {CSV_PATH}")
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(main())
