# Native LMCache MP compatibility triage

Source review: 2026-09-24. Parent: [RFC #1](https://github.com/kvnloo/ATOM/issues/1). This is a source-level integration trace, not GPU qualification or an exhaustive server audit.

## Decision

**Contribute to the existing MP guide, not a competing connector or guide.** The smallest concrete finding is that the server command in PR #2250 omits `--eviction-policy`, which the matching LMCache parser requires. The PR description also points to the old `mp/README.md` location; the substantial MP guide now lives in the parent offload README. Keep the proposed change to one explicit policy argument and a corrected description link. [S4, S5, S6, S7]

This supersedes two tempting but incorrect conclusions: a missing file at the old path does not mean the guide is missing, and main's TP-only restriction does not describe the newer PR. The PR already implements additional topology/state work that we should not duplicate.

[Minimal change, parser-only acceptance plan and unposted review question](MP_RECIPE_REVIEW.md).

## 1. Freeze three different references

| Reference | Snapshot | Meaning |
|---|---|---|
| ATOM main | `a5ad0a5086af9042fd23823392f59781d4806894` | Existing PAGE-only native MP implementation; primary lifecycle trace below. |
| LMCache dev and the selected ATOM wheel source | `05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb` | Source for the ATOM adapters and argument parser. The observed dev ref equals this pin; a compatible installed binary is still a separate requirement. |
| ATOM PR #2250 | `9c64bea07eeb16f75c746787490522abf0efbaec` | Open, not draft at inspection; owned by `yhl-amd`. Adds native PAGE/STATE and single-host DP work. Not merged into the first row. |

The PR author reports CPU testing but explicitly leaves full DSv4-Pro output/logit equivalence, TP8 serving and performance outstanding. Those author reports are not our reproduction. [S4]

## 2. Main's request/store/load lifecycle

The exact implementation seam is ATOM's `LMCacheMPConnectorScheduler` / `LMCacheMPConnector`, LMCache's `AtomMPSchedulerAdapter` / `AtomMPWorkerAdapter`, and the selected transfer context. ATOM retains scheduling and GPU allocation ownership; LMCache supplies external lookup/storage and transfer orchestration. [S1, S2]

| Phase | Observed path and ownership | What must not be inferred |
|---|---|---|
| Connect | Validate role/topology, create the scheduler adapter, query server chunk size and require divisibility by ATOM block size. Main connects to one configured endpoint; it does not launch the service. | Construction is not a cache hit or a hardware pass. |
| Register GPU views | Attention publishes `KVTransferTensors`; ATOM validates physical views and TP replication, builds `EngineGroupInfo` groups, and calls the worker adapter's registration. LMCache creates/registers its transfer context as `EngineType.ATOM` before marking the worker healthy. | A tensor shape alone does not establish that every required state/scale plane is present. |
| Lookup | `_MPLookupClient` calls `maybe_submit_lookup_request`, then polls `check_lookup_result`. LMCache aligns chunks and reserves lookup/read state. `None` means pending/unavailable, while zero is a real miss. | A pending result is not a reusable prefix. |
| Allocation and retained range | The shared scheduler rechecks the actual HBM floor after allocation; only the external gap is eligible for load. `prepare_retrieve` releases lookup locks outside the selected range. | Do not overwrite already shared HBM prefix blocks, or treat a pre-allocation hit count as the final load extent. |
| Dispatch | `start_load_kv` records an interprocess GPU event on the current stream. Concrete load/save operation IDs guard local submissions and completions. The LMCache future retains the event; submission leases protect the active transfer context. | An RPC being sent is not completed DMA, publication or correct output. |
| Degraded operation | The LMCache worker adapter returns `None` before submission when closed/unhealthy. ATOM finishes a skipped save opportunity or reports a failed load for recomputation. | A skipped save is not a successfully stored object. |
| Completion | `get_finished` polls futures and consumes terminal results. Loads require `result is True`; false loads fail. Terminal save results settle the source-release opportunity. Exceptions while resolving a submitted future retain the operation because device completion remains uncertain. | Save completion does not itself prove host publication; heartbeat failure does not make in-flight GPU memory safe to free. |
| Request/recovery/cleanup | Scheduler completion and session cleanup follow the selected range's ownership. Worker recovery re-registers saved cache views using lifecycle generations and registration/submission barriers. LMCache adapter shutdown drains operations before unregistering/closing resources. | The presence of adapter shutdown code does not prove every ATOM engine-exit path invokes it. Normal engine shutdown wiring was not fully traced in this pass. |

Sources: main backend and its existing tests [S1, S3], shared architecture [S10], and the real LMCache adapters [S2].

Two qualifications matter. First, main's local operation-generation bookkeeping is not the same thing as a generation-qualified identifier on every wire request: the inspected adapter calls still use the request ID. PR #2250 separately adds DP-scoped MP session IDs. Second, the scheduler/worker split above is not the old in-process lookup-server deployment; do not transplant legacy readiness assumptions into MP. [S1, S2, S8]

### Timeout is not one end-to-end deadline

Source-derived finding, not a measured stall: main starts its lookup polling deadline after submission, while the LMCache adapter performs blocking message-queue waits within submission/status calls. Therefore `lmcache.mp.lookup_timeout=30` does not imply that the whole scheduling callback returns within 30 seconds when an individual `mq_timeout` is longer. Changing this would require a deliberately tested cancellation/late-result/lock contract; it is not part of the docs recipe fix. [S1, S2]

## 3. Restriction → reason → evidence required to extend it

These rows describe **main at the pinned SHA**. A guard is a current integration boundary, not proof the underlying technique is impossible.

| Main restriction | Reason visible in code, or explicitly marked interpretation | What an expansion would have to establish |
|---|---|---|
| TP only; PP/DCP/PCP/DP all one; no DP attention | Explicit startup guards. Interpretation: current rank/key/allocation mapping is the supported contract; rejecting an axis avoids assuming an unimplemented mapping. | Layout and shard identity, per-rank lookup agreement, allocation and completion ownership for that axis. Do not simply delete the guard. |
| Exactly one server | `_server_urls` rejects any other count; no native multi-server routing is selected. | Per-worker server placement and complete-shard lookup semantics, not just a list of endpoints. |
| `auto` or `lmcache_driven`; reject explicit `engine_driven` | The error names multiple physical cache groups as the unsupported engine-driven case. | Preserve all physical groups under the chosen transfer context before widening modes. |
| PAGE-only, no populated SLOT/request-state descriptors | `_require_page_only_transfer_tensors` explicitly rejects those fields. | Matching PAGE and full state at one legal boundary. PR #2250 owns this expansion. |
| One contiguous 3-D physical tensor view per PAGE region | Exact block/unit/total byte geometry, data pointer and common device are checked. | Address/stride/byte round trips, including scale and index planes. A successful model-type check is insufficient. |
| Full TP replication or fully sharded; no intermediate replication factor | Factor must divide TP and be either one or TP. Config-time collapse prediction is checked against the attention backend's declaration. | Every physical plane must be identical on collapsed ranks. Scheduler locks must still count every reader. |
| Positive chunk size divisible by block size | Initial handshake and transfer-range validation enforce integral block/chunk mapping. | Agreement between server chunk size, ATOM geometry and namespace inputs. |
| Aligned load ranges and sufficient block IDs | Transfer specs explicitly validate alignment and coverage; last-token recomputation constrains full-prompt hits. | Correct partial-boundary behavior without writing below the HBM floor. |
| Worker dispatch creates GPU IPC events | `torch.cuda.Event(interprocess=True)` is used in the native dispatch path. | Generic LMCache CPU/SHM capability alone does not make this ATOM path CPU-runnable. |

Source: [S1, S3]. The model/attention layer can impose additional precision or representation guards. This matrix covers the native MP adapter, not every model kernel. Do not infer support for a model or quantization merely because it is absent from the table.

## 4. Main, the newer PR, and public LMCache features are not interchangeable

| Capability | Main `a5ad0a5` | PR #2250 `9c64bea` | Implication |
|---|---|---|---|
| DP | Rejected | Allows single-host DP / DP-attention; adds replica-scoped session IDs. Multi-node DP remains rejected. | Existing owner already addresses this gap; no parallel implementation. |
| Per-request native state | PAGE-only adapter refuses state descriptors | Capability-selected PAGE/STATE path and checkpoint leases | Keep baseline docs separate from branch-only claims and unfinished GPU qualification. |
| TP collapse | Whole PAGE replication validated | Additional native-state replication contracts and representation work | A one-writer optimization must still account for all readers. |
| PP/DCP/PCP, engine-driven transfer | Rejected | Still rejected in inspected guards | Public LMCache/vLLM capabilities do not override ATOM's restrictions. |
| MP guide | Main has legacy-oriented offload documentation | Parent `offload/README.md` now contains the MP guide | Fix the stale PR description pointer, not invent another guide. |

Code and proposed-guide sources: [S1, S4, S5, S8].

Current LMCache documentation describes vLLM-specific DCP, multi-server routing, auto-start, isolated IPC and nonblocking lookup controls. Treat them as integration-specific features, not native ATOM configuration promises. The native entry point is `lmcache_mp`, not vLLM's `LMCacheMPConnector`. [D1, S1]

### Main's nine directly consumed `lmcache.mp.*` keys

| Key suffix (after `lmcache.mp.`) | Main default / contract |
|---|---|
| `host` | `tcp://localhost`; used when `server_urls` is absent |
| `port` | `5555`; integer in 1–65535 |
| `server_urls` | Unset; when supplied must resolve to exactly one endpoint |
| `mp_transfer_mode` | Environment fallback `LMCACHE_MP_TRANSFER_MODE`, otherwise `auto` |
| `tp_rank_collapse` | `auto`; also accepts actual `true` / `false` booleans |
| `mq_timeout` | `300.0` seconds for adapter message waits |
| `heartbeat_interval` | `10.0` seconds |
| `lookup_timeout` | `30.0` seconds for the outer lookup polling loop, not a hard total callback deadline |
| `lookup_poll_interval` | `0.01` seconds |

This is a census of direct MP-prefixed readers in the inspected main backend, not a list of all ATOM/offload settings. Non-MP `lmcache.*`, environment and `OFFLOAD_*` settings have their own readers. PR #2250 adds branch-specific settings such as `lmcache.mp.model_revision` and `lmcache.mp.max_pinned_state_bytes`; do not use the nine-key table as its full schema. [S1, S5]

Main filters MP-prefixed extras out of the legacy storage-config builder and consumes its own selected keys. No main reader or forwarding path was found for vLLM's `lmcache.mp.autostart`, `lmcache.mp.autostart.server_args`, `lmcache.mp.isolated_ipc` or `lmcache.mp.nonblocking_lookup_status`. Copying those options does not give native ATOM their behavior. This is a source trace, not an executed ignored-option test. [S1, S2, D1]

A warning or strict unknown-key rejection could be a later design question. Strict rejection catches typos but may break permissive/forward-compatible callers; silently ignoring them avoids that break but can mislead operators. Implementing auto-start would add service ownership and exit semantics. The current smallest contribution needs none of these changes.

## 5. Concrete onboarding defect: the existing recipe omits a required argument

Evidence chain:

1. PR #2250's description points to `atom/kv_transfer/offload/mp/README.md`. Direct read at its inspected head returned 404; the exact-head directory listing has no such file. [S4, S9]
2. Reading the PR's changed parent README found the existing MP guide and launch example. The server command ends with `--supported-transfer-mode lmcache_driven --l1-size-gb 64`, with no eviction policy. [S5]
3. The selected LMCache `ServerCommand.add_arguments` calls `add_storage_manager_args`. That function declares `--eviction-policy` with `required=True`; `LRU` is an allowed value. [S6, S7]
4. ATOM's wheel validator checks the MP adapter imports and parses the special server flags, but it does not compose the storage-manager parser or validate the complete README command. Passing that validator does not catch this omission. [S11]

**Inference from the actual parser composition:** on the full compatible installation, the documented invocation is rejected by argument parsing before the requested server launch. The CLI was not executed here. Missing optional/binary dependencies may fail even earlier and would be a different result.

Proposed minimal change: append `--eviction-policy LRU` to this example and correct the PR description's guide pointer to the existing parent section. This makes an example's required choice explicit; it does not set a runtime default or claim LRU is the best policy for every workload.

## 6. Next actions and acceptance

1. Refresh #2250 before sending the short source-backed question. Stop if the author has already fixed the example/pointer. Keep this discussion on #2250, not the separately owned dense-save fence in #2339.
2. With owner agreement, submit only the one-line example correction; the author can edit the PR description pointer. Do not send this research packet as an upstream framework.
3. In an installed compatible dependency environment, construct the real server parser and parse the exact example without calling `execute()` or starting a server. Original should reject specifically for missing eviction policy; candidate should parse and retain `null_block_id=-1`, separate object groups and the intended transfer mode. Remove the added argument and confirm rejection returns.
4. Reuse existing MP configuration/layout tests rather than duplicating them. The corrected dense CI run is separate from MP compatibility and must not be cited as real MP integration evidence.
5. Hardware work remains the earlier bounded collaboration plan: selected stack, attributable external reload, correct bytes/output, then performance. No model weights, service startup or AMD run is needed to review this docs defect.

At the final status read used for this document, [corrected dense CPU run 36028507670](https://github.com/kvnloo/ATOM/actions/runs/36028507670) was `in_progress`, with no conclusion. No new MP product tests, parser execution, builds, GPU runs or upstream writes occurred in this pass. Container GitHub DNS prevented a checkout; connector reads supplied the source evidence.

## 7. Deliberately unresolved

Main's PAGE namespace hashes model name/tag, layout version, precision, geometry, chunk/block and parallel/speculation settings. This pass did not establish a complete independent model-revision or tenant-isolation contract. PR #2250 explicitly adds revision-related namespace inputs; it is not evidence that arbitrary deployments can share one cache safely. [S12, S5]

Also unresolved: the normal engine-exit invocation of adapter cleanup, real GPU completion/failure semantics, measured lookup latency under unavailable servers, and workload economics. These are bounded future questions, not claims of newly reproduced defects. A negative result or a decision to retain the simpler design is an acceptable outcome.

## Sources

- **S1:** [ATOM main MP backend](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/mp/backend.py), blob `12e309f3421c2de6b46b155f3de8529c6f6992c9`; inspected across the complete file.
- **S2:** [LMCache ATOM adapters](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/integration/atom/multi_process_adapter.py), blob `cf90391acbbf36997cc4034d1c373f2f4aeae348`; scheduler, registration, submission, recovery and shutdown sections inspected.
- **S3:** [Existing main MP tests](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/tests/test_lmcache_mp.py); initial topology/config/registration tests inspected, not executed.
- **S4:** [PR #2250](https://github.com/ROCm/ATOM/pull/2250), metadata/body at head `9c64bea07eeb16f75c746787490522abf0efbaec`.
- **S5:** [Actual proposed MP guide](https://github.com/ROCm/ATOM/blob/9c64bea07eeb16f75c746787490522abf0efbaec/atom/kv_transfer/offload/README.md#lmcache-multiprocess-lmcache_mp); source range 113–280 inspected.
- **S6:** [LMCache storage argument builder](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/v1/distributed/config.py), `add_storage_manager_args`; required eviction policy declaration.
- **S7:** [LMCache server command](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/cli/commands/server.py), `ServerCommand.add_arguments` and `execute`.
- **S8:** [PR #2250 backend](https://github.com/ROCm/ATOM/blob/9c64bea07eeb16f75c746787490522abf0efbaec/atom/kv_transfer/offload/mp/backend.py), `_mp_session_id` and topology guards; not a full branch audit.
- **S9:** [Exact-head MP directory](https://github.com/ROCm/ATOM/tree/9c64bea07eeb16f75c746787490522abf0efbaec/atom/kv_transfer/offload/mp), checked after the old README path returned 404.
- **S10:** [Main offload architecture](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/README.md), scheduler/HBM floor and shared ownership discussion.
- **S11:** [Existing ATOM wheel validator](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/.github/scripts/validate_lmcache_wheel_for_atom.py).
- **S12:** [Main PAGE namespace](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/config.py), `build_page_namespace` and shared configuration selection.
- **D1:** [Current LMCache configuration reference](https://docs.lmcache.ai/mp/configuration.html), read 2026-09-24; distinguish server arguments from the explicitly named vLLM client section.

AI-assisted analysis and drafting. All runtime validation limits above remain explicit.
