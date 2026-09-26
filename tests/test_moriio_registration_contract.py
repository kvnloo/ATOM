# SPDX-License-Identifier: MIT
"""Fail closed when MoRIIO would omit DSA index-cache state."""

from __future__ import annotations

import importlib
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest
import torch


def _install_import_stubs(monkeypatch) -> None:
    triton = ModuleType("triton")
    triton.jit = lambda fn: fn
    triton.cdiv = lambda x, y: (x + y - 1) // y
    triton.next_power_of_2 = lambda x: 1 << (max(1, x) - 1).bit_length()
    triton_language = ModuleType("triton.language")
    triton.language = triton_language
    monkeypatch.setitem(sys.modules, "triton", triton)
    monkeypatch.setitem(sys.modules, "triton.language", triton_language)


def _module(monkeypatch):
    _install_import_stubs(monkeypatch)
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


class _Wrapper:
    def __init__(self):
        self.lock = threading.Lock()
        self.registered = []

    def register_local_buffer(self, ptr, size, device_id):
        self.registered.append((ptr, size, device_id))
        return b"metadata"

    def get_agent_metadata(self):
        return b"agent"


class _Thread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True


def _connector(monkeypatch):
    module = _module(monkeypatch)
    monkeypatch.setattr(
        module,
        "chunk_tensor_for_rdma",
        lambda tensor, _block: (
            [(tensor.data_ptr(), tensor.numel() * tensor.element_size())],
            1,
        ),
    )
    monkeypatch.setattr(module.threading, "Thread", _Thread)

    connector = module.MoRIIOConnector.__new__(module.MoRIIOConnector)
    connector.kv_cache_shape = None
    connector.kv_cache_block_size = 4
    connector.blocks_per_chunk = None
    connector.num_k_chunks = 0
    connector.layer_name_to_local_kv_cache_metadata = {}
    connector.moriio_wrapper = _Wrapper()
    connector.engine_id = "local"
    connector.side_channel_port = 12345
    connector.tp_rank = 0
    connector.dp_rank = 0
    return connector


def _cache(*, index_cache=None, index_scale=None):
    return SimpleNamespace(
        k_cache=torch.zeros((8, 2, 4), dtype=torch.uint8),
        v_cache=None,
        index_cache=index_cache,
        index_scale=index_scale,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("index_cache", torch.zeros((8, 4, 8), dtype=torch.uint8)),
        ("index_scale", torch.zeros((8, 4), dtype=torch.uint8)),
    ],
)
def test_moriio_rejects_index_state_it_does_not_transfer(
    monkeypatch,
    field,
    value,
):
    connector = _connector(monkeypatch)
    kwargs = {field: value}

    with pytest.raises(
        NotImplementedError,
        match="does not transfer DSA index-cache PAGE state",
    ):
        connector.register_kv_caches({"layer.0": _cache(**kwargs)})

    assert connector.moriio_wrapper.registered == []


def test_moriio_plain_mla_registration_remains_available(monkeypatch):
    connector = _connector(monkeypatch)

    connector.register_kv_caches({"layer.0": _cache()})

    assert len(connector.moriio_wrapper.registered) == 1
    assert connector.layer_name_to_local_kv_cache_metadata["layer.0"] == [
        b"metadata"
    ]
    assert connector._handshake_listener_thread.started is True
