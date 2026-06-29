from __future__ import annotations

from types import SimpleNamespace

from api.store import SupabaseAppStore


def test_daily_limit_create_recovers_stale_running_job_before_rpc():
    """Stale `running` rows must be recovered before the atomic daily-limit RPC.

    The ``create_generation_job_with_daily_limit`` RPC guards against in-flight
    work purely in SQL (``status in ('queued', 'running')``) and has no
    staleness awareness. Without a recovery pass first, a stale ``running`` row
    left behind by a crashed worker would make the RPC raise
    ``generation_job_in_flight`` and permanently block new requests. This test
    pins the ordering: recovery runs before the RPC is invoked.
    """

    store = object.__new__(SupabaseAppStore)

    call_order: list[str] = []

    def _fake_fail_stale(athlete_id, *, stale_after_seconds, exclude_client_request_id=None):
        call_order.append("fail_stale")
        return None

    def _fake_recover(athlete_id, *, stale_after_seconds):
        call_order.append("recover")
        return None

    store._fail_stale_active_generation_jobs_for_athlete = _fake_fail_stale
    store.reconcile_active_generation_job_for_athlete = _fake_recover

    created_job = {"id": "job-1", "status": "queued", "client_request_id": "req-1"}

    class _RpcCall:
        def execute(self):
            call_order.append("rpc")
            return SimpleNamespace(data=[{"job": created_job, "limit_exceeded": False}])

    class _Client:
        def rpc(self, name, _params):
            assert name == "create_generation_job_with_daily_limit"
            return _RpcCall()

    store.client = _Client()
    store._run_with_transient_retry = lambda operation, fn: fn()

    job = store.create_or_get_generation_job_with_daily_limit(
        athlete_id="00000000-0000-0000-0000-000000000001",
        client_request_id="req-1",
        source="self_serve",
        request_payload={"hello": "world"},
        daily_limit=3,
        day_start_iso="2026-06-06T00:00:00+00:00",
        limit_reached_detail="Daily generation limit reached.",
        counted_sources={"self_serve"},
    )

    assert job == created_job
    # Both stale-recovery passes must run, and both must precede the RPC's
    # in-flight guard: the table-level stale failer first, then the active-job
    # recovery, then the atomic daily-limit RPC.
    assert call_order == ["fail_stale", "recover", "rpc"]
