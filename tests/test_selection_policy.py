from tests_selecter.selection_policy import (
    CRITICAL_TEST_BASE_IDS,
    build_selection_decision,
    impacted_tests,
)


def _inventory(*extra: str) -> list[str]:
    return [*CRITICAL_TEST_BASE_IDS, *extra]


def test_critical_tests_run_when_model_returns_nothing():
    decision = build_selection_decision(test_ids=_inventory(), max_tests=16)

    assert decision["selected_tests"] == list(CRITICAL_TEST_BASE_IDS)
    assert all(
        "critical_invariant" in decision["selection_reasons"][test_id]
        for test_id in CRITICAL_TEST_BASE_IDS
    )


def test_score_just_below_threshold_is_kept_by_uncertainty_band():
    test_id = "tests/test_extended.py::test_boundary_case"
    decision = build_selection_decision(
        test_ids=_inventory(test_id),
        score_runs=[[{"id": test_id, "score": 0.79, "reason": "affected"}]],
        high_threshold=0.80,
        uncertainty_margin=0.05,
        max_tests=16,
    )

    assert test_id in decision["selected_tests"]
    assert "threshold_uncertainty_band" in decision["selection_reasons"][test_id]


def test_repeated_scores_use_conservative_union_not_last_observation():
    test_id = "tests/test_extended.py::test_probabilistic_boundary"
    decision = build_selection_decision(
        test_ids=_inventory(test_id),
        score_runs=[
            [{"id": test_id, "score": 0.81, "reason": "run one"}],
            [{"id": test_id, "score": 0.77, "reason": "run two"}],
            [{"id": test_id, "score": 0.79, "reason": "run three"}],
        ],
        max_tests=16,
    )

    summary = decision["score_summaries"][0]
    assert summary["minimum"] == 0.77
    assert summary["maximum"] == 0.81
    assert summary["observations"] == 3
    assert "high_threshold_union" in decision["selection_reasons"][test_id]


def test_policy_fails_closed_when_mandatory_tests_exceed_budget():
    extra = [f"tests/test_extended.py::test_high_{index}" for index in range(10)]
    score_run = [
        {"id": test_id, "score": 0.95, "reason": "high impact"}
        for test_id in extra
    ]
    decision = build_selection_decision(
        test_ids=_inventory(*extra),
        score_runs=[score_run],
        max_tests=16,
    )

    assert decision["mandatory_overflow"] is True
    assert decision["selected_tests"] == []


def test_diff_mapping_keeps_all_parameterized_seed_boundaries():
    variants = [
        "tests/test.py::test_seed_db_invalid_limit[value=0]",
        "tests/test.py::test_seed_db_invalid_limit[value=1001]",
        "tests/test.py::test_invalid_seed_request_should_not_change_database",
        "tests_generated/generated_test.py::test_post_api_seed",
    ]

    selected = impacted_tests("class SeedRequest(BaseModel):", _inventory(*variants))

    assert selected == variants
