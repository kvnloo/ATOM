# Dense lookup diagnostic CPU evidence

Evidence snapshot: 2026-09-24. Parent [RFC #1](https://github.com/kvnloo/ATOM/issues/1). **Current result: run 2 passed the declared CPU gate.** Run 1's environment failure remains recorded below. Neither run qualifies a real LMCache binary or GPU path.

## Run 1: focused evidence obtained, overall gate NOT met

- [Workflow run 36024518922](https://github.com/kvnloo/ATOM/actions/runs/36024518922), job `107717531348`, attempt 1.
- Experiment commit: `dd54b080b6bd8f03c1c6acec268f184005115447`.
- Production base: `a5ad0a5086af9042fd23823392f59781d4806894`.
- Artifact ID: `10818063190`; name `lmcache-lookup-cpu-36024518922-1`. Artifacts expire after 14 days under this workflow; this summary preserves the findings, not the full artifact.
- `receipt.json` status: `CPU_GATE_NOT_MET`.

Counts below were read from the retained JUnit reports, not inferred from the workflow color:

| Arm / check | Observed result |
|---|---|
| Pristine existing dense tests | 49 passed |
| Test-only diagnostic control | 16 failed at the intended missing-class assertion; 13 passed |
| Candidate diagnostic probe | 29 passed |
| Candidate probe, fresh-process repeat | 29 passed |
| Candidate existing dense tests | 49 passed |
| Restore original diagnostic behavior, keep new tests | 16 intended failures; 13 passed |
| Black / Ruff / whitespace check | Each exited 0 |
| Production import-origin checks | Baseline, control and candidate each exited 0 |
| Dependency inventory within run | Before/after unchanged |
| Native baseline and candidate | Both exited 1 before pytest could run; no native JUnit reports |

The native log in both arms was:

```text
/opt/hostedtoolcache/Python/3.12.14/x64/bin/python: No module named pytest
```

**Classification:** experiment environment defect and missing full-suite coverage. It is not an ATOM product regression, nor a pass-with-skips result. The focused red/green/red sequence supplied evidence for the tested warning contract, but the overall CPU acceptance gate was unmet at that checkpoint.

### Retained identities

```text
base connector Git blob:
3b3d69581315071f308ec9b81b00cb06b641d520
candidate connector Git blob:
adacd2cbdf66dfc38cad3492f24fafabd5c5193b
formatted probe SHA-256:
cfc544f1500fa7c29fb8be4f7d884142b9189711ab086179cdfad582b6d53340
candidate.patch SHA-256:
b7cd2ebba012417b2419ee41c725c34ff880d5e2e7bf464a7483d3dfeb35a689
```

The patch changes only the two optional-lookup warning handlers plus the new constructor/registration tests. It remains an artifact generated in disposable worktrees, not a production-source commit on this branch.

## Run 2: complete CPU gate passed

[Commit e68e996f](https://github.com/kvnloo/ATOM/commit/e68e996fe9262a851df5434902173babadedb759) activates the already-installed virtual environment before starting the driver. The repository's native shell runner resolves `python` through `PATH`; launching only `.qualification-venv/bin/python` did not configure that child process.

- [Corrected run 36028507670](https://github.com/kvnloo/ATOM/actions/runs/36028507670), job `107731038762`, attempt 1, completed successfully.
- Experiment commit: `e68e996fe9262a851df5434902173babadedb759`.
- Same pinned production base as run 1; dependencies were held fixed within this run. This is not a claim of identical installations across runs.
- [Artifact 10822692041](https://github.com/kvnloo/ATOM/actions/runs/36028507670/artifacts/10822692041), `lmcache-lookup-cpu-36028507670-1`, 512,411 bytes.
- Downloaded archive SHA-256 independently matched the workflow's digest: `7cd70e971e568496af0fbd768cc8b3f4c826f7083319bf82f81fca5d9e8dfb21`.
- Receipt status: `CPU_GATE_PASSED`.

| Actual JUnit report | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| Original existing dense tests | 49 | 0 | 0 | 0 |
| Candidate existing dense tests | 49 | 0 | 0 | 0 |
| Original native suite | 6,820 | 0 | 0 | 589 |
| Candidate native suite | 6,849 | 0 | 0 | 589 |
| Test-only control | 13 | 16 | 0 | 0 |
| Candidate diagnostic probe | 29 | 0 | 0 | 0 |
| Candidate diagnostic probe, fresh process | 29 | 0 | 0 | 0 |
| Original warnings restored; tests retained | 13 | 16 | 0 | 0 |

After downloading the artifact, an independent XML comparison confirmed that every original native testcase remains present with the same status, the skipped-case sets are identical, and the only 29 added cases are the new diagnostic cases, all passing. Each control/sensitivity failure is one of the 16 declared initialization-exception cases and contains the intended `LOOKUP_DIAGNOSTIC_CLASS_MISSING` assertion. No collection/setup failures substituted for the desired regression.

Black, Ruff, whitespace and all three import-origin checks exited zero. The receipt records unchanged before/after dependencies, no new native regressions, no coverage loss and no changed failure details. The probe/production/patch hashes match the retained identities above. Native plugin/real-server exclusions were not removed; the 589 skips remain missing coverage, not successes. Do not sum repeated comparison arms as independent product coverage.

The recorded environment includes Python `3.12.14`, torch `2.14.0+cpu`, pytest `9.1.1`, Black `26.5.1`, Ruff `0.16.8` and transformers `5.16.1`; the complete installed inventory is in the artifact. This is **not** the author's LMCache `0.4.5` ROCm smoke environment, and these CPU results do not qualify PR #2339's different target revision.

## Meaning and limits

These tests invoke actual ATOM constructors and worker registration while replacing external lookup/engine/layout boundaries. They verify component/class diagnostics, payload handling for the synthetic fixture, valid non-hosting `None`, configured roles, successful construction and an ordinary miss.

They do **not** establish that class-only warnings are the preferred operator experience, that every possible secret is globally scrubbed, that the real LMCache binary works, or that AMD transfers, cache reload, model output or performance are correct. Maintainer preference and hardware qualification are separate gates. Passing the CPU gate does not automatically authorize an upstream submission or production rollout.

No upstream issue, comment or PR was posted by this experiment. Fork `main` and production source remain unchanged; only downstream experiment, workflow and research files have been committed. The separate [community GPU recipe](DENSE_HOST_SMOKE_RECIPE.md) reuses the author's smoke and remains unexecuted by us.
