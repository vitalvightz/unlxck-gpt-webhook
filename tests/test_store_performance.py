from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import api.store_performance as performance


@dataclass
class _Response:
    data: Any


class _RpcCall:
    def __init__(self, response: _Response):
        self.response = response

    def execute(self) -> _Response:
        return self.response


class _RpcClient:
    def __init__(self, responses: dict[str, list[Any]]):
        self.responses = {name: list(values) for name, values in responses.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcCall:
        self.calls.append((name, params))
        values = self.responses.setdefault(name, [])
        value = values.pop(0) if values else None
        return _RpcCall(_Response(value))


class _RpcStore:
    def __init__(self, responses: dict[str, list[Any]]):
        self.client = _RpcClient(responses)
        self.fallback_calls: list[tuple[str, tuple[Any, ...]]] = []

    def get_generation_job(self, job_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("job", (job_id,)))
        return {"id": job_id, "fallback": True}

    def get_visible_active_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("active", (athlete_id,)))
        return {"id": "active-fallback", "athlete_id": athlete_id}

    def get_latest_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("latest", (athlete_id,)))
        return {"id": "latest-fallback", "athlete_id": athlete_id}

    def list_claimable_generation_jobs(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.fallback_calls.append(("claimable", (kwargs,)))
        return [{"id": "fallback-job", "status": "queued"}]


class _LegacyStore:
    def __init__(self):
        self.calls: list[str] = []

    def get_generation_job(self, job_id: str) -> dict[str, Any]:
        self.calls.append(job_id)
        return {"id": job_id, "fallback": True}


def test_compact_status_read_uses_rpc_without_full_row_fallback() -> None:
    store = _RpcStore(
        {
            "get_generation_job_status_v2": [
                {
                    "id": "job-1",
                    "status": "running",
                    "progress_milestones": [],
                }
            ]
        }
    )

    result = performance.get_generation_job_status(store, "job-1")

    assert result == {
        "id": "job-1",
        "status": "running",
        "progress_milestones": [],
    }
    assert store.fallback_calls == []
    assert store.client.calls == [
        ("get_generation_job_status_v2", {"p_job_id": "job-1"})
    ]


def test_compact_status_read_falls_back_for_non_rpc_test_stores() -> None:
    store = _LegacyStore()

    result = performance.get_generation_job_status(store, "job-2")

    assert result == {"id": "job-2", "fallback": True}
    assert store.calls == ["job-2"]


def test_idle_worker_backoff_skips_database_until_deadline(monkeypatch) -> None:
    store = _RpcStore({"list_claimable_generation_jobs_v2": [[], []]})
    times = iter([100.0, 101.0, 107.0])
    monkeypatch.setattr(performance.time, "monotonic", lambda: next(times))
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_INITIAL_SECONDS", "6")
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_MAX_SECONDS", "15")

    assert performance.list_claimable_generation_jobs(store, limit=1, stale_after_seconds=90) == []
    assert performance.list_claimable_generation_jobs(store, limit=1, stale_after_seconds=90) == []
    assert performance.list_claimable_generation_jobs(store, limit=1, stale_after_seconds=90) == []

    assert [name for name, _ in store.client.calls] == [
        "list_claimable_generation_jobs_v2",
        "list_claimable_generation_jobs_v2",
    ]
    assert store._claimable_idle_delay_seconds == 12.0


def test_returned_job_resets_idle_backoff(monkeypatch) -> None:
    queued = {"id": "queued-job", "status": "queued", "progress_milestones": []}
    store = _RpcStore({"list_claimable_generation_jobs_v2": [[], [queued]]})
    times = iter([200.0, 207.0])
    monkeypatch.setattr(performance.time, "monotonic", lambda: next(times))
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_INITIAL_SECONDS", "6")
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_MAX_SECONDS", "15")

    assert performance.list_claimable_generation_jobs(store, limit=1, stale_after_seconds=90) == []
    assert performance.list_claimable_generation_jobs(store, limit=1, stale_after_seconds=90) == [queued]

    assert store._claimable_idle_delay_seconds == 0.0
    assert store._claimable_next_poll_at == 0.0
