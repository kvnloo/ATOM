# SPDX-License-Identifier: MIT
"""CPU contract for the homogeneous geometry MoRIIO's read path assumes."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest
import torch


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
    sys.modules.pop(name, None)
    return importlib.import_module(name)


class _Wrapper:
    def __init__(self):
        self.registered = []

    def register_local_buffer(self, ptr, size, device_id):
        self.registered.append((ptr, size, device_id))
        return b"metadata"

    def get_agent_metadata(self):
        return b"agent"


class _Thread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True


def _connector(monkeypatch):
    module = _module(monkeypatch)
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


def _mla(width, blocks=2):
    return SimpleNamespace(
        k_cache=torch.zeros((blocks * 4, 2, width), dtype=torch.uint8),
        v_cache=None,
    )


def _mha(width, blocks=2, value_width=None):
    return SimpleNamespace(
        k_cache=torch.zeros((blocks, width), dtype=torch.uint8),
        v_cache=torch.zeros(
            (blocks, width if value_width is None else value_width),
            dtype=torch.uint8,
        ),
    )


@pytest.mark.parametrize(
    "layers",
    [
        {"layer.0": _mla(4), "layer.1": _mla(8)},
        {"layer.0": _mla(4, blocks=2), "layer.1": _mla(4, blocks=3)},
        {"layer.0": _mla(4), "layer.1": _mha(32)},
    ],
    ids=["bytes-per-block", "block-count", "mla-vs-mha"],
)
def test_moriio_rejects_cross_layer_geometry_it_cannot_address(monkeypatch, layers):
    connector = _connector(monkeypatch)

    with pytest.raises(ValueError, match="homogeneous KV block geometry"):
        connector.register_kv_caches(layers)

    assert connector.moriio_wrapper.registered == []


def test_moriio_rejects_different_kv_bytes_per_block(monkeypatch):
    connector = _connector(monkeypatch)

    with pytest.raises(ValueError, match="K/V bytes per block differ"):
        connector.register_kv_caches({"layer.0": _mha(4, value_width=8)})

    assert connector.moriio_wrapper.registered == []


@pytest.mark.parametrize(
    "layers",
    [
        {"layer.0": _mla(4), "layer.1": _mla(4)},
        {"layer.0": _mha(4), "layer.1": _mha(4)},
    ],
    ids=["mla", "mha"],
)
def test_moriio_homogeneous_geometry_still_registers(monkeypatch, layers):
    connector = _connector(monkeypatch)

    connector.register_kv_caches(layers)

    expected_buffers = 2 if layers["layer.0"].v_cache is None else 4
    assert len(connector.moriio_wrapper.registered) == expected_buffers
    assert connector._handshake_listener_thread.started is True
