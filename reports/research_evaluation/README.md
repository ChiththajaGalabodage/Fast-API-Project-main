# Research evaluation evidence

This directory contains machine-generated evidence, not manually calculated
claims. Reproduce both experiments with:

```pwsh
uv run python tests_selecter/research_evaluation.py all --commits 20 --mutants 20
```

`history_results.json` replays 20 real Git commit diffs against one fixed
current application/test snapshot. Keeping the snapshot fixed isolates the
test-selection variable and makes timing and reduction values comparable. It
does **not** claim that every historical dependency snapshot was rebuilt.

`mutation_results.json` injects 20 first-order source defects, one at a time,
inside isolated temporary copies. Each mutant is executed against both the
complete application suite and the conservatively selected suite. The main
outcome is mutation recall:

```text
mutants killed by selected suite / mutants killed by complete suite
```

A mutant that the complete suite kills but the selected suite does not is
reported as a selector escape. A mutant that survives the complete suite is
reported separately as a test-suite weakness and is not counted as a selector
success.

The history experiment uses 20 observations, but 20 is still a modest sample.
Report the mean, median, standard deviation, range, and individual rows rather
than claiming permanent or universal performance.

## Current measured result

- History replay: 20/20 complete and selected runs passed.
- Test reduction: mean 82.75%, median 80.00%, SD 4.25%, range 80-90%.
- Wall-time reduction: mean 72.80%, median 74.03%, SD 6.38%, range 58.06-80.70%.
- Complete-suite mutation score: 19/20 (95%).
- Selector mutation recall: 19/19 killable mutants (100%), zero escapes.
- Mean mutation-run test reduction: 80.25%.
- One full-suite survivor is behaviorally equivalent because another validator
  still enforces the mutated constraint.

See `threshold_safety_report.json` for cutoff-boundary checks and limitations.
