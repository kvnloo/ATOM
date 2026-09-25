# LMCache wheel-pin preflight: verified contribution

**Implemented and CPU-tested downstream; no upstream PR or comment posted for this change.**

[Isolated two-file diff](https://github.com/kvnloo/ATOM/compare/9cb1dffaf8fc3ca5892f337938b3120aa8363bd3...9cc72463399bca340273ad4a7a3fc158de78ab62) · [Passing hosted run](https://github.com/kvnloo/ATOM/actions/runs/36096439800)

## Observed defect and bounded fix

At base `9cb1dffaf8fc3ca5892f337938b3120aa8363bd3`, `.github/scripts/bump_lmcache_wheel_pin.py` reads, validates and writes each Dockerfile before examining the next. If the later Dockerfile is absent or has a missing/duplicate pin ARG, the command fails after changing the first file. The tests reproduce that partial working-tree mutation.

The calling wheel workflow uses `set -e` and runs this script before its commit/push steps. This finding does **not** demonstrate that malformed pins are published or deployed; its consequence is an avoidably partially edited checkout on an input-validation/read failure.

The fix adds five lines: stage each validated replacement in memory, then write only after every input passes. Existing argument validation, error messages, successful output and filename order remain unchanged. No actual Dockerfile pin, release workflow or inference code is changed.

This is preflight, **not a multi-file atomic transaction**. Write-time I/O failures, process crashes and concurrent edits are not rolled back. Adding transaction machinery is outside this small fix.

## Source identity and scope

- Base: `9cb1dffaf8fc3ca5892f337938b3120aa8363bd3`.
- Candidate: `9cc72463399bca340273ad4a7a3fc158de78ab62`, branch `fix/lmcache-pin-preflight`.
- Original script Git blob: `7c3661444f5e1f4844223c4c1fcc0e87231b6efa`.
- Candidate script Git blob: `650d167b2d71a1e70e496fef78ec9828f0ae13ce`.
- Test Git blob: `a1b13e286b0ed1f9af9e23bae2ae8743d031305a`.
- Exactly two changed files: five script additions and `tests/test_bump_lmcache_wheel_pin.py` (103 lines, nine parametrized cases). The experiment workflow and this report stay on the separate research branch.

## Actual evidence

The tests execute the real standalone CLI in subprocesses against temporary synthetic Dockerfiles. They do not replace its parser or file I/O. `--noconftest` bypasses unrelated ATOM engine fixtures; this is not a full native-suite result.

| Arm | Passed | Failed | Skipped/errors |
|---|---:|---:|---:|
| Original script, new tests | 4 | 5 | 0 |
| Candidate, identical tests | 9 | 0 | 0 |
| Restore original script | 4 | 5 | 0 |

Five regression cases cover a missing/duplicate image or checksum ARG in the second file and a missing second file. Every failure is the intended unchanged-bytes assertion, not setup or collection failure. Four controls cover valid default/explicit-order updates (each run twice for idempotence) and invalid image/digest arguments. Successful updates preserve all unrelated content.

This sequence passed locally on Python 3.13.5 using hash-verified source/test files, and in a full checkout on hosted Python 3.12.14. Both used pytest 9.0.2; environments are recorded separately, not claimed identical across machines.

Hosted Black, Ruff and `git diff --check` exited zero; before/after dependency inventories are identical. Black 26.5.1 reported a Python-target-version warning while leaving both files unchanged; Ruff was 0.16.9. No formatting bypass or weaker regression assertion was introduced.

[Artifact 10846909628](https://github.com/kvnloo/ATOM/actions/runs/36096439800/artifacts/10846909628), archive SHA-256 `c09cb1b18ad9562ee280fdcaeeb7dee0a687dee39f5edcfb0dbdd676a852652e`, was downloaded and independently checked against the actual JUnit case identities, assertion messages and dependency inventories. Retention is 14 days. Receipt: `FOCUSED_CLI_GATE_PASSED`.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --noconftest \
  tests/test_bump_lmcache_wheel_pin.py -q
```

No full ATOM suite, Docker build, package publishing, server or GPU test ran. No deployed pins or fork `main` changed.

## Upstream draft — not posted

**Title:** `fix(ci): validate all LMCache Dockerfile pins before writing`

The wheel-pin updater currently changes the first Dockerfile before discovering an invalid or missing second input. This small change validates and prepares every replacement before the write loop, so those failures leave both files untouched.

Adds real CLI regression tests for later-file layout/read failures, plus success, idempotence and invalid-input controls. Original/candidate/restored results are 5 failed + 4 passed / 9 passed / 5 failed + 4 passed; hosted evidence is linked above. No new framework or runtime dependencies are included. This does not promise rollback on write-time failures.

AI-assisted implementation and evidence review. Full ATOM suite, Docker builds and GPU testing were not run.
