from types import SimpleNamespace
from unittest.mock import MagicMock

from api.store import SupabaseAppStore


def _store_with_rpc_rows(rows_per_call):
    store = SupabaseAppStore(client=MagicMock(), admin_emails=set())
    calls = {"count": 0}

    def _run_with_transient_retry(*, operation, fn):
        assert operation == "claim_next_generation_job:rpc"
        del fn
        idx = calls["count"]
        calls["count"] += 1
        rows = rows_per_call[idx] if idx < len(rows_per_call) else []
        return SimpleNamespace(data=rows)

    store._run_with_transient_retry = _run_with_transient_retry  # type: ignore[attr-defined]
    return store


def test_claim_next_generation_job_single_worker_claims_queued_job():
    claimed = {
        "id": "job-1",
        "status": "running",
        "attempt_count": 1,
        "progress_milestones": [{"code": "job_loaded"}],
    }
    store = _store_with_rpc_rows([[claimed]])

    row = store.claim_next_generation_job(worker_id="w-1", stale_after_seconds=90)

    assert row is not None
    assert row["id"] == "job-1"
    assert row["status"] == "running"
    assert row["attempt_count"] == 1
    assert row["progress_milestones"][0]["code"] == "job_loaded"


def test_claim_next_generation_job_no_duplicate_claim_on_second_call():
    claimed = {"id": "job-1", "status": "running", "attempt_count": 1}
    store = _store_with_rpc_rows([[claimed], []])

    first = store.claim_next_generation_job(worker_id="w-1", stale_after_seconds=90)
    second = store.claim_next_generation_job(worker_id="w-2", stale_after_seconds=90)

    assert first is not None
    assert first["id"] == "job-1"
    assert second is None


def test_claim_next_generation_job_returns_oldest_queued_first():
    oldest = {"id": "job-oldest", "created_at": "2026-01-01T00:00:00+00:00", "status": "running", "attempt_count": 1}
    store = _store_with_rpc_rows([[oldest]])

    row = store.claim_next_generation_job(worker_id="w-1", stale_after_seconds=90)

    assert row is not None
    assert row["id"] == "job-oldest"


def test_claim_next_generation_job_retries_startup_stale_running_job():
    stale_running = {
        "id": "job-stale",
        "status": "running",
        "attempt_count": 2,
        "progress_milestones": [{"code": "job_loaded"}, {"code": "job_recovered_startup_stale"}],
    }
    store = _store_with_rpc_rows([[stale_running]])

    row = store.claim_next_generation_job(worker_id="w-1", stale_after_seconds=90)

    assert row is not None
    assert row["id"] == "job-stale"
    assert row["attempt_count"] == 2


def test_claim_next_generation_job_does_not_claim_fresh_running_job():
    store = _store_with_rpc_rows([[]])

    row = store.claim_next_generation_job(worker_id="w-1", stale_after_seconds=90)

    assert row is None
