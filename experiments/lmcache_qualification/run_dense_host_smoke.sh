#!/usr/bin/env bash
set -euo pipefail

: "${PR_SRC:?Set PR_SRC to the clean reviewed ATOM checkout}"
: "${SMOKE_FILE:?Set SMOKE_FILE to pr2339_gpu_smoke.py from the pinned snapshot}"
: "${SMOKE_GPU:?Set SMOKE_GPU to the owner-approved single ROCm device selector}"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUAL_PY="$SELF_DIR/qualification.py"
RUN_DIR="${RUN_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/atom-lmcache-dense.XXXXXXXX")}"

export PR_COMMIT=e9be221f637d6a7e194e0d3201dbc9ddc3119067
export ROCR_VISIBLE_DEVICES="$SMOKE_GPU"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PR_SRC${PYTHONPATH:+:$PYTHONPATH}"
export SMOKE_RESULT="$RUN_DIR/result.json"

python "$QUAL_PY" dense-preflight   --source "$PR_SRC"   --smoke "$SMOKE_FILE"   --out "$RUN_DIR"

set +e
timeout --signal=TERM --kill-after=20s 600s   python "$SMOKE_FILE"   >"$RUN_DIR/stdout.log" 2>"$RUN_DIR/stderr.log"
smoke_exit=$?
set -e
printf '%s
' "$smoke_exit" >"$RUN_DIR/exit-code.txt"

printf 'Run directory: %s
' "$RUN_DIR"
printf '%s
'   'Machine owner: inspect stdout.log/stderr.log and GPU/process cleanup.'   'Then run one of:'   "  python '$QUAL_PY' dense-validate --run-dir '$RUN_DIR' --diagnostic-review KNOWN_ONLY --cleanup PASS"   "  python '$QUAL_PY' dense-validate --run-dir '$RUN_DIR' --diagnostic-review UNKNOWN --cleanup UNKNOWN"
