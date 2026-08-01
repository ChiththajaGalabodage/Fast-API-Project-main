"""Run a pytest batch and persist both per-test and wall-clock timings."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time

try:
    from tests_selecter.self_healing import sanitized_subprocess_env
except ModuleNotFoundError:  # Direct execution: python tests_selecter/run_test_batch.py
    from self_healing import sanitized_subprocess_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Timed pytest batch runner")
    parser.add_argument("tests", nargs="+", help="Test files, directories, or node IDs")
    parser.add_argument("--csv-out", required=True, help="Per-test pytest CSV output")
    parser.add_argument("--timing-out", required=True, help="Wall-clock metadata JSON")
    parser.add_argument("--label", default="test-batch", help="Strategy label")
    parser.add_argument("--timeout", type=int, default=600, help="Batch timeout in seconds")
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Fail when the executed CSV row count is not exactly this value",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    for path in (args.csv_out, args.timing_out):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "pytest",
        *args.tests,
        "-v" if args.verbose else "-q",
        "-p",
        "no:cacheprovider",
        f"--csv={args.csv_out}",
        "--csv-columns=id,status,duration,message",
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            env=sanitized_subprocess_env(),
            timeout=max(args.timeout, 1),
        )
    except subprocess.TimeoutExpired:
        print(f"{args.label} timed out after {args.timeout}s", file=sys.stderr)
        result = subprocess.CompletedProcess(command, 124)
    wall_time = round(time.monotonic() - started, 3)

    test_count = 0
    if os.path.exists(args.csv_out):
        with open(args.csv_out, encoding="utf-8", newline="") as handle:
            test_count = sum(1 for _ in csv.DictReader(handle))

    count_matches = args.expected_count is None or test_count == args.expected_count
    effective_exit_code = result.returncode if count_matches else 3
    if not count_matches:
        print(
            f"{args.label} count gate failed: expected {args.expected_count}, "
            f"executed {test_count}",
            file=sys.stderr,
        )

    metadata = {
        "strategy": args.label,
        "wall_time_sec": wall_time,
        "test_count": test_count,
        "expected_test_count": args.expected_count,
        "count_gate_passed": count_matches,
        "pytest_exit_code": result.returncode,
        "exit_code": effective_exit_code,
        "command": command,
    }
    with open(args.timing_out, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    print(f"{args.label} wall time: {wall_time:.3f}s")
    print(f"Wrote timing metadata to {args.timing_out}")
    return effective_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
