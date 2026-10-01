# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.lmcache_qualification import qualification as q


def _dense_receipt(root: Path):
    q._write(
        root / "preflight.json",
        {
            "atom_sha": q.DENSE_ATOM_SHA,
            "smoke_sha256": q.DENSE_SMOKE_SHA256,
            "lmcache": "0.4.5",
            "torch": "2.10.0+rocm",
            "hip": "7.2",
        },
    )
    payload = dict(q.DENSE_EXPECTED)
    payload.update(
        {
            "backends": ["LocalCPUBackend"],
            "torch_version": "2.10.0+rocm",
            "hip_version": "7.2",
        }
    )
    q._write(root / "result.json", payload)
    (root / "exit-code.txt").write_text("0\n")


def test_dense_validator_accepts_exact_bounded_receipt(tmp_path):
    _dense_receipt(tmp_path)
    args = SimpleNamespace(
        run_dir=str(tmp_path),
        cleanup="UNKNOWN",
        diagnostic_review="KNOWN_ONLY",
    )

    assert q.dense_validate(args) == 0
    verdict = json.loads((tmp_path / "qualification.json").read_text())
    assert verdict["passed"] is True
    assert verdict["cleanup"] == "UNKNOWN"


def test_dense_validator_rejects_missing_source_quiescence(tmp_path):
    _dense_receipt(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text())
    result["source_quiescent_reported"] = False
    q._write(tmp_path / "result.json", result)
    args = SimpleNamespace(
        run_dir=str(tmp_path),
        cleanup="UNKNOWN",
        diagnostic_review="KNOWN_ONLY",
    )

    assert q.dense_validate(args) == 1


def _mp_receipt():
    def arm(state, *, loaded=0, retrieves=0):
        return {
            "lmcache_initial_state": state,
            "fresh_atom": True,
            "requests_completed": 50,
            "retrieves_finished": retrieves,
            "load_failures": 0,
            "loaded_tokens": loaded,
            "wall_s": 10.0,
            "ttft": [],
            "tpot": [],
            "score": 0.94,
            "correctness_pass": True,
        }

    return {
        "schema": "atom-lmcache-native-mp-triplet-v1",
        "evidence_owner": "volunteer",
        "atom_sha": "abc",
        "lmcache_identity": "wheel-sha",
        "model_revision": "model-rev",
        "tokenizer_revision": "tok-rev",
        "gpu": "8x MI355X",
        "topology": "TP8",
        "kv_dtype": "fp8",
        "corpus_sha256": "deadbeef",
        "correctness_rule": "same frozen evaluator; no transport failures",
        "arms": {
            "cold_populate": arm("empty"),
            "restore": arm(
                "retained-from-cold-populate",
                loaded=429056,
                retrieves=328,
            ),
            "recompute_control": arm("empty"),
        },
        "unexpected_errors": [],
    }


def test_mp_validator_accepts_minimal_correctness_triplet(tmp_path):
    receipt = tmp_path / "receipt.json"
    q._write(receipt, _mp_receipt())
    args = SimpleNamespace(receipt=str(receipt), out=None)

    assert q.mp_validate(args) == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("loaded_tokens", 0),
        ("retrieves_finished", 0),
        ("load_failures", 1),
        ("correctness_pass", False),
    ],
)
def test_mp_validator_rejects_unqualified_restore(tmp_path, field, value):
    payload = _mp_receipt()
    payload["arms"]["restore"][field] = value
    receipt = tmp_path / "receipt.json"
    q._write(receipt, payload)
    args = SimpleNamespace(receipt=str(receipt), out=None)

    assert q.mp_validate(args) == 1
