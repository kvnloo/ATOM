# ATOM × LMCache: approach review and decision gates

Updated 2026-09-24. Downstream working document for [RFC #1](https://github.com/kvnloo/ATOM/issues/1). These are six research/critique cycles, not six GPU experiments. The contributor has no target AMD GPU; source/CPU evidence and community hardware evidence remain separate.

## Decision in one paragraph

Finish the bounded native lookup-diagnostic experiment, then ask whether the proposed loss of raw exception-message detail is acceptable before recommending that patch upstream. For a new deployment, investigate **the existing native `lmcache_mp` path first**, subject to its actual compatibility limits and the workload owner's requirements. Keep the legacy native path as a bounded maintenance/reproduction target, not our default long-term architecture. Use the vLLM plugin when that is the deployment people actually need, rather than adding it merely because its examples are familiar. Reuse existing validators, tensor tests and the save-fence author's hardware work before requesting new community GPU time.

There is no globally optimal choice established here. The decision is conditional on supported layout, lifecycle requirements, available hardware and measured workload economics.

## Three existing deployment paths

| Path | Reason to use it | Cost / boundary | Current decision |
|---|---|---|---|
| Native `lmcache_offload` | Smallest continuation of our already-pinned constructor tests and existing native dense save investigation. | In-process LMCache is now deprecated in its documentation. This path couples cache lifetime to the serving engine and has separately owned dense-save correctness work. | Finish a small maintenance slice; do not build a new legacy orchestration layer. [S1, S2, S5] |
| Native `lmcache_mp` | Uses ATOM's existing opaque PAGE adapter and an independently managed LMCache server; aligns with LMCache's deployment direction without adding vLLM. | The inspected adapter permits TP-only operation, one server, and rejects explicit `engine_driven` transfer for its multiple physical groups. Process separation introduces another lifecycle and dependency boundary to qualify. | Preferred **investigation** for new native deployment, not a production-readiness claim. [S1, S3] |
| ATOM vLLM plugin | Relevant when users already operate vLLM and need ATOM's backend within that serving stack. | Adds the vLLM/ATOM/LMCache version and layout intersection. The inspected generic recipe uses legacy `LMCacheConnectorV1`; a new MP recipe is not a drop-in consequence of that example. | Qualify a separate plugin cell only for an actual deployment requirement. [S4] |

Physical tier names are mandatory in results: **GPU HBM, host DRAM, local disk/NVMe, remote storage**. The legacy and MP docs use numbered tiers differently; a bare `L1 hit` is not enough to identify where the bytes came from. The inspected MP server also defaults its null block to `0`, while ATOM's validation requires `-1` and separate object groups. Do not copy vLLM server arguments unchanged. [S7, S8]

## Six ABAB cycles

Here A1 is the initial proposal, B1 its strongest counterexample, A2 the revision, and B2 the evidence or objection that remains. A cycle can legitimately end with an unresolved decision.

### 1. A failing qualification run: code regression or experiment defect?

**A1 — Proposal.** Use one virtual environment and compare unchanged production, candidate and sensitivity arms.

**B1 — Observation.** Run 1 reached all focused tests, but both native-suite subprocesses used the system Python and failed with `No module named pytest`. Calling the virtual-environment interpreter did not change the `PATH` used by the repository's shell runner. There were no native JUnit reports, so this is missing coverage, not an ATOM regression. [E1, S9]

**A2 — Revision.** Activate the same virtual environment before launching the experiment driver. Preserve the native runner and its existing exclusions. This is a workflow-only correction at `e68e996fe9262a851df5434902173babadedb759`. [E2]

**B2 — Remaining gate.** Rerun the complete comparison and inspect actual native reports. Focused success alone does not complete the CPU gate. Installation drift between runs must be recorded; comparisons remain within one unchanged environment per run, not across two assumed-identical installations.

### 2. Better warning text: useful information versus payload exposure

**A1 — Proposal.** Append the exception class to the existing exception message. This preserves the most diagnostic detail and makes an empty `RuntimeError()` identifiable.

**B1 — Counterexample.** An arbitrary message can contain configuration-derived values. Our synthetic secret fixture demonstrates the formatting contract, not an observed real-world credential leak. Conversely, hiding every message may remove the very endpoint/configuration clue an operator needs. [S2, E1]

**A2 — Revision.** Keep a class-only candidate limited to the two existing optional-lookup handlers. Preserve severity, roles, fallback and valid non-hosting `None`. Do not add a global logging policy, sanitization regexes, retries or startup readiness framework. [E1]

**B2 — Remaining decision.** Ask whether component plus exception class is sufficient at this boundary. A type-plus-original-message alternative maximizes debugging detail but violates the proposed no-payload criterion; a structured allowlist of known failure reasons adds maintenance and cannot reliably describe arbitrary third-party errors. Passing tests prove the chosen contract, **not that maintainers prefer that contract**. Resolve the preference before expanding the patch.

### 3. Finish what we started or follow multiprocess deployment?

**A1 — Proposal.** Expand the current in-process native integration because it is the smallest next code step.

**B1 — Counterexample.** LMCache explicitly deprecates in-process operation and recommends MP for new deployments. A short path to a patch is not necessarily a good long-term deployment choice. [S1]

**A2 — Revision.** Separate maintenance from architecture: finish the inexpensive diagnostic proof, but direct new native deployment investigation to the existing MP adapter. Do not rewrite the connector or import vLLM by default. [S3]

**B2 — Remaining gate.** At `a5ad0a5`, ATOM MP requires `PP=DCP=PCP=DP=1`, no DP attention, exactly one server, and a compatible attention-published tensor map. Other integrations' support for DCP or multiple servers is not ATOM support. Select a model/layout and owner first; if they require an excluded topology, record a compatibility gap rather than removing its guard. [S3, S7]

### 4. Ask for a model benchmark or isolate the cheaper question first?

**A1 — Proposal.** Ask an AMD volunteer to deploy a model and run cold/warm requests.

**B1 — Counterexample.** The second request can be satisfied by HBM, so a faster answer need not prove external reuse. ATOM already has a model-free GPU test that stores deterministic K/V and scale tensors to `LocalDiskBackend`, removes the GPU values, and checks exact restoration. It accepts supported CUDA or ROCm environments, reducing the first test's access burden. [S6]

**A2 — Revision.** Use a ladder: build/package contract inspection → existing tensor round-trip → owner-approved production host-DRAM smoke → one pinned AMD model cell with verified HBM eviction and attributable host reload. A CUDA result is useful shared-path evidence, not AMD qualification. [S6, S8]

**B2 — Remaining gate.** The disk test explicitly synchronizes the producer on the host before storage. It cannot prove production asynchronous stream ordering, native scheduler behavior, DRAM-specific behavior or model accuracy. Report exactly its narrower claim; require a separate production-path experiment for those properties. [S6]

### 5. Add another fence or collaborate with the existing owner?

**A1 — Proposal.** Independently implement stronger stream-fence and failure tests as the next contribution.

**B1 — Counterexample.** PR #2339 already has an author-reported AMD production smoke and substantial review, including revisions after thread-affinity and mixed-load/save concerns. Repeating that work or reposting old review concerns would add burden. The report's measured commit and the current PR head are different identifiers. [S5, S10]

**A2 — Revision.** Ask for the smallest reusable smoke script and the revision/configuration its owner recommends reviewing. Reconstruct an evidence table ourselves: reported result → commit → exact call path → model/precision/topology → unresolved claim. Treat other reviewers' assertions as leads until checked against the selected head, not as our own verified findings.

**B2 — Remaining gate.** At this inspection #2339 is open and reports a merge conflict. An earlier successful run is not a certificate for current HEAD or our separate diagnostic base. Do not transplant the patch, remove stream guards or request broad hardware certification without an agreed reference revision. [S5]

### 6. Maximize hits or maximize useful work?

**A1 — Proposal.** Add more storage tiers, prefetch, compression or more aggressive reuse to raise cache-hit rate.

**B1 — Counterexample.** Cache movement can consume more critical-path time than recomputation saves, and improvements to first-token latency can coexist with worse decoding latency. Approximate/context-mixing mechanisms additionally change the output contract. Paper speedups are not local predictions. [P1, P2, P3]

**A2 — Revision.** Begin with exact-prefix, opaque-byte reuse. Charge lookup, unoverlapped transfer, staging, fill/eviction and queueing costs; report correct requests meeting declared first-token and per-token latency targets under fixed resource budgets. Retain an HBM-fit workload and no-reuse workload as controls. Investigate compression or non-prefix fusion only after observing the bottleneck and defining a separate quality gate.

**B2 — Remaining gate.** Our data does not establish a performance benefit, target workload or numerical tolerances yet. Three paired repetitions can screen for gross instability but are not enough for a tail-latency claim. Select sample size/repetition and warm-up rules before the performance phase, after correctness and attribution work.

## Architecture contracts to keep explicit

ATOM owns scheduling, operation identity, concrete GPU allocation/lifetime and the physical cache layout. LMCache owns its external storage orchestration. A stored token-prefix identifier must not authorize incompatible model, revision, layout, precision, adapter or sharing-domain bytes. Audit the namespace already present rather than inventing duplicate hot-path metadata. [S2, S3, P1]

A completion event is not one interchangeable boolean: source-safe, visible in the external tier, reload-complete and all-ranks-complete answer different questions. Failure or cancellation must not release memory while a transfer can still touch it. Synchronous byte tests and constructor mocks are necessary evidence at their own boundaries, not substitutes for that lifecycle proof. [S2, S5, S6]

Do not apply dense assumptions to a recurrent-state model. The inspected native selector refuses some linear/GDN layouts because it cannot restore all required state. A future stateful cell must preserve compatible attention and recurrent state at the same legal boundary. [S2]

## Next actions and stop conditions

1. Read the corrected CPU run and retain native failures/skips instead of relaxing the gate. Then review the class-only diagnostic trade-off and prepare only the small production/test diff, not this downstream apparatus, for possible upstream review.
2. Complete a native-MP compatibility card using existing source and wheel validation. Record required model/layout, exact ATOM/LMCache binary pair, server lifetime and supported topology; do not start a server or assume that the build-only check proves GPU availability.
3. Use the [community validation plan](COMMUNITY_VALIDATION.md) to request one bounded inspection first. No upstream request has been posted from this work.

Stop when a result cannot be attributed to the intended tier, dependencies differ between comparison arms, a test merely skips, an applicable memory-lifetime question is unresolved, or another contributor already owns the fix. Correct-but-uneconomic caching and a well-supported decision not to add a feature are useful outcomes.

## Sources

Repository sources are pinned to the inspected commit. Documentation and discussions are snapshots read 2026-09-24 and must be refreshed before submitting or executing a new cell.

- **S1:** [LMCache deprecation and MP direction](https://docs.lmcache.ai/legacy/index.html).
- **S2:** [ATOM native offload architecture](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/README.md).
- **S3:** [Native MP adapter and guards](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/atom/kv_transfer/offload/mp/backend.py).
- **S4:** [ATOM vLLM LMCache recipe](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/recipes/atom_vllm/LMCache-KV-Cache-Offload.md).
- **S5:** [Dense save-fence PR #2339](https://github.com/ROCm/ATOM/pull/2339), observed head `6aefe2ee89e75f57e117479068f8d06a6eeb0092`; GPU smoke reported at `c6af1092f409ebfffd809ab8f8f0549afe136211`. Neither reproduced here.
- **S6:** [Existing model-free GPU/disk round-trip test](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/tests/test_lmcache_offload_gpu_disk_e2e.py).
- **S7:** [MP configuration reference](https://docs.lmcache.ai/mp/configuration.html); vLLM-specific options are not automatically native ATOM options.
- **S8:** [Existing build-only ATOM wheel validator](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/.github/scripts/validate_lmcache_wheel_for_atom.py). It overrides the CUDA-availability predicate for import checks; it does not touch/test a GPU.
- **S9:** [Native CPU runner](https://github.com/ROCm/ATOM/blob/a5ad0a5086af9042fd23823392f59781d4806894/.github/scripts/run_unit_tests.sh).
- **S10:** [Author's thread-affinity revision explanation](https://github.com/ROCm/ATOM/pull/2339#discussion_r4070871991) and [mixed-load/save revision](https://github.com/ROCm/ATOM/pull/2339#discussion_r4070871722); later reviews must be reconciled against their actual reviewed head.
- **E1:** [First CPU experiment](https://github.com/kvnloo/ATOM/actions/runs/36024518922); overall gate not met, focused diagnostic evidence retained. [Evidence record](CPU_EVIDENCE.md).
- **E2:** [Environment fix](https://github.com/kvnloo/ATOM/commit/e68e996fe9262a851df5434902173babadedb759) and [corrected run](https://github.com/kvnloo/ATOM/actions/runs/36028507670).
- **P1:** [LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Inference](https://arxiv.org/abs/2510.09665), 2025. Mechanism used here: external cache orchestration and engine/connector separation, not its reported maximum speedup.
- **P2:** [DistServe](https://arxiv.org/abs/2401.09670), 2024. Mechanism used here: evaluate serving capacity under both prefill and decode latency constraints, including communication costs.
- **P3:** [KV Cache Offloading for Context-Intensive Tasks](https://arxiv.org/abs/2604.08426), 2026. Its findings concern evaluated approximate offloading methods; they are not evidence that exact-byte ATOM offload loses accuracy. Used only to motivate a separate quality gate when considering approximation.
