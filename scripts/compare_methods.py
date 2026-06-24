import csv
import json
import subprocess
import time
from pathlib import Path


REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)


def run_pytest(label: str, test_path: str, coverage_json: str):
    start = time.perf_counter()

    cmd = [
        "python",
        "-m",
        "pytest",
        test_path,
        "-q",
        "--cov=main",
        "--cov-report=term-missing",
        f"--cov-report=json:{coverage_json}",
        "--tb=short",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    duration = round(time.perf_counter() - start, 3)

    coverage_percent = 0.0
    coverage_file = Path(coverage_json)

    if coverage_file.exists():
        try:
            with coverage_file.open("r", encoding="utf-8") as f:
                coverage_data = json.load(f)
            coverage_percent = round(
                coverage_data.get("totals", {}).get("percent_covered", 0.0), 2
            )
        except Exception:
            coverage_percent = 0.0

    return {
        "method": label,
        "test_path": test_path,
        "status": "passed" if result.returncode == 0 else "failed",
        "return_code": result.returncode,
        "duration_seconds": duration,
        "coverage_percent": coverage_percent,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def main():
    results = []

    results.append(
        run_pytest(
            label="traditional_tests",
            test_path="tests/test.py",
            coverage_json="reports/traditional_coverage.json",
        )
    )

    generated_test_file = Path("tests_generated/generated_tests.py")

    if generated_test_file.exists():
        results.append(
            run_pytest(
                label="agentic_generated_tests",
                test_path="tests_generated/generated_tests.py",
                coverage_json="reports/agentic_coverage.json",
            )
        )
    else:
        results.append(
            {
                "method": "agentic_generated_tests",
                "test_path": "tests_generated/generated_tests.py",
                "status": "skipped",
                "return_code": 0,
                "duration_seconds": 0,
                "coverage_percent": 0,
                "stdout": "Generated test file not found.",
                "stderr": "",
            }
        )

    csv_path = REPORTS_DIR / "comparison_report.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "method",
                "test_path",
                "status",
                "return_code",
                "duration_seconds",
                "coverage_percent",
            ],
        )
        writer.writeheader()

        for row in results:
            writer.writerow(
                {
                    "method": row["method"],
                    "test_path": row["test_path"],
                    "status": row["status"],
                    "return_code": row["return_code"],
                    "duration_seconds": row["duration_seconds"],
                    "coverage_percent": row["coverage_percent"],
                }
            )

    md_path = REPORTS_DIR / "comparison_report.md"

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# CI/CD Testing Comparison Report\n\n")
        f.write("| Method | Status | Time Seconds | Coverage % |\n")
        f.write("|---|---:|---:|---:|\n")

        for row in results:
            f.write(
                f"| {row['method']} | {row['status']} | "
                f"{row['duration_seconds']} | {row['coverage_percent']} |\n"
            )

        f.write("\n## Notes\n")
        f.write("- traditional_tests = manually written pytest tests.\n")
        f.write("- agentic_generated_tests = LLM-generated tests.\n")
        f.write("- This report is generated automatically inside GitHub Actions.\n")

    print(f"Comparison CSV written to {csv_path}")
    print(f"Comparison Markdown written to {md_path}")

    for row in results:
        print(
            f"{row['method']}: {row['status']} | "
            f"time={row['duration_seconds']}s | "
            f"coverage={row['coverage_percent']}%"
        )


if __name__ == "__main__":
    main()
