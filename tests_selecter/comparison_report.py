import csv
import json
import os
import sys
from typing import Dict, List

# ---------------------------------------------------------------------------
# Comparison Report Generator
#
# Compares the "traditional" run (full suite, every test executed - i.e.
# test-results.csv from `pytest tests/ tests_generated/`) against the
# "agentic" run (LLM-selected subset - reports/test_results.csv from
# selecter.py) and writes a single comparison CSV summarizing the delta.
# ---------------------------------------------------------------------------


def read_csv_rows(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required CSV report not found: {path}")
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"id", "status", "duration", "message"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Invalid pytest CSV columns in {path}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Required pytest CSV has no test rows: {path}")
    return rows


def summarize(rows: List[Dict[str, str]]) -> Dict[str, float]:
    total = len(rows)
    passed = sum(1 for r in rows if r.get("status", "").lower() == "passed")
    failed = total - passed
    duration = sum(float(r.get("duration") or 0) for r in rows)
    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "total_duration_sec": round(duration, 3),
    }


def build_comparison_rows(
    traditional: Dict[str, float],
    agentic: Dict[str, float],
    traditional_wall_time: float | None = None,
    agentic_wall_time: float | None = None,
    traditional_exit_code: int | None = None,
    agentic_exit_code: int | None = None,
) -> List[Dict[str, str]]:
    def pct_change(old: float, new: float) -> str:
        if old == 0:
            return "n/a"
        return f"{round(((new - old) / old) * 100, 1)}%"

    metrics = [
        ("total_tests", "Total tests executed"),
        ("passed", "Tests passed"),
        ("failed", "Tests failed"),
    ]

    if traditional_wall_time is not None and agentic_wall_time is not None:
        traditional["wall_time_sec"] = traditional_wall_time
        agentic["wall_time_sec"] = agentic_wall_time
        metrics.append(("wall_time_sec", "Total execution time (s)"))

    if traditional_exit_code is not None and agentic_exit_code is not None:
        traditional["exit_code"] = traditional_exit_code
        agentic["exit_code"] = agentic_exit_code
        metrics.append(("exit_code", "Process exit code"))

    metrics.append(("total_duration_sec", "Summed test call duration (s)"))

    rows = []
    for key, label in metrics:
        t_val = traditional.get(key, 0)
        a_val = agentic.get(key, 0)
        rows.append(
            {
                "metric": label,
                "traditional": t_val,
                "agentic": a_val,
                "delta": round(a_val - t_val, 3),
                "pct_change": pct_change(t_val, a_val),
            }
        )

    # Derived efficiency metric: % of tests skipped by predictive selection
    skip_pct = "n/a"
    if traditional.get("total_tests", 0) > 0:
        skipped = traditional["total_tests"] - agentic.get("total_tests", 0)
        skip_pct = f"{round((skipped / traditional['total_tests']) * 100, 1)}%"
    rows.append(
        {
            "metric": "Tests skipped by predictive selection",
            "traditional": "-",
            "agentic": "-",
            "delta": "-",
            "pct_change": skip_pct,
        }
    )

    return rows


def read_timing(path: str) -> tuple[float, int, int]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required timing metadata not found: {path}")
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return (
            float(payload["wall_time_sec"]),
            int(payload["exit_code"]),
            int(payload["test_count"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid timing metadata in {path}: {error}") from error


def write_comparison_csv(path: str, rows: List[Dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["metric", "traditional", "agentic", "delta", "pct_change"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote comparison report to {path}")


def main() -> int:
    traditional_path = sys.argv[1] if len(sys.argv) > 1 else "test-results.csv"
    agentic_path = sys.argv[2] if len(sys.argv) > 2 else "reports/test_results.csv"
    output_path = sys.argv[3] if len(sys.argv) > 3 else "reports/comparison_report.csv"
    traditional_timing_path = (
        sys.argv[4] if len(sys.argv) > 4 else "reports/traditional_timing.json"
    )
    agentic_timing_path = (
        sys.argv[5] if len(sys.argv) > 5 else "reports/agentic_timing.json"
    )

    print(f"Traditional run (full suite): {traditional_path}")
    print(f"Agentic run (predictive selection): {agentic_path}")

    try:
        traditional_rows = read_csv_rows(traditional_path)
        agentic_rows = read_csv_rows(agentic_path)
        traditional_wall_time, traditional_exit_code, traditional_timing_count = read_timing(
            traditional_timing_path
        )
        agentic_wall_time, agentic_exit_code, agentic_timing_count = read_timing(
            agentic_timing_path
        )
        if traditional_timing_count != len(traditional_rows):
            raise ValueError("Traditional CSV and timing test counts do not match")
        if agentic_timing_count != len(agentic_rows):
            raise ValueError("Agentic CSV and timing test counts do not match")
        traditional_summary = summarize(traditional_rows)
        agentic_summary = summarize(agentic_rows)
    except (OSError, ValueError) as error:
        print(f"Comparison report is invalid: {error}", file=sys.stderr)
        return 1

    print(f"   Traditional: {traditional_summary}")
    print(f"   Agentic:     {agentic_summary}")

    comparison_rows = build_comparison_rows(
        traditional_summary,
        agentic_summary,
        traditional_wall_time,
        agentic_wall_time,
        traditional_exit_code,
        agentic_exit_code,
    )
    write_comparison_csv(output_path, comparison_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
