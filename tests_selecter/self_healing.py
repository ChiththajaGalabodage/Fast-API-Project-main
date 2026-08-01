"""Guarded autonomous repair utilities for failed pytest functions.

The repair transaction is intentionally narrow: only the exact failed test
function may change, existing decorators and signatures are preserved, unsafe
AST constructs are rejected, and unsuccessful validation restores the original
file byte-for-byte.
"""

from __future__ import annotations

import ast
import csv
import difflib
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
}
SECRET_ENV_MARKERS = (
    "API_KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PRIVATE_KEY",
    "CREDENTIAL",
)
PROTECTED_TEST_FILES = {"tests/test_self_healing.py"}


class RepairValidationError(ValueError):
    """Raised when a proposed repair violates a safety invariant."""


@dataclass
class FileSnapshot:
    path: Path
    content: bytes
    mode: int


@dataclass
class RepairResult:
    test_id: str
    base_test_id: str
    test_file: str
    function_name: str
    outcome: str
    safety_validated: bool = False
    applied: bool = False
    kept: bool = False
    rolled_back: bool = False
    rollback_verified: bool = False
    rollback_error: str = ""
    validation_runs: int = 0
    rerun_wall_time_sec: float = 0.0
    rerun_test_duration_sec: float = 0.0
    original_sha256: str = ""
    repaired_sha256: str = ""
    reason: str = ""
    patch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitized_subprocess_env() -> dict[str, str]:
    """Return the current environment without API or repository credentials."""
    env = os.environ.copy()
    for key in list(env):
        upper_key = key.upper()
        if (
            key in SECRET_ENV_KEYS
            or upper_key.startswith(("GITHUB_", "ACTIONS_", "RUNNER_"))
            or any(marker in upper_key for marker in SECRET_ENV_MARKERS)
        ):
            env.pop(key, None)
    return env


def normalize_test_id(test_id: str) -> tuple[str, str, str]:
    """Return (file, function name, base node ID) for a pytest node ID."""
    parts = test_id.split("::")
    if len(parts) < 2:
        raise RepairValidationError(f"Invalid pytest node ID: {test_id}")
    function_name = parts[-1].split("[", 1)[0]
    if not function_name.startswith("test_"):
        raise RepairValidationError(f"Not a test function: {function_name}")
    base_test_id = "::".join([*parts[:-1], function_name])
    return parts[0], function_name, base_test_id


def resolve_test_target(test_id: str, project_root: Path | None = None) -> Path:
    """Resolve and allowlist a writable test source path."""
    test_file, _, _ = normalize_test_id(test_id)
    root = (project_root or Path.cwd()).resolve()
    raw_path = Path(test_file)
    path = raw_path if raw_path.is_absolute() else root / raw_path
    try:
        lexical_relative = path.absolute().relative_to(root)
    except ValueError as error:
        raise RepairValidationError("Repair target is outside the project root") from error

    current = root
    for component in lexical_relative.parts:
        current = current / component
        if current.is_symlink():
            raise RepairValidationError("Refusing to repair through a symbolic link")

    resolved = path.resolve(strict=True)
    allowed_roots = []
    for allowed_name in ("tests", "tests_generated"):
        allowed_path = root / allowed_name
        if allowed_path.is_symlink():
            raise RepairValidationError("Refusing a symbolic-link repair directory")
        allowed_root = allowed_path.resolve()
        if not allowed_root.is_relative_to(root):
            raise RepairValidationError("Repair directory resolves outside the project root")
        allowed_roots.append(allowed_root)
    if resolved.suffix.lower() != ".py" or not any(
        resolved.is_relative_to(allowed) for allowed in allowed_roots
    ):
        raise RepairValidationError(
            "Repair target must be a Python file under tests/ or tests_generated/"
        )
    relative_name = resolved.relative_to(root).as_posix().casefold()
    if relative_name in PROTECTED_TEST_FILES:
        raise RepairValidationError("The self-healing safety tests are protected from repair")
    return resolved


def snapshot_file(path: Path) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        content=path.read_bytes(),
        mode=stat.S_IMODE(path.stat().st_mode),
    )


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        ) as handle:
            temp_path = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def restore_snapshot(snapshot: FileSnapshot) -> None:
    _atomic_write(snapshot.path, snapshot.content, snapshot.mode)
    if snapshot.path.read_bytes() != snapshot.content:
        raise OSError(f"Rollback verification failed for {snapshot.path}")


def _rollback_result(result: RepairResult, snapshot: FileSnapshot) -> None:
    """Attempt and verify rollback without hiding the original repair outcome."""
    try:
        restore_snapshot(snapshot)
        result.rolled_back = True
        result.rollback_verified = True
    except Exception as error:  # A failed rollback must be visible in the audit report.
        result.rolled_back = False
        result.rollback_verified = False
        result.rollback_error = str(error)


def save_backup(snapshot: FileSnapshot, backup_dir: Path, project_root: Path | None = None) -> Path:
    root = (project_root or Path.cwd()).resolve()
    try:
        relative = snapshot.path.resolve().relative_to(root)
    except ValueError:
        relative = Path(snapshot.path.name)
    destination = backup_dir / relative
    destination = destination.with_suffix(destination.suffix + ".before")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(snapshot.content)
    return destination


def _find_function(tree: ast.AST, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise RepairValidationError(
            f"Expected exactly one {function_name} function; found {len(matches)}"
        )
    return matches[0]


def extract_test_function_source(test_id: str, project_root: Path | None = None) -> str:
    path = resolve_test_target(test_id, project_root)
    _, function_name, _ = normalize_test_id(test_id)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    node = _find_function(tree, function_name)
    start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
    lines = source.splitlines(keepends=True)
    return "".join(lines[start - 1 : node.end_lineno])


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _assert_count(node: ast.AST) -> int:
    return sum(isinstance(child, ast.Assert) for child in ast.walk(node))


class _ContractShapeNormalizer(ast.NodeTransformer):
    """Erase literal values while retaining assertion and call structure."""

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802 (AST API)
        if isinstance(node.value, bool):
            value: object = node.value
        elif isinstance(node.value, str):
            value = "<str>"
        elif isinstance(node.value, (int, float, complex)):
            value = "<number>"
        elif node.value is None:
            value = "<none>"
        else:
            value = f"<{type(node.value).__name__}>"
        return ast.copy_location(ast.Constant(value=value), node)


class _BodyShapeNormalizer(_ContractShapeNormalizer):
    """Keep reachability-control literals exact while normalizing contract data."""

    def __init__(self) -> None:
        self._preserve_literals = 0

    def visit_Constant(self, node: ast.Constant) -> ast.AST:  # noqa: N802 (AST API)
        if self._preserve_literals:
            return node
        return super().visit_Constant(node)

    def _visit_exact(self, node: ast.AST | None) -> ast.AST | None:
        if node is None:
            return None
        self._preserve_literals += 1
        try:
            return self.visit(node)
        finally:
            self._preserve_literals -= 1

    def visit_If(self, node: ast.If) -> ast.AST:  # noqa: N802 (AST API)
        node.test = self._visit_exact(node.test)
        node.body = [self.visit(item) for item in node.body]
        node.orelse = [self.visit(item) for item in node.orelse]
        return node

    def visit_While(self, node: ast.While) -> ast.AST:  # noqa: N802 (AST API)
        node.test = self._visit_exact(node.test)
        node.body = [self.visit(item) for item in node.body]
        node.orelse = [self.visit(item) for item in node.orelse]
        return node

    def visit_For(self, node: ast.For) -> ast.AST:  # noqa: N802 (AST API)
        node.iter = self._visit_exact(node.iter)
        node.body = [self.visit(item) for item in node.body]
        node.orelse = [self.visit(item) for item in node.orelse]
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AST:  # noqa: N802 (AST API)
        node.iter = self._visit_exact(node.iter)
        node.body = [self.visit(item) for item in node.body]
        node.orelse = [self.visit(item) for item in node.orelse]
        return node

    def visit_Match(self, node: ast.Match) -> ast.AST:  # noqa: N802 (AST API)
        node.subject = self._visit_exact(node.subject)
        for case in node.cases:
            case.pattern = self._visit_exact(case.pattern)
            case.guard = self._visit_exact(case.guard)
            case.body = [self.visit(item) for item in case.body]
        return node

    def visit_comprehension(self, node: ast.comprehension) -> ast.AST:  # noqa: N802
        node.target = self.visit(node.target)
        node.iter = self._visit_exact(node.iter)
        node.ifs = [self._visit_exact(item) for item in node.ifs]
        return node


def _shape(node: ast.AST) -> str:
    normalized = _ContractShapeNormalizer().visit(ast.fix_missing_locations(ast.parse(ast.unparse(node))))
    return ast.dump(normalized, include_attributes=False)


def _assertion_shapes(function: ast.AST) -> list[str]:
    return [_shape(node.test) for node in ast.walk(function) if isinstance(node, ast.Assert)]


def _call_shapes(function: ast.AST) -> list[str]:
    return [_call_name(node.func) for node in ast.walk(function) if isinstance(node, ast.Call)]


def _body_shapes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Preserve control/data flow while allowing contract literal corrections."""
    shapes = []
    for statement in function.body:
        parsed = ast.parse(ast.unparse(statement))
        normalized = _BodyShapeNormalizer().visit(parsed)
        shapes.append(ast.dump(normalized, include_attributes=False))
    return shapes


def _status_expectation_literals(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[int]:
    """Return integer literals compared directly with ``*.status_code``."""

    def is_status_code(node: ast.AST) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == "status_code"

    def integer_literals(node: ast.AST) -> list[int]:
        values = node.elts if isinstance(node, (ast.Tuple, ast.List, ast.Set)) else [node]
        return [
            value.value
            for value in values
            if isinstance(value, ast.Constant)
            and isinstance(value.value, int)
            and not isinstance(value.value, bool)
        ]

    expectations: list[int] = []
    for comparison in (
        node for node in ast.walk(function) if isinstance(node, ast.Compare)
    ):
        operands = [comparison.left, *comparison.comparators]
        for left, right in zip(operands, operands[1:]):
            if is_status_code(left):
                expectations.extend(integer_literals(right))
            elif is_status_code(right):
                expectations.extend(integer_literals(left))
    return expectations


def _contains_repair_sensitive_control_flow(function: ast.AST) -> bool:
    """Refuse repairs where a literal could alter assertion reachability."""
    control_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.TryStar,
        ast.Match,
        ast.With,
        ast.AsyncWith,
        ast.Return,
        ast.Break,
        ast.Continue,
        ast.Raise,
        ast.BoolOp,
        ast.IfExp,
        ast.NamedExpr,
        ast.comprehension,
    )
    return any(isinstance(node, control_nodes) for node in ast.walk(function))


def _is_trivial_assertion(node: ast.AST) -> bool:
    """Reject assertions whose truth can be established without system behavior."""
    try:
        if isinstance(node, ast.Constant):
            return bool(node.value)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            return bool(ast.literal_eval(node))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = ast.literal_eval(node.operand)
            return not bool(operand)
        if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
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


def validate_candidate(
    candidate: str,
    expected_name: str,
    original_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.Module, ast.FunctionDef | ast.AsyncFunctionDef]:
    try:
        module = ast.parse(candidate)
    except SyntaxError as error:
        raise RepairValidationError(f"Candidate syntax error: {error}") from error

    functions = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if len(module.body) != 1 or len(functions) != 1:
        raise RepairValidationError("Candidate must contain exactly one test function")
    function = functions[0]
    if function.name != expected_name:
        raise RepairValidationError(
            f"Candidate function name {function.name!r} does not match {expected_name!r}"
        )
    if isinstance(function, ast.AsyncFunctionDef) != isinstance(
        original_node, ast.AsyncFunctionDef
    ):
        raise RepairValidationError("Candidate must preserve sync/async function type")
    if ast.dump(function.args, include_attributes=False) != ast.dump(
        original_node.args, include_attributes=False
    ):
        raise RepairValidationError("Candidate must preserve the original function signature")
    candidate_return = (
        ast.dump(function.returns, include_attributes=False)
        if function.returns is not None
        else None
    )
    original_return = (
        ast.dump(original_node.returns, include_attributes=False)
        if original_node.returns is not None
        else None
    )
    candidate_type_params = [
        ast.dump(item, include_attributes=False)
        for item in getattr(function, "type_params", [])
    ]
    original_type_params = [
        ast.dump(item, include_attributes=False)
        for item in getattr(original_node, "type_params", [])
    ]
    if (
        candidate_return != original_return
        or function.type_comment != original_node.type_comment
        or candidate_type_params != original_type_params
    ):
        raise RepairValidationError("Candidate must preserve return and generic annotations")
    if function.decorator_list:
        raise RepairValidationError("Candidate must not add or replace decorators")
    if _assert_count(function) != max(1, _assert_count(original_node)):
        raise RepairValidationError("Candidate may not remove existing assertions")
    if _contains_repair_sensitive_control_flow(original_node):
        raise RepairValidationError(
            "Autonomous repair is refused for tests containing control flow that "
            "can change assertion reachability"
        )

    forbidden_nodes = (
        ast.Import,
        ast.ImportFrom,
        ast.Global,
        ast.Nonlocal,
        ast.ClassDef,
        ast.Lambda,
        ast.Yield,
        ast.YieldFrom,
    )
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
        "pytest.skip",
        "pytest.xfail",
        "AsyncClient",
        "Client",
        "urlopen",
        "urlretrieve",
    }
    forbidden_prefixes = (
        "os.",
        "subprocess.",
        "shutil.",
        "pathlib.",
        "socket.",
        "requests.",
        "httpx.",
    )
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
        "read_text",
        "read_bytes",
    }
    forbidden_names = {
        "AsyncClient",
        "Client",
        "aiohttp",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_names.update(forbidden_calls)

    body_nodes = (
        node
        for statement in function.body
        for node in ast.walk(statement)
    )
    for node in body_nodes:
        if isinstance(node, forbidden_nodes):
            raise RepairValidationError(f"Forbidden construct: {type(node).__name__}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not function:
            raise RepairValidationError("Nested functions are not allowed in a repair")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in forbidden_attributes:
                raise RepairValidationError(f"Forbidden attribute access: {node.attr}")
        if isinstance(node, ast.Name) and (
            node.id.startswith("__") or node.id in forbidden_names
        ):
            raise RepairValidationError(f"Forbidden name access: {node.id}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip().lower()
            if value.startswith(("http://", "https://", "//")):
                raise RepairValidationError("External network URLs are forbidden in repairs")
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in forbidden_calls or any(name.startswith(prefix) for prefix in forbidden_prefixes):
                raise RepairValidationError(f"Forbidden call: {name or '<dynamic>'}")

    candidate_assertions = [
        node.test for node in ast.walk(function) if isinstance(node, ast.Assert)
    ]
    if any(_is_trivial_assertion(assertion) for assertion in candidate_assertions):
        raise RepairValidationError("Candidate contains a trivially true assertion")
    if _assertion_shapes(function) != _assertion_shapes(original_node):
        raise RepairValidationError(
            "Candidate must preserve assertion structure; only contract literals may change"
        )
    if _call_shapes(function) != _call_shapes(original_node):
        raise RepairValidationError(
            "Candidate must preserve the original call structure"
        )
    if _body_shapes(function) != _body_shapes(original_node):
        raise RepairValidationError(
            "Candidate must preserve the complete function-body structure; "
            "only contract literals may change"
        )

    original_statuses = _status_expectation_literals(original_node)
    candidate_statuses = _status_expectation_literals(function)
    for index, value in enumerate(candidate_statuses):
        original_value = original_statuses[index] if index < len(original_statuses) else None
        if 500 <= value <= 599 and value != original_value:
            raise RepairValidationError(
                "Candidate may not introduce a new 5xx status expectation"
            )

    return module, function


def build_patched_source(
    original_source: str,
    candidate: str,
    function_name: str,
    filename: str = "<test-file>",
) -> tuple[str, str]:
    original_tree = ast.parse(original_source, filename=filename)
    original_node = _find_function(original_tree, function_name)
    _, candidate_node = validate_candidate(candidate, function_name, original_node)

    newline = "\r\n" if "\r\n" in original_source else "\n"
    candidate_lines = candidate.replace("\r\n", "\n").splitlines()
    candidate_body = candidate_lines[candidate_node.lineno - 1 : candidate_node.end_lineno]
    indentation = " " * original_node.col_offset
    replacement = newline.join(
        f"{indentation}{line}" if line.strip() else "" for line in candidate_body
    ).rstrip() + newline

    original_lines = original_source.splitlines(keepends=True)
    patched = (
        "".join(original_lines[: original_node.lineno - 1])
        + replacement
        + "".join(original_lines[original_node.end_lineno :])
    )
    compile(patched, filename, "exec")
    return patched, "".join(
        difflib.unified_diff(
            original_source.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )


def _run_test_node(
    test_id: str, timeout_sec: int, root_dir: Path | None = None
) -> tuple[bool, float, float, str]:
    pytest_root = (root_dir or Path.cwd()).resolve()
    with tempfile.TemporaryDirectory(prefix="llm_ctf_heal_") as temp_dir:
        csv_path = os.path.join(temp_dir, "rerun.csv")
        command = [
            sys.executable,
            "-m",
            "pytest",
            test_id,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            f"--rootdir={pytest_root}",
            f"--csv={csv_path}",
            "--csv-columns=id,status,duration,message",
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                env=sanitized_subprocess_env(),
                cwd=str(pytest_root),
            )
        except subprocess.TimeoutExpired as error:
            wall_time = round(time.monotonic() - started, 3)
            return False, wall_time, 0.0, f"Validation timed out after {timeout_sec}s: {error}"
        wall_time = round(time.monotonic() - started, 3)
        rows: list[dict[str, str]] = []
        if os.path.exists(csv_path):
            with open(csv_path, encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        passed = completed.returncode == 0 and bool(rows) and all(
            row.get("status") == "passed" for row in rows
        )
        duration = sum(float(row.get("duration") or 0) for row in rows)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        return passed, wall_time, round(duration, 6), output[-2000:]


def attempt_repair(
    test_id: str,
    candidate: str,
    *,
    project_root: Path | None = None,
    backup_dir: Path | None = None,
    validation_runs: int = 2,
    timeout_sec: int = 60,
) -> RepairResult:
    test_file, function_name, base_test_id = normalize_test_id(test_id)
    result = RepairResult(
        test_id=test_id,
        base_test_id=base_test_id,
        test_file=test_file,
        function_name=function_name,
        outcome="rejected",
    )
    snapshot: FileSnapshot | None = None
    try:
        path = resolve_test_target(test_id, project_root)
        snapshot = snapshot_file(path)
        result.original_sha256 = hashlib.sha256(snapshot.content).hexdigest()
        original_source = snapshot.content.decode("utf-8")
        patched_source, patch = build_patched_source(
            original_source, candidate, function_name, test_file
        )
        patched_bytes = patched_source.encode("utf-8")
        result.repaired_sha256 = hashlib.sha256(patched_bytes).hexdigest()
        result.patch = patch
        result.safety_validated = True

        if backup_dir:
            save_backup(snapshot, backup_dir, project_root)
        _atomic_write(path, patched_bytes, snapshot.mode)
        result.applied = True

        total_wall = 0.0
        total_duration = 0.0
        for _ in range(max(validation_runs, 1)):
            passed, wall, duration, output = _run_test_node(
                base_test_id, timeout_sec, project_root
            )
            total_wall += wall
            total_duration += duration
            result.validation_runs += 1
            if not passed:
                _rollback_result(result, snapshot)
                result.outcome = "rolled_back" if result.rollback_verified else "rollback_failed"
                result.reason = f"Repaired test did not pass validation: {output[-1000:]}"
                if result.rollback_error:
                    result.reason += f"; rollback error: {result.rollback_error}"
                result.rerun_wall_time_sec = round(total_wall, 3)
                result.rerun_test_duration_sec = round(total_duration, 6)
                return result

        result.kept = True
        result.outcome = "healed"
        result.reason = "Safety checks passed and the repaired test passed repeated validation"
        result.rerun_wall_time_sec = round(total_wall, 3)
        result.rerun_test_duration_sec = round(total_duration, 6)
        return result
    except (OSError, UnicodeError, SyntaxError, RepairValidationError) as error:
        if snapshot and result.applied:
            _rollback_result(result, snapshot)
        result.outcome = "rejected" if not result.rollback_error else "rollback_failed"
        result.reason = str(error)
        if result.rollback_error:
            result.reason += f"; rollback error: {result.rollback_error}"
        return result
    except Exception as error:
        if snapshot and result.applied:
            _rollback_result(result, snapshot)
        result.outcome = "error" if not result.rollback_error else "rollback_failed"
        result.reason = f"Unexpected repair error: {error}"
        if result.rollback_error:
            result.reason += f"; rollback error: {result.rollback_error}"
        return result


def write_healing_artifacts(
    report_path: str | Path,
    patch_path: str | Path,
    results: list[RepairResult],
    *,
    model: str,
    initial_failed_count: int,
    final_failed_count: int,
    final_validation_passed: bool,
) -> None:
    report = Path(report_path)
    patch = Path(patch_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    patch.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "initial_failed_count": initial_failed_count,
        "healed_count": sum(item.outcome == "healed" for item in results),
        "rollback_failed_count": sum(
            bool(item.rollback_error) or item.outcome == "rollback_failed"
            for item in results
        ),
        "final_failed_count": final_failed_count,
        "final_validation_passed": final_validation_passed,
        "attempts": [item.to_dict() for item in results],
    }
    report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    accepted_patches = [item.patch for item in results if item.kept and item.patch]
    patch.write_text("\n".join(accepted_patches), encoding="utf-8")
