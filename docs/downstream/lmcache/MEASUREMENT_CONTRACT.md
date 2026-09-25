# Measurement contract and unblocked execution queue

Checkpoint: 2026-09-25. Parent [RFC #1](https://github.com/kvnloo/ATOM/issues/1); measurement [lane F #7](https://github.com/kvnloo/ATOM/issues/7). Source pin: `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`.

## Completed while advancing another lane

[Run 36160612338](https://github.com/kvnloo/ATOM/actions/runs/36160612338) finished. Both artifacts were downloaded and their SHA-256 digests checked; the actual JUnit reports and before/after dependency inventories were inspected.

| Lane / arm | Observed result | Disposition |
|---|---|---|
| MP plus three downstream characterization cases | 65 passed, zero failures/errors/skips | Current native key/deadline behavior characterized; not a server latency measurement. |
| Existing dense and early-release tests | 79 passed, zero failures/errors/skips | Reuse the existing safety coverage; no duplicate test patch. |
| Temporarily remove the all-rank completion requirement | Both selected quorum tests fail at the expected premature-release assertion | Existing tests detect the intended broken invariant. |
| Restore the real completion requirement | Both selected quorum tests pass | No mutated source is committed or used on hardware. |

Artifacts: MP `10876325139`, SHA-256 `eb2ab7dcd13a4ec297bd7354b79285fa7282250061d4def7bfa20e4f4964714c`; lifetimes `10875517731`, SHA-256 `bdf1c2abfda4fa26df24b6f1f2ba5913492b565d2500c6ee0e9cb59be76f3c28`. Both receipts say `PINNED_CPU_LANE_PASSED`. Tests ran against normal ATOM fixtures. These selected suites are not a full native-suite or hardware qualification, and repeated control arms are not additional coverage.

## F1: what the existing observations can establish

| Observation | Boundary / admissible inference | Not established |
|---|---|---|
| Native lookup facade | Polling budget begins after submission; a non-None result is accepted before the deadline check. | A hard deadline on blocking adapter calls or measured production latency. |
| Dense `retrieve_ms` / `store_ms` | Host `perf_counter` duration around the corresponding engine call and nearby preparation. | Pure DMA, kernel time, durable publication, or full request time. |
| Dense `total_ms` | Outer worker-handler interval containing that operation timer. | Executor queue delay, scheduler delay, end-to-end TTFT or a second duration to add to its child timer. |
| Thread-local transfer counts | Byte/group/path evidence from the same worker thread; existing tests check snapshot isolation. | Phase timing, GPU utilization or compute/transfer overlap. |
| Store/source-safe completions | Distinct operation-level outcomes; existing CPU quorum tests keep them separate. | Model correctness or actual multi-GPU timing. |
| Request completion, recomputation and host attribution | Need a separately selected real serving cell with request/operation/rank and clock provenance. | Not supplied by the connector smoke, a global hit count or these unit tests. |

Sources: [native MP backend](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/mp/backend.py), [dense handlers](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/dense/connector.py#L305-L459), [transfer statistics](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/_block_gpu_connector.py#L330-L413), [existing instrumentation tests](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/tests/test_offload_transfer_instrumentation.py).

Absolute comparable endpoints, not only scalar durations, are needed to infer interval overlap. A union of known intervals measures observed wall-clock coverage, not a dependency-graph critical path or saved compute. Gaps remain unattributed, not automatically idle. Cold setup is reported separately and must not be silently removed from end-to-end economics.

## Concrete finding: absent timing currently prints as zero

`BlockGPUConnector.last_transfer_stats()` explicitly supplies counts without phase/GPU timings. The shared worker helper passes that dictionary through; it does not add missing timers. Nevertheless, the two dense profile log statements format `pack_ms`, `copy_ms`, `sync_ms`, `transfer_ms` and `effective_gbps` through `get(..., 0.0)`.

The [pinned log-expression probe](../../../experiments/lmcache_measurement/profile_log_probe.py) reproduced this formatting with synthetic count-only inputs: both the load and save expressions print all five absent fields as `0.00`. Supplying explicit zeroes produces byte-identical log lines. Supplying `1.25` values preserves those values. The tested source Git blob is `54e3cee334f007df7c4c9aa88b8ac63fc02fa1e6`.

This runs the exact two logging expressions extracted from the hash-checked source, not the whole worker, ATOM imports, LMCache or a GPU. It demonstrates a representation ambiguity, not an observed zero-cost transfer, runtime performance defect or end-to-end reproduction. [Shared helper](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/_offload_common.py#L338-L350).

Next minimal candidate: distinguish unavailable fields from real zeroes while preserving measured worker timers and count/fence evidence. Before selecting omission, an explicit availability marker or a sentinel, inspect log consumers and the existing author's intent. Do not add GPU synchronization or rebuild the removed phase instrumentation just to fill the fields. PR #2223 is the earlier merged transfer-instrumentation work; a new submission requires a fresh collision check, not an assumption that current logs have no consumers.

## F2: accounting checks executed locally, no remote runner needed

[Self-contained standard-library experiment](../../../experiments/lmcache_measurement/measurement_contract.py):

```bash
python experiments/lmcache_measurement/measurement_contract.py
python experiments/lmcache_measurement/profile_log_probe.py \
  /path/to/pinned/atom/kv_transfer/offload/dense/connector.py
```

Nine accounting tests passed on Python 3.13.5: overlapping, nested, repeated, adjacent and zero-length intervals; cold setup; missing endpoints; missing instrumentation; wrong clocks/trials; invalid ranges. For example, `[0,7)` plus `[4,10)` covers **10** synthetic milliseconds, not the naive sum **13**.

Two disposable negative controls were caught: summing overlapping durations produces two failed checks; treating unknown coverage as zero produces four failed checks including subtests. Restoring the original file leaves all nine tests passing. The wrapper initially expected two method-level failures for the second control; it was corrected to count the three incomplete subtests plus one absent-instrumentation failure. Neither the analyzer nor its assertions were weakened.

No GPU measurements, speedup, production-trace ingestion or critical-path estimate is produced. An absent setup measurement stays unknown rather than claiming setup cost zero. The helper rejects overlapping setup/request windows instead of silently trimming them. It is a downstream accounting contract, not a proposed runtime service or upstream test framework.

Source SHA-256: `measurement_contract.py` = `3d6a2bcde18278b4afb84002bea39d6f0ae8cbe74bd9a9ff44a417553997471d`; `profile_log_probe.py` = `28d6f89ae2761ad9d5536f3db487329fb7b2bcff5c2ff963aa53049c9205623c`. Local logs and result JSON retain synthetic inputs separately from the downloaded CI receipts.

## Dispatch rule and next ready work

During each work session, do one status sweep, consume new evidence, and pick the highest-value ready task. A waiting task must name its owner/input, existing evidence and exact restart condition. Do not manufacture progress by rerunning an unchanged queued job, reposting a question, creating a duplicate fix, or bypassing hardware/review gates. Returning “already covered” is a valid task result.

| State | Next bounded action | Restart / finish condition |
|---|---|---|
| READY — F profile semantics | Inspect log consumers and add a normal-worker CPU regression for absent versus measured-zero fields; prepare the smallest compatible output change. | Original fails the intended assertion; candidate preserves real timers and counts. No GPU required. |
| READY — C docs | Convert the verified native polling-budget behavior and config-key boundary into a small documentation proposal for the existing MP work. | Source-matched wording, owner collision check, no scheduler rewrite. |
| READY — E diagnostics | Compare class-plus-message versus class-only behavior and prepare the focused policy question without widening the patch. | Explicit contract selected; old source evidence is not treated as a new-base pass. |
| WAITING — A/F hardware | Keep the approved one-GPU recipe and separate model-attribution plan prepared. | A willing owner and named compatible environment; no automatic resource request. |
| WAITING — B review | Keep #2402's tested two-file candidate unchanged pending review/CI state. | Actual review or CI event, not another speculative code edit. |
| COVERED — D CPU invariants | Reuse the author's existing tests and retain the counterexample evidence. | Revisit only for changed source/contracts or a concrete uncovered scenario. |

No new CI workflow was added or unchanged C/D run duplicated. These files are outside that workflow's watched experiment path. No upstream comment, runtime source change, server, model, GPU job, merge or deployment occurred in this pass. AI-assisted analysis and downstream preparation; hardware and performance remain unqualified.
