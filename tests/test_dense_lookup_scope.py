# SPDX-License-Identifier: MIT
"""Dense scheduler lookup-scope validation before optional client fallback."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from conftest import atom_config_double

from atom.kv_transfer.offload import config as offcfg
from atom.kv_transfer.offload.dense.connector import DenseOffloadScheduler


def _install_lookup_factory(monkeypatch, factory):
    parts = "lmcache.v1.lookup_client.factory".split(".")
    for index in range(1, len(parts)):
        parent = ".".join(parts[:index])
        if parent not in sys.modules:
            package = ModuleType(parent)
            package.__path__ = []
            monkeypatch.setitem(sys.modules, parent, package)
    module = ModuleType("lmcache.v1.lookup_client.factory")
    module.LookupClientFactory = factory
    monkeypatch.setitem(sys.modules, module.__name__, module)


def _config():
    return atom_config_double(
        kv_transfer_config={"kv_role": "offload"},
        kv_cache_block_size=4,
        decode_context_parallel_size=1,
        tensor_parallel_size=1,
        pipeline_parallel_size=1,
    )


@pytest.fixture
def scheduler_boundary(monkeypatch):
    cfg = SimpleNamespace(chunk_size=8, lookup_server_worker_ids=[0])
    metadata = SimpleNamespace(
        engine_id="scope-test", world_size=1, worker_id=0, use_mla=False
    )
    sentinel = SimpleNamespace()

    def create_lookup_client(config, meta):
        # Pinned LMCache 05fc77a validates this scope with a bare assertion.
        for worker_id in config.lookup_server_worker_ids:
            assert -1 < worker_id < meta.world_size
        return sentinel

    factory = SimpleNamespace(create_lookup_client=Mock(side_effect=create_lookup_client))
    _install_lookup_factory(monkeypatch, factory)
    monkeypatch.setattr(offcfg, "build_lmcache_config", lambda *_args: cfg)
    monkeypatch.setattr(offcfg, "build_lmcache_metadata", lambda *_args: metadata)
    monkeypatch.setattr(offcfg, "lmcache_replica_world_size", lambda _config: 1)
    return SimpleNamespace(cfg=cfg, metadata=metadata, factory=factory, sentinel=sentinel)


@pytest.mark.parametrize("worker_ids", [[-1], [1], [0, 1]])
def test_invalid_lookup_scope_fails_before_optional_client_fallback(
    scheduler_boundary, worker_ids
):
    scheduler_boundary.cfg.lookup_server_worker_ids = worker_ids

    with pytest.raises(
        ValueError,
        match=r"lookup_server_worker_ids must be within the replica-local world \[0, 1\)",
    ):
        DenseOffloadScheduler(_config())

    scheduler_boundary.factory.create_lookup_client.assert_not_called()


@pytest.mark.parametrize("worker_ids", [[], [0]])
def test_valid_lookup_scope_preserves_client_construction(
    scheduler_boundary, worker_ids
):
    scheduler_boundary.cfg.lookup_server_worker_ids = worker_ids

    scheduler = DenseOffloadScheduler(_config())

    assert scheduler._lookup_client is scheduler_boundary.sentinel
    scheduler_boundary.factory.create_lookup_client.assert_called_once_with(
        scheduler_boundary.cfg, scheduler_boundary.metadata
    )
