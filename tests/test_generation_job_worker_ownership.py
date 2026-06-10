"""Worker-ownership behaviour for generation job claim/complete/fail.

Exercises the in-memory store, which mirrors the SQL contract of
claim_generation_job + the worker guard in the terminal RPCs:

* claiming records the owning worker,
* a job cannot be claimed twice while it is healthily running,
* only the owning worker (or a caller that explicitly skips the ownership
  check, i.e. stale-job recovery) can complete or fail the job,
* stale attempt counts and terminal states are rejected.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.generation_config import generation_worker_id
from support import FakeStore


def _seed_queued_job(store: FakeStore, job_id: str = "job-1") -> dict:
    job = {
        "id": job_id,
        "athlete_id": "athlete-1",
        "client_request_id": f"req-{job_id}",
        "source": "self_serve",
        "request_payload": {},
        "status": "queued",
        "error": None,
        "attempt_count": 0,
        "heartbeat_at": None,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "claimed_by": None,
        "claimed_at": None,
        "progress_milestones": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    store.generation_jobs[job_id] = job
    return job


def test_worker_can_claim_queued_job_and_ownership_is_recorded():
    store = FakeStore()
    _seed_queued_job(store)

    claimed = store.claim_generation_job_start("job-1", worker_id="worker-a")

    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["claimed_by"] == "worker-a"
    assert claimed["claimed_at"]


def test_claim_defaults_to_process_worker_id():
    store = FakeStore()
    _seed_queued_job(store)

    claimed = store.claim_generation_job_start("job-1")

    assert claimed is not None
    assert claimed["claimed_by"] == generation_worker_id()


def test_same_job_cannot_be_claimed_twice_while_running():
    store = FakeStore()
    _seed_queued_job(store)

    first = store.claim_generation_job_start("job-1", worker_id="worker-a")
    second = store.claim_generation_job_start("job-1", worker_id="worker-b")

    assert first is not None
    assert second is None
    assert store.generation_jobs["job-1"]["claimed_by"] == "worker-a"


def test_owning_worker_can_complete_claimed_job():
    store = FakeStore()
    _seed_queued_job(store)
    claimed = store.claim_generation_job_start("job-1", worker_id="worker-a")

    completed = store.complete_generation_job(
        "job-1",
        expected_attempt_count=int(claimed["attempt_count"]),
        final_status="completed",
        expected_worker_id="worker-a",
    )

    assert completed["status"] == "completed"


def test_different_worker_cannot_complete_claimed_job():
    store = FakeStore()
    _seed_queued_job(store)
    claimed = store.claim_generation_job_start("job-1", worker_id="worker-a")

    with pytest.raises(HTTPException) as exc_info:
        store.complete_generation_job(
            "job-1",
            expected_attempt_count=int(claimed["attempt_count"]),
            final_status="completed",
            expected_worker_id="worker-b",
        )

    assert exc_info.value.status_code == 409
    assert "stale_generation_job_worker" in str(exc_info.value.detail)
    assert store.generation_jobs["job-1"]["status"] == "running"


def test_different_worker_cannot_fail_claimed_job():
    store = FakeStore()
    _seed_queued_job(store)
    claimed = store.claim_generation_job_start("job-1", worker_id="worker-a")

    with pytest.raises(HTTPException) as exc_info:
        store.fail_generation_job(
            "job-1",
            expected_attempt_count=int(claimed["attempt_count"]),
            error="boom",
            expected_worker_id="worker-b",
        )

    assert exc_info.value.status_code == 409
    assert "stale_generation_job_worker" in str(exc_info.value.detail)


def test_stale_attempt_count_cannot_complete_or_fail_job():
    store = FakeStore()
    _seed_queued_job(store)
    claimed = store.claim_generation_job_start("job-1", worker_id="worker-a")
    stale_attempt = int(claimed["attempt_count"]) - 1

    with pytest.raises(HTTPException) as complete_exc:
        store.complete_generation_job(
            "job-1",
            expected_attempt_count=stale_attempt,
            final_status="completed",
            expected_worker_id="worker-a",
        )
    with pytest.raises(HTTPException) as fail_exc:
        store.fail_generation_job(
            "job-1",
            expected_attempt_count=stale_attempt,
            error="boom",
            expected_worker_id="worker-a",
        )

    assert "stale_generation_job_attempt" in str(complete_exc.value.detail)
    assert "stale_generation_job_attempt" in str(fail_exc.value.detail)
    assert store.generation_jobs["job-1"]["status"] == "running"


def test_completed_job_cannot_be_failed_afterwards():
    store = FakeStore()
    _seed_queued_job(store)
    claimed = store.claim_generation_job_start("job-1", worker_id="worker-a")
    store.complete_generation_job(
        "job-1",
        expected_attempt_count=int(claimed["attempt_count"]),
        final_status="completed",
        expected_worker_id="worker-a",
    )

    with pytest.raises(HTTPException) as exc_info:
        store.fail_generation_job(
            "job-1",
            expected_attempt_count=int(claimed["attempt_count"]),
            error="boom",
            expected_worker_id="worker-a",
        )

    assert exc_info.value.status_code == 409
    assert "wrong_generation_job_status" in str(exc_info.value.detail)
    assert store.generation_jobs["job-1"]["status"] == "completed"


def test_recovery_can_fail_other_workers_job_when_ownership_check_is_skipped():
    # Stale-job recovery acts on jobs owned by dead workers; it relies on the
    # status + attempt_count guards and explicitly skips the ownership check.
    store = FakeStore()
    _seed_queued_job(store)
    claimed = store.claim_generation_job_start("job-1", worker_id="worker-dead")

    failed = store.fail_generation_job(
        "job-1",
        expected_attempt_count=int(claimed["attempt_count"]),
        error="Generation worker stalled after loading the job.",
        enforce_worker_ownership=False,
    )

    assert failed["status"] == "failed"


def test_legacy_unowned_running_job_can_still_be_completed():
    # Rows claimed before the ownership migration have claimed_by null; the
    # ownership guard lets them through and attempt/status checks still apply.
    store = FakeStore()
    job = _seed_queued_job(store)
    job.update({"status": "running", "attempt_count": 1, "claimed_by": None})

    completed = store.complete_generation_job(
        "job-1",
        expected_attempt_count=1,
        final_status="completed",
        expected_worker_id="worker-a",
    )

    assert completed["status"] == "completed"
