# SPDX-License-Identifier: MIT
"""Shared-clock causal ordering contract from kvnloo/ATOM#15.

A child spawned by a parent cannot begin before the parent begins in the
same monotonic clock domain. Siblings may overlap; different clocks are not
comparable. These are synthetic CPU checks, not ATOM inference proofs.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / 'atom/benchmarks/session_replay.py'
spec = importlib.util.spec_from_file_location('replay_parent_causality', SCRIPT)
replay = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(replay)


class ParentCausalOrderTests(unittest.TestCase):
    def setUp(self):
        fixture = {'schema_version': 1, 'seed': 6, 'sessions': [
            {'session_id': 'parallel', 'turns': [
                {'turn_id': 'parent', 'endpoint': 'chat', 'input': ['synthetic']},
                {'turn_id': 'child-a', 'parent_turn_id': 'parent',
                 'endpoint': 'responses', 'input': ['synthetic']},
                {'turn_id': 'child-b', 'parent_turn_id': 'parent',
                 'endpoint': 'chat', 'input': ['synthetic']},
            ]}
        ]}
        self.plan = replay.compile_plan(fixture)
        self.rows = [
            {'request_id': r['request_id'], 'status': 'success',
             'session_id': r['session_id'], 'turn_id': r['turn_id'],
             'parent_request_id': r['parent_request_id'],
             'start_ns': s, 'end_ns': e, 'clock_id': 'client-monotonic',
             'tool_pause_ns': 0, 'think_ns': 0}
            for r, s, e in zip(self.plan['requests'],
                               [200, 225, 230], [300, 280, 290])
        ]

    def test_child_before_parent_start_fails_closed(self):
        rows = [dict(r) for r in self.rows]
        rows[1]['start_ns'] = 199
        with self.assertRaisesRegex(replay.ReplayContractError,
                                    'child starts before parent'):
            replay.reconcile(self.plan, rows)

    def test_child_can_begin_while_parent_streams_and_siblings_overlap(self):
        self.assertEqual(replay.reconcile(self.plan, self.rows[::-1])['result'],
                         'matched')

    def test_independent_clock_domains_are_not_ordered(self):
        rows = [dict(r) for r in self.rows]
        rows[1]['clock_id'] = 'different-host'
        rows[1]['start_ns'] = 10
        rows[1]['end_ns'] = 20
        report = replay.reconcile(self.plan, rows)
        self.assertEqual(report['result'], 'matched')
        self.assertIsNone(report['sessions']['parallel']['request_window_s'])

    def test_unstamped_parent_cannot_be_used_as_causal_proof(self):
        rows = [dict(r) for r in self.rows]
        for key in ('start_ns', 'end_ns', 'clock_id'):
            rows[0].pop(key)
        self.assertEqual(replay.reconcile(self.plan, rows)['result'], 'matched')


if __name__ == '__main__':
    unittest.main()
