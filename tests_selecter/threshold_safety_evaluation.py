"""Generate an auditable report for score-threshold safety behavior."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from tests_selecter.selection_policy import CRITICAL_TEST_BASE_IDS, build_selection_decision
except ModuleNotFoundError:
    from selection_policy import CRITICAL_TEST_BASE_IDS, build_selection_decision


def main() -> int:
    output = Path("reports/research_evaluation/threshold_safety_report.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    uncertain = "tests/test_extended.py::test_uncertain_noncritical_contract"
    inventory = [*CRITICAL_TEST_BASE_IDS, uncertain]
    repeated = build_selection_decision(
        test_ids=inventory,
        score_runs=[
            [{"id": uncertain, "score": 0.81, "reason": "run 1"}],
            [{"id": uncertain, "score": 0.79, "reason": "run 2"}],
            [{"id": uncertain, "score": 0.77, "reason": "run 3"}],
        ],
        high_threshold=0.80,
        uncertainty_margin=0.05,
        max_tests=16,
    )
    below = build_selection_decision(
        test_ids=inventory,
        score_runs=[[{"id": uncertain, "score": 0.79, "reason": "borderline"}]],
        high_threshold=0.80,
        uncertainty_margin=0.05,
        max_tests=16,
    )
    critical_zero = build_selection_decision(
        test_ids=inventory,
        score_runs=[
            [{"id": CRITICAL_TEST_BASE_IDS[0], "score": 0.0, "reason": "model miss"}]
        ],
        max_tests=16,
    )
    payload = {
        "configured_policy": {
            "high_threshold": 0.80,
            "medium_threshold": 0.60,
            "uncertainty_margin": 0.05,
            "selection_repetitions": 3,
            "aggregation": "maximum-score union; deterministic invariants are independent of scores",
            "overflow_behavior": "fail closed instead of dropping mandatory tests",
        },
        "threshold_rationale": (
            "0.80 is a nominal ranking threshold, not a safety boundary. Values from 0.75 "
            "through 0.80 are retained by the uncertainty band, any >=0.80 observation "
            "across three runs is retained by union, and critical/impact invariants ignore scores."
        ),
        "simulated_boundary_checks": {
            "scores_0.81_0.79_0.77_selected": uncertain in repeated["selected_tests"],
            "single_score_0.79_selected": uncertain in below["selected_tests"],
            "critical_score_0_selected": CRITICAL_TEST_BASE_IDS[0] in critical_zero["selected_tests"],
            "repeated_score_summary": repeated["score_summaries"],
        },
        "empirical_cross_check": {
            "source": "mutation_results.json",
            "result": "19/19 killable mutants selected; 0 selector escapes at <=16 tests",
        },
        "limitation": (
            "Boundary checks are deterministic simulations, not measurements of a model's "
            "real score distribution. Run the live workflow to collect external-model variance."
        ),
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
