# Dense host-memory smoke: reviewed community recipe

Updated 2026-09-25 after [the author's review](https://github.com/ROCm/ATOM/pull/2339#issuecomment-5831522164). **Acceptance table and running without the outer runner are author-approved. GPU execution by us remains NOT RUN.** Parent: [RFC #1](https://github.com/kvnloo/ATOM/issues/1).

The original full shell, GPU preflight and JSON-result instructions remain available at the [immutable prepared recipe](https://github.com/kvnloo/ATOM/blob/4feea25b027927a2cff1648d83f4931672f943a5/docs/downstream/lmcache/DENSE_HOST_SMOKE_RECIPE.md#execution-recipe--not-executed-here). Those commands and the author's smoke are unchanged. This revision supersedes its historical-checksum uncertainty and blanket cleanup-error rule with the precise boundaries below.

## One bounded claim, not full-system certification

The real dense worker store path uses the producer dependency on the actual pack thread, publishes to `LocalCPUBackend`, and retrieves identical K/V and scale tensors after clearing the destination tensors. Normal registration, scheduler-driven HBM eviction, model forward, TP quorum, failed-save retries, a forced ordering-race comparison and performance are not exercised by this smoke.

The smoke manually connects the real engine and codec to the worker and supplies synthetic request metadata. Its save/load worker path is real; the absent scheduler and distributed environment must not be inferred from the word 'production'. One process, one compatible GPU, no model and no lookup server are needed. [Author review](https://github.com/ROCm/ATOM/pull/2339#issuecomment-5831522164).

## Exact inputs and provenance

| Field | Value / evidence class |
|---|---|
| Keep the reviewed target | `e9be221f637d6a7e194e0d3201dbc9ddc3119067` |
| Upstream merge, verified via PR metadata | `68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`; [#2339 is merged](https://github.com/ROCm/ATOM/pull/2339) |
| Historical GPU result, author-reported | `4a8d76bea929a8925f299f8db98f2408a20cea7d`; MI350X, one GPU, LMCache `0.4.5`, ROCm `7.2.53211`, torch `2.10.0+rocm7.2.4`, no model |
| Captured Gist | `c881bce790f14d57fa026219af2d4466c2e4a154` |
| Smoke SHA-256 | `fc699dbc3465729fb8fa17593ee90c9830a28c5a7d41343a302edc43b968d342` |
| Outer runner SHA-256 | `daede71dd36bd6577c2b8a3e0c016151f324ab61cd8e9c9e077f7f106e57d627` |

The author now supplies both historical launch-time checksums from their `RUN.json`; they exactly match our retained source-capture checksums. Record **AUTHOR_ATTESTED_HISTORICAL_BYTES_MATCH_CAPTURE**, replacing 'historical byte identity unknown'. We have not independently fetched that historical `RUN.json` or rerun its hardware experiment. Do not transform the author's attestation into our own GPU result.

The author permits either the head or merge revision. Keep the existing head pin so this recipe and its strict preflight remain one consistent cell. Testing the merge revision later requires changing every recorded/asserted target together and recording a new cell; a merged PR is not itself a smoke run at the merge commit.

Source: [pinned Gist](https://gist.github.com/NidhoggD1/4768a59519b2e4a9c83e80037a21db79/c881bce790f14d57fa026219af2d4466c2e4a154), [source-capture run](https://github.com/kvnloo/ATOM/actions/runs/36064272664), [author review and historical checksum attestation](https://github.com/ROCm/ATOM/pull/2339#issuecomment-5831522164).

## Acceptance table — confirmed by the author

| Observation | Required result |
|---|---|
| Producer dependency | Exactly one real event wait inside `batched_from_gpu`, on a thread other than the dispatcher, with a live pack stream. |
| Store instrumentation | Exactly one store-side stats record with `producer_fenced == 1`; do not count load-side calls. |
| Source safety | Two source-safe groups for the fixed 16-token/chunk-8 geometry. |
| Operation completion | One successful `dense.page.store` plus one `dense.page.source_quiescent` for the same `SaveOperationId`. |
| Host attribution | 16/16-token lookup specifically in `LocalCPUBackend`. |
| Restored bytes | All eight tensors (two layers, K/V/k_scale/v_scale) compare equal after zeroing and actual retrieval. |

Zeroing destination tensors is not scheduler-driven HBM eviction. The smoke has no deliberately delayed-write/no-fence control; it demonstrates the asserted event plumbing and exact round trip, not a race frequency. [Author review](https://github.com/ROCm/ATOM/pull/2339#issuecomment-5831522164).

## Portable environment: omit the machine-specific outer runner

The author confirms coverage is unchanged without their outer runner. The smoke does not require `--ipc host`, a special network mode or a 4 GiB shared-memory allocation. Do not copy relaxed container permissions, device mappings, source paths or image-private assumptions into a generic recipe. The owner still selects an isolated compatible ROCm environment and available GPU.

Preserve the original preflight: exact clean checkout, script SHA-256, LMCache `0.4.5`, exactly one visible ROCm GPU, and the real `connector.__file__` import origin. In particular, **put `PR_SRC` first on `PYTHONPATH`**. The author's image also includes `/app/ATOM`; omitting this check can silently test the wrong checkout. Export `PR_COMMIT` and `SMOKE_RESULT`, the two environment values the smoke reads.

Use the [unchanged commands and preflight](https://github.com/kvnloo/ATOM/blob/4feea25b027927a2cff1648d83f4931672f943a5/docs/downstream/lmcache/DENSE_HOST_SMOKE_RECIPE.md#execution-recipe--not-executed-here) only after the owner agrees to the isolated environment and time budget. No serving process, model download, package installation, source reset or GPU reset is requested. Record image/build provenance in addition to version strings; do not export credentials or a full environment dump.

## Known teardown log: retain it, do not declare cleanup successful

The author reports the following non-raised log during `LMCacheEngineBuilder.destroy()` in LMCache `0.4.5`, after `result.json` is written, while the process still exits zero:

```text
LMCache ERROR: Error closing backend LocalCPUBackend: tuple index out of range
```

For this exact pinned smoke/dependency configuration, **that documented line alone does not invalidate otherwise valid transfer observations**. Preserve the complete stderr and annotate `KNOWN_TEARDOWN_LOG`. This is a version-scoped, author-reported exception, not permission to suppress all errors, modify the backend, or accept unknown cleanup.

Keep three separate outcomes:

| Dimension | What qualifies it |
|---|---|
| Bounded transfer result | Exact pinned provenance, exit zero, all acceptance observations and complete result JSON. |
| Diagnostic review | Known exact teardown message recorded separately; any additional/changed error, unreviewed diagnostics, nonzero exit or different dependency requires review. |
| Process/resource cleanup | Separate machine-owner observation. A successful transfer, zero exit, `container_removed=True`, or absence of error text does not establish this. |

The author reports independently checking no remaining container, zero GPU VRAM use and KFD process count returning to baseline for their historical run. Retain that as **author-reported historical cleanup**, not evidence about a future volunteer's run. Do not reset a device or terminate unrelated processes to produce a clean-looking result.

The original result-checking Python validates result fields and provenance; it is **not a stderr classifier or a process-cleanup check**. Run it, then review the actual diagnostics and cleanup separately using this table. Missing JSON, timeouts, nonzero exits or false/missing transfer observations still block acceptance. An unexpected backend list still requires investigation.

## Return packet and next gate

Return exact source/script/image or build identities, preflight, result JSON, exit code, complete sanitized stderr/stdout, diagnostic classification and the owner's separate cleanup observation (or explicitly `UNKNOWN`). No model weights, production prompts, credentials, container administration access or broad benchmark is needed.

The recipe's source-review gate is satisfied. **Next: one opt-in compatible hardware owner, one unchanged script, one pinned target, one bounded claim.** No hardware owner is assigned or assumed by this document, and no volunteer request has been posted from this update. A source-review approval is not endorsement of the wider RFC or its future architecture.

A downstream synthetic review-rule check exercises known versus unexpected diagnostics and incomplete results; it does not replay real LMCache teardown or qualify a GPU. The original smoke remains unchanged and authored by NidhoggD1. AI-assisted recipe maintenance and evidence review.
