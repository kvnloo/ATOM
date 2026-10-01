# ATOM–LMCache RFC closure kit

Parent: [RFC #1](https://github.com/kvnloo/ATOM/issues/1).

## Status

**All work that can be completed without access to a compatible AMD environment is prepared.**

That does not mean unexecuted hardware evidence is satisfied. It means the remaining evidence is reduced to two bounded external actions with machine-checkable receipts; nobody needs to reconstruct the RFC, design a benchmark, or invent an evidence format.

## What is already externally demonstrated

- Merged upstream [#2250](https://github.com/ROCm/ATOM/pull/2250) contains native DSv4 checkpoints with LMCache MP. Its owner reported real 8×MI355X TP8 cold / restore / empty-LMCache controls, hundreds of completed retrieves, hundreds of thousands of restored tokens, zero load failures and task-level accuracy checks. This is owner-generated hardware evidence, not our independent run.
- Merged [#2339](https://github.com/ROCm/ATOM/pull/2339) owns the dense producer fence. Its one-GPU smoke was author-run historically and its exact acceptance contract was reviewed by the author.

## Tier A — independent dense smoke

Purpose: independently reproduce the bounded one-GPU connector/fence cell.

Cost: one compatible AMD GPU, no model, no server, one 10-minute outer deadline, LMCache 0.4.5, exact reviewed source/script pins.

~~~bash
export PR_SRC=/path/to/clean/e9be221f-checkout
export SMOKE_FILE=/path/to/reviewed/pr2339_gpu_smoke.py
export SMOKE_GPU=0
bash experiments/lmcache_qualification/run_dense_host_smoke.sh
~~~

The wrapper verifies source SHA, clean checkout, smoke SHA-256, LMCache version, import origin and exactly one visible ROCm GPU. It runs only the reviewed smoke and retains stdout/stderr/result/exit.

Then the machine owner classifies diagnostics and cleanup explicitly:

~~~bash
python experiments/lmcache_qualification/qualification.py dense-validate \
  --run-dir /tmp/atom-lmcache-dense.XXXXXXXX \
  --diagnostic-review KNOWN_ONLY \
  --cleanup PASS
~~~

If cleanup was not checked, record UNKNOWN. A valid transfer does not become a cleanup claim.

## Tier B — independent native-MP correctness triplet

Purpose: reproduce the already demonstrated native-MP restore without asking a volunteer to replay the whole four-cell matrix.

The smallest hardware triplet is:

1. cold/populate — fresh ATOM, empty LMCache;
2. restore — fresh ATOM/HBM, retained LMCache from arm 1;
3. recompute control — fresh ATOM/HBM, empty LMCache again.

This already supplies empty-tier, retained-tier, fresh-HBM, positive-restore and same-build recompute discriminators. HBM-hit and synthetic missing-object controls remain useful, but they are already source/CPU-qualified and are not required merely to prove the external restore again.

Initialize the receipt before running:

~~~bash
python experiments/lmcache_qualification/qualification.py mp-init \
  --out trial-1.json \
  --evidence-owner '<name or handle>' \
  --atom-sha "$(git rev-parse HEAD)" \
  --lmcache-identity '<wheel/image/source identity>' \
  --model-revision '<model revision>' \
  --tokenizer-revision '<tokenizer revision>' \
  --gpu '8x MI355X' \
  --topology 'TP8' \
  --corpus-sha256 '<sha256>' \
  --correctness-rule '<frozen evaluator + tolerance>'
~~~

Fill the three arm results, then:

~~~bash
python experiments/lmcache_qualification/qualification.py mp-validate --receipt trial-1.json
~~~

The validator does not decide model quality. It rejects incomplete evidence: missing identity, zero restored tokens, zero completed retrieves, nonzero load failures, mismatched request counts, missing correctness result, missing wall time, or unexpected errors.

## Simplified performance burden

Correctness and economics are separate.

- One valid triplet is enough to close the independent correctness reproduction without making a speed claim.
- Three valid triplets are enough for a directional engineering decision about whether another optimization pass is worth pursuing.
- Five valid triplets remain the minimum before treating the packet as a reportable first-pass performance result.
- Mixed-sign or high-variance results are a valid stop condition; report inconclusive rather than extending indefinitely.

Hardware volunteers do not need to re-run parser checks, timeout characterization, TP/generation unit invariants, synthetic missing-object injection, missing-vs-zero profile checks, wheel-pin behavior, diagnostic formatting or the HBM-hit no-load branch. Those are cheaper source/CPU questions already answered elsewhere in the RFC.

## One return bundle

Return only: receipt/preflight JSON, qualification JSON, stdout/stderr, exit code, exact source/build identities, and cleanup = PASS | FAIL | UNKNOWN. No full environment dump, credentials, prompts, model weights, Docker inspection, device reset or production access is requested.

## Completion semantics

Track two states separately:

- **Preparation completeness:** source review, CPU evidence, upstream patches, owner map, runnable packets, validators and stop rules. This can reach 100% without owning AMD hardware.
- **Empirical evidence completeness:** only externally executed hardware receipts count.

Do not collapse them into one percentage. Once the closure-kit CPU tests are green, this RFC is **100% prepared for external closure**; remaining empirical work is a handoff, not unfinished experiment design.

_AI-assisted consolidation and tooling. No unexecuted hardware result is claimed._
