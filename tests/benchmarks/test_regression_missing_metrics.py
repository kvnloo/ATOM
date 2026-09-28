# SPDX-License-Identifier: MIT
"""Missing benchmark metrics remain unknown instead of becoming synthetic zeros."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_summarize():
    path = Path(__file__).parents[2] / ".github" / "scripts" / "summarize.py"
    spec = importlib.util.spec_from_file_location("atom_ci_summarize_missing", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(**overrides):
    row = {
        "benchmark_backend": "ATOM",
        "benchmark_model_name": "fixture-model",
        "random_input_len": 8192,
        "random_output_len": 1024,
        "max_concurrency": 8,
        "output_throughput": 100.0,
        "total_token_throughput": 100.0,
        "mean_ttft_ms": 100.0,
        "mean_tpot_ms": 100.0,
    }
    row.update(overrides)
    return row


def test_missing_current_throughput_is_not_a_synthetic_regression(capsys):
    summarize = _load_summarize()
    baseline = _row()
    current = _row()
    current.pop("total_token_throughput")

    count, regressions = summarize.print_regression_report([current], [baseline])
    output = capsys.readouterr().out

    assert count == 0
    assert regressions == []
    assert "N/A" in output


def test_missing_baseline_latency_is_not_an_infinite_regression(capsys):
    summarize = _load_summarize()
    baseline = _row()
    baseline.pop("mean_ttft_ms")
    current = _row(mean_ttft_ms=1000.0)

    count, regressions = summarize.print_regression_report([current], [baseline])
    capsys.readouterr()

    assert count == 0
    assert regressions == []


def test_other_comparable_metric_can_still_trigger(capsys):
    summarize = _load_summarize()
    baseline = _row()
    current = _row(output_throughput=94.0)
    current.pop("total_token_throughput")

    count, regressions = summarize.print_regression_report([current], [baseline])
    capsys.readouterr()

    assert count == 1
    assert regressions[0]["triggered_metrics"] == ["output_throughput"]
    assert regressions[0]["metrics"]["total_token_throughput"] == {
        "current": None,
        "baseline": 100.0,
        "pct": None,
        "comparable": False,
    }
