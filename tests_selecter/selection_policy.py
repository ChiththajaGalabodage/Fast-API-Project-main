"""Conservative, auditable policy for probabilistic test-selection scores."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, asdict
from statistics import fmean, pstdev
from typing import Iterable, Mapping, Sequence


# These are invariant safety checks, not model recommendations.  Parameterized
# variants are matched by their base node ID.
CRITICAL_TEST_BASE_IDS = (
    "tests/test_extended.py::test_health_response_has_typed_operational_fields",
    "tests/test.py::test_get_users",
    "tests/test.py::test_get_users_paginated",
    "tests/test.py::test_get_user_with_posts",
    "tests/test.py::test_create_post",
    "tests/test.py::test_update_post",
    "tests/test.py::test_delete_post",
    "tests/test.py::test_reset_db_restores_initial_state",
)

IMPACT_RULES = (
    (
        ("class createpostrequest",),
        (
            "tests/test.py::test_create_post_blank_title",
            "tests/test.py::test_create_post_title_too_long",
            "tests/test.py::test_create_post_content_too_long",
            "tests_generated/generated_test.py::test_post_api_posts",
        ),
    ),
    (
        ("class seedrequest",),
        (
            "tests/test.py::test_seed_db_invalid_limit",
            "tests/test.py::test_invalid_seed_request_should_not_change_database",
            "tests_generated/generated_test.py::test_post_api_seed",
        ),
    ),
    (
        ('"pages":', "ceiling division"),
        ("tests/test_extended.py::test_seed_updates_pagination_metadata",),
    ),
    (
        ("limit: int = query",),
        (
            "tests/test.py::test_get_users_paginated_invalid_values",
            "tests/test_extended.py::test_pagination_rejects_limit_above_maximum",
        ),
    ),
    (
        ("id=len(posts_db)",),
        ("tests/test_extended.py::test_delete_post_decrements_database_metrics",),
    ),
    (
        ("async def update_post", "post not found create post"),
        (
            "tests/test.py::test_update_post_not_found",
            "tests/test.py::test_deleted_post_cannot_be_updated",
            "tests_generated/generated_test.py::test_put_api_posts_post_id",
        ),
    ),
    (
        ("async def delete_post", "deleted_id"),
        (
            "tests/test.py::test_delete_post_not_found",
            "tests/test.py::test_delete_post_twice_second_attempt_should_fail",
            "tests/test_extended.py::test_missing_delete_does_not_change_database_metrics",
            "tests_generated/generated_test.py::test_delete_api_posts_post_id",
        ),
    ),
    (
        ("async def get_large_payload", "large-payload"),
        (
            "tests/test_extended.py::test_large_payload_rejects_size_below_minimum",
            "tests_generated/generated_test.py::test_get_api_large_payload",
        ),
    ),
    (
        ("global _force_error", "_force_error ="),
        ("tests/test_extended.py::test_reset_disables_error_injection",),
    ),
)


@dataclass(frozen=True)
class ScoreSummary:
    test_id: str
    observations: int
    mean: float
    minimum: float
    maximum: float
    stddev: float
    reasons: tuple[str, ...]


def _base_id(test_id: str) -> str:
    return test_id.split("[", 1)[0]


def critical_tests(test_ids: Sequence[str]) -> list[str]:
    """Return available invariant tests in a stable order."""
    by_base: dict[str, list[str]] = defaultdict(list)
    for test_id in test_ids:
        by_base[_base_id(test_id)].append(test_id)
    selected: list[str] = []
    for base_id in CRITICAL_TEST_BASE_IDS:
        selected.extend(sorted(by_base.get(base_id, ())))
    return selected


def impacted_tests(diff_text: str, test_ids: Sequence[str]) -> list[str]:
    """Map explicit changed contracts to invariant tests without using scores."""
    lowered = diff_text.lower()
    available: dict[str, list[str]] = defaultdict(list)
    for test_id in test_ids:
        available[_base_id(test_id)].append(test_id)
    selected = []
    for tokens, base_ids in IMPACT_RULES:
        if any(token in lowered for token in tokens):
            for base_id in base_ids:
                for test_id in sorted(available.get(base_id, ())):
                    if test_id not in selected:
                        selected.append(test_id)
    return selected


def aggregate_score_runs(
    runs: Sequence[Sequence[Mapping[str, object]]],
    allowed_tests: Iterable[str],
) -> list[ScoreSummary]:
    """Aggregate repeated LLM rankings without treating omission as score zero."""
    allowed = set(allowed_tests)
    values: dict[str, list[float]] = defaultdict(list)
    reasons: dict[str, list[str]] = defaultdict(list)
    for run in runs:
        best_in_run: dict[str, tuple[float, str]] = {}
        for item in run:
            test_id = str(item.get("id", ""))
            if test_id not in allowed:
                continue
            score = float(item.get("score", 0.0))
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                continue
            reason = str(item.get("reason", "")).strip()
            previous = best_in_run.get(test_id)
            if previous is None or score > previous[0]:
                best_in_run[test_id] = (score, reason)
        for test_id, (score, reason) in best_in_run.items():
            values[test_id].append(score)
            if reason and reason not in reasons[test_id]:
                reasons[test_id].append(reason)

    summaries = []
    for test_id, scores in values.items():
        summaries.append(
            ScoreSummary(
                test_id=test_id,
                observations=len(scores),
                mean=round(fmean(scores), 4),
                minimum=round(min(scores), 4),
                maximum=round(max(scores), 4),
                stddev=round(pstdev(scores), 4) if len(scores) > 1 else 0.0,
                reasons=tuple(reasons[test_id]),
            )
        )
    return sorted(summaries, key=lambda item: (-item.maximum, -item.mean, item.test_id))


def build_selection_decision(
    *,
    test_ids: Sequence[str],
    known_failures: Sequence[str] = (),
    deterministic_mandatory: Sequence[str] = (),
    score_runs: Sequence[Sequence[Mapping[str, object]]] = (),
    fallback_candidates: Sequence[str] = (),
    high_threshold: float = 0.80,
    medium_threshold: float = 0.60,
    uncertainty_margin: float = 0.05,
    max_tests: int = 16,
) -> dict[str, object]:
    """Select tests conservatively and return a complete audit decision.

    A test is mandatory if it is critical, previously failed, reached the high
    threshold in any repeated score run, or landed in the uncertainty band
    immediately below the high threshold.  This union rule prevents a 0.79
    observation from overriding a 0.80 observation in another run.
    """
    if not 0.0 <= medium_threshold <= high_threshold <= 1.0:
        raise ValueError("thresholds must satisfy 0 <= medium <= high <= 1")
    if not 0.0 <= uncertainty_margin <= 1.0:
        raise ValueError("uncertainty_margin must be between 0 and 1")
    if max_tests < 1:
        raise ValueError("max_tests must be positive")

    allowed = set(test_ids)
    summaries = aggregate_score_runs(score_runs, allowed)
    summary_by_id = {item.test_id: item for item in summaries}
    critical = critical_tests(test_ids)
    failures = [test_id for test_id in known_failures if test_id in allowed]
    impacted = [test_id for test_id in deterministic_mandatory if test_id in allowed]
    high_union = [item.test_id for item in summaries if item.maximum >= high_threshold]
    band_floor = max(0.0, high_threshold - uncertainty_margin)
    uncertainty = [
        item.test_id
        for item in summaries
        if band_floor <= item.maximum < high_threshold
        or item.minimum < high_threshold <= item.maximum
    ]

    mandatory = list(
        dict.fromkeys(failures + critical + impacted + high_union + uncertainty)
    )
    overflow = len(mandatory) > max_tests
    selected = mandatory[:]
    optional_ranked = [
        item.test_id
        for item in summaries
        if item.maximum >= medium_threshold and item.test_id not in selected
    ]
    optional_ranked.extend(
        test_id
        for test_id in fallback_candidates
        if test_id in allowed and test_id not in selected and test_id not in optional_ranked
    )
    if not overflow:
        for test_id in optional_ranked:
            if len(selected) >= max_tests:
                break
            selected.append(test_id)

    reasons: dict[str, list[str]] = defaultdict(list)
    for test_id in failures:
        reasons[test_id].append("known_baseline_failure")
    for test_id in critical:
        reasons[test_id].append("critical_invariant")
    for test_id in impacted:
        reasons[test_id].append("deterministic_impact_invariant")
    for test_id in high_union:
        reasons[test_id].append("high_threshold_union")
    for test_id in uncertainty:
        reasons[test_id].append("threshold_uncertainty_band")
    for test_id in selected:
        if not reasons[test_id]:
            reasons[test_id].append(
                "medium_score" if test_id in summary_by_id else "deterministic_fallback"
            )

    return {
        "policy_version": "conservative-union-v1",
        "high_threshold": high_threshold,
        "medium_threshold": medium_threshold,
        "uncertainty_margin": uncertainty_margin,
        "score_run_count": len(score_runs),
        "critical_tests": critical,
        "known_failures": failures,
        "deterministic_mandatory": impacted,
        "mandatory_tests": mandatory,
        "mandatory_overflow": overflow,
        "max_tests": max_tests,
        "selected_tests": selected if not overflow else [],
        "selection_reasons": {test_id: reasons[test_id] for test_id in selected},
        "score_summaries": [asdict(item) for item in summaries],
    }
