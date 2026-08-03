# Research evidence summary

Generated from the reproducible artifacts in this directory on 2026-08-03.

## Threat 1: one-change sample

`history_results.json` contains 20 real commit-diff observations evaluated
against one fixed 80-test benchmark snapshot. All 20 complete-suite runs and all
20 selected-suite runs passed.

| Metric | Mean | Median | SD | Range |
|---|---:|---:|---:|---:|
| Tests reduced | 82.75% | 80.00% | 4.25% | 80.00-90.00% |
| Wall time reduced | 72.80% | 74.03% | 6.38% | 58.06-80.70% |
| Complete-suite wall time | 17.167 s | 17.294 s | 1.361 s | 15.355-19.790 s |
| Selected-suite wall time | 4.646 s | 4.444 s | 1.052 s | 3.055-7.300 s |

This is a historical-diff replay, not a rebuild of old dependency snapshots.

## Threat 2: skipped defect-revealing tests

`mutation_results.json` contains 20 first-order source mutants executed in
isolated repository copies. The complete suite killed 19 (95% mutation score).
The selected suite killed all 19 killable mutants: 100% mutation recall and zero
selector escapes, with 80.25% mean test reduction. No run timed out.

The surviving blank-title mutant is behaviorally equivalent: changing the
Pydantic minimum length does not change behavior because an independent
validator still rejects blank strings.

## Threat 3: live self-healing

`../live_repair_before.csv` records a real committed stale test: 77 passed and
one failed because the test expected HTTP 200 while the endpoint contract
returns 201. `../live_repair_after_manual.csv` records the corrected 80/80 pass.

No live-model repair result is claimed yet. The isolated replay tool and manual
GitHub workflow are ready, but execution requires explicit authorization to send
the commit diff, failing test source, and failure text to OpenRouter.

## Threat 4: probabilistic cutoffs

`threshold_safety_report.json` demonstrates that scores 0.81/0.79/0.77 are
retained by three-run union, a single 0.79 is retained by the 0.05 uncertainty
band, and a critical test remains selected even at score 0.0. Contract-specific
invariants are derived from the diff, and mandatory-budget overflow fails
closed. These are deterministic boundary checks, not measured LLM variance.

## Threat 5: missing server log

`../server.log` is a real Uvicorn startup/request log. Its manifest records three
successful requests, file size, line count, and SHA-256. CI uploads this log on
every run.
