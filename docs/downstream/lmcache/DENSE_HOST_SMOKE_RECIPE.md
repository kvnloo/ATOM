# Dense host-memory smoke: pinned community recipe

Status, 2026-09-24: **source reviewed; recipe statically checked; GPU execution NOT RUN by us**. Parent: [RFC #1](https://github.com/kvnloo/ATOM/issues/1). Author guidance: [NidhoggD1 on #2339](https://github.com/ROCm/ATOM/pull/2339#issuecomment-5821947101).

## One bounded claim

On one compatible AMD GPU, the real dense worker store path waits on the producer on the actual pack thread, publishes to `LocalCPUBackend`, and retrieves identical K/V and scale tensors after the destination GPU tensors are cleared. This is a connector smoke, **not** model accuracy, performance, a forced ordering-race experiment, TP quorum, failed-save retry, or complete serving-system qualification.

## Pinned inputs and separate evidence

| Input / evidence | Exact reference |
|---|---|
| ATOM target for a new run | `e9be221f637d6a7e194e0d3201dbc9ddc3119067` |
| Author-reported previous GPU run | `4a8d76bea929a8925f299f8db98f2408a20cea7d`; MI350X, one GPU, no model, LMCache `0.4.5`, ROCm `7.2.53211`, torch `2.10.0+rocm7.2.4` |
| Captured Gist snapshot | `c881bce790f14d57fa026219af2d4466c2e4a154` |
| Smoke file | `pr2339_gpu_smoke.py`; 11,672 bytes; SHA-256 `fc699dbc3465729fb8fa17593ee90c9830a28c5a7d41343a302edc43b968d342` |
| Author's environment-specific runner | `pr2339_gpu_smoke_runner.py`; 6,167 bytes; SHA-256 `daede71dd36bd6577c2b8a3e0c016151f324ab61cd8e9c9e077f7f106e57d627` |

Sources: [immutable Gist snapshot](https://gist.github.com/NidhoggD1/4768a59519b2e4a9c83e80037a21db79/c881bce790f14d57fa026219af2d4466c2e4a154), [source-capture run](https://github.com/kvnloo/ATOM/actions/runs/36064272664), [captured files and receipt](https://github.com/kvnloo/ATOM/actions/runs/36064272664/artifacts/10834758626). Artifact archive SHA-256: `1f615c5e01138b1144fab174956b88b3b3cb94d64c226ec8ade8f4df507e5c3c`; retention is 14 days. The Gist supplies durable source references.

The author's earlier report does not supply this captured file's checksum, so we have not independently matched historical executed bytes to this snapshot. Do not label the captured snapshot or the new ATOM target as hardware-reproduced. The capture job downloaded and syntax-parsed source; it did not import or execute either script.

## What the source actually exercises

The smoke builds two synthetic layers, four blocks, block size four, chunk size eight and 16 tokens. K/V payloads are opaque `uint8`; scales are `float32`. It requires fused chunk-major staging. LMCache storage/retrieval is restricted to `LocalCPUBackend`, with `max_local_cpu_size=0.01`. That setting is not a cap on total process or GPU memory.

It constructs the real codec, GPU connector and LMCache engine, then manually attaches them to `DenseOffloadConnector` and supplies synthetic request metadata. The save/load calls, background worker and packing/retrieval are real. **Normal `register_kv_caches()`, scheduler allocation/eviction, model forward, lookup-server setup and distributed collectives are not exercised.** The single-rank engine uses stand-in collective callbacks. The two instrumentation wrappers delegate to the original pack/wait methods; statistics are read on the thread doing the pack.

| Acceptance observation | Exact source check |
|---|---|
| Producer dependency | Exactly one wait; event is a real torch event; thread differs from dispatch and is observed inside the pack call; pack stream exists. |
| Fence instrumentation | Exactly one captured store-stat record with `producer_fenced == 1`. |
| Source groups | Exactly two source-safe callbacks for the fixed geometry. |
| Save operation | Exactly one successful `dense.page.store` and one successful `dense.page.source_quiescent` completion for the same `SaveOperationId`. |
| Host publication | Lookup specifically in `LocalCPUBackend` returns all 16 tokens. |
| Reload | Clear all GPU K/V and scales, synchronize the clear, dispatch a load with HBM floor zero, wait for completion, then compare all eight layer/plane tensors with `torch.equal`. |

Zeroing the destination tensors removes the unchanged-destination explanation for this smoke, but is not scheduler-driven HBM eviction. The script has no deliberate delayed-write/no-fence control. A pass verifies the dependency is used and the round trip is exact; it does not quantify a race frequency. The explicit synchronizations after clearing and retrieval remain unchanged.

## Why the supplied outer runner is not copied into a generic command

The runner pins the author's `neurospark/glm52-mi35x` image, labels and dependency paths. It uses host IPC, broad ROCm device mounts, relaxed seccomp/label options and a writable results mount. These are environment assumptions for the machine owner to review, not permissions we should grant automatically. Its raw records include host/source paths and Docker inspection data; do not publish them without review.

It also sets `container_removed=True` after an unchecked `docker rm`, so that field alone is not verified cleanup. The recipe below reuses the **unchanged smoke script** inside an already provisioned, owner-approved isolated environment instead of reproducing that outer runner. It does not build/pull an image, install packages, launch a serving process or change any production source.

## Execution recipe — not executed here

A volunteer first chooses an isolated compatible ROCm development environment and one available GPU. Use the installed environment's Python, real LMCache `0.4.5` and compatible ATOM/Triton dependencies. A different build is a new qualification cell; our modern CPU diagnostic environment is not this GPU environment.

Obtain and review `pr2339_gpu_smoke.py` from the pinned snapshot/artifact above. Set `PR_SRC` to a separate clean checkout at the full target SHA, `SMOKE_DIR` to the directory containing that file, and `SMOKE_GPU` to the owner-approved device selector. No checkout is reset by these commands. Do not set these to a live deployment. Retain any dependency-specific Python paths only from the approved environment.

### 1. Freeze source, output directory and environment

```bash
set -euo pipefail
: "${PR_SRC:?Set the isolated target checkout}"
: "${SMOKE_DIR:?Set the reviewed smoke source directory}"
: "${SMOKE_GPU:?Set the owner-approved ROCm device selector}"
export PR_SRC SMOKE_DIR SMOKE_GPU
export PR_COMMIT=e9be221f637d6a7e194e0d3201dbc9ddc3119067
export ROCR_VISIBLE_DEVICES="$SMOKE_GPU"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PR_SRC${PYTHONPATH:+:$PYTHONPATH}"
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/atom-pr2339.XXXXXXXX")
export RUN_DIR
export SMOKE_RESULT="$RUN_DIR/result.json"
```

Run this preflight using the same Python as the smoke. It touches the selected GPU only in this future, owner-approved environment; it is not a CPU-only test.

```python
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import subprocess
import sys


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


source = Path(os.environ['PR_SRC']).resolve(strict=True)
smoke = Path(os.environ['SMOKE_DIR']).resolve(strict=True) / 'pr2339_gpu_smoke.py'
expected = 'e9be221f637d6a7e194e0d3201dbc9ddc3119067'
head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip()
require(head == expected and not dirty, 'Source must be the clean pinned checkout')
smoke_hash = hashlib.sha256(smoke.read_bytes()).hexdigest()
require(smoke_hash == 'fc699dbc3465729fb8fa17593ee90c9830a28c5a7d41343a302edc43b968d342', 'Smoke source changed')
require(md.version('lmcache') == '0.4.5', 'This cell requires LMCache 0.4.5')

import torch
import triton
from atom.kv_transfer.offload.dense import connector

require(Path(connector.__file__).resolve() == source / 'atom/kv_transfer/offload/dense/connector.py', 'Wrong ATOM import origin')
require(bool(torch.version.hip) and torch.cuda.is_available(), 'Compatible ROCm GPU required')
require(torch.cuda.device_count() == 1, 'Select exactly one visible GPU for this cell')
record = {
    'status': 'PREFLIGHT_ONLY', 'atom_sha': head, 'smoke_sha256': smoke_hash,
    'python': sys.version, 'torch': torch.__version__, 'hip': torch.version.hip,
    'lmcache': md.version('lmcache'), 'triton': getattr(triton, '__version__', 'UNKNOWN'),
    'gpu': torch.cuda.get_device_name(0), 'model_loaded': False,
    'gist_revision': 'c881bce790f14d57fa026219af2d4466c2e4a154',
}
(Path(os.environ['RUN_DIR']) / 'preflight.json').write_text(json.dumps(record, indent=2) + '\n')
```

Also record the selected image digest or environment provenance and, when available, LMCache wheel/source identity. Version strings alone are not binary hashes. Preserve the source and environment until the smoke finishes; any mutation invalidates this cell.

### 2. Run only the original smoke and retain its actual exit status

```bash
# Only proceed after preflight succeeds and the owner approves this time budget.
set +e
timeout --signal=TERM --kill-after=20s 600s \
  python "$SMOKE_DIR/pr2339_gpu_smoke.py" \
  >"$RUN_DIR/stdout.log" 2>"$RUN_DIR/stderr.log"
smoke_exit=$?
set -e
printf '%s\n' "$smoke_exit" >"$RUN_DIR/exit-code.txt"
printf 'Evidence directory: %s\n' "$RUN_DIR"
```

The outer deadline applies only to this isolated smoke process, never a shared server. Timeout, forced termination, missing JSON or cleanup errors are not a pass; stop and let the machine owner inspect remaining process/device state. Do not reset a GPU or kill unrelated processes. The smoke has 30-second polling limits internally, but setup or blocking GPU calls can outlast those loops.

### 3. Check the retained result, not a green-looking log line

```python
import json
import os
from pathlib import Path

root = Path(os.environ['RUN_DIR'])
code = int((root / 'exit-code.txt').read_text().strip())
if code != 0:
    raise RuntimeError(f'Smoke did not complete successfully: exit {code}')
preflight = json.loads((root / 'preflight.json').read_text())
result = json.loads((root / 'result.json').read_text())
expected = {
    'status': 'passed',
    'pr_commit': 'e9be221f637d6a7e194e0d3201dbc9ddc3119067',
    'producer_event_waits': 1,
    'producer_wait_on_pack_thread': True,
    'producer_fenced_stat': 1,
    'source_safe_groups': 2,
    'store_terminal_succeeded': True,
    'source_quiescent_reported': True,
    'host_tier_hit_tokens': 16,
    'requested_tokens': 16,
    'exact_gpu_kv_match': True,
}
for field, value in expected.items():
    if type(result.get(field)) is not type(value) or result[field] != value:
        raise RuntimeError(f'Missing or incorrect observation: {field}')
if preflight.get('atom_sha') != expected['pr_commit'] or preflight.get('smoke_sha256') != 'fc699dbc3465729fb8fa17593ee90c9830a28c5a7d41343a302edc43b968d342':
    raise RuntimeError('Missing pinned input provenance')
if preflight.get('lmcache') != '0.4.5' or not result.get('hip_version'):
    raise RuntimeError('Wrong qualification environment')
if result.get('torch_version') != preflight.get('torch') or result.get('hip_version') != preflight.get('hip'):
    raise RuntimeError('Preflight and smoke environments differ')
if result.get('backends') != ['LocalCPUBackend']:
    raise RuntimeError('Unexpected storage backends; inspect before claiming attribution')
print('PASSED_BOUNDED_HOST_SMOKE: not TP, retry, model, race-rate or performance qualification')
```

The source initializes its JSON result only after some setup; exceptions before that point, or during final cleanup, may leave no result file. Require both zero process exit and valid observations. Do not reduce this to checking `status` alone. An unexpected backend list requires inspection rather than silently relaxing attribution.

## Return packet and next decision

Return the pinned input identifiers, preflight, result, exit code, sanitized logs and actual image/build provenance. Do not return prompts, model weights, credentials, all environment variables or raw Docker inspection by default. No volunteer is asked to rerun a model benchmark or debug unrelated suites.

If this cell passes, it adds one independently reproduced single-GPU connector result at the target revision. TP quorum, failed-save retry and model behavior remain separate experiments. Before asking for GPU time, the next contribution is a short source/recipe review of this packet; the author has already supplied the script and need not reconstruct our plan.

Local preparation checks: both captured Python files parse; the recipe's shell and Python blocks pass syntax checks. The result-checking block is additionally exercised with synthetic receipts; those checks test receipt handling, not GPU behavior. Detailed results are in `DENSE_HOST_SMOKE_PREPARATION.json` beside this document. AI-assisted source review and drafting; the original smoke remains the author's code.
