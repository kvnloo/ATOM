# SPDX-License-Identifier: MIT
"""LMCache MP worker teardown unregisters views before the runner drops KV memory."""

from atom.kv_transfer.offload.mp import worker as mp_worker


class _Adapter:
    def __init__(self):
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


def test_close_shuts_down_registered_adapter_once():
    connector = mp_worker.LMCacheMPConnector.__new__(mp_worker.LMCacheMPConnector)
    adapter = _Adapter()
    connector._adapter = adapter

    connector.close()
    connector.close()

    assert adapter.shutdown_calls == 1
    assert connector._adapter is None


def test_close_before_registration_is_a_noop():
    connector = mp_worker.LMCacheMPConnector.__new__(mp_worker.LMCacheMPConnector)
    connector._adapter = None

    connector.close()

    assert connector._adapter is None
