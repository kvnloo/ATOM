"""Isolated, stdlib-only characterization of the ATOMesh benchmark numeric contract.
This is not an import or execution of the complete ATOM repository.
"""
import json
import math
import time
import unittest


def baseline_number(*values):
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def candidate_number(*values):
    for value in values:
        if value is None or value == "":
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            return parsed
    return None


def baseline_metric_entry(v):
    if v is None:
        return None
    return {"name": "TTFT", "unit": "ms", "value": round(float(v), 4)}


def candidate_metric_entry(v):
    measured = candidate_number(v)
    if measured is None:
        return None
    return {"name": "TTFT", "unit": "ms", "value": round(measured, 4)}


class ContractTests(unittest.TestCase):
    def test_nonfinite_handled_as_missing(self):
        for invalid in (float("nan"), float("inf"), -float("inf"), "NaN", "Infinity"):
            with self.subTest(invalid=str(invalid)):
                self.assertIsNone(candidate_number(invalid))
                self.assertTrue(math.isfinite(candidate_number(invalid, 17.25)))

    def test_missing_not_coerced_to_zero(self):
        self.assertIsNone(candidate_number(float("nan")))
        self.assertEqual(candidate_number(0, 17.25), 0.0)

    def test_dashboard_json_strict(self):
        self.assertIsNone(candidate_metric_entry("NaN"))
        json.dumps([candidate_metric_entry(17.25)], allow_nan=False)
        with self.assertRaises(ValueError):
            json.dumps([baseline_metric_entry("NaN")], allow_nan=False)

    def test_baseline_has_same_invariant_violation(self):
        for invalid in (float("nan"), float("inf"), -float("inf")):
            self.assertFalse(math.isfinite(baseline_number(invalid)))

    def test_finite_values_unchanged(self):
        for value in (0, 1, 17.25555, -123.21, "5.3", None, "garbage"):
            self.assertEqual(candidate_number(value), baseline_number(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
