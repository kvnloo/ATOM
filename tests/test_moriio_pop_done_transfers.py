# SPDX-License-Identifier: MIT
# Copyright (C) 2024-2026, Advanced Micro Devices, Inc. All rights reserved.
from __future__ import annotations

import threading
from collections import defaultdict

import pytest
from aiter_stub import stubbed_aiter

with stubbed_aiter():
    MoRIIOConnector = pytest.importorskip(
        "atom.kv_transfer.disaggregation.moriio.moriio_connector",
        reason="P/D backend deps (triton) are absent on a CPU-only runner",
    ).MoRIIOConnector


class _Status:
    def __init__(self, done: bool) -> None:
        self.done = done

    def Succeeded(self) -> bool:
        return self.done


class _Wrapper:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.notified: list[tuple] = []

    def send_notify(self, req_ids, remote_ip, remote_port) -> None:
        self.notified.append((req_ids, remote_ip, remote_port))


def _connector(statuses_by_req):
    conn = MoRIIOConnector.__new__(MoRIIOConnector)
    conn.moriio_wrapper = _Wrapper()
    conn._recving_transfers = defaultdict(list)
    conn._recving_transfers_callback_addr = {}
    conn.request_id_to_transfer_id = {}
    for i, (req_id, statuses) in enumerate(statuses_by_req.items()):
        conn._recving_transfers[req_id].extend(statuses)
        conn._recving_transfers_callback_addr[req_id] = ("10.0.0.1", "6301")
        conn.request_id_to_transfer_id[req_id] = 1000 + i
    return conn


@pytest.mark.parametrize(
    "flags",
    [
        pytest.param([False, True], id="last-done-earlier-in-flight"),
        pytest.param([True, False, True], id="middle-in-flight"),
    ],
)
def test_request_with_a_read_in_flight_is_not_done(flags):
    statuses = [_Status(flag) for flag in flags]
    conn = _connector({"req-a": statuses})
    assert conn._pop_done_transfers() == set()
    assert conn.moriio_wrapper.notified == []
    assert "req-a" in conn._recving_transfers
    assert conn._recving_transfers["req-a"] == statuses
    assert "req-a" in conn._recving_transfers_callback_addr


def test_request_is_done_and_notified_once_every_read_succeeded():
    statuses = [_Status(False), _Status(True)]
    conn = _connector({"req-a": statuses})
    assert conn._pop_done_transfers() == set()
    statuses[0].done = True
    assert conn._pop_done_transfers() == {"req-a"}
    assert conn.moriio_wrapper.notified == [(1000, "10.0.0.1", "6301")]
    assert "req-a" not in conn._recving_transfers
    assert "req-a" not in conn._recving_transfers_callback_addr
    assert conn._pop_done_transfers() == set()
    assert len(conn.moriio_wrapper.notified) == 1


def test_one_request_in_flight_does_not_hold_back_a_finished_one():
    conn = _connector(
        {
            "req-a": [_Status(True), _Status(True)],
            "req-b": [_Status(False), _Status(True)],
        }
    )
    assert conn._pop_done_transfers() == {"req-a"}
    assert conn.moriio_wrapper.notified == [(1000, "10.0.0.1", "6301")]
    assert "req-b" in conn._recving_transfers
