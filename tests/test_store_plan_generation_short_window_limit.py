from __future__ import annotations

from types import SimpleNamespace

from api.store import SupabaseAppStore


def test_short_window_limit_accepts_rpc_list_response_shape():
    store = object.__new__(SupabaseAppStore)

    class _RpcCall:
        def execute(self):
            return SimpleNamespace(data=[{"allowed": True, "retry_after_seconds": 0}])

    class _Client:
        def rpc(self, *_args, **_kwargs):
            return _RpcCall()

    store.client = _Client()
    store._run_with_transient_retry = lambda operation, fn: fn()

    allowed, retry_after = store.check_plan_generation_short_window_limit(
        athlete_id="00000000-0000-0000-0000-000000000001",
        max_requests=1,
        window_seconds=60.0,
    )

    assert allowed is True
    assert retry_after == 0
