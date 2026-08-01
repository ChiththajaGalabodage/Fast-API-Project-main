# TestSelectAgent and guarded self-healing

The selector builds a 16-test impacted sample from the current diff and the
78-test application inventory. An OpenRouter model ranks tests when
`OPENROUTER_API_KEY` is available; otherwise a deterministic keyword-based
fallback keeps the workflow reproducible.

## Run the agentic workflow

```pwsh
uv run python tests_selecter/selecter.py `
  --diff reports/dummy_diff.txt `
  --run-medium `
  --min-tests 16 `
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

An empty patch is expected when the selected batch already passes. Missing
credentials do not affect selection fallback, but failed tests remain
unresolved because no LLM repair is attempted.

## CI trust boundary

Autonomous LLM generation and repair receive credentials only on trusted
push/manual events. Pull-request runs receive no LLM key, run deterministic
selection, and still execute the secret-free final suite. The final complete
suite - not the pre-repair baseline - is the authoritative CI gate.
