# SPDX-License-Identifier: MIT
"""CPU contract for draining every first-contact MoRIIO handshake in a batch."""

from __future__ import annotations

import importlib
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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

    return importlib.import_module(
        "atom.kv_transfer.disaggregation.moriio.moriio_connector"
    )


class _CountingExecutor:
    def __init__(self):
        self._inner = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self.submitted = 0

    def submit(self, fn, *args):
        with self._lock:
            self.submitted += 1
        return self._inner.submit(fn, *args)

    def shutdown(self):
        self._inner.shutdown(wait=True)


def _meta(req_id):
    return SimpleNamespace(
        req_id=req_id,
        remote_host="10.0.0.2",
        remote_handshake_port=6301,
        tp_size=1,
        remote_dp_size=1,
        remote_dp_rank=0,
        local_block_ids=[1],
        remote_block_ids=[2],
        remote_engine_id=None,
    )


def _metadata(*req_ids):
    return SimpleNamespace(
        reqs_to_recv={req_id: _meta(req_id) for req_id in req_ids},
        request_id_to_transfer_id={
            req_id: f"transfer-{req_id}" for req_id in req_ids
        },
    )


def _connector(monkeypatch, release):
    module = _module(monkeypatch)
    connector = module.MoRIIOConnector.__new__(module.MoRIIOConnector)
    connector.is_producer = False
    connector._remote_agents = {}
    connector._handshake_lock = threading.RLock()
    connector._handshake_futures = {}
    connector._ready_requests = queue.Queue()
    connector._handshake_executor = _CountingExecutor()
    connector.load_ready_flag = {}
    connector.write_ready_flags = {}
    connector.request_id_to_transfer_id = {}
    connector._issued = []

    def execute(_host, _port, _tp_size, expected_engine_id, _remote_dp_rank=0):
        if not release.wait(timeout=5):
            raise TimeoutError("test handshake was not released")
        return {f"agent:{expected_engine_id}"}

    connector._execute_handshake = execute
    connector._issue_read_for_req = lambda req_id, meta: connector._issued.append(
        (req_id, meta.remote_engine_id)
    )
    return connector


def _wait_for_submissions(connector, count):
    deadline = time.monotonic() + 5
    while connector._handshake_executor.submitted < count:
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"expected {count} submissions, saw "
                f"{connector._handshake_executor.submitted}"
            )
        time.sleep(0.001)


def test_two_first_contact_requests_are_both_read_and_leave_no_ready_work(monkeypatch):
    release = threading.Event()
    connector = _connector(monkeypatch, release)
    worker = threading.Thread(
        target=connector.start_load_kv,
        args=(_metadata("a", "b"),),
    )
    worker.start()

    # Each request schedules one handshake task plus one aggregate waiter.
    _wait_for_submissions(connector, 4)
    release.set()
    worker.join(timeout=5)
    connector._handshake_executor.shutdown()

    assert not worker.is_alive()
    assert connector._issued == [
        ("a", "10.0.0.2:6301"),
        ("b", "10.0.0.2:6301"),
    ]
    assert connector._ready_requests.empty()


def test_one_first_contact_request_preserves_existing_success_path(monkeypatch):
    release = threading.Event()
    connector = _connector(monkeypatch, release)
    worker = threading.Thread(
        target=connector.start_load_kv,
        args=(_metadata("only"),),
    )
    worker.start()

    _wait_for_submissions(connector, 2)
    release.set()
    worker.join(timeout=5)
    connector._handshake_executor.shutdown()

    assert not worker.is_alive()
    assert connector._issued == [("only", "10.0.0.2:6301")]
    assert connector._ready_requests.empty()


def test_known_peer_still_issues_reads_without_new_handshake(monkeypatch):
    release = threading.Event()
    connector = _connector(monkeypatch, release)
    connector._remote_agents["10.0.0.2:6301_dp0"] = {"agent"}

    connector.start_load_kv(_metadata("a", "b"))
    connector._handshake_executor.shutdown()

    assert connector._handshake_executor.submitted == 0
    assert connector._issued == [
        ("a", "10.0.0.2:6301"),
        ("b", "10.0.0.2:6301"),
    ]
    assert connector._ready_requests.empty()
