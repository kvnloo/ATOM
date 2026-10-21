# SPDX-License-Identifier: MIT
"""CPU-only CLI safety regressions for session replay's public JSON contract."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "atom" / "benchmarks" / "session_replay.py"
spec = importlib.util.spec_from_file_location("replay_json_contract", SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def fixture():
    return {"schema_version": 1, "seed": 17, "sessions": [
        {"session_id": "s", "turns": [{"turn_id": "t", "endpoint": "chat",
            "input": [{"role": "user", "content": "synthetic only"}]}]}
    ]}


class ReplayJsonContract(unittest.TestCase):
    def cli(self, fixture_text, obs=None):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "fixture.json").write_text(fixture_text, encoding="utf-8")
            cmd = [sys.executable, str(SCRIPT), str(d / "fixture.json")]
            if obs is not None:
                (d / "events.jsonl").write_text(obs, encoding="utf-8")
                cmd += ["--observations", str(d / "events.jsonl")]
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    def rejects(self, result, phrase):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(phrase, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_fixture_member_is_not_silently_overwritten(self):
        raw = json.dumps(fixture()).replace('"seed": 17', '"seed": 0, "seed": 17')
        self.rejects(self.cli(raw), "duplicate JSON member")

    def test_duplicate_observation_terminal_is_not_silently_overwritten(self):
        req = replay.compile_plan(fixture())["requests"][0]
        obs = json.dumps({"request_id": req["request_id"], "status": "success"})
        obs = obs.replace('"status": "success"', '"status": "error", "status": "success"')
        self.rejects(self.cli(json.dumps(fixture()), obs), "duplicate JSON member")

    def test_nonfinite_or_underflow_observations_cannot_be_reported(self):
        req = replay.compile_plan(fixture())["requests"][0]
        for number, error in [("NaN", "non-JSON"), ("1e999", "non-finite"),
                              ("1e-999", "underflows")]:
            with self.subTest(number=number):
                obs = json.dumps({"request_id": req["request_id"], "status": "success"})
                obs = obs[:-1] + ',"untrusted":' + number + '}\n'
                self.rejects(self.cli(json.dumps(fixture()), obs), error)

    def test_nul_delimited_id_pairs_do_not_collide(self):
        data = fixture()
        data["sessions"] = [
            {"session_id": "a\x00b", "turns": [{"turn_id": "c", "endpoint": "chat", "input": ["x"]}]},
            {"session_id": "a", "turns": [{"turn_id": "b\x00c", "endpoint": "chat", "input": ["x"]}]},
        ]
        ids = [r["request_id"] for r in replay.compile_plan(data)["requests"]]
        self.assertEqual(len(set(ids)), 2)

    def test_safe_id_matches_existing_hash(self):
        req = replay.compile_plan(fixture())
        digest = req["scenario_sha256"]
        expected = "rep-" + hashlib.sha256(f"{digest}\x00s\x00t".encode()).hexdigest()[:24]
        self.assertEqual(req["requests"][0]["request_id"], expected)

    def test_unpaired_surrogate_is_controlled_contract_error(self):
        data = fixture()
        data["sessions"][0]["session_id"] = "bad\ud800"
        with self.assertRaisesRegex(replay.ReplayContractError, "UTF-8"):
            replay.compile_plan(data)

    def test_normal_public_fixture_and_successful_observation(self):
        raw = json.dumps(fixture())
        rid = replay.compile_plan(fixture())["requests"][0]["request_id"]
        obs = json.dumps({"request_id": rid, "status": "success"})
        result = self.cli(raw, obs)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["result"], "matched")
        self.assertEqual(report["status_counts"], {"success": 1})


if __name__ == "__main__":
    unittest.main()
