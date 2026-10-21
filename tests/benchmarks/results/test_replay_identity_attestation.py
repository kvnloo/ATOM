# SPDX-License-Identifier: MIT
"""Observed identity evidence is distinct from intended fixture identity.

The RFC requires reproducible parent/session/route attribution; a fixture's
planned IDs are not proof that a live observation echoed them.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'atom/benchmarks/session_replay.py'
spec = importlib.util.spec_from_file_location('replay_attestation', SCRIPT)
replay = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(replay)


class IdentityAttestationTests(unittest.TestCase):
    def setUp(self):
        fixture = {
            'schema_version': 1, 'seed': 42,
            'sessions': [{'session_id': 'session-a', 'turns': [
                {'turn_id': 'p', 'endpoint': 'chat', 'branch': 'main',
                 'prefix_group': 'cohort-1', 'input': ['synthetic']},
                {'turn_id': 'c', 'endpoint': 'responses', 'branch': 'experiment',
                 'prefix_group': 'cohort-1', 'parent_turn_id': 'p',
                 'input': ['synthetic result']},
            ]}],
        }
        self.plan = replay.compile_plan(fixture)
        self.rows = [
            {
                'request_id': r['request_id'], 'status': 'success',
                'session_id': r['session_id'], 'turn_id': r['turn_id'],
                'parent_request_id': r['parent_request_id'],
                'endpoint': r['endpoint'], 'branch': r['branch'],
                'prefix_group': r['prefix_group'],
            }
            for r in self.plan['requests']
        ]

    def test_full_echo_is_attested_independent_of_event_arrival_order(self):
        summary = replay.reconcile(self.plan, list(reversed(self.rows)))
        evidence = summary['identity_echo_evidence']
        self.assertTrue(evidence['all_requests_fully_echoed'])
        self.assertEqual(evidence['fully_echoed_requests'], 2)
        self.assertEqual(evidence['request_count'], 2)
        self.assertEqual(set(evidence['field_coverage'].values()), {2})
        self.assertEqual(summary['result'], 'matched')

    def test_minimal_terminals_match_without_claiming_identity_proof(self):
        # Backward compatible minimal observations are status matches, not
        # proof of which route/session/parent the producer actually used.
        minimal = [{ 'request_id': r['request_id'], 'status': r['status'] }
                   for r in self.rows]
        summary = replay.reconcile(self.plan, minimal)
        self.assertEqual(summary['result'], 'matched')
        self.assertFalse(summary['identity_echo_evidence']['all_requests_fully_echoed'])
        self.assertEqual(summary['identity_echo_evidence']['fully_echoed_requests'], 0)
        self.assertEqual(set(summary['identity_echo_evidence']['field_coverage'].values()), {0})

    def test_partial_echo_never_becomes_full_attestation(self):
        rows = [dict(row) for row in self.rows]
        rows[1].pop('prefix_group')
        summary = replay.reconcile(self.plan, rows)
        evidence = summary['identity_echo_evidence']
        self.assertFalse(evidence['all_requests_fully_echoed'])
        self.assertEqual(evidence['fully_echoed_requests'], 1)
        self.assertEqual(evidence['field_coverage']['prefix_group'], 1)
        self.assertEqual(evidence['field_coverage']['endpoint'], 2)

    def test_false_echo_is_invalid_not_partial_attestation(self):
        rows = [dict(row) for row in self.rows]
        rows[1]['branch'] = 'wrong'
        with self.assertRaisesRegex(replay.ReplayContractError, 'mismatched branch'):
            replay.reconcile(self.plan, rows)


if __name__ == '__main__':
    unittest.main()
