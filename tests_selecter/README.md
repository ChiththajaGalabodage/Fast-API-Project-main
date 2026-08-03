# TestSelectAgent and guarded self-healing

The selector builds an at-most-16-test impacted sample from the current diff and
the 80-test application inventory. An OpenRouter model ranks tests when
`OPENROUTER_API_KEY` is available; otherwise a deterministic keyword-based
fallback keeps the workflow reproducible.

## Probabilistic-score safety

The 0.80 high and 0.60 medium thresholds are ranking parameters, not hard
safety boundaries. On trusted model-backed runs the selector requests three
independent rankings and retains the union of tests that reach 0.80 in any run.
Scores in the 0.75-0.80 uncertainty band are also mandatory. Eight universal
health/CRUD invariants and diff-mapped contract tests run independently of
model scores. If mandatory tests exceed the 16-test budget, selection fails
closed. `selection_decisions.json` records observations, ranges, standard
deviations, and reasons.

The deterministic cutoff simulation is in
`reports/research_evaluation/threshold_safety_report.json`. It is not presented
as a measurement of the external model's real score distribution.

## Run the agentic workflow

```pwsh
uv run python tests_selecter/selecter.py `
  --diff reports/dummy_diff.txt `
  --selection-repetitions 3 `
  --threshold-margin 0.05 `
  --max-tests 16 `
  --max-heal-functions 3 `
  --heal-validation-runs 2 `
  --failure-csv test-results.csv `
  --before-csv reports/agentic_before_heal.csv `
  --csv-out reports/test_results.csv `
  --timing-out reports/agentic_timing.json `
  --healing-report reports/self_healing_report.json `
  --healing-patch reports/self_healing.patch `
  --healing-backup-dir reports/self_healing_backups
```

Selected tests run in one pytest process. This preserves per-test durations
while avoiding repeated interpreter, plugin-discovery, collection, and fixture
startup. Failed/error node IDs in `--failure-csv` are placed ahead of the LLM
ranking so a known baseline failure is not skipped by predictive selection.

## Autonomous repair transaction

For at most three distinct failed functions per run, the system:

1. Normalizes parameterized node IDs and extracts the exact failed function.
2. Asks the LLM for one replacement function, or `NO_FIX` when the failure is
   likely an application defect or a safe repair is uncertain.
3. Rejects changes to the name, complete typed signature, sync/async type,
   decorators, function-body structure, assertion structure, or calls. Only
   non-control contract literals may change. Functions containing branches,
   loops, exception/context control, returns, boolean short-circuiting,
   ternaries, or comprehensions are not autonomously repaired.
4. Rejects imports, skips/xfails, trivial assertions, filesystem/process/env
   access, external URLs/network clients, dynamic execution, nested code, and
   any newly introduced `5xx` status expectation.
5. Limits writes to Python tests under `tests/` and `tests_generated/`, while
   protecting `tests/test_self_healing.py` and rejecting symbolic-link paths.
6. Takes a byte snapshot and backup, applies the function patch atomically,
   reruns the whole base function twice, then reruns the complete selected
   batch.
7. Keeps the patch only when every validation passes. Otherwise it restores
   every touched file byte-for-byte, verifies rollback, and exits non-zero.

The repair subprocesses receive a credential-scrubbed environment. The system
does not commit or push a repair. CI separately checks that `HEAD` and protected
files did not change.

## Outputs

- `agentic_before_heal.csv`: initial selected-batch result.
- `test_results.csv`: final result after validation or rollback.
- `agentic_timing.json`: selector-workflow timing and repair counts; this does
  not include the separate final CI safety gate.
- `self_healing_report.json`: decision, hashes, validation runs, and rollback
  status for every attempted repair.
- `self_healing.patch`: accepted unified diffs only.
- `self_healing_backups/`: original source snapshots.
- `selection_decisions.json`: repeated scores and mandatory-selection reasons.

An empty patch is expected when the selected batch already passes. Missing
credentials do not affect selection fallback, but failed tests remain
unresolved because no LLM repair is attempted.

## CI trust boundary

Autonomous LLM generation and repair receive credentials only on trusted
push/manual events. Pull-request runs receive no LLM key, run deterministic
selection, and still execute the secret-free final suite. The final complete
suite - not the pre-repair baseline - is the authoritative CI gate.

## Research evaluation

```pwsh
uv run python tests_selecter/research_evaluation.py all --commits 20 --mutants 20
```

The measured evidence contains 20/20 passing historical replay pairs. Test
reduction averaged 82.75% (SD 4.25), while wall-time reduction averaged 72.80%
(SD 6.38). The complete suite killed 19/20 mutants; selection killed all 19
killable mutants (100% recall, zero escapes) with 80.25% mean test reduction.
One mutant is behaviorally equivalent because another validator still enforces
the changed constraint. These results support this benchmark only. Historical
diffs are replayed against a fixed current snapshot; old dependencies are not
rebuilt.

Capture the missing server artifact with:

```pwsh
uv run python tests_selecter/capture_server_log.py
```

This writes `reports/server.log` plus a checksum manifest. CI uploads the same
log on every run.

## Live repair evidence and disclosure

The real committed stale-test case expected HTTP 200 for an endpoint whose
contract returns 201. Its failing complete-suite baseline is retained in
`reports/live_repair_before.csv`; the corrected passing run is in
`reports/live_repair_after_manual.csv`.

`tests_selecter/live_repair_replay.py` reconstructs that committed failure in
an isolated copy and runs the guarded agent. It sends the commit diff, test IDs,
failing test source, and failure text to OpenRouter. Run it only after explicitly
authorizing that disclosure, or manually dispatch `Live Repair Evaluation`.
The script excludes `.env` from the sandbox and never records the credential.
