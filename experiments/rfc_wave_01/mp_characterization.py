# SPDX-License-Identifier: MIT
"""Pinned-source characterization, not a proposed runtime change or GPU test.

The workflow copies this file into the pinned checkout's tests directory so
normal shared fixtures apply. Existing timeout/late-cleanup tests are reused.
Only the external adapter and clock are simulated; the ATOM facade is real.
"""

import ast
import inspect
from copy import deepcopy
from types import SimpleNamespace

from atom.kv_transfer.offload.mp import backend as mp


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.sleeps.append(duration)
        self.now += duration


def test_submission_time_is_outside_the_polling_deadline(monkeypatch):
    clock = Clock()
    calls = []
    answers = iter([None, 0])

    def submit(lookup_id, tokens):
        calls.append(("submit", lookup_id, list(tokens)))
        clock.now += 8.0

    def poll(lookup_id):
        calls.append(("poll", lookup_id))
        return next(answers)

    monkeypatch.setattr(mp, "time", clock)
    adapter = SimpleNamespace(
        maybe_submit_lookup_request=submit, check_lookup_result=poll
    )
    client = mp._MPLookupClient(adapter, timeout=3.0, poll_interval=1.0)

    assert client.lookup([1, 2, 3, 4], "submit-delay") == 0
    assert clock.now == 9.0
    assert clock.sleeps == [1.0]
    assert calls == [
        ("submit", "submit-delay", [1, 2, 3, 4]),
        ("poll", "submit-delay"),
        ("poll", "submit-delay"),
    ]
    assert client.hit_tokens("submit-delay") == 0


def test_slow_status_call_can_return_a_hit_after_the_poll_deadline(monkeypatch):
    clock = Clock()
    submitted = []
    polled = []

    def poll(lookup_id):
        polled.append(lookup_id)
        clock.now += 8.0
        return 4

    monkeypatch.setattr(mp, "time", clock)
    adapter = SimpleNamespace(
        maybe_submit_lookup_request=lambda rid, tokens: submitted.append(
            (rid, list(tokens))
        ),
        check_lookup_result=poll,
    )
    client = mp._MPLookupClient(adapter, timeout=3.0, poll_interval=1.0)

    assert client.lookup([1, 2, 3, 4], "poll-delay") == 4
    assert clock.now == 8.0
    assert clock.sleeps == []
    assert submitted == [("poll-delay", [1, 2, 3, 4])]
    assert polled == ["poll-delay"]
    assert client.hit_tokens("poll-delay") == 4


def test_direct_native_readers_do_not_adopt_vllm_only_options(monkeypatch):
    # This census intentionally freezes the inspected revision. It is not a
    # proposed runtime allowlist or a promise about later feature branches.
    expected = {
        "lmcache.mp.host", "lmcache.mp.port", "lmcache.mp.server_urls",
        "lmcache.mp.mp_transfer_mode", "lmcache.mp.tp_rank_collapse",
        "lmcache.mp.mq_timeout", "lmcache.mp.heartbeat_interval",
        "lmcache.mp.lookup_timeout", "lmcache.mp.lookup_poll_interval",
    }
    tree = ast.parse(inspect.getsource(mp))
    read_keys = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get" and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.startswith("lmcache.mp.")
    }
    assert read_keys == expected
    copied_options = {
        "lmcache.mp.autostart": True,
        "lmcache.mp.autostart.server_args": "--l1-size-gb 1 --eviction-policy LRU",
        "lmcache.mp.isolated_ipc": True,
        "lmcache.mp.nonblocking_lookup_status": True,
    }
    extra = {"lmcache.local_cpu": True, **copied_options}
    config = SimpleNamespace(kv_transfer_config={
        "kv_connector": "lmcache_mp", "kv_role": "offload",
        "kv_connector_extra_config": extra,
    })
    before = deepcopy(config.kv_transfer_config)
    monkeypatch.delenv("LMCACHE_MP_TRANSFER_MODE", raising=False)

    assert not (copied_options.keys() & read_keys)
    assert mp._server_urls(config) == ["tcp://localhost:5555"]
    assert mp._transfer_mode(config) == "auto"
    assert mp._storage_kv_transfer_config(config)["kv_connector_extra_config"] == {
        "lmcache.local_cpu": True
    }
    assert config.kv_transfer_config == before
