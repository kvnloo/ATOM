# SPDX-License-Identifier: MIT
"""Native CLI ordering contract on the existing 12-turn public replay fixture.

These are CPU parser/localhost-style checks, not ATOM inference or GPU metrics.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "atom" / "benchmarks" / "session_replay.py"
FIXTURE = (
    ROOT
    / "tests"
    / "benchmarks"
    / "results"
    / "fixtures"
    / "agentic_session_replay_v1.json"
)


def plan():
    spec = importlib.util.spec_from_file_location("session_replay_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compile_plan(json.loads(FIXTURE.read_text(encoding="utf-8")))


def observations_and_boundaries():
    terminal_rows = []
    spans = {}
    for index, request in enumerate(plan()["requests"]):
        start = 1_000_000_000 + index * 1_000_000_000
        end = start + (index % 3 + 1) * 100_000_000
        sid = request["session_id"]
        lo, hi = spans.get(sid, (start, end))
        spans[sid] = min(start, lo), max(end, hi)
        terminal_rows.append(
            {
                "request_id": request["request_id"],
                "session_id": sid,
                "turn_id": request["turn_id"],
                "parent_request_id": request["parent_request_id"],
                "status": "error" if index < 2 else request["expected_terminal"],
                "start_ns": start,
                "end_ns": end,
                "clock_id": "synthetic-local-clock",
                "think_ns": 0,
                "tool_pause_ns": 0,
            }
        )
    boundaries = []
    for sid, (lo, hi) in spans.items():
        boundaries.extend(
            (
                {
                    "session_id": sid,
                    "event": "session_started",
                    "timestamp_ns": lo - 1,
                    "clock_id": "synthetic-local-clock",
                },
                {
                    "session_id": sid,
                    "event": "session_finished",
                    "timestamp_ns": hi + 1,
                    "clock_id": "synthetic-local-clock",
                },
            )
        )
    return terminal_rows, boundaries


def run_cli(rows=None, boundaries=None):
    with tempfile.TemporaryDirectory() as directory:
        cmd = [sys.executable, str(SCRIPT), str(FIXTURE)]
        if rows is not None:
            observation_path = Path(directory) / "observations.jsonl"
            observation_path.write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
            )
            cmd += ["--observations", str(observation_path)]
        if boundaries is not None:
            boundaries_path = Path(directory) / "boundaries.jsonl"
            boundaries_path.write_text(
                "".join(json.dumps(r) + "\n" for r in boundaries), encoding="utf-8"
            )
            cmd += ["--boundaries", str(boundaries_path)]
        return subprocess.run(
            cmd, text=True, capture_output=True, timeout=15, check=False
        )


class ReplayOrderDeterminism(unittest.TestCase):
    def test_reversed_terminal_arrival_preserves_byte_identical_report(self):
        observations, boundaries = observations_and_boundaries()
        a = run_cli(observations, boundaries)
        b = run_cli(list(reversed(observations)), boundaries)
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(a.stdout, b.stdout)
        report = json.loads(a.stdout)
        self.assertEqual(report["request_count"], 12)
        self.assertEqual(len(report["unexpected_terminals"]), 2)
        self.assertEqual(report["result"], "mismatch")
        self.assertEqual(len(report["sessions"]), 4)

    def test_reversed_both_observation_and_boundary_arrival(self):
        observations, boundaries = observations_and_boundaries()
        a = run_cli(observations, boundaries)
        b = run_cli(list(reversed(observations)), list(reversed(boundaries)))
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(b.returncode, 0, b.stderr)
        self.assertEqual(a.stdout, b.stdout)
        for session in json.loads(a.stdout)["sessions"].values():
            self.assertEqual(session["session_wall_clock_id"], "synthetic-local-clock")
            self.assertGreater(session["session_wall_s"], 0)

    def test_duplicate_terminal_still_returns_contract_error(self):
        observations, boundaries = observations_and_boundaries()
        observations.append(observations[0].copy())
        result = run_cli(observations, boundaries)
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate terminal", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_unknown_terminal_still_returns_contract_error(self):
        observations, boundaries = observations_and_boundaries()
        observations.append({**observations[0], "request_id": "not-in-plan"})
        result = run_cli(observations, boundaries)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown request_id", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_repeat_plan_retains_identities_and_excludes_raw_input(self):
        a = run_cli()
        b = run_cli()
        self.assertEqual(a.returncode, b.returncode)
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertEqual(a.stdout, b.stdout)
        ids = [entry["request_id"] for entry in json.loads(a.stdout)["requests"]]
        self.assertEqual(len(set(ids)), 12)
        for item in json.loads(FIXTURE.read_text(encoding="utf-8"))["sessions"]:
            for turn in item["turns"]:
                for msg in turn["input"]:
                    self.assertNotIn(msg["content"], a.stdout)


if __name__ == "__main__":
    unittest.main()
