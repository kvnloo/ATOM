# Native MP performance qualification packet

Parent: [RFC #1](https://github.com/kvnloo/ATOM/issues/1), measurement lane [#7](https://github.com/kvnloo/ATOM/issues/7).

This packet turns the first real native-MP restore evidence into a **performance experiment**, without treating that correctness run as a speedup result.

## Proven hardware cell to preserve

Owner evidence on [ROCm/ATOM #2250](https://github.com/ROCm/ATOM/pull/2250):

- hardware: **8 × MI355X**
- model: **DeepSeek-V4-Pro**
- topology: **TP8**
- KV dtype: **FP8**
- ATOM tested head: `62893d7`
- LMCache: **0.5.6.dev98**, pinned build containing `05fc77a`
- checkpoint interval: **8192 tokens**
- three arms:
  1. cold — fresh ATOM, empty HBM and empty LMCache;
  2. restore — fresh ATOM, empty HBM, retained LMCache L1;
  3. control — fresh ATOM, empty HBM and empty LMCache again.

Observed restore evidence:

- **460,032 tokens** loaded from LMCache;
- **352/352 retrieves finished**;
- **0 load failures**;
- one 18,095-token prompt restored `0:17920`, crossing the 8192 and 16384 checkpoint boundaries;
- GSM8K 64-shot, 50 samples: **0.94** on cold, restore and control;
- cold-vs-restore answer identity was 47/50, equal to the cold-vs-control floor, so exact string equality is not a valid per-run correctness requirement under this FP8/dynamic-batching cell.

This is owner-generated hardware evidence. It establishes that native MP can perform a real external restore in this cell; it does **not** establish performance benefit or replace the RFC's independent-reproduction goal.

## Promotion rule

Do not optimize or claim benefit until the exact restore cell above remains correct under the benchmark workload.

A performance trial is **invalid** if any arm has:
- nonzero load failures;
- incomplete required-rank completion;
- model/server failure;
- a different model/tokenizer/build/topology;
- unknown LMCache persistence state;
- a restore arm that silently recomputes because workers were reaped;
- missing request-completion data.

The #2250 owner already found one concrete false-positive trap: setting `--worker-registration-grace-seconds 30` caused restarted workers to be reaped before their first heartbeat, and restore silently fell back to prefill while accuracy still looked normal. Therefore **accuracy alone cannot identify a valid restore arm**.

## Exact performance question

Under fixed hardware, model, topology, memory/storage budgets and request corpus:

> Does a verified LMCache restore reduce end-to-end useful GPU time or latency relative to recomputing the same prefix, after charging the cost of populating and retaining the external tier?

This is intentionally narrower than “is LMCache faster?”

## Required arms

Use the same request corpus and order for every arm.

### A — cold / populate

Fresh ATOM + empty LMCache.

Purpose:
- establish baseline compute;
- populate the external tier for B;
- record fill/store cost separately.

Required evidence:
- LMCache starts empty;
- no external load credited to requests;
- successful request outputs;
- store/publication counts and completion;
- request metrics.

### B — restore

Fresh ATOM + the LMCache L1 produced by A.

Purpose:
- measure real external reuse.

Required evidence per request:
- HBM is fresh/empty for the reused prefix because ATOM restarted;
- external lookup hit length;
- emitted load range / exact operation identity where available;
- all required retrieves complete;
- zero load failures;
- request completes correctly;
- request latency/throughput metrics.

A positive lookup or `offload_loaded_tokens` value before terminal completion is not enough.

### C — recompute control

Fresh ATOM + empty LMCache, same corpus.

Purpose:
- estimate the same-build recompute floor independently from A's tier-fill work.

Required evidence:
- no external load;
- same model/tokenizer/build/topology;
- request completion and outputs;
- same metrics as B.

### Optional D — HBM-fit control

Only if the memory budget can be changed without changing the model execution path.

Purpose:
- separate “external tier versus recompute” from “native HBM prefix cache versus external tier.”

Do not substitute this arm for C.

## Trial design

Correctness first, then timing.

1. One untimed warm-up per server launch if required by the existing serving benchmark.
2. Run A → B → C once to verify arm identity.
3. If all three are valid, collect repeated paired trials. Prefer interleaving whole triplets rather than doing all A runs, then all B runs, then all C runs.
4. Minimum useful first pass: **5 valid triplets**. If variance is high enough that the sign of the effect changes, stop and report uncertainty rather than increasing repetitions indefinitely.
5. Keep concurrency, prompt corpus, generation limits, sampling parameters and scheduler budgets identical.
6. Keep LMCache capacity, chunk size, null marker, object-group mode and worker registration settings identical.
7. Record the exact ATOM/LMCache/model/tokenizer identity for every triplet.

## Metrics

Use existing serving/benchmark metrics first. Do not add GPU synchronization just to obtain a prettier decomposition.

Per request:
- TTFT / prefill-visible latency;
- TPOT / decode latency where applicable;
- total request wall time;
- prompt and generated token counts;
- success/failure;
- external loaded token count;
- load failure count.

Per arm/trial:
- completed requests;
- total wall time;
- aggregate input/output tokens;
- request throughput;
- output-token throughput;
- external bytes/tokens restored;
- store/fill work;
- peak/steady memory budget if already exposed.

Derived economics:
- **GPU-seconds = wall-clock seconds × 8 GPUs** for this fixed TP8 cell;
- correct completed requests per GPU-second;
- correct prompt tokens processed per GPU-second;
- delta(B,C) for request latency and GPU-seconds;
- A's fill cost reported separately, then amortized only under an explicitly stated reuse count.

Do not add `retrieve_ms` to `total_ms`, or sum any overlapping nested timers. The existing [measurement contract](https://github.com/kvnloo/ATOM/blob/work/lmcache-lookup-qualification/docs/downstream/lmcache/MEASUREMENT_CONTRACT.md) requires interval union for overlapping observations and keeps unmeasured time unknown.

## Correctness comparison

Because #2250 observed the same 47/50 answer identity between cold-vs-restore and cold-vs-control, use **the same task-level score/tolerance declared before results**, not raw string identity as the sole pass criterion.

For the existing GSM8K cell:
- preserve the same evaluator and 50-sample corpus if reusing that evidence;
- require restore score not to degrade beyond the predeclared tolerance relative to both A and C;
- separately require zero transport/load failures.

If a different workload is selected for performance, freeze its scorer/tolerance before running.

## Receipt template

Each triplet should return:

```json
{
  "atom_sha": "",
  "lmcache_identity": "",
  "model_revision": "",
  "tokenizer_revision": "",
  "gpu": "8x MI355X",
  "topology": "TP8",
  "kv_dtype": "fp8",
  "checkpoint_interval_tokens": 8192,
  "corpus_sha256": "",
  "trial": 1,
  "arms": {
    "cold_populate": {
      "lmcache_initial_state": "empty",
      "requests_completed": 0,
      "load_failures": 0,
      "loaded_tokens": 0,
      "wall_s": null,
      "ttft": [],
      "tpot": [],
      "score": null
    },
    "restore": {
      "lmcache_initial_state": "retained-from-cold-populate",
      "fresh_atom": true,
      "requests_completed": 0,
      "retrieves_finished": 0,
      "load_failures": 0,
      "loaded_tokens": 0,
      "wall_s": null,
      "ttft": [],
      "tpot": [],
      "score": null
    },
    "recompute_control": {
      "lmcache_initial_state": "empty",
      "fresh_atom": true,
      "requests_completed": 0,
      "load_failures": 0,
      "loaded_tokens": 0,
      "wall_s": null,
      "ttft": [],
      "tpot": [],
      "score": null
    }
  }
}
```

## Decision table

| Result | Disposition |
|---|---|
| B correct and faster/less GPU-time than C | Promote the measured bottleneck for targeted optimization / deployment analysis. |
| B correct but equal within variance | Keep correctness support; do not claim an economics win. |
| B correct but slower | “Correct but uneconomic caching” is a valid RFC outcome; analyze the measured cost before changing mechanisms. |
| B silently recomputes / has load failures | Invalid performance trial; fix correctness/availability first. |
| Scores differ beyond predeclared tolerance | Stop performance interpretation and investigate correctness. |

## Current status

- Real native-MP restore: **externally demonstrated by #2250 owner**.
- Independent RFC reproduction: **still open**.
- Logit-level equivalence: **still open**.
- Performance economics: **not executed**.
- This packet is **READY** once a willing compatible AMD owner wants to run the existing validated cell; no new model or architecture choice is required.

_AI-assisted experiment design. No performance result is claimed._
