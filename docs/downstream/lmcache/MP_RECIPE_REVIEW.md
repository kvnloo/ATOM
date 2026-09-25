# MP recipe review: one argument, one stale pointer

**The real server-argument parser comparison passed.** This supersedes the earlier queued/source-only status. No LMCache server, cache allocation, model or GPU test ran. The [initial question](https://github.com/ROCm/ATOM/pull/2250#issuecomment-5822156319) is already posted; do not duplicate it. Full architecture analysis remains in [MP compatibility triage](MP_COMPATIBILITY_TRIAGE.md).

## Pinned target and minimal change

- Author discussion: [ROCm/ATOM #2250](https://github.com/ROCm/ATOM/pull/2250), `yhl-amd`, branch `feat/dsv4-lmcache-mp`.
- ATOM recipe revision: `9c64bea07eeb16f75c746787490522abf0efbaec`.
- Matching LMCache parser/build source: `05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb`.
- Existing guide: [parent offload README, MP section](https://github.com/ROCm/ATOM/blob/9c64bea07eeb16f75c746787490522abf0efbaec/atom/kv_transfer/offload/README.md#lmcache-multiprocess-lmcache_mp). The PR description still points to the obsolete `mp/README.md` at the last source check; updating that description is an author edit, not a new repository file.

[Prepared unified patch](mp-recipe-eviction-policy.patch):

```diff
-  --supported-transfer-mode lmcache_driven --l1-size-gb 64
+  --supported-transfer-mode lmcache_driven --l1-size-gb 64 --eviction-policy LRU
```

This is one insertion and one deletion in one README. `LRU` is an explicit choice for this example, not a new runtime default or a performance recommendation. The existing 64 GB argument was parsed only; that cache was never allocated.

The upstream contribution contains no experiment framework, topology change or connector change. Do not submit this downstream research branch against `main`. The patch belongs on the author's feature branch, or on refreshed main after that branch merges if the omission is still present. Stop when the author has already fixed it.

## Actual execution: original → candidate → restored

**[Passing run 36094203732](https://github.com/kvnloo/ATOM/actions/runs/36094203732)**, experiment commit `bfe589c8085facd487d58d2a2123f611e76d70f6`; job `107942872996`.

The unchanged [probe](https://github.com/kvnloo/ATOM/blob/bfe589c8085facd487d58d2a2123f611e76d70f6/experiments/lmcache_mp_recipe/probe.py) extracts the exact first bash command under `### Running the MP server`, imports the real `ServerCommand`, calls `add_arguments()` on a real argument parser, and parses the command's arguments. It does not invoke CLI dispatch or `ServerCommand.execute()`.

| Comparison arm | Observed parser exit | Observed result |
|---|---:|---|
| Original example | 2 | Required-argument error names only `--eviction-policy`. |
| Add only `--eviction-policy LRU` | 0 | Successful parsing; documented settings preserved. |
| Restore original arguments | 2 | The same missing-policy rejection returns. |

The candidate retained host `127.0.0.1`, port `5555`, chunk size `256`, null block `-1`, separate object groups enabled, transfer mode `lmcache_driven`, and memory-size argument `64.0`. The new policy value is `LRU`.

The receipt reports `REAL_PARSER_GATE_PASSED`, no parser replacements, complete argument registration, unchanged tracked input sources, and unchanged dependencies across all three arms. Module-origin checks cover the real server, distributed-storage, multiprocess and observability configuration modules from the pinned checkout.

After downloading the artifact, a separate local check verified its archive hash, the three actual exit codes, both stderr rejection reasons, the exact two added argument tokens, the selected parsed values, and byte-identical before/after dependency inventories. It also verified that the staged patch and the experiment-generated patch change exactly the same two README lines. Their archive formatting differs, so their complete-file hashes differ; do not call the patch files byte-identical.

### Retained evidence

- [Artifact 10846468941](https://github.com/kvnloo/ATOM/actions/runs/36094203732/artifacts/10846468941), `lmcache-mp-recipe-36094203732-1`; archive SHA-256 `fd1f2ce7cd9a2f9dfc67745e3a2dbade6f2fb0b8fb6228ad5de255edfafc9381`.
- Contents: actual argument vectors, full parser stderr, parsed namespace, receipt, candidate patch, before/after dependencies, install log, native-build log and probe log. Workflow retention is 14 days; the source and this summary remain downstream.
- ATOM README SHA-256: `bf405d4f793c2d492f2011d628629e2dc5f2f6e1748852375e37ec1396a0a20e`; Git blob `9727a8e3de3418e4b82c700d8c9e9c438a66e183`.
- LMCache server source SHA-256: `749621e3c0ba4cca8cc722a22322d0ef833deb5aacb36368a9f212f65a3c9d7d`.
- Prepared patch SHA-256: `16638d3d5b871ddac2139d97864601670c51240bc04b3bf1d5040d448507ccc5`.
- Generated patch SHA-256: `1764b342bc1265c2d396d8e93d13d6b5deffd0679eb9be72ac83418669e5abe0`.

## Preserve the first attempt's failure

[Run 36075462321](https://github.com/kvnloo/ATOM/actions/runs/36075462321), job `107885553480`, installed CPU dependencies but lacked the compiled `lmcache.lmcache_native` extension. LMCache fell back to CLI-only initialization, and server argument registration was incomplete. The receipt correctly reported **`BLOCKED_ENVIRONMENT` at `PARSER_REGISTRATION`, with zero comparison arms executed**. It did not demonstrate the missing-policy error.

[Artifact 10841834916](https://github.com/kvnloo/ATOM/actions/runs/36075462321/artifacts/10841834916), archive SHA-256 `8801c226a9f54a413129fabc02993c2ed7562526d40d9b5ada6b83947db10515`, was downloaded and its digest and empty comparison results were independently checked.

The correction was confined to the [downstream workflow](https://github.com/kvnloo/ATOM/commit/bfe589c8085facd487d58d2a2123f611e76d70f6): build the unmodified pinned package's common CPU C++ extensions with `NO_GPU_EXT=1`, keeping native extensions enabled, before running the unchanged probe. The build runs with `MAX_JOBS=2`, retains extension checksums, and checks that tracked source is unchanged. No import stub or replacement parser was introduced, and no production source or dependency pin was changed to make the test pass.

The package's [build-profile contract](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/setup_extensions/build_profiles/__init__.py) distinguishes `NO_GPU_EXT` from `NO_NATIVE_EXT` and its legacy `NO_CUDA_EXT` alias. Disabling all native extensions would reproduce the missing dependency rather than solve it. This is a correction to our experiment environment, not a new ATOM defect or an additional upstream change request.

## Source chain and scope

[ServerCommand.add_arguments](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/cli/commands/server.py) composes [add_storage_manager_args](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/v1/distributed/config.py), which requires `--eviction-policy` and accepts `LRU`. The source-level finding is now reproduced at that real parser boundary.

The existing ATOM wheel validator covers a different, narrower import/special-server-flag contract and is not changed here. The CPU common extensions were built to make real imports available; this does not qualify a ROCm wheel, GPU kernels, MP server startup, storage/retrieval, model output or runtime memory budgets.

The source inputs and parser acceptance assertions stayed fixed across the environment correction. Installed packages were held constant within the successful run; no claim of identical complete environments across the failed and successful runs is made. All execution occurred in a fork-only hosted CPU job with read-only repository credentials. No server or GPU time is requested from maintainers for this documentation correction.

## Handoff

The next upstream message should contain the one-line patch, the passing real-parser evidence and its scope, not this full research record. The original question is already posted. Refresh #2250 before sending evidence and stop if the author has already applied the change. Applying the patch or editing the author's PR description remains separate from sharing the verified proposal.

AI-assisted source analysis, experiment preparation and evidence review. Hardware execution: not run.
