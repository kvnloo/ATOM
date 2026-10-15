# SPDX-License-Identifier: MIT
"""CPU contract tests for synthetic agentic replay; no server/GPU involved."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "atom" / "benchmarks" / "session_replay.py"
FIXTURE = Path(__file__).parent / "fixtures" / "agentic_session_replay_v1.json"
spec = importlib.util.spec_from_file_location("session_replay", SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.fixture
def fixture():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def plan(fixture):
    return replay.compile_plan(fixture)


def observations(plan):
    # Construct synthetic observation spans only to test parser and aggregation.
    rows = []
    for i, r in enumerate(plan["requests"]):
        start = 1_700_000_000_000_000_000 + i * 1_000_000_000
        rows.append({
            "request_id": r["request_id"],
            "session_id": r["session_id"],
            "parent_request_id": r["parent_request_id"],
            "status": r["expected_terminal"],
            "start_ns": str(start), "end_ns": str(start + 2_000_000_000),
            "tool_pause_ns": str(r["planned_tool_pause_ms"] * 1_000_000),
            "think_ns": str(r["planned_think_ms"] * 1_000_000),
        })
    return rows


def test_four_scenarios_and_both_endpoints(fixture, plan):
    assert len(fixture["sessions"]) == 4
    assert len(plan["requests"]) == 12
    assert {r["endpoint"] for r in plan["requests"]} == {"chat", "responses"}
    assert {r["expected_terminal"] for r in plan["requests"]} == {"cancelled", "error", "success"}


def test_plan_deterministic_under_json_reformat(fixture, plan):
    again = json.loads(json.dumps(fixture, indent=3, sort_keys=True))
    assert replay.compile_plan(again) == plan
    changed = copy.deepcopy(fixture)
    changed["seed"] = 43
    assert replay.compile_plan(changed)["scenario_sha256"] != plan["scenario_sha256"]
    assert replay.compile_plan(changed)["requests"][0]["request_id"] != plan["requests"][0]["request_id"]


def test_plan_does_not_export_raw_prompt(fixture, plan):
    text = json.dumps(plan)
    assert "Inspect toy code" not in text
    assert "Simulate an external cache miss" not in text
    assert all(r["prefix_group"] != "" for r in plan["requests"] if r["prefix_group"] is not None)


def test_parallel_fanout_parent_identity(plan):
    by_turn = {(r["session_id"], r["turn_id"]): r for r in plan["requests"]}
    parent = by_turn["synthetic-research", "plan"]["request_id"]
    assert by_turn["synthetic-research", "source-a"]["parent_request_id"] == parent
    assert by_turn["synthetic-research", "source-b"]["parent_request_id"] == parent
    assert by_turn["synthetic-coding", "edit"]["parent_request_id"] == by_turn["synthetic-coding", "inspect"]["request_id"]


def test_reconcile_preserves_terminal_and_unknown_metrics(plan):
    summary = replay.reconcile(plan, observations(plan))
    assert summary["status_counts"] == {"success": 10, "error": 1, "cancelled": 1}
    assert summary["request_count"] == 12
    assert summary["result"] == "matched"
    assert summary["unexpected_terminals"] == []
    assert summary["sessions"]["synthetic-recovery"]["statuses"]["cancelled"] == 1
    assert summary["sessions"]["synthetic-research"]["client_request_s"] == 8
    assert summary["sessions"]["synthetic-research"]["request_window_s"] is None
    assert summary["sessions"]["synthetic-research"]["session_wall_s"] is None
    assert summary["sessions"]["synthetic-research"]["gpu_compute_s"] is None
    assert summary["sessions"]["synthetic-durable"]["observed_think_s"] == 1800


def test_missing_optional_observations_are_unknown_not_partial_sum(plan):
    events = observations(plan)
    events[0].pop("tool_pause_ns")
    events[0].pop("start_ns")
    events[0].pop("end_ns")
    summary = replay.reconcile(plan, events)
    coding = summary["sessions"]["synthetic-coding"]
    assert coding["observed_tool_pause_s"] is None
    assert coding["client_request_s"] is None
    assert coding["request_window_s"] is None
    assert coding["observed_think_s"] == 0.3


def test_tool_pause_not_counted_as_request_latency(plan):
    events = observations(plan)
    summary = replay.reconcile(plan, events)
    coding = summary["sessions"]["synthetic-coding"]
    assert coding["client_request_s"] == 6
    assert coding["observed_tool_pause_s"] == 1.7
    assert coding["observed_think_s"] == 0.3


@pytest.mark.parametrize("mutation,part", [
    (lambda x: x["sessions"][0].update(session_id="synthetic-research"), "duplicate session"),
    (lambda x: x["sessions"][0]["turns"][1].update(turn_id="inspect"), "duplicate turn"),
    (lambda x: x["sessions"][0]["turns"][0].update(endpoint="messages"), "endpoint"),
    (lambda x: x["sessions"][0]["turns"][0].update(tool_pause_ms=-1), "tool_pause_ms"),
    (lambda x: x["sessions"][0]["turns"][0].update(tool_pause_ms=True), "tool_pause_ms"),
    (lambda x: x["sessions"][0]["turns"][0].update(parent_turn_id="verify"), "parent_turn_id"),
    (lambda x: x["sessions"][0]["turns"][0].update(expected_terminal="pending"), "expected_terminal"),
    (lambda x: x.update(seed=True), "seed"),
    (lambda x: x["sessions"][0]["turns"][0].update(input=[]), "input"),
])
def test_bad_fixtures_fail_closed(fixture, mutation, part):
    mutation(fixture)
    with pytest.raises(replay.ReplayContractError, match=part):
        replay.compile_plan(fixture)


@pytest.mark.parametrize("mutation,part", [
    (lambda r: r.pop(), "missing terminal"),
    (lambda r: r.append(copy.deepcopy(r[0])), "duplicate terminal"),
    (lambda r: r[0].update(request_id="unknown"), "unknown request_id"),
    (lambda r: r[0].update(end_ns="1"), "ends before"),
    (lambda r: r[0].update(start_ns=1.7000000000000000e18), "integer nanoseconds"),
])
def test_bad_observations_fail_closed(plan, mutation, part):
    rows = observations(plan)
    mutation(rows)
    with pytest.raises(replay.ReplayContractError, match=part):
        replay.reconcile(plan, rows)


def test_partial_timestamp_pair_rejected(plan):
    rows = observations(plan)
    rows[0].pop("start_ns")
    with pytest.raises(replay.ReplayContractError, match="incomplete request timestamp"):
        replay.reconcile(plan, rows)


def test_nonfinite_fixture_rejected(fixture):
    fixture["sessions"][0]["turns"][0]["input"][0]["value"] = float("nan")
    with pytest.raises(replay.ReplayContractError, match="not finite"):
        replay.compile_plan(fixture)


def test_unexpected_terminal_is_preserved_as_failed_outcome(plan):
    rows = observations(plan)
    rows[0]["status"] = "error"
    result = replay.reconcile(plan, rows)
    assert result["result"] == "mismatch"
    assert result["unexpected_terminals"] == [{
        "request_id": rows[0]["request_id"],
        "expected": "success", "observed": "error"
    }]
    assert result["status_counts"]["error"] == 2


def test_observation_wrong_session_rejected(plan):
    rows = observations(plan)
    rows[0]["session_id"] = "synthetic-research"
    with pytest.raises(replay.ReplayContractError, match="mismatched session"):
        replay.reconcile(plan, rows)


def test_observation_wrong_parent_rejected(plan):
    rows = observations(plan)
    rows[1]["parent_request_id"] = "wrong-parent"
    with pytest.raises(replay.ReplayContractError, match="mismatched parent"):
        replay.reconcile(plan, rows)


def test_negative_observed_pause_rejected(plan):
    rows = observations(plan)
    rows[0]["tool_pause_ns"] = -10
    with pytest.raises(replay.ReplayContractError, match="non-negative nanoseconds"):
        replay.reconcile(plan, rows)


def explicit_boundaries(plan):
    """Synthetic monotonic boundary pairs, each session's own clock source."""
    result = []
    for session_id in dict.fromkeys(r["session_id"] for r in plan["requests"]):
        result.extend([
            {"session_id": session_id, "event": "session_started",
             "timestamp_ns": "1000000000000000000", "clock_id": f"runner/{session_id}"},
            {"session_id": session_id, "event": "session_finished",
             "timestamp_ns": "1000000008000000000", "clock_id": f"runner/{session_id}"},
        ])
    return result


def test_explicit_boundaries_supply_wall_not_gpu_compute(plan):
    result = replay.reconcile(plan, observations(plan), boundaries=explicit_boundaries(plan))
    for session in result["sessions"].values():
        assert session["session_wall_s"] == 8
        assert session["gpu_compute_s"] is None


def test_no_clock_provenance_means_unknown_request_window(plan):
    result = replay.reconcile(plan, observations(plan))
    assert result["sessions"]["synthetic-research"]["request_window_s"] is None
    assert result["sessions"]["synthetic-research"]["client_request_s"] == 8


def test_same_request_clock_allows_request_window(plan):
    rows = observations(plan)
    for row in rows:
        row["clock_id"] = "single-monotonic-clock"
    result = replay.reconcile(plan, rows)
    assert result["sessions"]["synthetic-research"]["request_window_s"] == 5


def test_mixed_request_clock_disallows_request_window(plan):
    rows = observations(plan)
    for row in rows:
        row["clock_id"] = f"runner/{row['request_id']}"
    result = replay.reconcile(plan, rows)
    assert result["sessions"]["synthetic-research"]["request_window_s"] is None
    assert result["sessions"]["synthetic-research"]["client_request_s"] == 8


@pytest.mark.parametrize("mutation,part", [
    (lambda x: x.pop(), "missing session boundary"),
    (lambda x: x.append(copy.deepcopy(x[0])), "duplicate session boundary"),
    (lambda x: x[0].update(session_id="foreign"), "unknown session"),
    (lambda x: x[0].update(event="paused"), "unknown session event"),
    (lambda x: x[0].update(timestamp_ns="NaN"), "integer nanoseconds"),
    (lambda x: x[0].update(timestamp_ns=1e18), "integer nanoseconds"),
    (lambda x: x[0].update(clock_id=""), "clock_id"),
    (lambda x: x[1].update(clock_id="other-clock"), "mixed clock"),
    (lambda x: x[1].update(timestamp_ns="999999999999999999"), "ends before"),
])
def test_invalid_session_boundaries_fail_closed(plan, mutation, part):
    bounds = explicit_boundaries(plan)
    mutation(bounds)
    with pytest.raises(replay.ReplayContractError, match=part):
        replay.reconcile(plan, observations(plan), boundaries=bounds)


def test_same_clock_outside_session_window_rejected(plan):
    rows = observations(plan)
    bounds = explicit_boundaries(plan)
    # One row shares runner clock but lies outside the session's [start, end] range.
    rows[0]["clock_id"] = bounds[0]["clock_id"]
    with pytest.raises(replay.ReplayContractError, match="outside session boundaries"):
        replay.reconcile(plan, rows, boundaries=bounds)


def test_other_clock_request_not_compared_against_session_wall(plan):
    rows = observations(plan)
    rows[0]["clock_id"] = "separate-host-monotonic"
    assert replay.reconcile(plan, rows, boundaries=explicit_boundaries(plan))["sessions"]["synthetic-coding"]["session_wall_s"] == 8


def test_clock_id_without_request_timestamp_rejected(plan):
    rows = observations(plan)
    rows[0]["clock_id"] = "runner"
    rows[0].pop("start_ns")
    rows[0].pop("end_ns")
    with pytest.raises(replay.ReplayContractError, match="clock_id requires request timestamps"):
        replay.reconcile(plan, rows)


def test_partial_explicit_session_boundaries_rejected(plan):
    with pytest.raises(replay.ReplayContractError, match="missing session boundary"):
        replay.reconcile(plan, observations(plan), boundaries=[])


def test_explicit_durable_wall_includes_wait_without_inflating_inference(plan):
    bounds = explicit_boundaries(plan)
    for row in bounds:
        if row["session_id"] == "synthetic-durable" and row["event"] == "session_finished":
            row["timestamp_ns"] = "1000003600000000000"  # synthetic 3600-second session
    result = replay.reconcile(plan, observations(plan), boundaries=bounds)
    durable = result["sessions"]["synthetic-durable"]
    assert durable["session_wall_s"] == 3600
    assert durable["client_request_s"] < durable["session_wall_s"]
    assert durable["gpu_compute_s"] is None


def test_cli_accepts_explicit_session_boundaries(tmp_path, plan):
    import subprocess
    import sys

    terminal_file = tmp_path / "synthetic-terminals.jsonl"
    boundary_file = tmp_path / "synthetic-boundaries.jsonl"
    terminal_file.write_text("\n".join(map(json.dumps, observations(plan))))
    boundary_file.write_text("\n".join(map(json.dumps, explicit_boundaries(plan))))
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE),
         "--observations", str(terminal_file), "--boundaries", str(boundary_file)],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["source"] == "observed_request_terminals_and_session_boundaries"
    assert len(result["sessions"]) == 4
    assert result["sessions"]["synthetic-coding"]["session_wall_s"] == 8
