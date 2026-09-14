from __future__ import annotations

import asyncio

import pytest

from api.worker import _drain_active_tasks, _worker_shutdown_grace_seconds


def test_shutdown_grace_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_GENERATION_WORKER_SHUTDOWN_GRACE_SECONDS", raising=False)
    assert _worker_shutdown_grace_seconds() == 25


def test_shutdown_grace_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_SHUTDOWN_GRACE_SECONDS", "10")
    assert _worker_shutdown_grace_seconds() == 10


def test_shutdown_grace_enforces_minimum(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_SHUTDOWN_GRACE_SECONDS", "0")
    assert _worker_shutdown_grace_seconds() == 1


def test_shutdown_grace_invalid_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_SHUTDOWN_GRACE_SECONDS", "not-a-number")
    assert _worker_shutdown_grace_seconds() == 25


def test_drain_lets_finished_tasks_complete_without_cancelling():
    async def scenario() -> None:
        async def quick() -> None:
            await asyncio.sleep(0.01)

        active_tasks: set[str] = {"job-1"}
        task = asyncio.create_task(quick())
        detached_tasks: set[asyncio.Task[None]] = {task}

        await _drain_active_tasks(
            detached_tasks=detached_tasks,
            active_tasks=active_tasks,
            grace_seconds=5,
        )

        assert task.done()
        assert not task.cancelled()
        assert detached_tasks == set()
        assert active_tasks == set()

    asyncio.run(scenario())


def test_drain_cancels_unfinished_tasks_after_grace():
    async def scenario() -> None:
        async def hang() -> None:
            await asyncio.sleep(100)

        active_tasks: set[str] = {"job-1"}
        task = asyncio.create_task(hang())
        detached_tasks: set[asyncio.Task[None]] = {task}

        # Use a fractional grace so the test stays fast.
        await _drain_active_tasks(
            detached_tasks=detached_tasks,
            active_tasks=active_tasks,
            grace_seconds=0.05,  # type: ignore[arg-type]
        )

        assert task.cancelled()
        assert detached_tasks == set()
        assert active_tasks == set()

    asyncio.run(scenario())


def test_drain_with_no_tasks_clears_state():
    async def scenario() -> None:
        active_tasks: set[str] = set()
        detached_tasks: set[asyncio.Task[None]] = set()
        await _drain_active_tasks(
            detached_tasks=detached_tasks,
            active_tasks=active_tasks,
            grace_seconds=1,
        )
        assert detached_tasks == set()
        assert active_tasks == set()

    asyncio.run(scenario())


def test_run_claimed_job_sanitizes_pre_runtime_error(monkeypatch: pytest.MonkeyPatch):
    """A pre-runtime worker failure must not persist raw exception text (which can
    carry tokens/PII) into the athlete/admin-visible job error."""
    import api.worker as worker

    captured: dict[str, object] = {}

    class _CaptureStore:
        def get_generation_job(self, job_id):
            return {"id": job_id, "status": "queued", "attempt_count": 0}

        def fail_generation_job(self, job_id, **kwargs):
            captured["job_id"] = job_id
            captured.update(kwargs)
            captured["status"] = "failed"
            return {}

    def _boom(**_kwargs):
        raise RuntimeError("connect failed for user@example.com with token=abcdef1234567890")

    monkeypatch.setattr(worker, "build_default_stage2_automator", lambda: object())
    monkeypatch.setattr(worker, "run_generation_job", _boom)

    active_tasks: set[str] = {"job-1"}
    asyncio.run(
        worker._run_claimed_job(job_id="job-1", store=_CaptureStore(), active_tasks=active_tasks)
    )

    stored_error = str(captured.get("error", ""))
    assert captured.get("status") == "failed"
    assert "Worker failed before generation runtime" in stored_error
    assert "user@example.com" not in stored_error
    assert "abcdef1234567890" not in stored_error
    assert active_tasks == set()
