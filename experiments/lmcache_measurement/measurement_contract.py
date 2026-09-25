# SPDX-License-Identifier: MIT
"""Downstream synthetic interval checks; no ATOM timing or speedup is measured.

One trial and one comparable clock only. Interval unions describe observed
wall-clock coverage, not causality, GPU utilization, or a critical path.
Run: python measurement_contract.py
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import unittest


@dataclass(frozen=True)
class Span:
    trial: str
    clock: str
    phase: str
    start_ms: float
    end_ms: float | None


def number(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Timestamp must be a finite number")


def union_ms(intervals: list[tuple[float, float]]) -> float:
    total = 0.0
    frontier = -math.inf
    for start, end in sorted(intervals):
        total += max(0.0, end - max(start, frontier))
        frontier = max(frontier, end)
    return total


def account(trial: str, clock: str, start_ms: float, end_ms: float | None,
            spans: list[Span]) -> dict:
    """Keep absent endpoints and absent instrumentation distinct from zero."""
    number(start_ms)
    if end_ms is not None:
        number(end_ms)
        if end_ms < start_ms:
            raise ValueError("Reversed request window")
    incomplete = end_ms is None
    phase_spans: dict[str, list[tuple[float, float]]] = {"setup": [], "request": []}
    for span in spans:
        if (span.trial, span.clock) != (trial, clock):
            raise ValueError("Cannot combine different trials or unaligned clocks")
        if span.phase not in phase_spans:
            raise ValueError("Unknown phase")
        number(span.start_ms)
        if span.phase == "request" and span.start_ms < start_ms:
            raise ValueError("Request span starts outside its window")
        if span.phase == "request" and end_ms is not None and span.start_ms > end_ms:
            raise ValueError("Request span starts after completion")
        if span.phase == "setup" and span.start_ms > start_ms:
            raise ValueError("Setup starts after the request")
        if span.end_ms is None:
            incomplete = True
            continue
        number(span.end_ms)
        if span.end_ms < span.start_ms:
            raise ValueError("Reversed span")
        if span.phase == "setup" and span.end_ms > start_ms:
            raise ValueError("Setup overlaps the measured request; choose another window")
        if span.phase == "request" and end_ms is not None and span.end_ms > end_ms:
            raise ValueError("Request span ends outside its window")
        phase_spans[span.phase].append((span.start_ms, span.end_ms))
    duration = None if end_ms is None else end_ms - start_ms
    observed = None if incomplete or not phase_spans["request"] else union_ms(phase_spans["request"])
    return {
        "status": "INCOMPLETE" if incomplete else "UNMEASURED" if observed is None else "INTERVALS_ACCOUNTED",
        "request_window_ms": duration,
        "observed_request_coverage_ms": observed,
        "unattributed_request_ms": None if observed is None else duration - observed,
        "observed_setup_coverage_ms": None if incomplete or not phase_spans["setup"] else union_ms(phase_spans["setup"]),
        "speedup": None,
        "critical_path": None,
    }


def span(start: float, end: float | None, phase: str = "request") -> Span:
    return Span("synthetic", "clock-1", phase, start, end)


def example(start: float, end: float | None, spans: list[Span]) -> dict:
    return account("synthetic", "clock-1", start, end, spans)


class AccountingTests(unittest.TestCase):
    def test_overlap_is_not_summed(self):
        result = example(0, 10, [span(0, 7), span(4, 10)])
        self.assertEqual(result["observed_request_coverage_ms"], 10)
        self.assertNotEqual(result["observed_request_coverage_ms"], 13)
        self.assertIsNone(result["speedup"])
        self.assertIsNone(result["critical_path"])

    def test_nested_duplicate_adjacent_and_zero_intervals(self):
        result = example(0, 12, [span(10, 12), span(2, 5), span(0, 10), span(0, 10), span(6, 6)])
        self.assertEqual(result["observed_request_coverage_ms"], 12)

    def test_gaps_remain_unattributed_not_assumed_idle(self):
        result = example(100, 120, [span(105, 109), span(111, 115)])
        self.assertEqual(result["observed_request_coverage_ms"], 8)
        self.assertEqual(result["unattributed_request_ms"], 12)

    def test_cold_setup_is_not_added_to_request_coverage(self):
        result = example(10, 30, [span(0, 10, "setup"), span(12, 17)])
        self.assertEqual(result["observed_setup_coverage_ms"], 10)
        self.assertEqual(result["request_window_ms"], 20)
        self.assertEqual(result["observed_request_coverage_ms"], 5)

    def test_incomplete_request_or_span_never_gets_a_total(self):
        for end, spans in [(None, [span(0, 2)]), (10, [span(0, None)]), (10, [span(0, None, "setup")])]:
            with self.subTest(end=end, spans=spans):
                result = example(0, end, spans)
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertIsNone(result["observed_request_coverage_ms"])
                self.assertIsNone(result["unattributed_request_ms"])

    def test_missing_instrumentation_is_not_zero_work(self):
        result = example(0, 10, [])
        self.assertEqual(result["status"], "UNMEASURED")
        self.assertIsNone(result["observed_request_coverage_ms"])
        self.assertIsNone(result["observed_setup_coverage_ms"])

    def test_actual_zero_duration_remains_a_measured_zero(self):
        result = example(5, 5, [span(5, 5)])
        self.assertEqual(result["status"], "INTERVALS_ACCOUNTED")
        self.assertEqual(result["observed_request_coverage_ms"], 0)

    def test_reject_cross_clock_or_cross_trial_merges(self):
        for field, value in [("trial", "other-request"), ("clock", "unmapped-gpu-clock")]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    example(0, 10, [replace(span(0, 1), **{field: value})])

    def test_reject_invalid_or_out_of_window_spans(self):
        bad = [span(3, 2), span(-1, 2), span(0, 11), span(11, None),
               span(1, math.inf), span(math.nan, 2), span(True, 2),
               span(-2, 1, "setup"), span(0, 1, "unknown")]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                example(0, 10, [item])
        for start, end in [(10, 0), (math.inf, 10), (0, math.nan)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                example(start, end, [])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AccountingTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({
        "status": "SYNTHETIC_CHECKS_PASSED" if result.wasSuccessful() else "CHECKS_FAILED",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "overlap_example": example(0, 10, [span(0, 7), span(4, 10)]),
        "source_timing": "NOT_MEASURED", "gpu": "NOT_RUN", "speedup": "NOT_CLAIMED",
    }, indent=2))
    raise SystemExit(not result.wasSuccessful())
