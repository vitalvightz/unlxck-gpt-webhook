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
