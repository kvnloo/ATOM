# SPDX-License-Identifier: MIT
"""CPU-only tests for untrusted replay timestamp parsing (no GPU)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT = Path(__file__).resolve().parents[3] / "atom" / "benchmarks" / "session_replay.py"
spec = importlib.util.spec_from_file_location("session_replay", SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

FIXTURE = {
    "schema_version": 1,
    "seed": 3,
    "sessions": [
        {
            "session_id": "public-cpu-case",
            "turns": [
                {
                    "turn_id": "one",
                    "endpoint": "chat",
                    "input": [{"role": "user", "content": "synthetic input"}],
                }
            ],
        }
    ],
}


class TestUntrustedNanoseconds(unittest.TestCase):
    def test_normal_high_precision_timestamp_preserved(self):
        self.assertEqual(replay._ns("1700000000000000001", "start_ns"), 1700000000000000001)

    def test_oversized_decimal_raises_contract_error(self):
        with self.assertRaisesRegex(replay.ReplayContractError, "start_ns"):
            replay._ns("9" * 6000, "start_ns")

    def test_reconcile_oversized_request_timestamp_fails_closed(self):
        plan = replay.compile_plan(FIXTURE)
        req = plan["requests"][0]
        events = [
            {
                "request_id": req["request_id"],
                "status": "success",
                "start_ns": "9" * 6000,
                "end_ns": "9" * 6000,
                "clock_id": "origin-1",
            }
        ]
        with self.assertRaises(replay.ReplayContractError):
            replay.reconcile(plan, events)

    def test_reconcile_oversized_boundary_timestamp_fails_closed(self):
        plan = replay.compile_plan(FIXTURE)
        req = plan["requests"][0]
        events = [
            {
                "request_id": req["request_id"],
                "status": "success",
                "start_ns": "1000",
                "end_ns": "2000",
                "clock_id": "origin-1",
            }
        ]
        boundaries = [
            {
                "session_id": "public-cpu-case",
                "event": "session_started",
                "timestamp_ns": "9" * 6000,
                "clock_id": "origin-1",
            },
            {
                "session_id": "public-cpu-case",
                "event": "session_finished",
                "timestamp_ns": "3000",
                "clock_id": "origin-1",
            },
        ]
        with self.assertRaises(replay.ReplayContractError):
            replay.reconcile(plan, events, boundaries)

    def test_cli_oversized_timestamp_is_controlled_error(self):
        plan = replay.compile_plan(FIXTURE)
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fixture_file = directory / "fixture.json"
            fixture_file.write_text(json.dumps(FIXTURE))
            observation_file = directory / "events.jsonl"
            observation_file.write_text(
                json.dumps(
                    {
                        "request_id": plan["requests"][0]["request_id"],
                        "status": "success",
                        "start_ns": "9" * 6000,
                        "end_ns": "9" * 6000,
                    }
                )
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(fixture_file),
                    "--observations",
                    str(observation_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2, result.stderr[:500])
        self.assertIn("replay contract:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_unquoted_oversized_json_integer_is_controlled_error(self):
        get_limit = getattr(sys, "get_int_max_str_digits", None)
        if get_limit is None or not (0 < get_limit() < 6000):
            self.skipTest("requires CPython's default JSON integer digit limit")

        huge = "9" * 6000
        plan = replay.compile_plan(FIXTURE)
        request_id = plan["requests"][0]["request_id"]

        def json_line(payload):
            # Substitute a bare JSON number rather than an oversized string.
            return json.dumps(payload).replace('"OVERLONG"', huge) + "\n"

        for affected in ("fixture", "observations", "boundaries"):
            with self.subTest(affected=affected), TemporaryDirectory() as tmp:
                directory = Path(tmp)
                fixture_file = directory / "fixture.json"
                fixture = {**FIXTURE, "seed": "OVERLONG" if affected == "fixture" else 3}
                fixture_file.write_text(json_line(fixture))

                observations_file = directory / "events.jsonl"
                observations_file.write_text(
                    json_line(
                        {
                            "request_id": request_id,
                            "status": "success",
                            "start_ns": "OVERLONG" if affected == "observations" else 1000,
                            "end_ns": 2000,
                            "clock_id": "origin-1",
                        }
                    )
                )

                boundaries_file = directory / "boundaries.jsonl"
                boundaries_file.write_text(
                    json_line(
                        {"session_id": "public-cpu-case", "event": "session_started",
                         "timestamp_ns": "OVERLONG" if affected == "boundaries" else 500,
                         "clock_id": "origin-1"}
                    )
                    + json_line(
                        {"session_id": "public-cpu-case", "event": "session_finished",
                         "timestamp_ns": 3000, "clock_id": "origin-1"}
                    )
                )

                command = [sys.executable, str(SCRIPT), str(fixture_file),
                           "--observations", str(observations_file)]
                if affected == "boundaries":
                    command.extend(["--boundaries", str(boundaries_file)])
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 2, result.stderr[:500])
                self.assertIn("replay contract:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_normal_cli_plan_still_succeeds(self):
        with TemporaryDirectory() as tmp:
            fixture_file = Path(tmp) / "fixture.json"
            fixture_file.write_text(json.dumps(FIXTURE))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(fixture_file)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(len(plan["requests"]), 1)
        self.assertEqual(plan["seed"], 3)


if __name__ == "__main__":
    unittest.main()
