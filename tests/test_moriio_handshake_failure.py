# SPDX-License-Identifier: MIT
"""CPU contract for MoRIIO background-handshake failure propagation."""

from __future__ import annotations

import importlib
import queue
import sys
import threading
from collections import defaultdict
from concurrent.futures import Future
from types import ModuleType, SimpleNamespace


def _module(monkeypatch):
    triton = ModuleType("triton")
    triton.jit = lambda fn: fn
    triton.cdiv = lambda x, y: (x + y - 1) // y
    triton.next_power_of_2 = lambda x: 1 << (max(1, x) - 1).bit_length()
    triton_language = ModuleType("triton.language")
    triton.language = triton_language
    monkeypatch.setitem(sys.modules, "triton", triton)
    monkeypatch.setitem(sys.modules, "triton.language", triton_language)

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

    name = "atom.kv_transfer.disaggregation.moriio.moriio_connector"
    return importlib.import_module(name)


class _ImmediateExecutor:
    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _connector(monkeypatch, *, fail_dp_rank=None):
    module = _module(monkeypatch)
    connector = module.MoRIIOConnector.__new__(module.MoRIIOConnector)
    connector.is_producer = False
    connector._remote_agents = {}
    connector._handshake_lock = threading.RLock()
    connector._handshake_futures = {}
    connector._ready_requests = queue.Queue()
    connector._handshake_executor = _ImmediateExecutor()
    connector.load_ready_flag = {}
    connector.write_ready_flags = {}
    connector.failed_recving = set()
    connector._recving_transfers = defaultdict(list)
    connector._recving_transfers_callback_addr = {}
    connector.done_sending = set()
    connector.request_id_to_transfer_id = {}
    connector.moriio_wrapper = SimpleNamespace(lock=threading.Lock())

    def execute(_host, _port, _tp_size, expected_engine_id, remote_dp_rank=0):
        if remote_dp_rank == fail_dp_rank:
            raise RuntimeError(f"handshake failed for dp={remote_dp_rank}")
        return {f"agent:{expected_engine_id}"}

    connector._execute_handshake = execute
    connector._issued = []
    connector._issue_read_for_req = lambda req_id, meta: connector._issued.append(
        (req_id, meta.remote_engine_id)
    )
    return connector


def _metadata(remote_dp_size=2):
    meta = SimpleNamespace(
        remote_host="10.0.0.2",
        remote_handshake_port=6301,
        tp_size=1,
        remote_dp_size=remote_dp_size,
        remote_dp_rank=0,
        local_block_ids=[1],
        remote_block_ids=[2],
        remote_engine_id=None,
    )
    return SimpleNamespace(
        reqs_to_recv={"req-7": meta},
        request_id_to_transfer_id={"req-7": "transfer-7"},
    )


def test_failed_handshake_group_never_issues_read_and_reports_receive_failure(
    monkeypatch,
):
    connector = _connector(monkeypatch, fail_dp_rank=1)

    connector.start_load_kv(_metadata())

    assert connector._issued == []
    assert connector._ready_requests.empty()
    assert connector.load_ready_flag["10.0.0.2:6301"] is False
    assert "10.0.0.2:6301" not in connector.write_ready_flags

    output = connector.get_finished()
    assert output.finished_sending == set()
    assert output.finished_recving == set()
    assert output.failed_recving == {"req-7"}

    # The terminal is drained once.
    assert connector.get_finished() == (set(), set())


def test_successful_handshake_group_preserves_legacy_success_path(monkeypatch):
    connector = _connector(monkeypatch)

    connector.start_load_kv(_metadata())

    assert connector._issued == [("req-7", "10.0.0.2:6301")]
    assert connector.load_ready_flag["10.0.0.2:6301"] is True
    assert connector.write_ready_flags["10.0.0.2:6301"] is True
    assert connector.get_finished() == (set(), set())
