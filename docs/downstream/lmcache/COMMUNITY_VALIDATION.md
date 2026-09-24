# Community inspection and hardware validation plan

Downstream draft, 2026-09-24. Parent: [RFC #1](https://github.com/kvnloo/ATOM/issues/1). No upstream outreach or hardware execution is implied by this document.

## Objective and division of work

We do not have the target AMD GPU. We own source triage, CPU comparisons, a small reviewable patch, input preparation, evidence analysis and follow-up. A collaborator should supply only the smallest missing inspection or hardware observation, not reconstruct this project or debug our setup from scratch.

First request: **an approximately 15-minute source/reproduction review**, not an open-ended benchmark. Once a compatible installed stack and an agreed test revision exist, offer one bounded test at a time. The collaborator may decline or return an incompatibility result without doing a build, downloading a model or changing their live deployment.

Use an isolated development process and synthetic data. Do not ask for production prompts, cache dumps, credentials, environment-variable dumps, server access or administrative permissions. New host services, device-container privileges, time limits and resource budgets require the machine owner's agreement.

## Gate 0: package and source compatibility, no GPU claim

Reuse the existing [ATOM LMCache wheel validator](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/.github/scripts/validate_lmcache_wheel_for_atom.py) rather than making another dependency checklist executable.

That validator checks the installed version, compiled extension presence, ATOM MP adapter classes, and the server parser's `--null-block-id -1 --separate-object-groups` support. It deliberately overrides the CUDA-availability predicate for import selection in build-only environments. **A passing result does not establish GPU availability, GPU execution, ABI compatibility beyond its checks, or end-to-end cache reuse.**

Do not run it in the existing CPU-torch mock experiment and call that a real ROCm wheel validation. Select an agreed, compatible image/wheel tuple first, then record the existing validator's command and result in a disposable environment. The expected version must come from that selected tuple, not from guessing the latest package release.

For a future native MP cell, record before execution:

| Field | Inspected constraint / decision still needed |
|---|---|
| Native adapter | `lmcache_mp` already exists; do not create a new connector. |
| Topology | Pinned ATOM supports TP; requires `PP=DCP=PCP=DP=1` and no DP attention. |
| Servers | Exactly one configured LMCache server at this ATOM revision. |
| Transfer | `auto` / `lmcache_driven`; explicit `engine_driven` is rejected for multiple physical cache groups. |
| Layout | Compatible attention-published `KVTransferTensors`, full required planes and validated TP replication declaration. |
| Block semantics | Use the ATOM server recipe's `-1` null block and separate object groups; do not reuse vLLM's default block-zero assumption. |
| Lifecycle | Decide who starts/stops the standalone service; do not assume an auto-started child persists or is cleaned up. |
| Model/build | Model, tokenizer, precision, binary/image and topology still need selection with the collaborator. |

Sources: [ATOM MP adapter](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/mp/backend.py), [wheel validator](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/.github/scripts/validate_lmcache_wheel_for_atom.py), [LMCache MP reference](https://docs.lmcache.ai/mp/configuration.html). Do not infer ATOM support from vLLM-specific options in the latter.

## Gate 1: one existing model-free tensor round trip

**Question:** can this installed stack restore deterministic AITER-layout K/V and scale tensors through the existing disk backend test?

**Prerequisites:** a disposable checkout of the agreed source, compatible installed real GPU PyTorch, LMCache and Triton, a supported GPU and a writable temporary directory. This test permits either ROCm or CUDA. A CUDA result does not qualify AMD kernels or an AMD serving stack.

Source-inspected command, **not executed here**, at `a5ad0a5086af9042fd23823392f59781d4806894`:

```bash
python -m pytest -q -rs \
  tests/test_lmcache_offload_gpu_disk_e2e.py::test_gpu_kv_round_trip_through_local_disk_backend \
  --junitxml=atom-gpu-disk-roundtrip.xml
```

Run only in an already-compatible isolated environment. Do not reset a collaborator's checkout, change installed packages or grant device access automatically. Re-inspect the test when choosing a different source revision. Agree on a wall-clock budget beforehand; a timeout is an incomplete result, not a reason to release unknown in-flight GPU memory or kill a shared server.

**Acceptance:** exactly the selected test actually passes, with no skip/error. Record the source SHA, command, exit code, JUnit and sanitized log. A pytest exit code of zero with the case skipped is **not** hardware evidence.

The inspected test uses two layers, four blocks, block size four and chunk size eight. It stores 16 synthetic tokens via `LocalDiskBackend`, checks disk visibility and absence of a CPU-backend hit, zeros GPU K/V and scales, then asserts exact restoration. It needs no model weights. [Test source](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/tests/test_lmcache_offload_gpu_disk_e2e.py).

**Limit:** the test explicitly host-synchronizes the producer before storage. Passing it proves neither the production background-save fence nor host-DRAM operation, scheduler-driven HBM eviction, model accuracy or performance. Do not relabel disk storage as DRAM or physical NVMe without verifying the actual device.

## Gate 2: reuse an owner's production host-DRAM smoke

[PR #2339](https://github.com/ROCm/ATOM/pull/2339) already reports a real `DenseOffloadConnector.start_load_kv()` → `LocalCPUBackend` → retrieval smoke, including K/V and scale equality. Its reported smoke commit is `c6af1092f409ebfffd809ab8f8f0549afe136211`; the inspected PR head is `6aefe2ee89e75f57e117479068f8d06a6eeb0092`. The report is **author evidence, not our reproduction**, and does not automatically qualify the latter commit or our diagnostic base.

Before requesting a run, ask for an existing reusable script and an owner-approved revision. Refresh review status and applicable lifetime concerns. Do not rebuild the same fence in parallel or repeat reviewer claims against a newer head without checking them.

The agreed smoke must observe the actual save path, its producer ordering, host publication, removal of the GPU-copy explanation, retrieval completion and byte equality including auxiliary scale planes. It must distinguish a store that returned without publishing from a completed, available host object.

There is deliberately **no invented launch command** here: the production smoke script, safe source/build pair and machine-specific setup have not been supplied. Gate 2 is a collaboration design request until they are pinned. The existing Gate 1 command is not a substitute.

## Gate 3: one AMD/model/workload cell

Only after the applicable production path is approved for development testing, select one supported dense model already available to the collaborator, one AMD machine/topology, and fixed synthetic token inputs spanning several cache chunks. Start with exact-prefix reuse and host DRAM, not compression, remote storage, recurrent-state expansion or multiple serving engines.

Required observations:

1. Offload-disabled reference and an ordinary HBM-hit control.
2. Completed external host publication for a identified request/prefix.
3. Evidence that the repeat's reusable range is no longer in HBM while the host object still exists. If pressure removes both copies, mark the trial invalid.
4. Request/operation-specific host load range and completion on every required rank, followed by correct continuation.
5. Ordinary miss and unavailable-object controls with the intended recomputation behavior. Add cancellation/lifecycle cases only as individually reviewed bounded tests, not ad hoc fault injection into a shared service.

For example, the relevant native gap is `[hbm_cached_tokens, lmcache_cached_tokens)`, not the total reported prefix length. Preserve shared HBM blocks below that floor. For MP, obtain equivalent observations from the selected adapter rather than assuming identical events/counters. [Native architecture](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/README.md).

Predeclare token/output comparison rules and numerical tolerances with the model owner. Encoded-byte equality, continuation correctness and task accuracy are separate observations. A short marker-recall example is not general model-quality certification. No tail-latency or throughput claim follows from this smoke.

## Minimal return packet

Use a short text/JSON receipt with these fields; absent fields remain `UNKNOWN`, never inferred from another run:

- `claim`, `source_sha`, `patch_sha256`, selected test/node id, exact command, exit code, actual passed/failed/skipped counts and JUnit/log filenames.
- Image digest or explicit environment description; ATOM/AITER/LMCache source and installed versions, wheel checksum, Python/PyTorch/ROCm/Triton versions; only whitelisted values, not a full environment dump.
- GPU model/count and relevant topology, physical storage tier, fixed resource/time budget and transfer/layout/chunk geometry.
- For model runs only: model/tokenizer revisions, precision, fixed synthetic input seed/hash, observed host publication/eviction/load attribution, output result and predeclared tolerance.
- `limits`, `unexpected_observations`, `stop_reason`; distinguish `SKIPPED_ENVIRONMENT`, `FAILED_ASSERTION`, `INVALID_ATTRIBUTION`, `TIMED_OUT` and `PASSED_BOUNDED_CLAIM`.

We inspect the return packet and prepare any follow-up ourselves. Do not ask a volunteer to interpret hundreds of unrelated tests or certify an unbounded configuration matrix.

## First outreach draft — NOT POSTED

Intended context: the existing dense-save discussion, after refreshing the head and keeping the request relevant to its owner. Avoid mass mentions or a second upstream RFC.

> Thanks for documenting the real-GPU smoke and the follow-up work on the save path. I'm preparing a small downstream ATOM–LMCache qualification packet and don't have the target AMD hardware locally.
>
> Would it be useful for me to turn your existing `LocalCPUBackend` smoke into a reproducible, narrowly scoped validation recipe, using a script and revision you recommend? I can handle the source/CPU checks and result write-up; I'm not proposing another fence implementation or asking for a full benchmark.
>
> The key claim I'd like to preserve is actual production-path storage and reload with K/V and scale equality, separately from model accuracy or performance. The existing GPU/disk test is a useful earlier check, but its explicit host synchronization means I wouldn't present it as proof of this asynchronous path.
>
> AI-assisted source review and drafting; no GPU results of my own are claimed.

Hold this draft until we have inspected the corrected CPU run and can link a short evidence summary. A useful first response could be only a script link, a corrected assumption or a suggested existing test; no GPU time is required for that first collaboration step.
