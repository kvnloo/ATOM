# SPDX-License-Identifier: MIT
"""Read-only MP lookup-status failures keep the local cleanup obligation."""

import pytest

from atom.kv_transfer.offload.mp import lookup as mp_lookup


class _Adapter:
    def __init__(self):
        self.checks = 0
        self.freed = []
        self.cleaned = []

    def check_lookup_result(self, request_id):
        self.checks += 1
        if self.checks == 1:
            raise RuntimeError("temporary status failure")
        return 8

    def free_lookup_locks(self, **kwargs):
        self.freed.append(kwargs)

    def cleanup_lookup_result(self, request_id):
        self.cleaned.append(request_id)


def test_status_exception_keeps_lookup_cleanup_obligation(monkeypatch):
    monkeypatch.setattr(mp_lookup, "_mp_session_id", lambda _config, req_id: f"s:{req_id}")
    adapter = _Adapter()
    client = mp_lookup._MPLookupClient(
        adapter,
        config=object(),
        timeout=1,
        poll_interval=0.01,
    )
    client._lookups["req"] = mp_lookup._LookupState(token_ids=list(range(8)))

    with pytest.raises(RuntimeError, match="temporary status failure"):
        client.clear_lookup_status("req")

    assert "req" in client._lookups
    assert adapter.freed == []
    assert adapter.cleaned == []

    client.clear_lookup_status("req")

    assert "req" not in client._lookups
    assert adapter.freed == [
        {
            "token_ids": list(range(8)),
            "start": 0,
            "end": 8,
            "request_id": "s:req",
        }
    ]
    assert adapter.cleaned == ["s:req"]


def test_pending_nonanswer_keeps_existing_session_cleanup_fallback(monkeypatch):
    monkeypatch.setattr(mp_lookup, "_mp_session_id", lambda _config, req_id: f"s:{req_id}")
    adapter = _Adapter()
    adapter.check_lookup_result = lambda _request_id: None
    client = mp_lookup._MPLookupClient(
        adapter,
        config=object(),
        timeout=1,
        poll_interval=0.01,
    )
    client._lookups["req"] = mp_lookup._LookupState(token_ids=list(range(8)))

    client.clear_lookup_status("req")

    assert "req" not in client._lookups
    assert adapter.freed == []
    assert adapter.cleaned == ["s:req"]
