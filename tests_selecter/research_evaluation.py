"""Reproducible multi-change and mutation evaluation for the research prototype.

The history experiment replays real commit diffs against one fixed benchmark
snapshot so selector decisions are comparable.  The mutation experiment copies
the repository to an isolated temporary directory, injects one source defect at
a time, and compares the complete application suite with the selected subset.
The working tree is never mutated by these experiments.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Sequence

try:
    from tests_selecter.selection_policy import build_selection_decision, impacted_tests
    from tests_selecter.selecter import collect_tests, fallback_selected_tests
    from tests_selecter.self_healing import sanitized_subprocess_env
except ModuleNotFoundError:
    from selection_policy import build_selection_decision, impacted_tests
    from selecter import collect_tests, fallback_selected_tests
    from self_healing import sanitized_subprocess_env


ROOT = Path(__file__).resolve().parents[1]
APP_TEST_PATHS = (
    "tests/test.py",
    "tests/test_extended.py",
    "tests_generated/generated_test.py",
)


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    old: str
    new: str
    description: str


MUTANTS = (
    Mutant(
        "M01_create_blank_title",
        'class CreatePostRequest(BaseModel):\n    user_id: int = Field(..., gt=0)\n    title: str = Field(..., min_length=1, max_length=200)',
        'class CreatePostRequest(BaseModel):\n    user_id: int = Field(..., gt=0)\n    title: str = Field(..., min_length=0, max_length=200)',
        "Allow blank titles when creating a post",
    ),
    Mutant(
        "M02_create_title_limit",
        'class CreatePostRequest(BaseModel):\n    user_id: int = Field(..., gt=0)\n    title: str = Field(..., min_length=1, max_length=200)',
        'class CreatePostRequest(BaseModel):\n    user_id: int = Field(..., gt=0)\n    title: str = Field(..., min_length=1, max_length=201)',
        "Increase create-title maximum by one",
    ),
    Mutant(
        "M03_create_content_limit",
        'class CreatePostRequest(BaseModel):\n    user_id: int = Field(..., gt=0)\n    title: str = Field(..., min_length=1, max_length=200)\n    content: str = Field(..., min_length=1, max_length=5000)',
        'class CreatePostRequest(BaseModel):\n    user_id: int = Field(..., gt=0)\n    title: str = Field(..., min_length=1, max_length=200)\n    content: str = Field(..., min_length=1, max_length=5001)',
        "Increase create-content maximum by one",
    ),
    Mutant(
        "M04_seed_minimum",
        '10, ge=1, le=1000, description="How many users to seed (default 10)"',
        '10, ge=0, le=1000, description="How many users to seed (default 10)"',
        "Allow an empty database seed",
    ),
    Mutant(
        "M05_seed_maximum",
        '10, ge=1, le=1000, description="How many users to seed (default 10)"',
        '10, ge=1, le=1001, description="How many users to seed (default 10)"',
        "Increase seed maximum by one",
    ),
    Mutant(
        "M06_page_minimum",
        'page: int = Query(1, ge=1, description="Page number (1-based)")',
        'page: int = Query(1, ge=0, description="Page number (1-based)")',
        "Allow page zero",
    ),
    Mutant(
        "M07_page_limit",
        'limit: int = Query(20, ge=1, le=100, description="Records per page")',
        'limit: int = Query(20, ge=1, le=101, description="Records per page")',
        "Increase page-size maximum by one",
    ),
    Mutant(
        "M08_page_count",
        '"pages": -(-len(users_db) // limit),  # ceiling division',
        '"pages": len(users_db) // limit,  # mutated floor division',
        "Use floor rather than ceiling pagination",
    ),
    Mutant(
        "M09_user_not_found_status",
        'if not user:\n        raise HTTPException(status_code=404, detail="User not found")',
        'if not user:\n        raise HTTPException(status_code=200, detail="User not found")',
        "Return success for a missing user",
    ),
    Mutant(
        "M10_create_missing_user_status",
        'if not any(u.id == post.user_id for u in users_db):\n        raise HTTPException(status_code=404, detail="User not found")',
        'if not any(u.id == post.user_id for u in users_db):\n        raise HTTPException(status_code=200, detail="User not found")',
        "Return success for create with a missing user",
    ),
    Mutant(
        "M11_create_duplicate_id",
        'id=len(posts_db) + 1,\n        user_id=post.user_id,',
        'id=len(posts_db),\n        user_id=post.user_id,',
        "Create a duplicate post identifier",
    ),
    Mutant(
        "M12_update_wrong_title",
        'p.title = body.title.strip()\n            p.content = body.content.strip()',
        'p.title = body.content.strip()\n            p.content = body.content.strip()',
        "Write content into the title during update",
    ),
    Mutant(
        "M13_update_wrong_content",
        'p.title = body.title.strip()\n            p.content = body.content.strip()',
        'p.title = body.title.strip()\n            p.content = body.title.strip()',
        "Write title into the content during update",
    ),
    Mutant(
        "M14_update_not_found_status",
        'return {"success": True, "post": p}\n    raise HTTPException(status_code=404, detail="Post not found")',
        'return {"success": True, "post": p}\n    raise HTTPException(status_code=200, detail="Post not found")',
        "Return success when an update target is missing",
    ),
    Mutant(
        "M15_delete_not_persisted",
        'posts_db = new_posts\n    logger.info("post_deleted post_id=%d", post_id)',
        'posts_db = posts_db\n    logger.info("post_deleted post_id=%d", post_id)',
        "Report deletion without persisting it",
    ),
    Mutant(
        "M16_delete_not_found_status",
        'if len(new_posts) == len(posts_db):\n        raise HTTPException(status_code=404, detail="Post not found")',
        'if len(new_posts) == len(posts_db):\n        raise HTTPException(status_code=200, detail="Post not found")',
        "Return success when deleting a missing post",
    ),
    Mutant(
        "M17_large_payload_minimum",
        '100, ge=10, le=1000, description="Number of paragraphs to return (10',
        '100, ge=9, le=1000, description="Number of paragraphs to return (10',
        "Allow payload size below the documented minimum",
    ),
    Mutant(
        "M18_health_status",
        '"status": "ok",\n        "api_version": app.version',
        '"status": "degraded",\n        "api_version": app.version',
        "Report a degraded service as the health payload",
    ),
    Mutant(
        "M19_reset_error_flag",
        'global _force_error\n    _force_error = False\n    _seed_db()',
        'global _force_error\n    _force_error = True\n    _seed_db()',
        "Keep forced errors enabled after reset",
    ),
    Mutant(
        "M20_metrics_swap",
        '"users": len(users_db),\n        "posts": len(posts_db),\n        "total_records": len(users_db) + len(posts_db),',
        '"users": len(posts_db),\n        "posts": len(users_db),\n        "total_records": len(users_db) + len(posts_db),',
        "Swap user and post metric counts",
    ),
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return result.stdout


def _evaluation_env(cwd: Path) -> dict[str, str]:
    env = sanitized_subprocess_env()
    env.update(
        {
            "NUM_USERS": "100",
            "BASE_DELAY": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(cwd),
        }
    )
    return env


def _run_pytest(cwd: Path, test_ids: Sequence[str], timeout: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="llm_ctf_results_") as result_dir:
        csv_path = Path(result_dir) / "results.csv"
        command = [
            sys.executable,
            "-m",
            "pytest",
            *test_ids,
            "-q",
            "-p",
            "no:cacheprovider",
            f"--csv={csv_path}",
            "--csv-columns=id,status,duration,message",
        ]
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=_evaluation_env(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            exit_code = result.returncode
            output = (result.stdout + "\n" + result.stderr)[-4000:]
        except subprocess.TimeoutExpired as error:
            exit_code = 124
            output = f"Timed out after {timeout}s: {error}"
        wall_time = round(time.monotonic() - started, 3)
        rows = []
        if csv_path.exists():
            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        failing = [
            row.get("id", "")
            for row in rows
            if row.get("status", "").lower() in {"failed", "error"}
        ]
        return {
            "exit_code": exit_code,
            "wall_time_sec": wall_time,
            "test_count": len(rows),
            "failing_tests": failing,
            "output_tail": output if exit_code else "",
        }


def _selection(diff_text: str, tests: Sequence[str], max_tests: int) -> dict[str, object]:
    return build_selection_decision(
        test_ids=tests,
        deterministic_mandatory=impacted_tests(diff_text, tests),
        fallback_candidates=fallback_selected_tests(diff_text, list(tests), limit=len(tests)),
        max_tests=max_tests,
    )


def _stats(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(fmean(values), 3),
        "median": round(median(values), 3),
        "stddev": round(pstdev(values), 3) if len(values) > 1 else 0.0,
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def evaluate_history(args: argparse.Namespace, tests: Sequence[str]) -> dict[str, object]:
    commits = _git("rev-list", f"--max-count={args.commits}", "HEAD").splitlines()
    rows = []
    for index, commit in enumerate(commits, 1):
        metadata = _git("show", "-s", "--format=%h|%ad|%s", "--date=short", commit).strip()
        short_sha, date, subject = metadata.split("|", 2)
        diff_text = _git("show", "--format=", "--no-ext-diff", commit)
        changed_files = sorted(
            line[4:] for line in diff_text.splitlines() if line.startswith("+++ b/")
        )
        decision = _selection(diff_text, tests, args.max_tests)
        selected = list(decision["selected_tests"])
        print(f"history {index}/{len(commits)} {short_sha}: {len(selected)}/{len(tests)} tests")
        traditional = _run_pytest(ROOT, APP_TEST_PATHS, args.timeout)
        agentic = _run_pytest(ROOT, selected, args.timeout)
        rows.append(
            {
                "commit": commit,
                "short_sha": short_sha,
                "date": date,
                "subject": subject,
                "changed_files": changed_files,
                "selected_tests": selected,
                "traditional": traditional,
                "agentic": agentic,
                "test_reduction_pct": round((1 - len(selected) / len(tests)) * 100, 2),
                "time_reduction_pct": round(
                    (1 - float(agentic["wall_time_sec"]) / float(traditional["wall_time_sec"])) * 100,
                    2,
                ) if traditional["wall_time_sec"] else 0.0,
            }
        )
    return {
        "design": "fixed-current-snapshot historical-diff replay",
        "commit_count": len(rows),
        "benchmark_test_count": len(tests),
        "rows": rows,
        "summary": {
            "test_reduction_pct": _stats([row["test_reduction_pct"] for row in rows]),
            "time_reduction_pct": _stats([row["time_reduction_pct"] for row in rows]),
            "traditional_wall_time_sec": _stats([row["traditional"]["wall_time_sec"] for row in rows]),
            "agentic_wall_time_sec": _stats([row["agentic"]["wall_time_sec"] for row in rows]),
            "traditional_pass_runs": sum(row["traditional"]["exit_code"] == 0 for row in rows),
            "agentic_pass_runs": sum(row["agentic"]["exit_code"] == 0 for row in rows),
        },
        "limitation": (
            "Each real commit diff is replayed against one fixed current test/application snapshot. "
            "This isolates selection behavior but is not a checkout-and-build study of old dependencies."
        ),
    }


def _copy_benchmark(destination: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".git", ".venv", ".env", ".pytest_cache", "__pycache__", "reports", "visualizations", "*.pyc"
    )
    shutil.copytree(ROOT, destination, ignore=ignored)


def evaluate_mutations(args: argparse.Namespace, tests: Sequence[str]) -> dict[str, object]:
    results = []
    selected_mutants = MUTANTS[: args.mutants]
    with tempfile.TemporaryDirectory(prefix="llm_ctf_mutation_") as temp_root:
        base = Path(temp_root) / "base"
        _copy_benchmark(base)
        original = (base / "main.py").read_text(encoding="utf-8")
        for index, mutant in enumerate(selected_mutants, 1):
            sandbox = Path(temp_root) / mutant.mutant_id
            shutil.copytree(base, sandbox)
            if original.count(mutant.old) != 1:
                raise RuntimeError(
                    f"{mutant.mutant_id} anchor count is {original.count(mutant.old)}, expected 1"
                )
            mutated = original.replace(mutant.old, mutant.new, 1)
            (sandbox / "main.py").write_text(mutated, encoding="utf-8")
            diff_text = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    mutated.splitlines(keepends=True),
                    fromfile="a/main.py",
                    tofile="b/main.py",
                )
            )
            decision = _selection(diff_text, tests, args.max_tests)
            selected = list(decision["selected_tests"])
            print(f"mutant {index}/{len(selected_mutants)} {mutant.mutant_id}")
            traditional = _run_pytest(sandbox, APP_TEST_PATHS, args.timeout)
            agentic = _run_pytest(sandbox, selected, args.timeout)
            full_killed = traditional["exit_code"] != 0
            selected_killed = agentic["exit_code"] != 0
            results.append(
                {
                    **asdict(mutant),
                    "selected_tests": selected,
                    "traditional": traditional,
                    "agentic": agentic,
                    "killed_by_full_suite": full_killed,
                    "killed_by_selected_suite": selected_killed,
                    "selector_escape": full_killed and not selected_killed,
                }
            )
    killable = [row for row in results if row["killed_by_full_suite"]]
    selected_kills = [row for row in killable if row["killed_by_selected_suite"]]
    return {
        "design": "first-order source mutation in isolated repository copies",
        "mutant_count": len(results),
        "results": results,
        "summary": {
            "full_suite_killed": len(killable),
            "full_suite_mutation_score_pct": round(len(killable) / len(results) * 100, 2) if results else 0.0,
            "selected_suite_killed": len(selected_kills),
            "selector_mutation_recall_pct": round(len(selected_kills) / len(killable) * 100, 2) if killable else 0.0,
            "selector_escapes": len(killable) - len(selected_kills),
            "survived_full_suite": len(results) - len(killable),
            "mean_selected_tests": round(fmean(len(row["selected_tests"]) for row in results), 2) if results else 0.0,
            "mean_test_reduction_pct": round(
                fmean((1 - len(row["selected_tests"]) / len(tests)) * 100 for row in results), 2
            ) if results else 0.0,
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def _write_summary(
    path: Path,
    manifest: dict[str, object],
    history: dict[str, object],
    mutation: dict[str, object],
) -> None:
    history_summary = history["summary"]
    mutation_summary = mutation["summary"]
    lines = [
        "# Research Evaluation Summary",
        "",
        "## Evaluation manifest",
        "",
        f"- Commit: `{manifest['head']}`",
        f"- Application tests: {manifest['application_test_count']}",
        f"- Historical diffs evaluated: {history['commit_count']}",
        f"- Source mutants evaluated: {mutation['mutant_count']}",
        "",
        "## Historical-diff replay",
        "",
        f"- Traditional passing runs: {history_summary['traditional_pass_runs']}/{history['commit_count']}",
        f"- Selected-suite passing runs: {history_summary['agentic_pass_runs']}/{history['commit_count']}",
        f"- Mean test reduction: {history_summary['test_reduction_pct']['mean']}%",
        f"- Mean time reduction: {history_summary['time_reduction_pct']['mean']}%",
        "",
        "## Mutation evaluation",
        "",
        f"- Full-suite mutants killed: {mutation_summary['full_suite_killed']}/{mutation['mutant_count']}",
        f"- Full-suite mutation score: {mutation_summary['full_suite_mutation_score_pct']}%",
        f"- Selected-suite mutants killed: {mutation_summary['selected_suite_killed']}/{mutation_summary['full_suite_killed']}",
        f"- Selector mutation recall: {mutation_summary['selector_mutation_recall_pct']}%",
        f"- Selector escapes: {mutation_summary['selector_escapes']}",
        f"- Full-suite survivors: {mutation_summary['survived_full_suite']}",
        f"- Mean selected tests: {mutation_summary['mean_selected_tests']}",
        f"- Mean test reduction: {mutation_summary['mean_test_reduction_pct']}%",
        "",
        "The historical experiment replays commit diffs against one fixed current snapshot. "
        "Mutation trials execute in isolated repository copies.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("history", "mutation", "all"))
    parser.add_argument("--commits", type=int, default=20)
    parser.add_argument("--mutants", type=int, default=20)
    parser.add_argument("--max-tests", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", default="reports/research_evaluation")
    args = parser.parse_args()
    if not 1 <= args.commits <= 100:
        parser.error("--commits must be between 1 and 100")
    if not 1 <= args.mutants <= len(MUTANTS):
        parser.error(f"--mutants must be between 1 and {len(MUTANTS)}")

    os.chdir(ROOT)
    tests = collect_tests()
    if not tests:
        print("Application test collection failed", file=sys.stderr)
        return 2
    output_dir = ROOT / args.output_dir
    manifest = {
        "python": sys.version,
        "head": _git("rev-parse", "HEAD").strip(),
        "application_test_count": len(tests),
        "evaluation_environment": {"NUM_USERS": 100, "BASE_DELAY": 0},
    }
    _write_json(output_dir / "evaluation_manifest.json", manifest)
    history_path = output_dir / "history_results.json"
    mutation_path = output_dir / "mutation_results.json"
    if args.mode in {"history", "all"}:
        _write_json(history_path, evaluate_history(args, tests))
    if args.mode in {"mutation", "all"}:
        _write_json(mutation_path, evaluate_mutations(args, tests))
    if history_path.exists() and mutation_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
        mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
        _write_summary(output_dir / "summary.md", manifest, history, mutation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
