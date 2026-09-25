# RFC wave 01: execution checkpoint

Parent [RFC #1](https://github.com/kvnloo/ATOM/issues/1). Target for new source work: **`68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e`**, the inspected upstream main containing the dense-save fence. New runtime source is not being changed in this wave.

## B: shared-fixture integration completed

[Run 36156042802](https://github.com/kvnloo/ATOM/actions/runs/36156042802) passed **all nine** pin-updater cases on unchanged PR head `9cc72463`, with the normal `tests/conftest.py` loaded, no `--noconftest` and no plugin-disable override. No cases skipped or errored; the dependency inventories match.

Downloaded artifact `10873539349` was independently checked: SHA-256 `0fbc1452624f28d054dcc7f745d4fe1d6e68199b0c026cb3fa659e188ef6d50b`, nine JUnit testcases without failure/error/skip, real conftest registration in the log, and identical before/after inventories. This closes B2's fixture-compatibility gap, not a full-suite or upstream-CI approval gap.

The candidate remains exactly the two-file diff: five updater lines and its CLI tests. It is three upstream commits behind the inspected main; the compare still contains only those two proposed changes. No rebase or claim of testing a new merge result was made. [Evidence follow-up posted on #2402](https://github.com/ROCm/ATOM/pull/2402#issuecomment-5835780223); no extra test requested.

## C and D: independent hosted CPU jobs launched

[Execution run 36160612338](https://github.com/kvnloo/ATOM/actions/runs/36160612338) has independent `mp` and `lifetimes` jobs, with `fail-fast: false`. Both were queued at the status read used to prepare this checkpoint. The result of either job is not required to start the other. Do not read a queued job or a planned assertion as a pass.

[Experiment source at `22a52648`](https://github.com/kvnloo/ATOM/tree/22a52648cd4c7c8e8bfe48d49c0a8d15408a70b8/experiments/rfc_wave_01). Both jobs use an isolated hosted CPU environment, normal repository fixtures, pinned production source, retained logs/JUnit/source hashes and within-job dependency inventories. No model downloads, serving process, deployment secrets, self-hosted runners or GPU requests. The large experiments remain downstream.

### C3: native configuration is not the vLLM connector configuration

At the pinned main, the nine directly consumed MP-prefixed keys are `host`, `port`, `server_urls`, `mp_transfer_mode`, `tp_rank_collapse`, `mq_timeout`, `heartbeat_interval`, `lookup_timeout` and `lookup_poll_interval` (each prefixed `lmcache.mp.`). The remaining MP-prefixed values are removed before legacy storage-config parsing. [Actual native readers](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/atom/kv_transfer/offload/mp/backend.py).

The public [LMCache configuration reference](https://docs.lmcache.ai/mp/configuration.html#vllm-client-configuration) explicitly places automatic startup, nonblocking lookup status and isolated IPC in its vLLM client configuration. Those features are not established for native ATOM by copying their keys. This is a deployment-boundary correction, not a request to prohibit every unknown field or implement these capabilities now.

The downstream characterization test freezes the actual direct-read key set, checks the selected native readers keep their defaults when these vLLM-only settings are copied, and confirms storage parsing does not receive them. It does not instantiate a real remote adapter or certify all possible configuration handling. Existing MP tests are run beside it, not replaced.

### C4: characterize timeout semantics before changing scheduling

The real `_MPLookupClient.lookup()` creates its polling deadline **after** submission and accepts a non-`None` result **before** rechecking that deadline. Two new deterministic-clock tests exercise the actual ATOM method:

| Simulated external behavior | Declared observation |
|---|---|
| Submission consumes eight clock seconds; timeout is three; one pending poll then a real zero result | Current facade returns the genuine miss after nine simulated seconds, because the polling budget begins after submission. |
| Status call consumes eight clock seconds then returns a four-token hit; timeout is three | Current facade accepts the hit after the status call rather than enforcing a hard whole-callback deadline. |

These are characterization hypotheses derived from code, pending the linked run. They are **not measured server latency, an incident report or a proposed deadline change**. Existing tests already cover timeout-as-non-answer and delayed cleanup; we reuse them. Rewriting this into a hard deadline or nonblocking interface would require explicit late-result/read-lock ownership and scheduler behavior, not just moving one timer.

Potential next contribution after execution: a small native-doc clarification distinguishing the outer lookup polling budget from blocking adapter RPC timeouts. No new upstream question has been posted for this finding.

### D2–D4: reuse the author's existing safety tests

The merged tests already cover the principal invariants we were about to add. Run the actual `test_offload_early_block_release.py` and `test_dense_offload_connector.py` rather than creating another implementation or a duplicate suite. [Existing source](https://github.com/ROCm/ATOM/blob/68e0df5e7cc0e9eff9b5f8155ddb99bdcb43b32e/tests/test_offload_early_block_release.py).

| Requested invariant | Existing exact test to retain |
|---|---|
| One incomplete TP rank blocks memory release | `TestTPQuorum.test_one_incomplete_rank_prevents_logical_group_release` |
| Rejected save waits for source quiescence before retry | `TestStoreOutcomeSeparation.test_pre_submit_failure_retries_only_after_tp_source_quorum` |
| Mixed rank outcomes still need every rank's source completion | `TestStoreOutcomeSeparation.test_mixed_tp_outcome_waits_for_all_source_quiescent_reports` |
| Live post-submit failure can retry after its source groups are safe | `TestStoreOutcomeSeparation.test_live_post_submit_failure_retries_once_all_source_groups_are_safe` |
| Safe-to-release is not successful-storage accounting | `TestStoreOutcomeSeparation.test_commit_failure_after_source_safe_releases_without_success_stats` |
| Late completions after reclaim have no second effect | `TestNoDoubleFree.test_late_completions_after_timeout_reclaim_are_noops` |
| Duplicate or stale completions cannot release twice | `TestNoDoubleFree.test_duplicate_and_stale_source_completions_do_not_double_release` |
| Reused request IDs retain distinct allocation ownership | `TestNoDoubleFree.test_request_id_reuse_cannot_attach_an_old_lease_to_new_blocks` |

The job also checks test sensitivity in a **disposable CPU checkout**: change the single all-ranks drain guard in `_TPCompletionGroup` to permit one report, run the two existing quorum tests, require failures specifically at premature-release assertions, restore the source and require both to pass again. No mutated production source is committed or used with hardware.

If the existing tests pass and detect the control, the disposition is **reuse / no duplicate patch**, not an invented missing regression. This does not establish actual multi-GPU timing or revisit the owner's implementation unasked.

## E: diagnostics decision isolated from the merged fence

The dense worker and scheduler still log an optional initialization exception using `%s` and the exception object. An empty exception message is therefore still the old diagnostic case. The merged safety work has not implemented our earlier class-only candidate. Current search also finds the worker warning in `hybrid/m3/connector.py` and both analogous warnings in `hybrid/dsv4/connector.py`; matching strings alone do not prove equivalent lifecycle contracts.

The policy choice remains open:

| Choice | Benefit | Cost / unresolved decision |
|---|---|---|
| Add exception class while retaining the existing message | Diagnoses empty exceptions and preserves current operator context | Still formats arbitrary third-party exception text, just as today. |
| Component plus class only | No arbitrary message payload in these warnings | Removes information operators currently receive; needs deliberate agreement. |
| New global sanitizer/status layer | Potential standardized reporting | Disproportionate scope for this slice; not proposed. |

A synthetic secret fixture demonstrates a formatting contract, not an observed credential leak. The old CPU pass does not establish either maintainer preference or qualification at this new base. Valid non-hosting `None`, warning level, roles and fallback must remain unchanged whichever wording is selected.

**Unposted design question:** “For the two optional dense lookup initialization warnings, would you prefer adding the exception class while retaining the existing message, or component/class only? The current message is empty for `RuntimeError()`. I would preserve the existing fallback, roles and valid non-hosting `None`, and keep this separate from the merged fence and sibling connectors.”

E1's source refresh and E2's alternatives are ready; E3 remains gated on choosing the contract. No broad helper, hidden policy decision or revived fence patch was introduced.

## F and A remain honest boundaries

F1's source inspection found `BlockGPUConnector.last_transfer_stats()` deliberately reports counts/fast-path evidence without phase or GPU-event timings. Do not turn `producer_fenced=1`, a hit count, or wall-clock durations from separate runs into claimed transfer/compute overlap. Missing intervals remain unknown. The existing transfer-instrumentation tests are the next evidence source before considering additional instrumentation; no timing hooks were added this wave.

A4 still needs a willing owner of a compatible one-GPU development environment. The approved smoke recipe and known-teardown caveat remain intact. No new volunteer was recruited, hardware run performed or performance benefit claimed during this pass.

## Next decisions

Read the C/D receipts, including setup failures and skipped cases, before changing dispositions. Keep positive and counterexample evidence separate from hardware qualification. Advance B only on actual upstream review/CI state; do not label nine selected cases a full native-suite pass. Update the lane issues with observed results rather than estimated completion percentages.
