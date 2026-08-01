import argparse
import asyncio
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

try:
    from tests_selecter.self_healing import (
        RepairResult,
        RepairValidationError,
        attempt_repair,
        extract_test_function_source,
        normalize_test_id,
        resolve_test_target,
        restore_snapshot,
        sanitized_subprocess_env,
        snapshot_file,
        write_healing_artifacts,
    )
except ModuleNotFoundError:  # Direct execution: python tests_selecter/selecter.py
    from self_healing import (
        RepairResult,
        RepairValidationError,
        attempt_repair,
        extract_test_function_source,
        normalize_test_id,
        resolve_test_target,
        restore_snapshot,
        sanitized_subprocess_env,
        snapshot_file,
        write_healing_artifacts,
    )

# ---------------------------------------------------------------------------
# Load environment and OpenRouter client
# ---------------------------------------------------------------------------
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    print("OPENROUTER_API_KEY is not set; using deterministic selector fallback.")

MODEL_NAME = os.getenv("GEMINI_MODEL", "google/gemini-2.5-flash")
if OPENROUTER_API_KEY:
    print(f"Using OpenRouter Gemini model: {MODEL_NAME}")

client = (
    OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
    if OPENROUTER_API_KEY
    else None
)


# ---------------------------------------------------------------------------
# Step 1 - Get code diff
# ---------------------------------------------------------------------------
def get_git_diff(commit: str = "HEAD") -> str:
    """Run git diff and return the unified diff as string."""
    try:
        result = subprocess.run(
            ["git", "diff", commit],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        print("Could not run git diff. Ensure you are in a git repo.")
        return ""


def read_diff_file(path: str) -> str:
    """Read a unified diff from a file on disk."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Could not read diff file {path}: {e}")
        return ""


def parse_diff(diff_text: str) -> Dict[str, List[int]]:
    """
    Extract changed files and line numbers from a unified diff.
    Returns a dict: {filename: [line_numbers_of_changes]}.
    """
    changes: Dict[str, List[int]] = {}
    current_file = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            # Extract file path
            match = re.search(r" b/(.+)$", line)
            if match:
                current_file = match.group(1)
                changes[current_file] = []
        elif line.startswith("@@") and current_file:
            # Parse hunk header: @@ -a,b +c,d @@
            match = re.search(r"\+(\d+),?(\d+)?", line)
            if match:
                start = int(match.group(1))
                length = int(match.group(2)) if match.group(2) else 1
                # Store the start line and mark changed lines from start to start+length-1
                changes[current_file].extend(range(start, start + length))
    return changes


# ---------------------------------------------------------------------------
# Step 2 - Collect existing tests
# ---------------------------------------------------------------------------
def collect_tests() -> List[str]:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test.py",
                "tests/test_extended.py",
                "tests_generated/generated_test.py",
                "--collect-only",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sanitized_subprocess_env(),
            timeout=60,
        )
        if result.returncode != 0:
            print("Test collection failed; refusing to select from a partial inventory.")
            if result.stdout.strip():
                print(result.stdout.rstrip())
            if result.stderr.strip():
                print(result.stderr.rstrip())
            return []
        tests = []
        for line in result.stdout.splitlines():
            # Parameterized node IDs are valid runnable tests and must not be
            # discarded merely because they contain square brackets.
            if "::" in line:
                tests.append(line.strip())
        return tests
    except subprocess.TimeoutExpired:
        print("Test collection timed out after 60 seconds.")
        return []
    except Exception as e:
        print(f"Failed to collect tests: {e}")
        return []


# ---------------------------------------------------------------------------
# Step 3 - Build LLM prompt for test selection
# ---------------------------------------------------------------------------
def build_selection_prompt(diff_text: str, test_list: List[str]) -> str:
    # Truncate diff if too long
    diff_preview = diff_text[:4000] + ("..." if len(diff_text) > 4000 else "")

    tests_preview = "\n".join(test_list[:120])

    prompt = f"""You are a test-selection assistant for a FastAPI project.

The code diff below shows what changed:
```diff
{diff_preview}
```

Here is the list of all test functions (including file names):
```
{tests_preview}
```

Your task:
1. Analyse the diff and determine which tests are most likely to be affected.
2. Rank them by relevance: high, medium, low.
3. Place no more than 16 tests in the high and medium lists combined.
4. Return a JSON object exactly like this:
{{
  "high": ["test_file::test_func", "..."],
  "medium": ["test_file::test_func", "..."],
  "low": ["test_file::test_func", "..."]
}}

Only include test IDs that exist in the list above. Do not invent names.
If no tests are relevant, return empty lists.
Return only the JSON object, no additional text or markdown.
"""
    return prompt


def _strip_code_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences (```json, ```python, ```) from a string."""
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line (e.g. ``` or ```json or ```python)
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def select_tests(diff_text: str, test_list: List[str]) -> Dict[str, List[str]]:
    if client is None:
        return {"high": [], "medium": [], "low": []}

    prompt = build_selection_prompt(diff_text, test_list)
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800,
            extra_headers={
                "HTTP-Referer": "https://localhost:8000",
                "X-Title": "TestSelectAgent",
            },
        )
        raw = response.choices[0].message.content.strip()
        raw = _strip_code_fences(raw)
        data = json.loads(raw)

        # Ensure keys exist
        return {
            "high": data.get("high", []),
            "medium": data.get("medium", []),
            "low": data.get("low", []),
        }
    except Exception as e:
        print(f"Selection LLM call failed: {e}")
        return {"high": [], "medium": [], "low": []}


# ---------------------------------------------------------------------------
# Step 4 - Self-healing: suggest fix for a failed test
# ---------------------------------------------------------------------------
async def suggest_fix(test_id: str, error_output: str) -> Optional[str]:
    """Ask LLM to fix the test function based on error."""
    if client is None:
        print("Self-healing skipped: OPENROUTER_API_KEY is unavailable.")
        return None
    try:
        test_file, test_func, _ = normalize_test_id(test_id)
        function_source = extract_test_function_source(test_id)
    except (OSError, UnicodeError, RepairValidationError, SyntaxError) as error:
        print(f"Could not extract the failed function: {error}")
        return None

    prompt = f"""The test {test_id} failed with this error:
```
{error_output[:2000]}
```

Here is the exact failing function from {test_file}:
```python
{function_source}
```

Decide whether this is a stale or brittle test rather than an application defect.
If it appears to be an application defect, or a safe repair is uncertain, return exactly NO_FIX.

Otherwise return a corrected version of {test_func} under these invariants:
- Return exactly one function with the same name, signature, and sync/async type.
- Do not include decorators or imports; existing decorators are preserved automatically.
- Do not remove or weaken assertions, skip the test, or mark it xfail.
- Do not access files, processes, environment variables, secrets, or external networks.
- Change only what is needed to align the test with the observed API contract.

Return only the corrected function code or NO_FIX, with no markdown fences.
"""

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=900,
            extra_headers={
                "HTTP-Referer": "https://localhost:8000",
                "X-Title": "TestSelectAgent (heal)",
            },
        )
        fixed = response.choices[0].message.content.strip()
        fixed = _strip_code_fences(fixed)
        if fixed.strip().upper() == "NO_FIX":
            print(f"LLM declined to repair {test_id}; likely application defect or uncertainty.")
            return None
        return fixed
    except Exception as e:
        print(f"Self-heal LLM call failed: {e}")
        return None


# ---------------------------------------------------------------------------
# CSV reporting helper
# ---------------------------------------------------------------------------
def _write_csv(path: Optional[str], rows: List[Dict[str, str]]) -> None:
    """Write the selected/executed tests to a CSV with columns:
    id,status,duration,message

    Writes a header-only CSV when there are no rows, so downstream steps
    (e.g. actions/upload-artifact) always have a file to pick up, and so the
    artifact is consistent in shape with the main pytest --csv report.
    """
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id", "status", "duration", "message"]
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"Wrote CSV report to {path} ({len(rows)} row(s))")
    except Exception as e:
        print(f"Could not write CSV report to {path}: {e}")


def _write_timing(path: Optional[str], payload: Dict[str, object]) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    print(f"Wrote timing metadata to {path}")


def _write_early_artifacts(
    args: argparse.Namespace,
    *,
    exit_code: int,
    reason: str,
    final_validation_passed: bool,
    collected_test_count: int = 0,
) -> None:
    """Keep the artifact contract complete even when execution stops early."""
    _write_csv(args.before_csv, [])
    _write_csv(args.csv_out, [])
    write_healing_artifacts(
        args.healing_report,
        args.healing_patch,
        [],
        model=MODEL_NAME,
        initial_failed_count=0,
        final_failed_count=0 if final_validation_passed else 1,
        final_validation_passed=final_validation_passed,
    )
    _write_timing(
        args.timing_out,
        {
            "strategy": "agentic-selected-batch",
            "wall_time_sec": 0.0,
            "initial_batch_wall_time_sec": 0.0,
            "healing_wall_time_sec": 0.0,
            "final_validation_wall_time_sec": 0.0,
            "test_count": 0,
            "collected_test_count": collected_test_count,
            "initial_failed_count": 0,
            "healed_count": 0,
            "final_failed_count": 0 if final_validation_passed else 1,
            "exit_code": exit_code,
            "early_exit_reason": reason,
        },
    )


def read_failed_test_ids(path: Optional[str], allowed_tests: set[str]) -> List[str]:
    """Load known baseline failures so the agentic run always prioritizes them."""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as error:
        print(f"Could not read baseline failure CSV {path}: {error}")
        return []
    failed = []
    for row in rows:
        test_id = row.get("id", "")
        if row.get("status", "").lower() in {"failed", "error"} and test_id in allowed_tests:
            failed.append(test_id)
    return list(dict.fromkeys(failed))


def fallback_selected_tests(diff_text: str, tests: List[str], limit: int = 16) -> List[str]:
    """Pick a deterministic impacted subset when the LLM returns no runnable tests."""
    lowered_diff = diff_text.lower()
    keywords = []
    if "post" in lowered_diff or "updatepostrequest" in lowered_diff:
        keywords.extend(["post", "posts"])
    if "user" in lowered_diff or "pagination" in lowered_diff:
        keywords.extend(["user", "paginated"])
    if "seed" in lowered_diff or "reset" in lowered_diff:
        keywords.extend(["seed", "reset"])
    if "health" in lowered_diff or "metrics" in lowered_diff:
        keywords.extend(["health", "metrics"])

    impacted = [
        test_id
        for test_id in tests
        if keywords and any(keyword in test_id.lower() for keyword in keywords)
    ]
    remaining = [test_id for test_id in tests if test_id not in impacted]
    return (impacted + remaining)[: min(limit, len(tests))]


def run_selected_tests_batch(
    test_ids: List[str],
    timeout_sec: int = 300,
) -> tuple[subprocess.CompletedProcess[str], List[Dict[str, str]], float]:
    """Execute all selected tests in one pytest process.

    The previous implementation launched a fresh pytest process per test. That
    repeatedly paid interpreter, plugin-discovery, collection, and fixture
    startup costs. A single batch preserves per-test CSV durations while
    removing that avoidable orchestration overhead.
    """
    with tempfile.TemporaryDirectory(prefix="llm_ctf_selector_") as temp_dir:
        csv_path = os.path.join(temp_dir, "selected_results.csv")
        command = [
            sys.executable,
            "-m",
            "pytest",
            *test_ids,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
            f"--csv={csv_path}",
            "--csv-columns=id,status,duration,message",
        ]
        start = time.monotonic()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=sanitized_subprocess_env(),
                timeout=max(timeout_sec, 1),
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout if isinstance(error.stdout, str) else ""
            stderr = error.stderr if isinstance(error.stderr, str) else ""
            result = subprocess.CompletedProcess(
                command,
                124,
                stdout,
                (stderr + f"\nSelected-test batch timed out after {timeout_sec}s").strip(),
            )
        wall_time = round(time.monotonic() - start, 3)

        rows: List[Dict[str, str]] = []
        if os.path.exists(csv_path):
            with open(csv_path, encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

    return result, rows, wall_time


def rollback_repair_transaction(
    transaction_snapshots,
    repair_results: List[RepairResult],
    *,
    reason_code: str,
    reason: str,
) -> Dict[Path, str]:
    """Restore every touched file, verify each restore, and audit all failures."""
    rollback_errors: Dict[Path, str] = {}
    for target, snapshot in reversed(list(transaction_snapshots.items())):
        try:
            restore_snapshot(snapshot)
        except Exception as error:
            rollback_errors[target] = str(error)

    for item in repair_results:
        if not item.applied and not item.kept:
            continue
        previous_rollback_error = item.rollback_error
        item.kept = False
        try:
            item_target = resolve_test_target(item.test_id)
        except (OSError, RepairValidationError):
            item_target = None
        rollback_error = rollback_errors.get(item_target, "")
        item.rollback_error = rollback_error
        if rollback_error:
            item.rolled_back = False
            item.rollback_verified = False
            item.outcome = "rollback_failed"
            item.reason = f"{reason}; rollback failed: {rollback_error}"
        else:
            item.rolled_back = True
            item.rollback_verified = True
            item.rollback_error = previous_rollback_error
            if previous_rollback_error:
                item.outcome = "rolled_back_after_rollback_failure"
                item.reason = (
                    f"{reason}; transaction restore later succeeded after an earlier "
                    f"rollback error: {previous_rollback_error}"
                )
            else:
                item.outcome = f"rolled_back_{reason_code}"
                item.reason = reason
    return rollback_errors


# ---------------------------------------------------------------------------
# Step 5 - Main driver
# ---------------------------------------------------------------------------
async def main() -> int:
    parser = argparse.ArgumentParser(description="TestSelectAgent")
    parser.add_argument("--diff", help="Path to a diff file (instead of git diff)")
    parser.add_argument(
        "--run-medium", action="store_true", help="Also run medium-relevance tests"
    )
    parser.add_argument("--commit", default="HEAD", help="Git commit to diff against")
    parser.add_argument(
        "--no-heal", action="store_true", help="Skip self-healing attempts"
    )
    parser.add_argument(
        "--csv-out",
        default=None,
        help="Path to write a CSV report (columns: id,status,duration,message) "
        "for the tests that were actually selected and run",
    )
    parser.add_argument(
        "--min-tests",
        type=int,
        default=16,
        help="Minimum selected tests; deterministic impacted tests supplement the LLM result",
    )
    parser.add_argument(
        "--max-tests",
        type=int,
        default=16,
        help="Maximum tests executed in the agentic batch",
    )
    parser.add_argument(
        "--timing-out",
        default=None,
        help="Optional JSON path for selected-batch wall-clock metadata",
    )
    parser.add_argument(
        "--before-csv",
        default="reports/agentic_before_heal.csv",
        help="Initial selected-test CSV captured before repair attempts",
    )
    parser.add_argument(
        "--healing-report",
        default="reports/self_healing_report.json",
        help="JSON audit report for all healing decisions",
    )
    parser.add_argument(
        "--healing-patch",
        default="reports/self_healing.patch",
        help="Unified patch containing only accepted repairs",
    )
    parser.add_argument(
        "--healing-backup-dir",
        default="reports/self_healing_backups",
        help="Directory containing pre-repair source snapshots",
    )
    parser.add_argument(
        "--max-heal-functions",
        type=int,
        default=3,
        help="Maximum distinct failed functions that may be repaired in one run",
    )
    parser.add_argument(
        "--heal-validation-runs",
        type=int,
        default=2,
        help="Required consecutive passes for each proposed repair",
    )
    parser.add_argument(
        "--heal-timeout",
        type=int,
        default=60,
        help="Timeout in seconds for each repair-validation run",
    )
    parser.add_argument(
        "--batch-timeout",
        type=int,
        default=300,
        help="Timeout in seconds for each complete selected-test batch",
    )
    parser.add_argument(
        "--failure-csv",
        default=None,
        help="Optional baseline pytest CSV whose failed/error tests are prioritized",
    )
    args = parser.parse_args()
    agent_started = time.monotonic()
    Path(args.healing_backup_dir).mkdir(parents=True, exist_ok=True)

    # Obtain diff
    if args.diff:
        diff_text = read_diff_file(args.diff)
    else:
        diff_text = get_git_diff(commit=args.commit)

    if not diff_text:
        print("No changes detected. Exiting.")
        _write_early_artifacts(
            args,
            exit_code=0,
            reason="no_changes",
            final_validation_passed=True,
        )
        return 0

    print("Analysing code changes...")
    changed_files = parse_diff(diff_text)
    if changed_files:
        print("Changed files:")
        for f, lines in changed_files.items():
            preview = lines[:5]
            suffix = "..." if len(lines) > 5 else ""
            print(f"   {f} (lines {preview}{suffix})")
    else:
        print("Could not parse diff line numbers (will still use full diff).")

    # Collect tests
    tests = collect_tests()
    if not tests:
        print("No tests found. Are you in the correct directory?")
        _write_early_artifacts(
            args,
            exit_code=1,
            reason="test_collection_failed",
            final_validation_passed=False,
        )
        return 1
    print(f"Found {len(tests)} tests.")

    # Select tests
    print("Asking LLM to select relevant tests...")
    selection = await select_tests(diff_text, tests)
    high = selection.get("high", [])
    medium = selection.get("medium", [])
    low = selection.get("low", [])

    print("\nSelected tests:")
    print(f"   HIGH ({len(high)}):")
    for t in high:
        print(f"     - {t}")
    print(f"   MEDIUM ({len(medium)}):")
    for t in medium:
        print(f"     - {t}")
    print(f"   LOW ({len(low)}):")
    for t in low:
        print(f"     - {t}")

    # Decide which to run
    allowed_tests = set(tests)
    known_failures = read_failed_test_ids(args.failure_csv, allowed_tests)
    if known_failures:
        print(f"Prioritizing {len(known_failures)} known baseline failure(s).")
    to_run = list(known_failures)
    to_run.extend(test_id for test_id in high if test_id in allowed_tests)
    if args.run_medium:
        to_run.extend(test_id for test_id in medium if test_id in allowed_tests)
    to_run = list(dict.fromkeys(to_run))

    minimum = min(max(args.min_tests, 0), len(tests))
    maximum = min(max(args.max_tests, minimum), len(tests))
    if len(to_run) < minimum:
        print(
            f"Supplementing selection to the minimum sample size of {minimum} tests."
        )
        for test_id in fallback_selected_tests(diff_text, tests, limit=len(tests)):
            if test_id not in to_run:
                to_run.append(test_id)
            if len(to_run) >= minimum:
                break
    to_run = to_run[:maximum]

    if not to_run:
        print("No runnable tests selected.")
        _write_early_artifacts(
            args,
            exit_code=1,
            reason="no_runnable_tests_selected",
            final_validation_passed=False,
            collected_test_count=len(tests),
        )
        return 1

    print(f"\nRunning {len(to_run)} selected tests in one pytest batch...")
    result, csv_rows, wall_time = run_selected_tests_batch(
        to_run, timeout_sec=max(args.batch_timeout, 1)
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.stderr.strip():
        print(result.stderr.rstrip())
    print(f"Selected-test batch wall time: {wall_time:.3f}s")
    _write_csv(args.before_csv, csv_rows)

    initial_rows = [dict(row) for row in csv_rows]
    initial_failed_rows = [
        row for row in initial_rows if row.get("status") in {"failed", "error"}
    ]
    initial_failed_count = len(initial_failed_rows)
    if result.returncode != 0 and not initial_failed_rows:
        initial_failed_count = 1

    for row in initial_rows:
        print(f"   {row.get('status', 'unknown').upper():7} {row.get('id', 'unknown test')}")

    repair_results: List[RepairResult] = []
    transaction_snapshots = {}
    healing_wall_time = 0.0
    final_validation_wall_time = 0.0
    final_validation_passed = result.returncode == 0 and initial_failed_count == 0

    if initial_failed_rows:
        healing_started = time.monotonic()
        failed_groups: Dict[str, Dict[str, str]] = {}
        for row in initial_failed_rows:
            test_id = row.get("id", "")
            try:
                test_file, function_name, base_test_id = normalize_test_id(test_id)
            except RepairValidationError as error:
                repair_results.append(
                    RepairResult(
                        test_id=test_id,
                        base_test_id=test_id,
                        test_file=test_id.split("::", 1)[0],
                        function_name="",
                        outcome="rejected",
                        reason=str(error),
                    )
                )
                continue
            group = failed_groups.setdefault(
                base_test_id,
                {
                    "test_id": test_id,
                    "test_file": test_file,
                    "function_name": function_name,
                    "message": "",
                },
            )
            message = row.get("message") or (result.stdout + "\n" + result.stderr)
            group["message"] = (group["message"] + "\n" + message).strip()[-3000:]

        groups = list(failed_groups.values())
        repair_limit = max(args.max_heal_functions, 0)
        for index, group in enumerate(groups):
            test_id = group["test_id"]
            test_file = group["test_file"]
            function_name = group["function_name"]
            _, _, base_test_id = normalize_test_id(test_id)

            if args.no_heal:
                repair_results.append(
                    RepairResult(
                        test_id=test_id,
                        base_test_id=base_test_id,
                        test_file=test_file,
                        function_name=function_name,
                        outcome="disabled",
                        reason="Self-healing disabled by --no-heal",
                    )
                )
                continue
            if client is None:
                repair_results.append(
                    RepairResult(
                        test_id=test_id,
                        base_test_id=base_test_id,
                        test_file=test_file,
                        function_name=function_name,
                        outcome="skipped_no_credentials",
                        reason="OPENROUTER_API_KEY is unavailable",
                    )
                )
                continue
            if index >= repair_limit:
                repair_results.append(
                    RepairResult(
                        test_id=test_id,
                        base_test_id=base_test_id,
                        test_file=test_file,
                        function_name=function_name,
                        outcome="skipped_limit",
                        reason=f"Maximum repair limit of {repair_limit} functions reached",
                    )
                )
                continue

            print(f"   Attempting guarded autonomous repair for {base_test_id}...")
            try:
                target = resolve_test_target(test_id)
                if target not in transaction_snapshots:
                    transaction_snapshots[target] = snapshot_file(target)
            except (OSError, RepairValidationError) as error:
                repair_results.append(
                    RepairResult(
                        test_id=test_id,
                        base_test_id=base_test_id,
                        test_file=test_file,
                        function_name=function_name,
                        outcome="rejected",
                        reason=str(error),
                    )
                )
                continue

            fixed = await suggest_fix(test_id, group["message"])
            if not fixed:
                repair_results.append(
                    RepairResult(
                        test_id=test_id,
                        base_test_id=base_test_id,
                        test_file=test_file,
                        function_name=function_name,
                        outcome="no_fix",
                        reason="LLM returned NO_FIX or did not provide a candidate",
                    )
                )
                continue

            repair = attempt_repair(
                test_id,
                fixed,
                backup_dir=Path(args.healing_backup_dir),
                validation_runs=max(args.heal_validation_runs, 1),
                timeout_sec=max(args.heal_timeout, 1),
            )
            repair_results.append(repair)
            print(f"   Repair outcome: {repair.outcome} - {repair.reason}")

        accepted = [item for item in repair_results if item.kept]
        unresolved = [item for item in repair_results if not item.kept]
        if unresolved:
            if any(item.applied or item.kept for item in repair_results):
                print("At least one repair is unresolved; rolling back the repair transaction.")
                rollback_repair_transaction(
                    transaction_snapshots,
                    repair_results,
                    reason_code="unresolved_repair",
                    reason="At least one failed function was not safely healed",
                )
            final_validation_passed = False
            csv_rows = initial_rows
        elif accepted:
            print("\nRunning final selected-batch regression validation...")
            final_result, final_rows, final_validation_wall_time = run_selected_tests_batch(
                to_run, timeout_sec=max(args.batch_timeout, 1)
            )
            if final_result.stdout.strip():
                print(final_result.stdout.rstrip())
            if final_result.stderr.strip():
                print(final_result.stderr.rstrip())
            final_validation_passed = (
                final_result.returncode == 0
                and bool(final_rows)
                and all(row.get("status") == "passed" for row in final_rows)
            )
            if final_validation_passed:
                healed_bases = {item.base_test_id for item in accepted}
                for row in final_rows:
                    try:
                        _, _, base_id = normalize_test_id(row.get("id", ""))
                    except RepairValidationError:
                        continue
                    if base_id in healed_bases:
                        row["message"] = "guarded autonomous self-healing succeeded"
                csv_rows = final_rows
            else:
                print("Final batch validation failed; rolling back every accepted repair.")
                rollback_repair_transaction(
                    transaction_snapshots,
                    repair_results,
                    reason_code="final_validation",
                    reason="A final selected-batch regression check failed",
                )
                csv_rows = initial_rows
        else:
            final_validation_passed = False

        healing_wall_time = round(time.monotonic() - healing_started, 3)

    final_failed_count = sum(
        row.get("status") in {"failed", "error"} for row in csv_rows
    )
    if not final_validation_passed and result.returncode != 0 and final_failed_count == 0:
        final_failed_count = 1

    write_healing_artifacts(
        args.healing_report,
        args.healing_patch,
        repair_results,
        model=MODEL_NAME,
        initial_failed_count=initial_failed_count,
        final_failed_count=final_failed_count,
        final_validation_passed=final_validation_passed,
    )
    print(f"Wrote healing audit report to {args.healing_report}")
    print(f"Wrote accepted repair patch to {args.healing_patch}")

    total_wall_time = round(time.monotonic() - agent_started, 3)
    repair_transaction_clean = not any(
        item.rollback_error or item.outcome == "rollback_failed"
        for item in repair_results
    )
    all_initial_failures_healed = not initial_failed_rows or (
        bool(repair_results) and all(item.kept for item in repair_results)
    )
    final_exit_code = (
        0
        if final_failed_count == 0
        and final_validation_passed
        and repair_transaction_clean
        and all_initial_failures_healed
        else 1
    )
    if args.timing_out:
        _write_timing(
            args.timing_out,
            {
                "strategy": "agentic-selected-batch",
                "wall_time_sec": total_wall_time,
                "initial_batch_wall_time_sec": wall_time,
                "healing_wall_time_sec": healing_wall_time,
                "final_validation_wall_time_sec": final_validation_wall_time,
                "test_count": len(csv_rows),
                "collected_test_count": len(tests),
                "initial_failed_count": initial_failed_count,
                "healed_count": sum(item.outcome == "healed" for item in repair_results),
                "rollback_failed_count": sum(
                    bool(item.rollback_error) or item.outcome == "rollback_failed"
                    for item in repair_results
                ),
                "final_failed_count": final_failed_count,
                "exit_code": final_exit_code,
            },
        )

    _write_csv(args.csv_out, csv_rows)
    print("\nTest selection and execution complete.")
    return final_exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
