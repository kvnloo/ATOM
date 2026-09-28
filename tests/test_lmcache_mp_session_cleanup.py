# SPDX-License-Identifier: MIT
"""Finished MP sessions stay pending until end_session actually succeeds."""

from types import SimpleNamespace

from atom.kv_transfer.offload.mp import scheduler as mp_scheduler


class _FlakyAdapter:
    def __init__(self):
        self.calls = 0
        self.ended = []

    def end_session(self, request_id):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary control-plane failure")
        self.ended.append(request_id)


def _scheduler(monkeypatch):
    scheduler = mp_scheduler.LMCacheMPConnectorScheduler.__new__(
        mp_scheduler.LMCacheMPConnectorScheduler
    )
    scheduler._save_tracker = {}
    scheduler._save_inflight = {}
    scheduler._mp_adapter = _FlakyAdapter()
    scheduler._config = object()
    scheduler.__dict__["_sessions_to_end"] = {
        "7": SimpleNamespace(id=7),
    }
    monkeypatch.setattr(mp_scheduler, "_mp_session_id", lambda _config, req_id: f"s:{req_id}")
    return scheduler


def test_failed_end_session_is_retried_instead_of_forgotten(monkeypatch):
    scheduler = _scheduler(monkeypatch)

    scheduler._end_finished_sessions()
    assert "7" in scheduler._pending_session_ends()
    assert scheduler._mp_adapter.ended == []

    scheduler._end_finished_sessions()
    assert scheduler._pending_session_ends() == {}
    assert scheduler._mp_adapter.ended == ["s:7"]


def test_persistent_end_session_failure_logs_once_but_keeps_retrying(monkeypatch, caplog):
    scheduler = _scheduler(monkeypatch)

    def always_fail(_request_id):
        scheduler._mp_adapter.calls += 1
        raise RuntimeError("still unavailable")

    scheduler._mp_adapter.end_session = always_fail

    scheduler._end_finished_sessions()
    scheduler._end_finished_sessions()

    assert scheduler._mp_adapter.calls == 2
    assert "7" in scheduler._pending_session_ends()
    assert caplog.text.count("will retry") == 1
