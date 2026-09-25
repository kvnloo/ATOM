# SPDX-License-Identifier: MIT
"""CPU contract for MoRIIO receive completion ordering."""

from __future__ import annotations

import importlib
import sys
import threading
from types import ModuleType, SimpleNamespace


class _Status:
    def __init__(self, succeeded: bool) -> None:
        self.succeeded = succeeded
        self.calls = 0

    def Succeeded(self) -> bool:
        self.calls += 1
        return self.succeeded


class _Wrapper:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.notifications: list[tuple[str, str, str]] = []

    def send_notify(self, transfer_id, host, port) -> None:
        self.notifications.append((transfer_id, host, port))


def _connector(monkeypatch, statuses):
    # moriio_connector needs only these AITER rank helpers at import time.
    # The method under test never calls them or creates an RDMA engine.
    aiter = ModuleType("aiter")
    dist = ModuleType("aiter.dist")
    parallel_state = ModuleType("aiter.dist.parallel_state")
    parallel_state.get_dp_group = lambda: SimpleNamespace(
        rank_in_group=0, world_size=1
    )
    parallel_state.get_tp_group = lambda: SimpleNamespace(
        rank_in_group=0, world_size=1
    )
    aiter.dist = dist
    dist.parallel_state = parallel_state
    monkeypatch.setitem(sys.modules, "aiter", aiter)
    monkeypatch.setitem(sys.modules, "aiter.dist", dist)
    monkeypatch.setitem(sys.modules, "aiter.dist.parallel_state", parallel_state)

    module_name = "atom.kv_transfer.disaggregation.moriio.moriio_connector"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    connector = module.MoRIIOConnector.__new__(module.MoRIIOConnector)
    connector.moriio_wrapper = _Wrapper()
    connector._recving_transfers = {"req": list(statuses)}
    connector._recving_transfers_callback_addr = {
        "req": ("127.0.0.1", "7001")
    }
    connector.request_id_to_transfer_id = {"req": "transfer-req"}
    return connector


def test_last_completed_status_does_not_retire_earlier_inflight_transfer(
    monkeypatch,
):
    statuses = [_Status(False), _Status(True)]
    connector = _connector(monkeypatch, statuses)

    assert connector._pop_done_transfers() == set()
    assert connector._recving_transfers["req"] == statuses
    assert connector._recving_transfers_callback_addr["req"] == (
        "127.0.0.1",
        "7001",
    )
    assert connector.moriio_wrapper.notifications == []


def test_all_transfer_statuses_must_complete_before_one_notification(monkeypatch):
    statuses = [_Status(True), _Status(True), _Status(True)]
    connector = _connector(monkeypatch, statuses)

    assert connector._pop_done_transfers() == {"req"}
    assert "req" not in connector._recving_transfers
    assert "req" not in connector._recving_transfers_callback_addr
    assert connector.moriio_wrapper.notifications == [
        ("transfer-req", "127.0.0.1", "7001")
    ]

    assert connector._pop_done_transfers() == set()
    assert connector.moriio_wrapper.notifications == [
        ("transfer-req", "127.0.0.1", "7001")
    ]


def test_nonfinal_pending_status_also_blocks_retirement(monkeypatch):
    statuses = [_Status(True), _Status(False), _Status(True)]
    connector = _connector(monkeypatch, statuses)

    assert connector._pop_done_transfers() == set()
    assert "req" in connector._recving_transfers
    assert connector.moriio_wrapper.notifications == []
