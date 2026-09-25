# Parallel RFC wave 01 — 24 tasks, six lanes

Snapshot: 2026-09-25. Parent [RFC #1](https://github.com/kvnloo/ATOM/issues/1). This is the first expanded execution wave, not 24 completed contributions or 24 concurrently running agents.

## Method transferred from CUA

Apply the process behind [CUA RFC #3963](https://github.com/trycua/cua/issues/3963): measure the actual boundary, preserve ownership, split work into small coherent contracts, and prove a behavior before promoting it. For ATOM, these are repo-native functions, tests, example corrections and evidence packets—not literal network nanoservices or another connector framework.

Every task has: existing owner/context → one invariant → pinned evidence → smallest intervention → counterexample/mutation control → result/limits → disposition. Its output may be a patch, measurement, scoped question, handoff or a no-op. More internal investigation must not mean more unsolicited upstream comments.

**Effort rule:** start with one source pass or one bounded CPU experiment per task. Stop/rescope after an invalid experiment, an existing equivalent fix, unclear ownership or a missing hardware requirement. Keep one active write stream per branch/file and one coherent external thread per owner. Concurrent inspection/CPU work may continue while another lane waits for review; unanswered messages are not agreement.

## Six ABAB plan critiques

| Initial approach | Counterexample | Revised approach | Remaining evidence gate |
|---|---|---|---|
| Make 24 patches | Many tasks are already owned, and some hypotheses should be rejected | 24 internal task dispositions, compressed into a few useful packets | Only independently useful evidence earns a new upstream interaction |
| Wait for the GPU lane before any further work | Build, CLI, fixture, diagnostics and accounting checks do not require it | Separate six lanes; only hardware-specific acceptance waits | No CPU result is promoted to GPU correctness |
| Treat successful result JSON as full success | The author reports a logged teardown error and separately observed resource cleanup | Track transfer result, diagnostics and cleanup independently | Unknown cleanup remains unknown |
| Move all work to the newest main | Prior runs and feature branches establish different contracts | Keep exact per-task code/build pins; requalify changed candidates | A merged PR is not a run at its merge commit |
| Reimplement fence/STATE support to fill the RFC | #2339 is merged; #2250 already owns native PAGE/STATE expansion | Adopt existing owners' work and contribute missing evidence or tiny scoped changes | Credit the original implementation; do not imply its entire roadmap is accepted |
| Extract a shared helper early | Similar wording can hide different lifetimes/layouts | Keep small native seams; extract only after multiple concrete callers prove the same contract | Maintainer preference and behavior-preservation tests |

## Lane/task ledger

`VERIFIED` is limited to the described source/action. `CARRIED` means prior evidence, not a new experiment. `READY` is planned work, not executed. Each linked issue contains its invariant, source links, stopping rules and full acceptance conditions.

| Task | Scope and next decision | State at wave creation |
|---|---|---|
| A1 | Author reply + fence merge; separate reported and independently checked evidence | VERIFIED this wave |
| A2 | Reviewed smoke recipe; checksum attestation; import origin; known teardown line | UPDATED this wave |
| A3 | Review-rule counterexamples; never infer cleanup from a transfer pass | 12 SYNTHETIC scenarios passed locally |
| A4 | One opt-in owner, exact one-GPU smoke and return packet | AWAITING_VOLUNTEER; not requested |
| B1 | Actual #2402 submission and prior real-CLI regression evidence | VERIFIED / CARRIED |
| B2 | Same nine tests with real ATOM shared conftest, no `--noconftest` | NEW CI queued; result pending |
| B3 | Inspect current merge diff and any actual conflict before edits | READY |
| B4 | Handle owner feedback and upstream CI; record disposition | WAITING_REVIEW, not a reason to pause other lanes |
| C1 | Exact MP example against the real parser | CARRIED: prior comparison passed |
| C2 | Existing one-line example patch handed to #2250 owner | VERIFIED; awaiting response/application |
| C3 | Exact native key/capability crosswalk versus public client docs | READY |
| C4 | Outer lookup deadline versus blocking RPC and late-result ownership | READY after C3 boundary refresh |
| D1 | Reuse merged dense fence, do not compete with it | VERIFIED upstream merge; not our implementation |
| D2 | Map source-safe/store/quiescent/load completion contracts to existing tests | READY |
| D3 | One discriminating failed-save retry / quorum regression, only if missing | Depends on D2 |
| D4 | Request retirement and late completion with reused identity | Depends on D2 |
| E1 | Rebase analysis of the two diagnostic handlers, not automatic code rebase | READY |
| E2 | One question: exception class alone versus retained message detail | Depends on E1 |
| E3 | Requalify selected minimal policy/diff with original/candidate/restored control | Depends on E2's actual decision |
| E4 | Sibling contract sweep; no automatic shared helper | Depends on E1 |
| F1 | Existing critical-path measurements and explicit unknown time | READY |
| F2 | Overlap-safe interval accounting and incomplete-trial handling | Depends on F1; CPU-only logic check |
| F3 | Actual HBM absence + retained host object + attributable request reload | HARDWARE + model/observation selection gate |
| F4 | One measured bottleneck-driven optimization with paired controls | Depends on F2 and F3 |

Lane issues: **[A #2](https://github.com/kvnloo/ATOM/issues/2)** · **[B #3](https://github.com/kvnloo/ATOM/issues/3)** · **[C #4](https://github.com/kvnloo/ATOM/issues/4)** · **[D #5](https://github.com/kvnloo/ATOM/issues/5)** · **[E #6](https://github.com/kvnloo/ATOM/issues/6)** · **[F #7](https://github.com/kvnloo/ATOM/issues/7)**.

The source-ready queue is B3, C3, D2, E1 and F1. It does not wait for A4, B4 or C2. D3/D4 and E2/E4 can branch after their own source gate. F3 additionally needs a supported model, hardware owner and real request observation plan; the one-GPU connector smoke alone does not satisfy it.

## Architecture crosswalk: small contracts, existing ownership

| Capability | Existing seam / owner | Invariant and lane |
|---|---|---|
| Validate a complete input change | Wheel-pin script and Dockerfile pin contract; our #2402 | Read/validate all inputs before the first write; B |
| Admit a supported configuration | Native MP adapter and real LMCache parser; #2250 owner | Only actual supported keys/topology/layouts; C |
| Identify a construction outcome | Existing dense optional-lookup handlers | Exception differs from valid non-hosting `None`; E |
| Fence and settle an operation | Dense connector / GPU pack path / `SaveOperationId`; #2339 owner | Producer wait, publication, source-safe and quiescence differ; D |
| Protect against stale/reused state | Scheduler, leases, request/operation identity and native state | No release/retry from an unrelated or incomplete completion; D/C |
| Qualify exact bytes | Author's existing `LocalCPUBackend` smoke | Exact target, eight restored tensors and retained diagnostic evidence; A |
| Prove useful request reuse | Scheduler HBM floor, external lookup/load and output observation | Count only the actual missing range retrieved from the intended tier; F |
| Decide whether optimization is earned | Downstream benchmark specification, not a serving policy service | Complete outcomes and critical-path cost under fixed budgets; F |

No new runtime service, registry, network API, global readiness flag or background agent is introduced by this plan. ATOM keeps scheduling/GPU representation/lifetime ownership; LMCache keeps external storage orchestration. Future compression, prefetch, tiering or disaggregation is conditional on measured need and a separate correctness contract.

## What actually changed in this wave

- Refreshed #2339/#2250/#2402 discussions and metadata before writes; identified the new #2339 owner response rather than guessing it was on our new PR.
- Corrected the [smoke recipe](DENSE_HOST_SMOKE_RECIPE.md). Historical script hashes now match the owner's launch-time attestation; the historical hardware result remains theirs. Kept `e9be221f` as the reproduction target.
- Ran [12 synthetic teardown-review scenarios](../../../experiments/rfc_wave1/teardown_contract.py) locally. The rule does not parse raw logs, rerun LMCache or certify a GPU. Its input requires complete reviewed diagnostics and validated result/provenance; cleanup always remains a separate observation.
- Started [shared-fixture CI](https://github.com/kvnloo/ATOM/actions/runs/36156042802) for #2402's exact head. At this snapshot it is queued. This closes a different evidence gap from the earlier standalone CLI run, and it does not bypass upstream approval.
- Created six downstream issues with four tasks each. No maintainer or volunteer was assigned work without agreement.

**Not done:** no new GPU/model/server run, latency measurement, merge, production rollout or 24-task completion. No new upstream issue or competing implementation was created. The only fresh upstream follow-up appropriate to this wave is a short acknowledgment of applied recipe feedback, not another review or GPU request.

## Publication and progress

Before each external action: reread the entire relevant discussion, verify head/owner, check for an existing solution, state one invariant, link only the minimal evidence and disclose limits. Serialize each external thread. Any hypothetical design question stays a draft until its real source context is checked.

Report separate counts/statuses for source understanding, reproduced behavior, submitted change, owner selection, merge and hardware qualification. Do not turn a task checkbox, paper read, comment, reaction, or another author's merge into an overall RFC completion percentage. The dense fence merge is an upstream prerequisite now available, not proof that our full cache-reuse vertical slice is finished.

Source anchors: [owner review](https://github.com/ROCm/ATOM/pull/2339#issuecomment-5831522164), [fence merge](https://github.com/ROCm/ATOM/pull/2339), [MP feature](https://github.com/ROCm/ATOM/pull/2250), [our pin PR](https://github.com/ROCm/ATOM/pull/2402), [CUA process reference](https://github.com/trycua/cua/issues/3963), [LMCache integration-specific configuration reference](https://docs.lmcache.ai/mp/configuration.html).
