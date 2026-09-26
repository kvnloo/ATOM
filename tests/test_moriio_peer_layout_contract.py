# SPDX-License-Identifier: MIT
"""CPU contract for fail-closed MoRIIO peer layout compatibility."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


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
    def __init__(self, sizes):
        self.sizes = sizes
        self.sessions = []

    def get_unpack_memory_metadata(self, packed):
        return SimpleNamespace(size=self.sizes[packed])

    def build_session(self, local, remote):
        session = (local.size, remote.size)
        self.sessions.append(session)
        return session


def _connector(monkeypatch, *, remote_blocks=2, remote_block_len=4, remote_size=32):
    module = _module(monkeypatch)
    connector = module.MoRIIOConnector.__new__(module.MoRIIOConnector)
    connector.num_k_chunks = 1
    connector.num_blocks = 2
    connector.block_len = 4
    connector._built_sessions = {}
    connector.layer_name_to_local_kv_cache_metadata = {"layer.0": [b"local"]}
    connector.layer_name_to_remote_kv_cache_metadata = {
        "peer": {"layer.0": [b"remote"]}
    }
    connector.remote_moriio_metadata = {
        "peer": SimpleNamespace(
            num_blocks=remote_blocks,
            block_len=remote_block_len,
        )
    }
    connector.moriio_wrapper = _Wrapper(
        {b"local": 32, b"remote": remote_size}
    )
    return connector


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"remote_blocks": 3}, "num_blocks"),
        ({"remote_block_len": 8}, "block_len"),
        ({"remote_size": 64}, "registered byte geometry"),
    ],
)
def test_moriio_rejects_peer_geometry_before_building_sessions(
    monkeypatch,
    kwargs,
    message,
):
    connector = _connector(monkeypatch, **kwargs)

    with pytest.raises(ValueError, match=message):
        connector._get_or_build_sessions("peer")

    assert connector.moriio_wrapper.sessions == []


def test_moriio_matching_peer_geometry_builds_sessions(monkeypatch):
    connector = _connector(monkeypatch)

    sessions, metadata = connector._get_or_build_sessions("peer")

    assert sessions == [({(0, 0): (32, 32)}, {})]
    assert metadata.num_blocks == 2
    assert metadata.block_len == 4
    assert connector.moriio_wrapper.sessions == [(32, 32)]
