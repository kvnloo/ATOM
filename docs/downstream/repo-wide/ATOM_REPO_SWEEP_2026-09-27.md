# ATOM repo-wide invariant sweep — 2026-09-27

Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

This is a coordination/reliability map, not a claim that every listed surface has a bug.

## Repository shape

First-pass recursive tree census:

- **1,583 tracked files**
- **874** under `atom/`
- **420** under `tests/`
- **29** GitHub workflows
- **74** recipes
- large implementation clusters:
  - `atom/mesh/src`: 166 files
  - `atom/plugin/sglang`: 59
  - `atom/plugin/vllm`: 48
  - `atom/model_ops`: 45
  - `atom/model_ops/attentions`: 34
  - `atom/models`: 34
  - `atom/entrypoints/openai`: 30
  - `atom/kv_transfer/offload`: 30
  - `atom/model_engine`: 27
  - `atom/kv_transfer/disaggregation`: 22
  - `atom/utils`: 22

The repo is large enough that “work the highest-priority bug serially” leaves useful independent surfaces idle. It is also coupled enough that parallel work needs owner/file boundaries.

## Parallelization map

### P0 — core correctness contracts

These are source/CPU-friendly and cross multiple features:

1. **Configuration truth**
   - topology/config shape must survive native/plugin adapters;
   - invalid values that silently disable a feature should fail before optional fallback;
   - preserve valid `None`/unsupported roles when they are part of the contract.

2. **Lifetime/completion**
   - distinguish submission, source-safe, publication, quiescence, successful restore, rank quorum and request wake;
   - generation/operation identity must survive cancellation and request-id reuse;
   - elapsed time cannot manufacture source safety for unknown device work.

3. **Capability/layout**
   - capability flags must correspond to bytes/state actually consumed;
   - do not derive heterogeneous layouts from a first/last element unless homogeneity is validated;
   - fail closed narrowly before building generalized transport/layout machinery.

### P1 — reproducibility and operator truth

4. **Runtime provenance**
   - actual installed framework/cache/transport identity, not desired pin;
   - unknown stays unknown;
   - only dependencies that can affect the executed cell should define a performance curve.

5. **Regression evidence**
   - issue/report must show the metric that actually crossed the classifier threshold;
   - missing/unmeasured is not zero;
   - a rerun/profiler trace is evidence only for the exact cell it executed.

6. **Recipes as interfaces**
   - parser-required arguments and version-sensitive flags get cheap parser/source validation first;
   - “parses” is separate from “server starts,” which is separate from “model/path is qualified.”

### P2 — framework integration

7. **Plugin compatibility**
   - native/vLLM/SGLang/RTP config and lifecycle semantics should be compared by contract, not copied mechanically;
   - ATOM compatibility shims need a stand-down detector when upstream fixes the gap;
   - broad fallback is acceptable for optional acceleration, not when it can silently remove a correctness dependency.

8. **Liveness/concurrency**
   - queue/future/thread-pool work must have explicit ownership and terminal paths;
   - batch drains must account for every admitted item;
   - timeout/cancel maps to an existing failure terminal rather than orphaning resources.

## Current owner / collision boundaries

Do not create competing work in these active surfaces without re-reading the owner branch first:

- **#2250 / #2353** — native LMCache MP, state, save admission.
- **#2369** — vLLM deferred-save / SeqView / hybrid-offload regression surface.
- **#1594 / #2354** — generalized MoRIIO write/regions vs current-main read safety.
- **#2411 / #2384 / #2376 / #2381** — hot kernel/performance work.
- **#2236 / #2280 / #2357** — framework upgrades and plugin model enablement.
- **#2374 / #2322 / #1497** — CI orchestration / CI performance.
- Existing downstream/upstream contributions **#2402 / #2404 / #2406 / #2407 / #2412** remain separate review streams.

## Concrete first findings

### 1. Performance regression issues can hide their own trigger

`.github/scripts/summarize.py` classifies four metrics:

- output throughput;
- total-token throughput;
- mean TTFT;
- mean TPOT.

The generated GitHub issue table in `.github/workflows/atom-benchmark.yaml` shows only output throughput and mean TPOT.

That explains apparently contradictory rows in automated issues such as #2408: a row can show near-flat displayed throughput/TPOT yet still be correctly classified because total throughput or TTFT crossed threshold.

Downstream candidate `fix/perf-regression-trigger-metrics` makes the structured report retain the actual triggering metric keys and renders a `Trigger(s)` column. It intentionally does **not** change thresholds or statistical policy.

### 2. vLLM hybrid scheduler fallback is conditionally unsafe, but not ready for a blanket fail-fast

ATOM's vLLM scheduler shim exists because upstream failed-load recovery assumes one KV group and can kill the engine on a hybrid failed load under `kv_load_failure_policy=recompute`.

The platform hook catches **any** exception while selecting that shim and falls back to vanilla vLLM. That is harmless for many workloads and dangerous only in the exact hybrid/recompute/failed-load cell.

The correct design question is therefore **where to verify the correctness dependency once the actual KV groups are known**, not “remove the catch.”

See `VLLM_HYBRID_SCHEDULER_FALLBACK_AUDIT.md`.

### 3. Benchmark provenance is strong but stops short of selected framework/cache/transport identity

Bundles capture ATOM, AITER, image, ROCm, harness, model, hardware, argv and workload identities.

They do not yet directly capture every selected plugin/cache/transport package. But `recipe_fingerprint()` fingerprints the whole `software` dict, so blindly adding all installed packages would create false curve splits when an unused package changes.

The next implementation must be **executed-backend-aware**.

See `BENCHMARK_RUNTIME_PROVENANCE_AUDIT.md`.

## Work that should *not* be parallelized blindly

- Multiple branches changing the same hot kernel/tuning family.
- Generic refactors of all broad `except Exception` blocks.
- Converting all runtime `assert` statements to explicit exceptions.
- Centralizing every direct `os.getenv` into one config layer.
- A universal recipe parser before several concrete parser-drift classes exist.
- A new tracing/readiness/provenance service where existing structs/hooks can carry the evidence.

These are high-churn moves with weak causal evidence.

## Recommended concurrent work budget

A practical steady-state wave can keep **6 independent source lanes** active without stepping on owner files:

1. core RFC adoption/evidence;
2. benchmark/regression observability;
3. benchmark provenance;
4. plugin correctness/fallback parity;
5. capability/layout audit;
6. liveness/concurrency audit.

GPU/kernel work stays owner-led unless a source audit yields a narrow, reproducible gap.

## Stop rule

Each lane ends in one of:

- already covered;
- active owner already owns it;
- concrete counterexample;
- smallest tested candidate;
- bounded owner question;
- hardware dependency.

A large issue list is not progress by itself. The output is reusable invariants and small adoption surfaces.

_AI-assisted repository census and source analysis. No GPU or benchmark performance result is implied._
