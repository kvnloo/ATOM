# Performance regression baseline-key audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This is the second finding in the regression-evidence lane. It is intentionally **not** patched in parallel with the trigger-metric candidate because both edit `.github/scripts/summarize.py`.

## Current matcher

`summarize._config_key()` matches a current point to a baseline using only:

```
(backend, display_model, ISL, OSL, max_concurrency)
```

The benchmark workload itself also includes `random_range_ratio`. That value is not cosmetic:

- benchmark clients use it to vary input/output lengths around the target;
- catalogs carry it per scenario;
- result filenames include it;
- recipes use both 0.8 and 1.0;
- strict benchmark bundles record it as `workload.range_ratio`.

Therefore two runs can currently have the **same regression key while executing different random-length distributions**.

## Concrete counterexample

Two rows:

- backend `ATOM`, model `fixture`, 8192/1024, concurrency 8, ratio **0.8**
- same backend/model/lengths/concurrency, ratio **1.0**

produce the same `_config_key()` today.

A baseline lookup can therefore compare the second curve to the first and classify the resulting delta as a code performance regression even though the workload distribution changed.

This is source-level evidence about the matcher. It does not establish that a published regression issue has already been caused by this exact collision.

## Minimal correction after the trigger-metric lane settles

Add a normalized `random_range_ratio` component to the key.

Compatibility rule:

- values that are numerically equivalent (`0.8`, `"0.8"`) should match;
- a missing/unknown ratio must remain distinguishable from an explicit value;
- agentic/non-random results should not invent a ratio.

Do **not** expand this patch into a full recipe fingerprint migration. The existing dashboard/baseline system is keyed by lightweight result JSON, not strict benchmark bundles.

## Further provenance fields

TP/DP/EP, framework version, image and model revision can also change a performance curve, but some current display names already encode topology and plugin workflows separately enrich framework/image fields. Their key semantics need a separate compatibility audit before inclusion.

The range ratio is the smallest demonstrated omitted workload dimension because the repository explicitly treats it as part of result naming and workload generation today.

## Adoption order

1. finish the independent trigger-metric reporting patch;
2. rebase/stack this matcher correction on the accepted form of that file;
3. add one causal test: ratio 0.8 baseline must **not** match ratio 1.0 current;
4. add one normalization control: float/string 0.8 **do** match;
5. no threshold changes.

_AI-assisted source analysis; no existing regression issue is reclassified by this document._
