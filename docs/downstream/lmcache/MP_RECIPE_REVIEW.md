# MP recipe review: one argument, one stale pointer

Downstream draft, 2026-09-24. **Not posted upstream; no parser or server execution claimed.** Full analysis: [MP compatibility triage](MP_COMPATIBILITY_TRIAGE.md).

## Target and verified source chain

- Discussion: [ROCm/ATOM #2250](https://github.com/ROCm/ATOM/pull/2250), owned by `yhl-amd`.
- Inspected PR head: `9c64bea07eeb16f75c746787490522abf0efbaec`.
- Existing guide: [parent offload README, MP section](https://github.com/ROCm/ATOM/blob/9c64bea07eeb16f75c746787490522abf0efbaec/atom/kv_transfer/offload/README.md#lmcache-multiprocess-lmcache_mp). Do not create another guide at the obsolete path merely to match the PR description.
- Matching LMCache source: `05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb`.
- [ServerCommand.add_arguments](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/cli/commands/server.py) composes [add_storage_manager_args](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/v1/distributed/config.py), which makes `--eviction-policy` required and accepts `LRU`.

The existing launch example supplies host, port, chunk size, null-block marker, group separation, transfer mode and memory size, but omits the required policy. With the full argument set registered, argument parsing rejects that invocation before a server is launched. This conclusion comes from source composition; it is not an observed CLI run.

## Proposed documentation-only change

The only file-content change proposed for the author's branch is:

```diff
-  --supported-transfer-mode lmcache_driven --l1-size-gb 64
+  --supported-transfer-mode lmcache_driven --l1-size-gb 64 --eviction-policy LRU
```

Separately, update the PR description's `atom/kv_transfer/offload/mp/README.md` pointer to the existing parent README's MP section. A contributor cannot fix the author's PR description by changing a repository file.

`LRU` is an explicit choice for this example, not a change to LMCache defaults or an optimization claim. The existing 64 GB budget is shown only to identify the minimal diff; it is not a recommendation to allocate memory on a collaborator's machine. **No server-start command is to be executed as part of this docs validation.**

## Parser-only acceptance plan

Use an isolated environment in which the pinned full LMCache package and compatible binary dependencies can be imported. This check requires no model, no GPU transfer and no running server, but import/backend-selection requirements may still block a CPU-only environment. Report that as an environment block; do not quietly replace the parser with a mock.

1. Record the exact ATOM README SHA, LMCache source/installed version and dependency inventory. Read the actual first bash block beneath `### Running the MP server`; tokenize it with `shlex` after joining shell continuation lines. Require its command prefix to be `lmcache server`.
2. Construct an `argparse.ArgumentParser` and call the real `ServerCommand().add_arguments(parser)`. **Do not call `execute()`.** That method would start services and is outside the test.
3. Verify the composed parser actually contains the expected server and storage arguments, including `--eviction-policy`, `--null-block-id`, `--separate-object-groups`, `--supported-transfer-mode` and `--l1-size-gb`. `ServerCommand.add_arguments` catches `ImportError`; an incompletely registered parser is an invalid environment, not evidence for the recipe bug.
4. Parse the original example's arguments. Require exit code 2 and a required-argument error identifying `--eviction-policy`. An unrelated unrecognized-option or dependency error does not satisfy this control.
5. Add only `--eviction-policy LRU` and parse again. Require success and verify `eviction_policy == 'LRU'`, `null_block_id == -1`, group separation remains enabled, and transfer mode/chunk size/memory size match the example.
6. Remove only the added argument and confirm the original rejection returns. Retain stdout/stderr and exit codes. Do not allocate a cache, construct a storage manager, download a model, modify a live service or claim GPU correctness.
7. Recheck the latest PR before preparing a contribution. If the example is already corrected, stop rather than submit a duplicate.

The existing ATOM wheel validator checks a narrower contract: imports and special MP server-flag parsing. It does not compose the full storage parser or validate this README invocation. A new permanent test is optional and should be discussed only if it can reuse the existing checks without introducing a large documentation-test framework.

## Review comment — NOT POSTED

> While tracing the native MP path, could we add `--eviction-policy LRU` to the existing `Running the MP server` example?
>
> In the pinned LMCache `05fc77a`, `ServerCommand.add_arguments()` includes `add_storage_manager_args()`, which requires `--eviction-policy`; the command in this branch currently omits it. This is a source-level finding—I haven't run the full CLI or GPU path.
>
> I also noticed the PR description still points to `mp/README.md`, while the guide is now in the parent offload README. Would a one-line recipe correction plus updating that pointer be the right scope? I'd keep the topology, checkpoint and lifetime design unchanged.
>
> AI-assisted source review and drafting; no GPU results claimed.

No request for a benchmark is needed to answer this question. If the owner agrees, the next missing evidence is the small real-parser comparison, not a new AMD hardware campaign.
