# SPDX-License-Identifier: MIT
"""CPU contract for MoRIIO first-contact handshake batching."""

from __future__ import annotations

import importlib
import queue
import sys
import threading
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


def _connector(monkeypatch):
    module = _module(monkeypatch)
    connector = module.MoRIIOConnector.__new__(module.MoRIIOConnector)
    connector.is_producer = False
    connector._remote_agents = {}
    connector._handshake_lock = threading.RLock()
    connector._handshake_futures = {}
    connector.load_ready_flag = {}
    connector.write_ready_flags = {}
    connector.request_id_to_transfer_id = {}
    connector._issued = []
    connector._issue_read_for_req = lambda req_id, meta: connector._issued.append(
        (req_id, meta.remote_engine_id)
    )
    # Original source owns this queue; the candidate removes it. The fake
    # handshake uses it only when present so the same test file runs both arms.
    if hasattr(module.MoRIIOConnector, "start_load_kv"):
        connector._ready_requests = queue.Queue()
    return connector


def _meta(host, port=6301):
    return SimpleNamespace(
        remote_host=host,
        remote_handshake_port=port,
        tp_size=1,
        remote_dp_size=1,
        remote_dp_rank=0,
        local_block_ids=[1],
        remote_block_ids=[2],
        remote_engine_id=None,
    )


def _metadata(items):
    return SimpleNamespace(
        reqs_to_recv=dict(items),
        request_id_to_transfer_id={req_id: f"transfer-{req_id}" for req_id, _ in items},
    )


def test_two_first_contact_engines_release_both_requests(monkeypatch):
    connector = _connector(monkeypatch)
    starts = []

    def initiate(req_id, engine_id, meta):
        starts.append(engine_id)
        if hasattr(connector, "_ready_requests"):
            connector._ready_requests.put((req_id, meta))
        if len(starts) == 2:
            for started in starts:
                connector.load_ready_flag[started] = True

    connector._initiate_background_handshake = initiate
    metadata = _metadata(
        [("a", _meta("10.0.0.1")), ("b", _meta("10.0.0.2"))]
    )

    connector.start_load_kv(metadata)

    assert starts == ["10.0.0.1:6301", "10.0.0.2:6301"]
    assert connector._issued == [
        ("a", "10.0.0.1:6301"),
        ("b", "10.0.0.2:6301"),
    ]


def test_same_engine_first_contact_starts_one_handshake_for_batch(monkeypatch):
    connector = _connector(monkeypatch)
    starts = []

    def initiate(req_id, engine_id, meta):
        starts.append(engine_id)
        connector.load_ready_flag[engine_id] = True
        if hasattr(connector, "_ready_requests"):
            connector._ready_requests.put((req_id, meta))

    connector._initiate_background_handshake = initiate
    metadata = _metadata(
        [("a", _meta("10.0.0.3")), ("b", _meta("10.0.0.3"))]
    )

    connector.start_load_kv(metadata)

    assert starts == ["10.0.0.3:6301"]
    assert connector._issued == [
        ("a", "10.0.0.3:6301"),
        ("b", "10.0.0.3:6301"),
    ]


def test_known_peer_keeps_direct_read_path(monkeypatch):
    connector = _connector(monkeypatch)
    connector._remote_agents["10.0.0.4:6301_dp0"] = {"agent"}
    connector._initiate_background_handshake = lambda *_args: (_ for _ in ()).throw(
        AssertionError("known peer should not handshake")
    )

    connector.start_load_kv(_metadata([("a", _meta("10.0.0.4"))]))

    assert connector._issued == [("a", "10.0.0.4:6301")]
