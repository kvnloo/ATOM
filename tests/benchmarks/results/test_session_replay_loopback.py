# SPDX-License-Identifier: MIT
"""Actual loopback HTTP socket observations for the offline replay contract.

This uses a toy localhost server: no ATOM runtime, inference, GPU or remote traffic.
Waiting periods are intentionally scaled down from the synthetic workload. The
measured numbers describe this test process only, NOT model/SLO performance.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures" / "agentic_session_replay_v1.json"
SCRIPT = ROOT / "atom" / "benchmarks" / "session_replay.py"
spec = importlib.util.spec_from_file_location("session_replay_live_probe", SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ToyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(n))
        request_id = payload.get("request_id")
        expected = self.server.expected.get(request_id)
        if expected is None or self.path not in {"/v1/chat/completions", "/v1/responses"}:
            code = 400
        else:
            code = 503 if expected == "error" else 200
        self.server.received.add(request_id)
        if request_id in self.server.fanout_ids:
            self.server.fanout_barrier.wait(timeout=5)
        if expected == "cancelled":
            self.server.cancel_received.set()
            # Permit client to disconnect while this fake request is outstanding.
            time.sleep(0.10)
        else:
            time.sleep(0.015)
        body = json.dumps({"request_id": request_id, "mock": True}).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client-closed socket is not proof of server-side cancellation.

    def log_message(self, *_args):
        pass


def run_loopback():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    plan = replay.compile_plan(fixture)
    requests = plan["requests"]
    expected = {r["request_id"]: r["expected_terminal"] for r in requests}
    by_turn = {(r["session_id"], r["turn_id"]): r for r in requests}
    fanout_ids = {
        by_turn[("synthetic-research", "source-a")]["request_id"],
        by_turn[("synthetic-research", "source-b")]["request_id"],
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), ToyHandler)
    server.expected = expected
    server.received = set()
    server.fanout_ids = fanout_ids
    server.fanout_barrier = threading.Barrier(2)
    server.cancel_received = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    clock_id = f"one-python-process-monotonic:{uuid.uuid4().hex}"
    observations = []
    boundaries = []
    port = server.server_port

    def send_one(request):
        # These sleeps exercise measurement placement; they do NOT reproduce
        # the fixture's real minute-scale durable-agent idle interval.
        planned_think_ms = request["planned_think_ms"]
        planned_pause_ms = request["planned_tool_pause_ms"]
        a = time.monotonic_ns()
        time.sleep(min(planned_think_ms / 1000 * 0.001, 0.025))
        think_ns = time.monotonic_ns() - a
        status = "error"
        start_ns = time.monotonic_ns()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            path = "/v1/chat/completions" if request["endpoint"] == "chat" else "/v1/responses"
            body = json.dumps({"request_id": request["request_id"]}).encode()
            conn.request("POST", path, body, {"Content-Type": "application/json"})
            if request["expected_terminal"] == "cancelled":
                if not server.cancel_received.wait(2):
                    raise RuntimeError("toy server never accepted client-aborted request")
                conn.close()
                status = "cancelled"  # Client-initiated only; no server abort claim.
            else:
                response = conn.getresponse()
                response.read()
                status = "success" if response.status == 200 else "error"
        finally:
            conn.close()
        end_ns = time.monotonic_ns()
        a = time.monotonic_ns()
        time.sleep(min(planned_pause_ms / 1000 * 0.001, 0.025))
        pause_ns = time.monotonic_ns() - a
        return {
            "request_id": request["request_id"], "session_id": request["session_id"],
            "turn_id": request["turn_id"],
            "parent_request_id": request["parent_request_id"], "status": status,
            "start_ns": str(start_ns), "end_ns": str(end_ns), "clock_id": clock_id,
            "think_ns": str(think_ns), "tool_pause_ns": str(pause_ns),
            "observation_origin": "local_loopback_http_client",
            "cancel_scope": "client_connection_only" if status == "cancelled" else None,
        }

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for session in fixture["sessions"]:
                sid = session["session_id"]
                session_start = time.monotonic_ns()
                boundaries.append({"session_id": sid, "event": "session_started",
                                   "timestamp_ns": str(session_start), "clock_id": clock_id})
                depth = {}
                for turn in session["turns"]:
                    parent = turn.get("parent_turn_id")
                    depth[turn["turn_id"]] = depth[parent] + 1 if parent else 0
                for d in sorted(set(depth.values())):
                    layer = [by_turn[(sid, t["turn_id"])] for t in session["turns"]
                             if depth[t["turn_id"]] == d]
                    observations.extend(pool.map(send_one, layer))
                boundaries.append({"session_id": sid, "event": "session_finished",
                                   "timestamp_ns": str(time.monotonic_ns()),
                                   "clock_id": clock_id})
        output = replay.reconcile(plan, observations, boundaries)
        return {"plan": plan, "observations": observations,
                "boundaries": boundaries, "summary": output,
                "mock_server_received": len(server.received),
                "scope": "localhost HTTP, synthetic payloads, real monotonic timestamps; no GPU"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_loopback_all_scenarios_terminal_and_measured_boundaries():
    receipt = run_loopback()
    report = receipt["summary"]
    assert report["result"] == "matched"
    assert report["request_count"] == 12
    assert report["status_counts"] == {"success": 10, "error": 1, "cancelled": 1}
    assert receipt["mock_server_received"] == 12
    assert len(receipt["boundaries"]) == 8
    assert len({o["clock_id"] for o in receipt["observations"]}) == 1
    for value in report["sessions"].values():
        assert value["session_wall_s"] >= value["request_window_s"]
        assert value["client_request_s"] > 0
        assert value["gpu_compute_s"] is None
    assert report["sessions"]["synthetic-durable"]["observed_think_s"] < 1
    assert [o["cancel_scope"] for o in receipt["observations"]
            if o["status"] == "cancelled"] == ["client_connection_only"]
    # Actual concurrent, distinct requests, not just a source DAG annotation.
    fanout = {o["turn_id"]: o for o in receipt["observations"]
              if o["session_id"] == "synthetic-research"}
    a, b = fanout["source-a"], fanout["source-b"]
    assert max(int(a["start_ns"]), int(b["start_ns"])) < min(
        int(a["end_ns"]), int(b["end_ns"]))
    assert report["sessions"]["synthetic-research"]["request_window_s"] < (
        report["sessions"]["synthetic-research"]["client_request_s"])


def test_loopback_reconciler_rejects_lost_terminal():
    receipt = run_loopback()
    try:
        replay.reconcile(receipt["plan"], receipt["observations"][:-1],
                         receipt["boundaries"])
    except replay.ReplayContractError as exc:
        assert "missing terminal" in str(exc)
    else:
        raise AssertionError("lost real terminal was accepted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    output = run_loopback()
    args.receipt.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"request_count": output["summary"]["request_count"],
                      "status_counts": output["summary"]["status_counts"],
                      "reconciliation": output["summary"]["result"],
                      "mock_server_received": output["mock_server_received"]}))
