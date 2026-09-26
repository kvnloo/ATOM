# Full-request offload qualification packet

Source contract reviewed at `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`. This document prepares the model-level gate without choosing hardware/model for the user and without adding a tracing service.

## I1 — existing attribution chain

The shipped code already carries an exact load identity end to end. The key distinction is **planned range versus proven reload**.

| Stage | Existing identity / observation | What it proves |
|---|---|---|
| Lookup | raw request id + lookup hit | External tier claims a prefix. **Not reload proof.** |
| Post-allocation decision | `hbm_cached_tokens`, `lmcache_cached_tokens` | Scheduler chooses the physical gap `[hbm,lmc)` after seeing the real HBM prefix. |
| Load emission | `LoadOperationId(req_id, generation)` | Exact scheduler-lifetime load generation. The scheduler stores `(seq, operation)` in `_active_load_operations` and puts the same typed operation in `LMCacheReqMeta.load_operation`. |
| Worker retrieve | same `LMCacheReqMeta` | Dense worker asks LMCache to retrieve the selected token range into the request's block table. |
| Local worker terminal | `finished_loading={LoadOperationId}` only when `ret_mask[hbm:lmc].all()`; otherwise `failed_loading={LoadOperationId}` | This worker says the entire selected range was supplied. A partial/missing object is failure, not a smaller success. |
| TP aggregation | same typed load operation + worker index | `KVOutputAggregator` releases success only after every required worker reports the same identity; failure is failure-dominant. Different generations cannot complete one another. |
| Scheduler settlement | active `(seq, LoadOperationId)` equality check | A stale completion is ignored. On success `load_finished` clears the active operation and finishes its exact load statistics; on failure `load_failed` lowers the save floor so recomputed chunks can be stored. |
| Engine wake | raw `req_id` after connector settlement | The parked request resumes only after the connector's exact-generation result has been accepted. |
| Published range | `offload_loaded_tokens`, plus DSV4 `offload_load_start_tokens` | Range the scheduler may expose to resumed execution **after terminal success**. Before terminal success, these fields are intent/state, not evidence that bytes arrived. |

Relevant source:
- [load identity types and TP aggregator](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/disaggregation/types.py)
- [scheduler emission and exact-generation settlement](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/chunked_scheduler.py)
- [worker all-token retrieve verdict](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/dense/connector.py)
- [TP aggregation](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/disaggregation/aggregator.py)
- [engine wake path](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/model_engine/scheduler.py)

### Important evidence rule

`seq.offload_loaded_tokens` is assigned when the scheduler emits the load, before the worker finishes. It is therefore a **claim boundary waiting for proof**, not a success counter. A qualified receipt must join it to the same `LoadOperationId` that later reaches all-rank `finished_loading`. Merely printing `offload_loaded_tokens` or a lookup hit would recreate the “configured/claimed capability = observed capability” mistake this RFC is intended to avoid.

The existing profile lines currently identify `req`, `hbm` and `lmc` but do not print the load generation. Do not open another logging PR while #2404 is in review. For a bounded qualification harness, capture `LMCacheReqMeta.load_operation`/worker output directly or add a downstream-only receipt hook. A global tracing layer is unnecessary.

## I2 — four-cell correctness matrix

Use one exact model/tokenizer/build, one prompt fixture, one topology and fixed memory/storage budgets. Do **not** collect performance until the reload cell passes correctness.

| Cell | Setup | Required observations | Forbidden interpretation |
|---|---|---|---|
| Offload disabled | Same request with LMCache connector absent/disabled | No external lookup/load operation; output establishes same-build baseline | Does not prove HBM behavior of offload-on arm |
| HBM hit | Reuse prefix while it remains in native HBM prefix cache | Post-allocation `lmc <= hbm` / `hbm_satisfies_after_alloc`; no `LoadOperationId`; no worker retrieve | A lookup hit is not evidence external storage was used |
| Ordinary external miss | Offload on, prefix absent from external tier | Lookup returns zero/no useful prefix; no emitted load operation; request computes locally | A successful request is not an offload success |
| Host-tier reload | Seed/publish prefix, then make native HBM prefix unavailable while external copy remains | `hbm < lmc`, exact `LoadOperationId`, worker all-token success on every rank, scheduler exact-generation settlement, resumed request/output within declared tolerance | Host hit count alone, store count alone, or `offload_loaded_tokens` before completion |

Existing CPU coverage already pins major control semantics:
- `test_load_is_skipped_if_hbm_satisfies_after_allocation` covers the HBM-satisfied no-load branch.
- dense load tests require the worker's `ret_mask[hbm:lmc]` to be complete before success.
- aggregator tests require all workers and keep exact load generations distinct.
- `test_dense_stale_load_generation_does_not_clear_active_operation` guards request-ID/generation reuse.

The hardware reload cell still needs actual external publication, HBM-prefix absence and continuation. Unit tests cannot promote that cell.

## I3 — missing-object-after-lookup control

Do **not** corrupt a live hardware cache by reaching into LMCache internals merely to satisfy a checklist. The shipped failure boundary already gives a safe, falsifiable injection point:

1. Scheduler receives a positive hit and emits a real `LoadOperationId` for `[hbm,lmc)`.
2. The worker's retrieve result omits at least one token in that range (synthetic engine/adapter in CPU validation).
3. Worker must emit `failed_loading` for the **same typed operation**, never a smaller success.
4. TP aggregation must remain failure-dominant.
5. Scheduler `load_failed` must accept only the active generation, lower the save frontier for recomputation, clear the pending load, and never publish the intended `offload_loaded_tokens` as successfully restored data.
6. Request resumes through the configured recompute/failure policy, not over partially restored KV.

A real-host deletion variant is optional only if the selected LMCache build exposes a documented safe way to remove the object after lookup without breaking its pin/lifetime contract. Otherwise the CPU failure injection is the correct control and the hardware volunteer should not improvise one.

## I4 — bounded volunteer return packet

Before a hardware run, fill every **INPUT** below and freeze the packet.

### Inputs

- ATOM source SHA: **INPUT**
- LMCache version/commit/wheel SHA: **INPUT**
- image/runtime + ROCm/PyTorch identity: **INPUT**
- GPU model/count: **INPUT**
- supported ATOM layout/path: **INPUT** (legacy dense / DSV4 / MP are separate cells)
- model + revision: **INPUT**
- tokenizer + revision: **INPUT**
- prompt fixture SHA-256: **INPUT**
- TP/DP/PP/DCP/PCP: **INPUT**
- ATOM block size / LMCache chunk size: **INPUT**
- HBM pool/capacity setting: **INPUT**
- external tier and exact capacity: **INPUT**
- output comparison rule/tolerance declared **before** results: **INPUT**

### Per-cell receipt

For each control/reload cell return:
- exact command/config hashes;
- request id;
- whether a lookup ran and its hit length;
- scheduler HBM frontier and intended load range;
- typed `LoadOperationId` if one was emitted;
- per-rank local success/failure for that exact generation;
- aggregate terminal outcome;
- final scheduler-published loaded range;
- output + comparison result;
- unexpected warnings/errors;
- process exit and cleanup separately.

### Stop conditions

Stop and return the partial packet on source/import drift, a different LMCache API, wrong model/tokenizer revision, missing exact operation identity, incomplete rank evidence, unexpected exception, nonzero exit, or inability to prove the HBM/external-tier distinction. Do not widen into a benchmark.

### Performance promotion

Only after the host-tier reload cell is correct should a later gate run repeated paired performance trials. Those trials must keep the same workload and budgets and attribute lookup, unoverlapped transfer/codec work and queueing. They must not sum overlapping timers or promote incomplete requests.

## Current disposition

- **I1:** source mapping complete; no new tracing service needed.
- **I2:** control matrix complete; hardware reload remains intentionally unexecuted.
- **I3:** safe CPU failure-injection contract defined; no unsafe live-cache mutation requested.
- **I4:** return-packet template ready; blocked only on a willing hardware owner and explicit model/environment selection.

_AI-assisted source analysis and experiment design. No model/GPU correctness or performance result is claimed here._
