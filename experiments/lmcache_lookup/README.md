# Dense lookup initialization: downstream CPU experiment

Tracker: [RFC #1](https://github.com/kvnloo/ATOM/issues/1).

This directory is experiment infrastructure, not a proposed upstream framework.
It generates a small production/test patch only after running comparisons in
disposable worktrees. The branch leaves production source and fork `main`
unchanged. AI-assisted source analysis, test design and drafting; recorded runs,
not this document, establish execution results.

## Question

Can the two existing dense lookup-startup warnings identify an empty exception
without printing arbitrary exception payloads or changing fallback/role behavior?

The candidate retains each existing component prefix and warning level, replacing
`%s` formatting of the exception object with `error_type=%s` and its class name.
A valid lookup-server factory return of `None` remains silent and does not disable
configured loads. Construction is not a readiness or actual-reuse assertion.

## Pinned source

- ATOM: `a5ad0a5086af9042fd23823392f59781d4806894`.
- Dense connector blob: `3b3d69581315071f308ec9b81b00cb06b641d520`.
- Dependency contract inspected: [LMCache lookup factory at 05fc77a](https://github.com/LMCache/LMCache/blob/05fc77a0a7ababd9a7f2e343a771bc4bbc5b65cb/lmcache/v1/lookup_client/factory.py).

The runner rejects a different production blob or unexpected replacement count.
It never fetches a moving upstream branch during the comparison. CPU dependencies
are installed once and held constant across arms; the artifact records exact
installed versions before and after. A later installation is a new environment,
not automatically the same experiment.

## Comparison

1. Run existing dense tests against pristine production.
2. Add the constructor tests while keeping production unchanged.
3. Apply only the two warning changes and rerun identical tests in a fresh process.
4. Repeat the candidate probe; run existing dense tests and the repository's
   native CPU runner on baseline/candidate separately.
5. Restore original production in the disposable candidate while retaining tests;
   require the diagnostic assertions to fail again.

The declared new-test matrix is 29 cases: 16 exception cases across two components,
four roles and two messages; eight successful constructions; four valid non-hosting
workers; and one ordinary miss. These are expected collected cases, not claimed
passes. Control and sensitivity must fail at the explicit missing-class assertion,
not fixture setup, import, collection, or some unrelated error.

Tests invoke real ATOM constructors/worker registration. Only external lookup,
GPU-layout and engine-construction boundaries are replaced. Factory-invocation
assertions prove the intended call was reached. Module patches are fixture-scoped,
ATOM modules are not reloaded, and worker executors are closed. Existing role,
validation, partial-retrieval and operation-lifetime tests are reused rather than
copied into the new matrix.

The new test file is formatted with the pinned checkout's Black settings before
the identical bytes are copied to both comparison arms. Production code is not
autoformatted to hide unrelated changes. Black/Ruff and whitespace checks must
pass for the generated patch.

## Execute

Use a disposable CPU environment with the dependencies from the pinned
`.github/workflows/pre-checks.yaml`, plus Black and Ruff. The fork-only workflow
installs that environment and retains installation logs even when setup fails.

```bash
python experiments/lmcache_lookup/run.py
```

`QUALIFICATION_OUT` may name a fresh absolute output directory; it must not already
exist. Do not run this in a shared live deployment. The driver writes only its own
temporary worktrees and result directory, never resets or pushes a branch, and
uses fresh Python processes with model downloads disabled during tests.

The hosted workflow is limited to this fork and this work branch. It has
`contents: read`, no deployment/model credentials and no self-hosted/GPU jobs.
It does not modify the native runner's plugin/real-server exclusions.

## Outputs and interpretation

The artifact contains command logs/exit codes, JUnit reports, source and patch
hashes, dependency inventories, the formatted new tests and `candidate.patch`.
Inspect `receipt.json` before drawing conclusions. `CPU_GATE_PASSED` requires the
expected red/green/red sequence, unchanged dependencies, candidate probes passing
both alone and in the native suite, no missing coverage/new skips/new failures,
and successful formatting/lint checks. Changed details of a pre-existing failure
also block automatic promotion and require inspection.

A green CPU gate proves only the mocked-boundary diagnostic contract. It does not
qualify a real LMCache installation, GPU kernels, cache identity across deployments,
host publication/reload, model output or performance. No automatic upstream PR,
merge or rollout follows. Environment failures and timeouts remain visible.

## Sibling sweep and hardware boundary

The same worker warning text also appears in
`atom/kv_transfer/offload/hybrid/m3/connector.py` and
`atom/kv_transfer/offload/hybrid/dsv4/connector.py`. Those are follow-up inspection
leads, not evidence that their complete startup/state contracts match dense.
This experiment does not change them or create a shared diagnostics framework.

[ROCm/ATOM#2339](https://github.com/ROCm/ATOM/pull/2339) remains separately owned
save-stream correctness work. Its applicable lifetime gate must be resolved before
certifying a real dense host-reload path. The initial AMD machine, model and
workload still need selection; see RFC #1 for the hardware acceptance sequence.
