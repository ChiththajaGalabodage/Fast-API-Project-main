"""Replay a real committed stale-test failure in an isolated temporary copy.

This command sends the committed diff, failing test source, and failure text to
the configured OpenRouter model. Run it only after authorizing that disclosure.
No credential is copied into the sandbox or written to an artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", default="HEAD")
    parser.add_argument("--output-dir", default="reports/live_repair_evaluation")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_API_KEY is required for a live repair replay", file=sys.stderr)
        return 2

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "NUM_USERS": "100",
            "BASE_DELAY": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    with tempfile.TemporaryDirectory(prefix="llm_ctf_live_repair_") as temp_root:
        sandbox = Path(temp_root) / "repository"
        shutil.copytree(
            ROOT,
            sandbox,
            ignore=shutil.ignore_patterns(
                ".git", ".venv", ".env", ".pytest_cache", "__pycache__", "reports", "visualizations", "*.pyc"
            ),
        )
        stale_test = subprocess.run(
            ["git", "show", f"{args.source_commit}:tests/test.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        (sandbox / "tests/test.py").write_text(stale_test, encoding="utf-8")
        source_diff = subprocess.run(
            ["git", "show", "--format=", "--no-ext-diff", args.source_commit],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
        (sandbox / "source_commit.diff").write_text(source_diff, encoding="utf-8")
        (sandbox / "reports").mkdir()

        baseline = _run(
            [
                sys.executable,
                "tests_selecter/run_test_batch.py",
                "--csv-out", "reports/live_before.csv",
                "--timing-out", "reports/live_before_timing.json",
                "--label", "live-repair-real-commit-before",
                "--expected-count", "80",
                "tests/test.py", "tests/test_extended.py", "tests_generated/generated_test.py",
            ],
            sandbox,
            env,
            args.timeout,
        )
        if baseline.returncode == 0:
            print("The historical test did not reproduce a failure", file=sys.stderr)
            return 3

        selector = _run(
            [
                sys.executable,
                "tests_selecter/selecter.py",
                "--diff", "source_commit.diff",
                "--selection-repetitions", "3",
                "--threshold-margin", "0.05",
                "--max-tests", "16",
                "--failure-csv", "reports/live_before.csv",
                "--before-csv", "reports/live_selected_before.csv",
                "--csv-out", "reports/live_after.csv",
                "--timing-out", "reports/live_timing.json",
                "--selection-report", "reports/live_selection_decisions.json",
                "--healing-report", "reports/live_repair_report.json",
                "--healing-patch", "reports/live_repair.patch",
                "--healing-backup-dir", "reports/live_repair_backups",
                "--heal-validation-runs", "2",
            ],
            sandbox,
            env,
            args.timeout,
        )
        for artifact in (sandbox / "reports").iterdir():
            target = output_dir / artifact.name
            if artifact.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(artifact, target)
            else:
                shutil.copy2(artifact, target)

        report_path = output_dir / "live_repair_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        summary = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_commit": args.source_commit,
            "external_destination": "OpenRouter API",
            "data_disclosed": ["source commit diff", "test IDs", "failing test source", "failure text"],
            "credential_recorded": False,
            "baseline_exit_code": baseline.returncode,
            "selector_exit_code": selector.returncode,
            "initial_failed_count": report.get("initial_failed_count"),
            "healed_count": report.get("healed_count"),
            "final_validation_passed": report.get("final_validation_passed"),
            "stdout_tail": selector.stdout[-3000:],
            "stderr_tail": selector.stderr[-3000:],
        }
        (output_dir / "live_repair_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote isolated live-repair evidence to {output_dir}")
        return selector.returncode


if __name__ == "__main__":
    raise SystemExit(main())
