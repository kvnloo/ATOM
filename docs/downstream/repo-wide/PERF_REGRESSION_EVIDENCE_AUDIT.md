# Performance regression evidence audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This lane applies one rule to the automated performance pipeline:

> the issue must describe exactly the comparison that triggered it, and missing evidence must stay missing.

Four independent defects/gaps are now isolated. They should be landed serially because they touch the same small scripts/workflow.

## P1 — hidden trigger metric

Classifier: Output Tput, Total Tput, Mean TTFT, Mean TPOT.

Issue table today: Output Tput + Mean TPOT only.

Result: a row can correctly trip on Total Tput or TTFT while the two displayed metrics look healthy.

Status: candidate `fix/perf-regression-trigger-metrics` adds `triggered_metrics` to the structured report and a `Trigger(s)` column. Thresholds unchanged.

## P2 — missing metric is silently converted to zero

Current classifier does:

```python
cur_val = data.get(metric_key, 0)
base_val = baseline.get(metric_key, 0)
```

For a higher-is-better metric, a missing current value therefore becomes a synthetic **-100% regression** against a positive baseline.

For a latency metric, a missing baseline can also produce an infinite percentage through `_pct_change`.

This directly violates the benchmark-bundle contract used elsewhere in the repo: unknown is not zero.

Desired behavior:

- if either side lacks a tracked metric or the value is not a finite number, that metric is **not comparable**;
- preserve it as unavailable in the structured report;
- other comparable metrics may still trigger the row;
- a row with no comparable triggering metric is not a regression.

Do not substitute zero, do not impute from another metric, and do not change thresholds.

## P3 — baseline key omits workload range ratio

Current key:

```
(backend, model, ISL, OSL, concurrency)
```

`random_range_ratio` changes the actual length distribution, appears in benchmark catalogs/result filenames, and is recorded by strict bundles, but it is not part of the regression key.

Thus ratio 0.8 and ratio 1.0 currently collide if the other five fields match.

Desired correction after P1/P2 settle:

- add normalized range ratio to random-workload matching;
- numeric/string spellings of the same ratio match;
- missing remains distinct from explicit values;
- do not turn this into a full recipe-fingerprint migration.

See `PERF_REGRESSION_BASELINE_KEY_AUDIT.md`.

## P4 — profiler summary is arbitrarily the first directory

The regression issue creator walks `profiler-analysis/*`, reads the first `performance_summary.md` it sees, and places it under the generic heading “Performance Summary.”

When several configurations regress, that summary is evidence for one specific rerun, not for all rows. Directory order is not an attribution rule.

Smallest safe correction:

- record the directory/config name next to any embedded summary;
- preferably link/list all available per-config summaries in the artifact rather than imply one is global;
- do not infer that the first trace explains the regression.

## Landing order

1. P1 trigger metric reporting.
2. P2 unknown-vs-zero semantics, with causal missing-current/missing-baseline controls.
3. P3 range-ratio matching.
4. P4 profiler-summary attribution.

Each step gets its own red/green/control evidence. Keep thresholds/noise policy untouched so review stays about evidence integrity rather than performance policy.

_AI-assisted source audit; no existing regression classification is retroactively changed here._
