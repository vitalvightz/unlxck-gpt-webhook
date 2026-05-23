from __future__ import annotations

import asyncio

import pytest

from tests.support import FakeStore, _build_request
from worker import generation_worker


@pytest.mark.asyncio
async def test_worker_once_exits_cleanly_when_no_job_available():
    store = FakeStore()
    await generation_worker.run_worker_loop(store=store, once=True)


@pytest.mark.asyncio
async def test_worker_once_uses_runtime_claim_and_advances_job(monkeypatch):
    store = FakeStore()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-once",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    async def _fake_run_generation_job(*, job_id, store, planner_fn, stage2, active_tasks):
        claimed = store.claim_generation_job_start(job_id)
        if not claimed:
            return
        store.update_generation_job(job_id, status="completed")

    monkeypatch.setattr(generation_worker, "run_generation_job", _fake_run_generation_job)

    await generation_worker.run_worker_loop(store=store, once=True)

    assert store.get_generation_job(created["id"])["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_two_consumers_only_one_claim_succeeds(monkeypatch):
    store = FakeStore()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-race",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    claimed_ids: list[str] = []

    async def _fake_run_generation_job(*, job_id, store, planner_fn, stage2, active_tasks):
        await asyncio.sleep(0)
        claimed = store.claim_generation_job_start(job_id)
        if not claimed:
            return
        claimed_ids.append(job_id)
        store.update_generation_job(job_id, status="completed")

    monkeypatch.setattr(generation_worker, "run_generation_job", _fake_run_generation_job)

    await asyncio.gather(
        generation_worker.run_worker_loop(store=store, once=True),
        generation_worker.run_worker_loop(store=store, once=True),
    )

    assert claimed_ids == [created["id"]]


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
        claimed = store.claim_generation_job_start(job_id)
        if not claimed:
            return
        store.update_generation_job(job_id, status="completed")

    monkeypatch.setattr(generation_worker, "run_generation_job", _fake_run_generation_job)

    await generation_worker.run_worker_loop(store=store, once=True)

    assert store.get_generation_job(first["id"])["status"] == "completed"
    assert store.get_generation_job(second["id"])["status"] == "queued"


def test_worker_env_parsing_falls_back_for_invalid_values(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_WORKER_POLL_SECONDS", "abc")
    monkeypatch.setenv("APP_GENERATION_WORKER_IDLE_SECONDS", "0")
    monkeypatch.setenv("APP_GENERATION_WORKER_MAX_JOBS_PER_LOOP", "-3")

    assert generation_worker._worker_poll_seconds() == 5.0
    assert generation_worker._worker_idle_seconds() == 5.0
    assert generation_worker._worker_max_jobs_per_loop() == 1
