# SPDX-License-Identifier: MIT
"""Regression issues must not present one arbitrary profiler summary as global."""

from pathlib import Path


def _workflow_text() -> str:
    return (
        Path(__file__).parents[2] / ".github" / "workflows" / "atom-benchmark.yaml"
    ).read_text(encoding="utf-8")


def test_multiple_profiler_summaries_are_explicitly_per_config():
    text = _workflow_text()

    assert "summaries.length > 1" in text
    assert "No single summary is embedded" in text
    assert "inspect each configuration separately" in text


def test_single_profiler_summary_names_its_config():
    text = _workflow_text()

    assert "summaries.length === 1" in text
    assert "summaries[0].config" in text


def test_issue_no_longer_selects_first_summary_and_breaks():
    text = _workflow_text()

    assert "summary = fs.readFileSync(p, 'utf8'); break;" not in text
