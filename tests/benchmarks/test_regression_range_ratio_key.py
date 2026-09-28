# SPDX-License-Identifier: MIT
"""Regression baselines must not mix different random length distributions."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_summarize():
    path = Path(__file__).parents[2] / ".github" / "scripts" / "summarize.py"
    spec = importlib.util.spec_from_file_location("atom_ci_summarize_ratio", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(ratio):
    return {
        "benchmark_backend": "ATOM",
        "benchmark_model_name": "fixture-model",
        "random_input_len": 8192,
        "random_output_len": 1024,
        "max_concurrency": 8,
        "random_range_ratio": ratio,
    }


def test_different_range_ratios_do_not_share_a_baseline_key():
    summarize = _load_summarize()

    assert summarize._config_key(_row(0.8)) != summarize._config_key(_row(1.0))


def test_numeric_and_string_spellings_of_same_ratio_match():
    summarize = _load_summarize()

    assert summarize._config_key(_row(0.8)) == summarize._config_key(_row("0.8"))


def test_missing_ratio_is_distinct_from_an_explicit_ratio():
    summarize = _load_summarize()
    missing = _row(None)
    missing.pop("random_range_ratio")

    assert summarize._config_key(missing) != summarize._config_key(_row(0.8))
