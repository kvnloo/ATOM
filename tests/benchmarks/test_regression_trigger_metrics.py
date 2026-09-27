# SPDX-License-Identifier: MIT
"""Regression reports must say which tracked metric crossed its threshold."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_summarize():
    path = Path(__file__).parents[2] / ".github" / "scripts" / "summarize.py"
    spec = importlib.util.spec_from_file_location("atom_ci_summarize", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(**metrics):
    return {
        "benchmark_backend": "ATOM",
        "benchmark_model_name": "fixture-model",
        "random_input_len": 8192,
        "random_output_len": 1024,
        "max_concurrency": 8,
        "output_throughput": metrics.get("output_throughput", 100.0),
        "total_token_throughput": metrics.get("total_token_throughput", 100.0),
        "mean_ttft_ms": metrics.get("mean_ttft_ms", 100.0),
        "mean_tpot_ms": metrics.get("mean_tpot_ms", 100.0),
    }


def test_hidden_ttft_trigger_is_explicit(capsys):
    summarize = _load_summarize()
    baseline = _row()
    current = _row(output_throughput=99.0, mean_tpot_ms=99.0, mean_ttft_ms=111.0)

    count, regressions = summarize.print_regression_report([current], [baseline])
    capsys.readouterr()

    assert count == 1
    assert regressions[0]["triggered_metrics"] == ["mean_ttft_ms"]


def test_multiple_trigger_metrics_preserve_classifier_semantics(capsys):
    summarize = _load_summarize()
    baseline = _row()
    current = _row(output_throughput=94.0, total_token_throughput=93.0)

    count, regressions = summarize.print_regression_report([current], [baseline])
    capsys.readouterr()

    assert count == 1
    assert regressions[0]["triggered_metrics"] == [
        "output_throughput",
        "total_token_throughput",
    ]
