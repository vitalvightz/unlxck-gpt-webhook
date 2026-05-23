from __future__ import annotations

import pytest

from tests.support import FakeStore, _build_request
from worker import generation_worker


@pytest.mark.asyncio
async def test_worker_once_exits_cleanly_when_no_job_available():
    store = FakeStore()
    await generation_worker.run_worker_loop(store=store, once=True)


@pytest.mark.asyncio
async def test_worker_once_claims_job_and_calls_runtime(monkeypatch):
    store = FakeStore()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-once",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    called: list[str] = []

    async def _fake_run_generation_job(*, job_id, store, planner_fn, stage2, active_tasks):
        called.append(job_id)
        store.update_generation_job(job_id, status="completed")

    monkeypatch.setattr(generation_worker, "run_generation_job", _fake_run_generation_job)

    await generation_worker.run_worker_loop(store=store, once=True)

    assert called == [created["id"]]


@pytest.mark.asyncio
async def test_worker_single_loop_max_jobs_one(monkeypatch):
    store = FakeStore()
    first = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-first",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    second = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-second",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    monkeypatch.setenv("APP_GENERATION_WORKER_MAX_JOBS_PER_LOOP", "1")

    async def _fake_run_generation_job(*, job_id, store, planner_fn, stage2, active_tasks):
        store.update_generation_job(job_id, status="completed")

    monkeypatch.setattr(generation_worker, "run_generation_job", _fake_run_generation_job)

    await generation_worker.run_worker_loop(store=store, once=True)

    assert store.get_generation_job(first["id"])["status"] == "completed"
    assert store.get_generation_job(second["id"])["status"] == "queued"
