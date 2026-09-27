# Benchmark runtime provenance audit

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

ATOM's benchmark bundle is already unusually strict about provenance. The next improvement should preserve that property rather than adding package names indiscriminately.

## What is captured now

`atom.benchmarks.results.metadata.capture_config()` records:

- executing ATOM Git SHA;
- installed AITER version, commit source, commit/abbreviation when defensible, and wheel SHA-256 when available;
- image + image digest;
- harness version/SHA;
- ROCm version;
- model revision/precision;
- hardware identities and parallelism;
- executed server/client recipe inputs through the bundle pipeline.

`installed_package()` is already generic for installed Python distributions and deliberately leaves unknown identity unknown. AITER has one additional conservative rule: a clean `+g<sha>` package-version suffix may supply an abbreviated commit; it is never expanded or replaced by a checkout guess.

## Gap

The `software` section does not directly identify the installed framework/transport/cache packages that may actually execute a benchmark cell, for example the selected plugin framework or an external cache/transport Python package.

That matters for cross-feature work because ATOM increasingly has:
- native and vLLM/SGLang plugin paths;
- LMCache and P/D transport paths;
- out-of-tree framework pins that can change behavior while the ATOM SHA stays fixed.

A requested Docker pin is not sufficient evidence of what Python imported at runtime.

## Why “record every installed package” is the wrong patch

`recipe_fingerprint()` fingerprints the entire `software` object.

Therefore adding every package found in the environment would split performance curves when an **unused** framework/package version changed. Example: a native ATOM benchmark could get a new recipe fingerprint merely because an unused SGLang wheel was updated in the same image.

That would improve provenance while making benchmark comparability worse.

## Desired contract

Capture **executed-backend-relevant** software identity, not environment inventory.

A clean design should separate two questions:

1. **Evidence:** what relevant packages were installed/imported?
2. **Curve identity:** which of those packages can affect this executed cell?

Two viable shapes:

- Add backend/connector-selected package identities to `software`, so the current fingerprinting rule naturally includes only relevant dependencies.
- Or add a broader evidence inventory outside the fingerprinted subset and explicitly select the curve-defining package identities inside `recipe_fingerprint()`.

The first is smaller if backend/connector selection can be determined reliably from executed argv/config. The second scales better if one cell can dynamically use several transports.

## First implementation candidates

Without changing schema version, `software` already accepts extra fields. Reuse `installed_package()` and keep missing distributions as `None`.

Candidate mappings should be proven one at a time:
- vLLM plugin cell → executing `vllm` distribution identity;
- SGLang plugin cell → executing `sglang` distribution identity;
- LMCache-enabled cell → executing LMCache distribution identity;
- MoRI-backed cell → executing MORI distribution identity.

Do not guess package distribution names from import module names; verify each in the actual image/pin workflow before landing it.

## Acceptance

A CPU/source qualification can prove:
- changing a **selected** framework identity changes the recipe fingerprint;
- changing an **unselected** installed framework does not;
- missing package identity remains unknown rather than borrowed from a desired pin;
- bundle rebuild preserves the captured identity.

This is source/fixture evidence only. It does not prove performance reproducibility by itself.

## Disposition

**Prepared design, no code patch yet.** The next useful decision is selecting one concrete backend (vLLM is the strongest current candidate) and tracing how its executed backend identity reaches `capture_config()` without model-name or filename heuristics.

_AI-assisted source review. No benchmark result is reclassified by this audit._
