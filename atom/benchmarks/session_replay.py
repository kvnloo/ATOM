# SPDX-License-Identifier: MIT
"""CPU-only deterministic plan and completion checks for agentic session replay.

This is a planning/QA layer, not a load generator or inference performance
measurement. No raw prompts are exported in the plan. Requirement context:
https://github.com/kvnloo/ATOM/issues/15
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ENDPOINTS = frozenset({"chat", "responses"})
TERMINALS = frozenset({"success", "error", "cancelled", "timeout"})


class ReplayContractError(ValueError):
    """The replay fixture or observed completion violates its contract."""


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayContractError(f"{label} must be a non-empty string")
    return value


def _duration(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReplayContractError(
            f"{label} must be a non-negative integer milliseconds"
        )
    return value


def _ns(value: Any, label: str) -> int:
    """Parse precise timestamps; binary floats silently lose nanoseconds."""
    if isinstance(value, bool) or not (
        isinstance(value, int) or (isinstance(value, str) and value.isdecimal())
    ):
        raise ReplayContractError(
            f"{label} must be integer nanoseconds or decimal string"
        )
    try:
        parsed = int(value)
    except ValueError as exc:
        # CPython limits decimal-to-int conversion length; return a contract
        # error rather than crashing the replay CLI on untrusted JSONL input.
        raise ReplayContractError(
            f"{label} must be parseable integer nanoseconds"
        ) from exc
    if parsed < 0:
        raise ReplayContractError(f"{label} must be non-negative nanoseconds")
    return parsed


def canonical_sha256(value: Any) -> str:
    try:
        canonical = json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (ValueError, TypeError) as exc:
        raise ReplayContractError(
            "fixture is not finite, JSON-serializable data"
        ) from exc
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_fixture(fixture: dict[str, Any]) -> None:
    """Check the bounded v1 fixture contract before any request is dispatched."""
    if (
        not isinstance(fixture, dict)
        or type(fixture.get("schema_version")) is not int
        or fixture["schema_version"] != SCHEMA_VERSION
    ):
        raise ReplayContractError("unsupported replay schema_version")
    seed = fixture.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ReplayContractError("seed must be a non-negative integer")
    sessions = fixture.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        raise ReplayContractError("sessions must be a non-empty list")

    known_sessions: set[str] = set()
    for s_idx, session in enumerate(sessions):
        if not isinstance(session, dict):
            raise ReplayContractError(f"sessions[{s_idx}] must be an object")
        session_id = _id(session.get("session_id"), f"sessions[{s_idx}].session_id")
        if session_id in known_sessions:
            raise ReplayContractError(f"duplicate session_id {session_id!r}")
        known_sessions.add(session_id)
        turns = session.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ReplayContractError(f"{session_id}: turns must be a non-empty list")
        previous_turns: set[str] = set()
        for idx, turn in enumerate(turns):
            label = f"{session_id}.turns[{idx}]"
            if not isinstance(turn, dict):
                raise ReplayContractError(f"{label} must be an object")
            turn_id = _id(turn.get("turn_id"), f"{label}.turn_id")
            if turn_id in previous_turns:
                raise ReplayContractError(
                    f"{session_id}: duplicate turn_id {turn_id!r}"
                )
            if (
                not isinstance(turn.get("endpoint"), str)
                or turn["endpoint"] not in ENDPOINTS
            ):
                raise ReplayContractError(f"{label}.endpoint must be chat or responses")
            if not isinstance(turn.get("input"), list) or not turn["input"]:
                raise ReplayContractError(f"{label}.input must be a non-empty list")
            for field in ("think_time_ms", "tool_pause_ms"):
                _duration(turn.get(field, 0), f"{label}.{field}")
            terminal = turn.get("expected_terminal", "success")
            if not isinstance(terminal, str) or terminal not in TERMINALS:
                raise ReplayContractError(f"{label}.expected_terminal unsupported")
            parent = turn.get("parent_turn_id")
            if parent is not None and (
                not isinstance(parent, str) or parent not in previous_turns
            ):
                raise ReplayContractError(
                    f"{label}.parent_turn_id must refer to an earlier turn "
                    "in the same session"
                )
            _id(turn.get("branch", "main"), f"{label}.branch")
            if "prefix_group" in turn:
                _id(turn["prefix_group"], f"{label}.prefix_group")
            previous_turns.add(turn_id)


def compile_plan(fixture: dict[str, Any]) -> dict[str, Any]:
    """Stable, content-addressed identities without copying sensitive inputs."""
    validate_fixture(fixture)
    digest = canonical_sha256(fixture)
    requests: list[dict[str, Any]] = []
    for session in fixture["sessions"]:
        ids: dict[str, str] = {}
        for turn in session["turns"]:
            turn_id = turn["turn_id"]
            req_id = "rep-" + hashlib.sha256(
                f"{digest}\0{session['session_id']}\0{turn_id}".encode()
            ).hexdigest()[:24]
            parent = turn.get("parent_turn_id")
            requests.append(
                {
                    "request_id": req_id,
                    "session_id": session["session_id"],
                    "turn_id": turn_id,
                    "parent_request_id": ids.get(parent),
                    "endpoint": turn["endpoint"],
                    "branch": turn.get("branch", "main"),
                    "prefix_group": turn.get("prefix_group"),
                    "planned_think_ms": turn.get("think_time_ms", 0),
                    "planned_tool_pause_ms": turn.get("tool_pause_ms", 0),
                    "expected_terminal": turn.get("expected_terminal", "success"),
                }
            )
            ids[turn_id] = req_id
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_sha256": digest,
        "seed": fixture["seed"],
        "requests": requests,
    }


def _session_spans(
    session_ids: set[str], boundaries: list[dict[str, Any]] | None
) -> dict[str, tuple[int, int, str]]:
    """Measure wall duration only between explicit same-clock session markers.

    ``clock_id`` names one monotonic clock domain, not a machine's wall clock.
    Different hosts/processes must not reuse it unless their timestamps truly
    share that domain. This is a parser contract, not a clock synchronizer.
    """
    if boundaries is None:
        return {}
    if not isinstance(boundaries, list):
        raise ReplayContractError("session boundaries must be a list")
    seen: dict[str, dict[str, tuple[int, str]]] = {}
    for row in boundaries:
        if not isinstance(row, dict):
            raise ReplayContractError("every session boundary must be an object")
        sid = row.get("session_id")
        if not isinstance(sid, str) or sid not in session_ids:
            raise ReplayContractError(f"unknown session in boundary: {sid!r}")
        event = row.get("event")
        if event not in ("session_started", "session_finished"):
            raise ReplayContractError(f"unknown session event {event!r}")
        timestamp = _ns(row.get("timestamp_ns"), f"{sid}.{event}.timestamp_ns")
        clock = _id(row.get("clock_id"), f"{sid}.{event}.clock_id")
        if event in seen.setdefault(sid, {}):
            raise ReplayContractError(f"duplicate session boundary {sid}.{event}")
        seen[sid][event] = (timestamp, clock)

    spans: dict[str, tuple[int, int, str]] = {}
    for sid in sorted(session_ids):
        events = seen.get(sid, {})
        if set(events) != {"session_started", "session_finished"}:
            raise ReplayContractError(f"missing session boundary for {sid}")
        start, a_clock = events["session_started"]
        end, b_clock = events["session_finished"]
        if a_clock != b_clock:
            raise ReplayContractError(f"{sid}: mixed clock domains across boundaries")
        if end < start:
            raise ReplayContractError(f"{sid}: session ends before it starts")
        spans[sid] = (start, end, a_clock)
    return spans


def reconcile(
    plan: dict[str, Any],
    events: list[dict[str, Any]],
    boundaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reconcile actual terminals; missing, duplicate and foreign rows are errors.

    Client-observed request time is not GPU compute time. Tool and think delays
    are never added to request latency. Unknown server-side compute stays None.
    Cross-request windows require one explicit request clock domain; session
    wall time requires explicit matching start/end markers on one clock.
    """
    requests = {r["request_id"]: r for r in plan["requests"]}
    if len(requests) != len(plan["requests"]):
        raise ReplayContractError("plan contains duplicate request IDs")
    spans = _session_spans({r["session_id"] for r in plan["requests"]}, boundaries)
    seen: set[str] = set()
    status_counts: Counter[str] = Counter()
    unexpected_terminals: list[dict[str, str]] = []
    session: dict[str, dict[str, Any]] = {}
    for req in plan["requests"]:
        session.setdefault(req["session_id"], {
            "statuses": Counter(), "request_start_ns": None, "request_end_ns": None,
            "client_request_s": 0.0, "observed_tool_pause_s": 0.0,
            "observed_think_s": 0.0, "gpu_compute_s": None,
            "_timestamps": 0, "_tool_pauses": 0, "_thinks": 0,
            "_request_clocks": set(), "_stamped_requests": [],
        })
    for row in events:
        if not isinstance(row, dict):
            raise ReplayContractError("every observation must be an object")
        req_id = row.get("request_id")
        if not isinstance(req_id, str) or req_id not in requests:
            raise ReplayContractError(f"observation for unknown request_id {req_id!r}")
        if req_id in seen:
            raise ReplayContractError(f"duplicate terminal for request_id {req_id!r}")
        seen.add(req_id)
        expected = requests[req_id]
        status = row.get("status")
        if not isinstance(status, str) or status not in TERMINALS:
            raise ReplayContractError(f"{req_id}: missing or invalid terminal status")
        if row.get("session_id", expected["session_id"]) != expected["session_id"]:
            raise ReplayContractError(f"{req_id}: mismatched session identity")
        if row.get("turn_id", expected["turn_id"]) != expected["turn_id"]:
            raise ReplayContractError(f"{req_id}: mismatched turn identity")
        if row.get("parent_request_id", expected["parent_request_id"]) != expected["parent_request_id"]:
            raise ReplayContractError(f"{req_id}: mismatched parent identity")
        if status != expected["expected_terminal"]:
            # Unexpected responses are benchmark outcomes, not malformed input.
            # Retain them in summaries instead of hiding a genuine failure.
            unexpected_terminals.append({
                "request_id": req_id,
                "expected": expected["expected_terminal"],
                "observed": status,
            })
        status_counts[status] += 1
        s = session[expected["session_id"]]
        s["statuses"][status] += 1
        a = row.get("start_ns")
        b = row.get("end_ns")
        if "clock_id" in row and (a is None or b is None):
            raise ReplayContractError(f"{req_id}: clock_id requires request timestamps")
        if a is not None or b is not None:
            if a is None or b is None:
                raise ReplayContractError(
                    f"{req_id}: incomplete request timestamp pair"
                )
            start = _ns(a, f"{req_id}.start_ns")
            end = _ns(b, f"{req_id}.end_ns")
            if end < start:
                raise ReplayContractError(f"{req_id}: request ends before it starts")
            if s["request_start_ns"] is None:
                s["request_start_ns"] = start
            else:
                s["request_start_ns"] = min(start, s["request_start_ns"])
            if s["request_end_ns"] is None:
                s["request_end_ns"] = end
            else:
                s["request_end_ns"] = max(end, s["request_end_ns"])
            s["client_request_s"] += (end - start) / 1e9
            s["_timestamps"] += 1
            clock = (
                _id(row["clock_id"], f"{req_id}.clock_id")
                if "clock_id" in row else None
            )
            s["_request_clocks"].add(clock)
            s["_stamped_requests"].append((req_id, start, end, clock))
        for key, target, counter in (
            ("tool_pause_ns", "observed_tool_pause_s", "_tool_pauses"),
            ("think_ns", "observed_think_s", "_thinks"),
        ):
            if key in row:
                value = _ns(row[key], f"{req_id}.{key}")
                s[target] += value / 1e9
                s[counter] += 1

    missing = sorted(set(requests) - seen)
    if missing:
        raise ReplayContractError(
            f"missing terminal for {len(missing)} request(s): {missing}"
        )
    for sid, value in session.items():
        a, b = value.pop("request_start_ns"), value.pop("request_end_ns")
        clocks = value.pop("_request_clocks")
        stamped = value.pop("_stamped_requests")
        n = sum(value["statuses"].values())
        if value.pop("_timestamps") != n:
            value["request_window_s"] = None
            value["client_request_s"] = None
        else:
            # A cross-request min/max span is meaningless across clock domains.
            value["request_window_s"] = (
                (b - a) / 1e9
                if a is not None and len(clocks) == 1 and None not in clocks
                else None
            )
        value["request_window_clock_id"] = (
            next(iter(clocks)) if value["request_window_s"] is not None else None
        )
        if value.pop("_tool_pauses") != n:
            value["observed_tool_pause_s"] = None
        if value.pop("_thinks") != n:
            value["observed_think_s"] = None
        value["session_wall_s"] = None
        value["session_wall_clock_id"] = None
        if sid in spans:
            begin, finish, boundary_clock = spans[sid]
            for req_id, start, end, request_clock in stamped:
                if request_clock == boundary_clock and not (
                    begin <= start <= end <= finish
                ):
                    raise ReplayContractError(
                        f"{req_id}: request outside session boundaries on same clock"
                    )
            value["session_wall_s"] = (finish - begin) / 1e9
            value["session_wall_clock_id"] = boundary_clock
        value["statuses"] = dict(value["statuses"])
    return {
        "scenario_sha256": plan["scenario_sha256"],
        "request_count": len(requests),
        "status_counts": dict(status_counts),
        "unexpected_terminals": unexpected_terminals,
        "result": "mismatch" if unexpected_terminals else "matched",
        "sessions": session,
        "source": (
            "observed_request_terminals_and_session_boundaries"
            if boundaries is not None else "observed_request_terminals"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument(
        "--observations",
        type=Path,
        help="optional JSONL terminal observations to reconcile",
    )
    parser.add_argument(
        "--boundaries", type=Path,
        help="optional JSONL explicit session start/end markers (requires --observations)",
    )
    args = parser.parse_args()
    if args.boundaries and not args.observations:
        parser.error("--boundaries requires --observations")
    try:
        plan = compile_plan(json.loads(args.fixture.read_text(encoding="utf-8")))
        output = plan
        if args.observations:
            observations = [
                json.loads(line)
                for line in args.observations.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            boundaries = None
            if args.boundaries:
                boundaries = [
                    json.loads(line)
                    for line in args.boundaries.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            output = reconcile(plan, observations, boundaries=boundaries)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, ReplayContractError, json.JSONDecodeError) as exc:
        print(f"replay contract: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
