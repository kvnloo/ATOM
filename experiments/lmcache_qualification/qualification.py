#!/usr/bin/env python3
"""Small, offline-safe qualification helper for the final ATOM–LMCache gates.

This tool does not install packages, start containers, reset GPUs, or mutate ATOM
source. It only (a) validates the reviewed dense one-GPU smoke preflight/result
and (b) creates/validates structured native-MP correctness/economics receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

DENSE_ATOM_SHA = "e9be221f637d6a7e194e0d3201dbc9ddc3119067"
DENSE_SMOKE_SHA256 = "fc699dbc3465729fb8fa17593ee90c9830a28c5a7d41343a302edc43b968d342"
DENSE_GIST_REVISION = "c881bce790f14d57fa026219af2d4466c2e4a154"

DENSE_EXPECTED = {
    "status": "passed",
    "pr_commit": DENSE_ATOM_SHA,
    "producer_event_waits": 1,
    "producer_wait_on_pack_thread": True,
    "producer_fenced_stat": 1,
    "source_safe_groups": 2,
    "store_terminal_succeeded": True,
    "source_quiescent_reported": True,
    "host_tier_hit_tokens": 16,
    "requested_tokens": 16,
    "exact_gpu_kv_match": True,
}


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(source: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(source), *args], text=True
    ).strip()


def dense_preflight(args: argparse.Namespace) -> int:
    source = Path(args.source).resolve(strict=True)
    smoke = Path(args.smoke).resolve(strict=True)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    head = _git(source, "rev-parse", "HEAD")
    dirty = _git(source, "status", "--porcelain")
    if head != DENSE_ATOM_SHA or dirty:
        raise RuntimeError(
            "dense smoke requires the clean reviewed checkout "
            f"{DENSE_ATOM_SHA}; got head={head!r}, dirty={bool(dirty)}"
        )
    smoke_hash = _sha256(smoke)
    if smoke_hash != DENSE_SMOKE_SHA256:
        raise RuntimeError(
            "reviewed smoke source changed: "
            f"expected {DENSE_SMOKE_SHA256}, got {smoke_hash}"
        )
    if md.version("lmcache") != "0.4.5":
        raise RuntimeError(
            f"dense smoke requires LMCache 0.4.5; got {md.version('lmcache')}"
        )

    import torch
    import triton
    from atom.kv_transfer.offload.dense import connector

    expected_connector = source / "atom/kv_transfer/offload/dense/connector.py"
    if Path(connector.__file__).resolve() != expected_connector:
        raise RuntimeError(
            "wrong ATOM import origin: "
            f"{Path(connector.__file__).resolve()} != {expected_connector}"
        )
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError("a compatible ROCm GPU is required")
    if torch.cuda.device_count() != 1:
        raise RuntimeError(
            "select exactly one visible GPU for this bounded smoke; "
            f"found {torch.cuda.device_count()}"
        )

    record = {
        "status": "PREFLIGHT_ONLY",
        "atom_sha": head,
        "smoke_sha256": smoke_hash,
        "python": sys.version,
        "torch": torch.__version__,
        "hip": torch.version.hip,
        "lmcache": md.version("lmcache"),
        "triton": getattr(triton, "__version__", "UNKNOWN"),
        "gpu": torch.cuda.get_device_name(0),
        "model_loaded": False,
        "gist_revision": DENSE_GIST_REVISION,
    }
    _write(out / "preflight.json", record)
    print(out / "preflight.json")
    return 0


def dense_validate(args: argparse.Namespace) -> int:
    root = Path(args.run_dir).resolve(strict=True)
    preflight = json.loads((root / "preflight.json").read_text())
    result = json.loads((root / "result.json").read_text())
    code = int((root / "exit-code.txt").read_text().strip())

    errors: list[str] = []
    if code != 0:
        errors.append(f"smoke exit code was {code}, expected 0")
    for field, value in DENSE_EXPECTED.items():
        observed = result.get(field)
        if type(observed) is not type(value) or observed != value:
            errors.append(
                f"{field}: expected {value!r} ({type(value).__name__}), "
                f"got {observed!r}"
            )
    if preflight.get("atom_sha") != DENSE_ATOM_SHA:
        errors.append("preflight ATOM SHA does not match reviewed cell")
    if preflight.get("smoke_sha256") != DENSE_SMOKE_SHA256:
        errors.append("preflight smoke hash does not match reviewed source")
    if preflight.get("lmcache") != "0.4.5":
        errors.append("preflight LMCache is not 0.4.5")
    if result.get("backends") != ["LocalCPUBackend"]:
        errors.append(
            "storage attribution is not exactly ['LocalCPUBackend']; "
            f"got {result.get('backends')!r}"
        )
    if result.get("torch_version") != preflight.get("torch"):
        errors.append("preflight and smoke torch versions differ")
    if result.get("hip_version") != preflight.get("hip"):
        errors.append("preflight and smoke HIP versions differ")

    verdict = {
        "gate": "dense_host_smoke",
        "passed": not errors,
        "errors": errors,
        "scope": (
            "bounded one-GPU dense connector round trip only; "
            "not TP, model, scheduler eviction, retry, race-rate or performance"
        ),
        "cleanup": args.cleanup,
        "diagnostic_review": args.diagnostic_review,
    }
    _write(root / "qualification.json", verdict)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASSED_BOUNDED_HOST_SMOKE")
    return 0


def _blank_arm(initial_state: str) -> dict[str, Any]:
    return {
        "lmcache_initial_state": initial_state,
        "fresh_atom": None,
        "requests_completed": None,
        "retrieves_finished": None,
        "load_failures": None,
        "loaded_tokens": None,
        "wall_s": None,
        "ttft": [],
        "tpot": [],
        "score": None,
        "correctness_pass": None,
    }


def mp_init(args: argparse.Namespace) -> int:
    out = Path(args.out).resolve()
    payload = {
        "schema": "atom-lmcache-native-mp-triplet-v1",
        "evidence_owner": args.evidence_owner,
        "atom_sha": args.atom_sha,
        "lmcache_identity": args.lmcache_identity,
        "model_revision": args.model_revision,
        "tokenizer_revision": args.tokenizer_revision,
        "gpu": args.gpu,
        "topology": args.topology,
        "kv_dtype": args.kv_dtype,
        "checkpoint_interval_tokens": args.checkpoint_interval,
        "corpus_sha256": args.corpus_sha256,
        "correctness_rule": args.correctness_rule,
        "trial": args.trial,
        "arms": {
            "cold_populate": _blank_arm("empty"),
            "restore": _blank_arm("retained-from-cold-populate"),
            "recompute_control": _blank_arm("empty"),
        },
        "unexpected_errors": [],
        "cleanup": "UNKNOWN",
        "notes": "",
    }
    payload["arms"]["restore"]["fresh_atom"] = True
    payload["arms"]["recompute_control"]["fresh_atom"] = True
    _write(out, payload)
    print(out)
    return 0


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_arm(name: str, arm: dict[str, Any], errors: list[str]) -> None:
    completed = arm.get("requests_completed")
    if not isinstance(completed, int) or completed <= 0:
        errors.append(f"{name}: requests_completed must be a positive integer")
    failures = arm.get("load_failures")
    if not isinstance(failures, int) or failures != 0:
        errors.append(f"{name}: load_failures must be exactly 0")
    if arm.get("correctness_pass") is not True:
        errors.append(f"{name}: correctness_pass must be true")
    if not _finite_number(arm.get("wall_s")) or float(arm["wall_s"]) <= 0:
        errors.append(f"{name}: wall_s must be a finite positive number")


def mp_validate(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.receipt).read_text())
    errors: list[str] = []

    if payload.get("schema") != "atom-lmcache-native-mp-triplet-v1":
        errors.append("unsupported or missing receipt schema")
    for field in (
        "evidence_owner",
        "atom_sha",
        "lmcache_identity",
        "model_revision",
        "tokenizer_revision",
        "gpu",
        "topology",
        "kv_dtype",
        "corpus_sha256",
        "correctness_rule",
    ):
        if not str(payload.get(field, "")).strip():
            errors.append(f"missing required identity field: {field}")

    arms = payload.get("arms")
    if not isinstance(arms, dict):
        errors.append("arms must be an object")
        arms = {}
    for name in ("cold_populate", "restore", "recompute_control"):
        arm = arms.get(name)
        if not isinstance(arm, dict):
            errors.append(f"missing arm: {name}")
            continue
        _validate_arm(name, arm, errors)

    restore = arms.get("restore", {}) if isinstance(arms, dict) else {}
    cold = arms.get("cold_populate", {}) if isinstance(arms, dict) else {}
    control = arms.get("recompute_control", {}) if isinstance(arms, dict) else {}

    if restore.get("fresh_atom") is not True:
        errors.append("restore: fresh_atom must be true")
    if control.get("fresh_atom") is not True:
        errors.append("recompute_control: fresh_atom must be true")
    if restore.get("lmcache_initial_state") != "retained-from-cold-populate":
        errors.append("restore: LMCache must be retained from cold-populate")
    if cold.get("lmcache_initial_state") != "empty":
        errors.append("cold_populate: LMCache initial state must be empty")
    if control.get("lmcache_initial_state") != "empty":
        errors.append("recompute_control: LMCache initial state must be empty")
    loaded = restore.get("loaded_tokens")
    if not isinstance(loaded, int) or loaded <= 0:
        errors.append("restore: loaded_tokens must be positive")
    retrieves = restore.get("retrieves_finished")
    if not isinstance(retrieves, int) or retrieves <= 0:
        errors.append("restore: retrieves_finished must be positive")
    if payload.get("unexpected_errors"):
        errors.append("receipt contains unexpected_errors; inspect before promotion")

    completed = [
        arms.get(name, {}).get("requests_completed")
        for name in ("cold_populate", "restore", "recompute_control")
    ]
    if all(isinstance(v, int) for v in completed) and len(set(completed)) != 1:
        errors.append(
            "request counts differ across cold/restore/control; "
            f"got {completed}"
        )

    verdict = {
        "gate": "native_mp_triplet",
        "passed": not errors,
        "errors": errors,
        "claim": (
            "correctness-qualified external restore triplet"
            if not errors
            else "not qualified"
        ),
    }
    out = Path(args.out) if args.out else Path(args.receipt).with_suffix(
        ".qualification.json"
    )
    _write(out, verdict)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASSED_NATIVE_MP_CORRECTNESS_TRIPLET")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("dense-preflight")
    p.add_argument("--source", required=True)
    p.add_argument("--smoke", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=dense_preflight)

    p = sub.add_parser("dense-validate")
    p.add_argument("--run-dir", required=True)
    p.add_argument(
        "--cleanup",
        choices=("PASS", "FAIL", "UNKNOWN"),
        default="UNKNOWN",
        help="machine-owner observation; never inferred from transfer success",
    )
    p.add_argument(
        "--diagnostic-review",
        choices=("KNOWN_ONLY", "UNEXPECTED", "UNKNOWN"),
        default="UNKNOWN",
    )
    p.set_defaults(func=dense_validate)

    p = sub.add_parser("mp-init")
    p.add_argument("--out", required=True)
    p.add_argument("--evidence-owner", required=True)
    p.add_argument("--atom-sha", required=True)
    p.add_argument("--lmcache-identity", required=True)
    p.add_argument("--model-revision", required=True)
    p.add_argument("--tokenizer-revision", required=True)
    p.add_argument("--gpu", required=True)
    p.add_argument("--topology", required=True)
    p.add_argument("--kv-dtype", default="fp8")
    p.add_argument("--checkpoint-interval", type=int, default=8192)
    p.add_argument("--corpus-sha256", required=True)
    p.add_argument("--correctness-rule", required=True)
    p.add_argument("--trial", type=int, default=1)
    p.set_defaults(func=mp_init)

    p = sub.add_parser("mp-validate")
    p.add_argument("--receipt", required=True)
    p.add_argument("--out")
    p.set_defaults(func=mp_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
