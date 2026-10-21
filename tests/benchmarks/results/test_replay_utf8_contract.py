# SPDX-License-Identifier: MIT
"""Identity strings must be transportable UTF-8, not escaped lone surrogates."""
import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "atom/benchmarks/session_replay.py"
SPEC = importlib.util.spec_from_file_location("session_replay_utf8", SOURCE)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def fixture():
    return {"schema_version": 1, "seed": 5, "sessions": [{
        "session_id": "s", "turns": [{
            "turn_id": "t", "endpoint": "chat", "branch": "main",
            "prefix_group": "cohort-a", "input": ["synthetic"],
        }],
    }]}


class ReplayUTF8Contract(unittest.TestCase):
    def test_unpaired_surrogate_route_and_cohort_rejected(self):
        for field in ("branch", "prefix_group"):
            with self.subTest(field=field):
                raw = fixture()
                raw["sessions"][0]["turns"][0][field] = "bad\ud800"
                with self.assertRaisesRegex(replay.ReplayContractError, "UTF-8"):
                    replay.compile_plan(raw)

    def test_unpaired_surrogate_boundary_clock_rejected(self):
        plan = replay.compile_plan(fixture())
        req = plan["requests"][0]
        events = [{"request_id": req["request_id"], "status": "success",
                   "start_ns": 10, "end_ns": 20, "clock_id": "bad\ud800"}]
        with self.assertRaisesRegex(replay.ReplayContractError, "UTF-8"):
            replay.reconcile(plan, events)

    def test_utf8_route_and_cohort_preserved_byte_for_byte(self):
        raw = fixture()
        raw["sessions"][0]["turns"][0].update(branch="équipe", prefix_group="组-𝄞")
        plan = replay.compile_plan(raw)
        req = plan["requests"][0]
        self.assertEqual(req["branch"], "équipe")
        self.assertEqual(req["prefix_group"], "组-𝄞")
        observed = [{"request_id": req["request_id"], "status": "success",
                     "branch": "équipe", "prefix_group": "组-𝄞", "endpoint": "chat"}]
        self.assertEqual(replay.reconcile(plan, observed)["result"], "matched")

    def test_cli_surrogate_is_controlled_error_without_traceback(self):
        raw = fixture()
        raw["sessions"][0]["turns"][0]["branch"] = "bad\ud800"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SOURCE), str(path)],
                                    capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("valid UTF-8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
