from __future__ import annotations

import asyncio

from api.generation.heartbeat import heartbeat_generation_job


class _FakeHeartbeatStore:
    """Minimal store double: just enough state for the heartbeat loop to
    read/write against, independent of Supabase or FakeStore."""

    def __init__(self, *, status: str = "running") -> None:
        self.status = status
        self.heartbeat_writes = 0
        self.status_reads = 0

    def get_generation_job(self, job_id: str) -> dict:
        self.status_reads += 1
        return {"id": job_id, "status": self.status}

    def update_generation_job(self, job_id: str, **changes: object) -> dict:
        if "heartbeat_at" in changes:
            self.heartbeat_writes += 1
        return {"id": job_id, "status": self.status, **changes}


def test_heartbeat_keeps_refreshing_while_job_stays_running() -> None:
    store = _FakeHeartbeatStore(status="running")
    stop_event = asyncio.Event()
    cancelled_calls: list[None] = []

    async def scenario() -> None:
        task = asyncio.create_task(
            heartbeat_generation_job(
                "job-1", store, stop_event, on_cancelled=lambda: cancelled_calls.append(None), interval_seconds=0.01
            )
        )
        await asyncio.sleep(0.05)
        stop_event.set()
        await task

    asyncio.run(scenario())

    assert store.heartbeat_writes >= 2
    assert cancelled_calls == []


def test_heartbeat_stops_and_signals_cancellation_when_status_changes_externally() -> None:
    """Simulates a manual cancel (or the hard-runtime-ceiling recovery)
    flipping the job's status while the heartbeat loop is mid-run: the loop
    must notice on its next tick, stop writing heartbeats, and fire
    on_cancelled so the orchestrator can abort between stages instead of
    continuing to burn CPU/API calls on a job nobody is waiting on."""
    store = _FakeHeartbeatStore(status="running")
    stop_event = asyncio.Event()
    cancelled_calls: list[None] = []

    async def scenario() -> None:
        task = asyncio.create_task(
            heartbeat_generation_job(
                "job-1", store, stop_event, on_cancelled=lambda: cancelled_calls.append(None), interval_seconds=0.01
            )
        )
        await asyncio.sleep(0.03)
        writes_before_cancel = store.heartbeat_writes
        store.status = "failed"  # external cancel/recovery flips status
        await asyncio.sleep(0.05)
        assert task.done()
        # No further heartbeat writes happened once the loop noticed the
        # external status change.
        assert store.heartbeat_writes == writes_before_cancel
        stop_event.set()

    asyncio.run(scenario())

    assert cancelled_calls == [None]


def test_heartbeat_stops_immediately_when_stop_event_is_already_set() -> None:
    store = _FakeHeartbeatStore(status="running")
    stop_event = asyncio.Event()
    stop_event.set()

    asyncio.run(heartbeat_generation_job("job-1", store, stop_event, interval_seconds=0.01))

    assert store.heartbeat_writes == 0
    assert store.status_reads == 0
