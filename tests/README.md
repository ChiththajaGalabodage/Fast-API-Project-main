# Execution

to run this

```pwsh
uv run pytest .\tests\test.py -v
```
# Test suite

The API test inventory contains the original functional tests plus
`test_extended.py`, which adds deterministic checks for observability, request
IDs, error injection, seeding, pagination, boundary validation, OpenAPI, CORS,
concurrent reads, and data consistency.

The application experiment contains 78 tests: 65 handwritten API tests and 13
generated tests. `test_self_healing.py` adds 28 separate deterministic
guardrail tests for AST policy enforcement, path protection, repeated reruns,
atomic apply/rollback, rollback-failure reporting, audit artifacts, and the
complete fail-repair-validate-keep orchestration flow. These guardrail tests are
run in CI but excluded from predictive-selection performance comparisons.

Run the complete traditional suite:

```pwsh
uv run python tests_selecter/run_test_batch.py `
  --csv-out test-results.csv `
  --timing-out reports/traditional_timing.json `
  --label traditional-full-suite `
  --verbose `
  tests/test.py tests/test_extended.py tests_generated/generated_test.py
```

Run the self-healing guardrails separately:

```pwsh
uv run pytest tests/test_self_healing.py -q -p no:cacheprovider
```

The agentic selector runs a minimum and maximum sample of 16 impacted tests in
one pytest batch. The fixed sample size makes experiment runs comparable and
avoids the repeated process-startup overhead of the previous per-test loop.
