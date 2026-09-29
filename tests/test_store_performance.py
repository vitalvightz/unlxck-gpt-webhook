"""SupabaseAppStore's compact generation reads (api/store_performance.py).

These used to be module functions that probed each store for a raw client and
fell back to full-row reads when it had none, so the compact path ran only
against hand-built client doubles. They are store methods now; these tests run
them on SupabaseAppStore itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import api.store_performance as performance
from api.store import SupabaseAppStore


@dataclass
class _Response:
    data: Any


class _Call:
    def __init__(self, log: list, name: str, response: Any):
        self._log = log
        self._name = name
        self._response = response

    def __getattr__(self, method: str):
        def record(*args: Any, **kwargs: Any) -> "_Call":
            self._log.append((self._name, method, args, kwargs))
            return self

        return record

    def execute(self) -> _Response:
        if isinstance(self._response, Exception):
            raise self._response
        return _Response(self._response)


class _Client:
    def __init__(self, responses: dict[str, list[Any]]):
        self.responses = {name: list(values) for name, values in responses.items()}
        self.log: list[tuple[str, str, tuple, dict]] = []

    def _next(self, name: str) -> Any:
        values = self.responses.setdefault(name, [])
        return values.pop(0) if values else None

    def rpc(self, name: str, params: dict[str, Any]) -> _Call:
        self.log.append((name, "rpc", (params,), {}))
        return _Call(self.log, name, self._next(name))

    def table(self, name: str) -> _Call:
        return _Call(self.log, name, self._next(name))

    def rpc_calls(self) -> list[tuple[str, dict[str, Any]]]:
        return [(name, args[0]) for name, method, args, _ in self.log if method == "rpc"]


class _Store(SupabaseAppStore):
    """The production store with its full-row reads replaced by recorders."""

    def __init__(self, responses: dict[str, list[Any]]):
        super().__init__(client=_Client(responses), admin_emails=set())
        self.fallback_calls: list[tuple[str, Any]] = []

    def get_generation_job(self, job_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("job", job_id))
        return {"id": job_id, "fallback": True}

    def get_visible_active_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("active", athlete_id))
        return {"id": "active-fallback", "athlete_id": athlete_id}

    def get_latest_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("latest", athlete_id))
        return {"id": "latest-fallback", "athlete_id": athlete_id}

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("plan", plan_id))
        return {"id": plan_id, "plan_text": "full row"}

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any]:
        self.fallback_calls.append(("latest_plan", athlete_id))
        return {"id": "latest-plan", "plan_text": "full row"}

    def list_claimable_generation_jobs(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.fallback_calls.append(("claimable", kwargs))
        return [{"id": "fallback-job", "status": "queued"}]

    def list_admin_active_generation_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.fallback_calls.append(("active_jobs", limit))
        return [{"id": "fallback-active"}]


def test_compact_status_read_uses_rpc_without_full_row_fallback() -> None:
    store = _Store(
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

    result = store.get_generation_job_status("job-1")

    assert result == {
        "id": "job-1",
        "status": "running",
        "progress_milestones": [],
    }
    assert store.fallback_calls == []
    assert store.client.rpc_calls() == [("get_generation_job_status_v2", {"p_job_id": "job-1"})]


def test_athlete_status_reads_send_the_athlete_id() -> None:
    active = {"id": "job-a", "status": "queued"}
    latest = {"id": "job-l", "status": "completed"}
    store = _Store(
        {
            "get_visible_active_generation_job_status_v2": [[active]],
            "get_latest_generation_job_status_v2": [latest],
        }
    )

    assert store.get_visible_active_generation_job_status("athlete-1") == active
    assert store.get_latest_generation_job_status("athlete-1") == latest
    assert store.fallback_calls == []
    assert store.client.rpc_calls() == [
        ("get_visible_active_generation_job_status_v2", {"p_athlete_id": "athlete-1"}),
        ("get_latest_generation_job_status_v2", {"p_athlete_id": "athlete-1"}),
    ]


def test_compact_status_read_falls_back_to_the_full_row_when_the_rpc_fails() -> None:
    store = _Store(
        {
            "get_generation_job_status_v2": [RuntimeError("function does not exist")],
            "get_visible_active_generation_job_status_v2": [RuntimeError("down")],
            "get_latest_generation_job_status_v2": [RuntimeError("down")],
        }
    )

    assert store.get_generation_job_status("job-2") == {"id": "job-2", "fallback": True}
    assert store.get_visible_active_generation_job_status("a1")["id"] == "active-fallback"
    assert store.get_latest_generation_job_status("a1")["id"] == "latest-fallback"
    assert store.fallback_calls == [("job", "job-2"), ("active", "a1"), ("latest", "a1")]


def test_plan_status_reads_select_four_columns() -> None:
    row = {"id": "plan-1", "status": "ready", "stage2_status": "stage2_pass", "intake_id": "i1"}
    store = _Store({"plans": [[row], [row]]})

    assert store.get_plan_status("plan-1") == row
    assert store.get_latest_plan_status("athlete-1") == row
    assert store.fallback_calls == []
    assert [(method, args, kwargs) for _, method, args, kwargs in store.client.log] == [
        ("select", ("id,status,stage2_status,intake_id",), {}),
        ("eq", ("id", "plan-1"), {}),
        ("limit", (1,), {}),
        ("select", ("id,status,stage2_status,intake_id",), {}),
        ("eq", ("athlete_id", "athlete-1"), {}),
        ("order", ("created_at",), {"desc": True}),
        ("limit", (1,), {}),
    ]


def test_plan_status_reads_fall_back_to_the_full_row() -> None:
    store = _Store({"plans": [RuntimeError("down"), RuntimeError("down")]})

    assert store.get_plan_status("plan-1")["plan_text"] == "full row"
    assert store.get_latest_plan_status("athlete-1")["plan_text"] == "full row"
    assert store.fallback_calls == [("plan", "plan-1"), ("latest_plan", "athlete-1")]


def test_compact_status_store_caches_plan_status_within_one_response() -> None:
    row = {"id": "plan-1", "status": "ready", "stage2_status": "stage2_pass", "intake_id": "i1"}
    store = _Store({"plans": [[row]]})
    compact = performance.compact_status_store(store)

    assert compact.get_plan(" plan-1 ") == row
    assert compact.get_plan("plan-1") == row
    assert compact.get_plan("") is None
    assert len([entry for entry in store.client.log if entry[1] == "select"]) == 1
    # Everything else still reaches the store.
    assert compact.get_generation_job("job-9") == {"id": "job-9", "fallback": True}


def test_idle_worker_backoff_skips_database_until_deadline(monkeypatch) -> None:
    store = _Store({"list_claimable_generation_jobs_v2": [[], []]})
    times = iter([100.0, 101.0, 107.0])
    monkeypatch.setattr(performance.time, "monotonic", lambda: next(times))
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_INITIAL_SECONDS", "6")
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_MAX_SECONDS", "15")

    assert store.poll_claimable_generation_jobs(limit=1, stale_after_seconds=90) == []
    assert store.poll_claimable_generation_jobs(limit=1, stale_after_seconds=90) == []
    assert store.poll_claimable_generation_jobs(limit=1, stale_after_seconds=90) == []

    assert [name for name, _ in store.client.rpc_calls()] == [
        "list_claimable_generation_jobs_v2",
        "list_claimable_generation_jobs_v2",
    ]
    assert store._claimable_idle_delay_seconds == 12.0


def test_returned_job_resets_idle_backoff(monkeypatch) -> None:
    queued = {"id": "queued-job", "status": "queued", "progress_milestones": []}
    store = _Store({"list_claimable_generation_jobs_v2": [[], [queued]]})
    times = iter([200.0, 207.0])
    monkeypatch.setattr(performance.time, "monotonic", lambda: next(times))
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_INITIAL_SECONDS", "6")
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_IDLE_POLL_MAX_SECONDS", "15")

    assert store.poll_claimable_generation_jobs(limit=1, stale_after_seconds=90) == []
    assert store.poll_claimable_generation_jobs(limit=1, stale_after_seconds=90) == [queued]

    assert store._claimable_idle_delay_seconds == 0.0
    assert store._claimable_next_poll_at == 0.0


def test_queue_poll_sends_its_parameters_and_falls_back_on_failure(monkeypatch) -> None:
    monkeypatch.delenv("UNLXCK_CLAIM_LEGACY_BLANK_STATUS_JOBS", raising=False)
    store = _Store({"list_claimable_generation_jobs_v2": [RuntimeError("missing rpc")]})

    assert store.poll_claimable_generation_jobs(limit=500, stale_after_seconds=30) == [
        {"id": "fallback-job", "status": "queued"}
    ]
    ((name, params),) = store.client.rpc_calls()
    assert name == "list_claimable_generation_jobs_v2"
    assert params["p_limit"] == 100
    assert params["p_include_legacy_blank"] is False
    assert isinstance(params["p_stale_before"], str)
    assert store.fallback_calls == [("claimable", {"limit": 500, "stale_after_seconds": 30})]
    assert store._claimable_next_poll_at == 0.0


def test_recovery_candidates_use_the_compact_scan() -> None:
    summary = {"id": "job-1", "status": "running"}
    store = _Store({"list_active_generation_jobs_for_recovery_v1": [[summary, "junk"]]})

    assert store.list_generation_job_recovery_candidates(limit=250) == [summary]
    assert store.client.rpc_calls() == [("list_active_generation_jobs_for_recovery_v1", {"p_limit": 100})]
    assert store.fallback_calls == []


def test_recovery_candidates_fall_back_to_the_admin_listing() -> None:
    failing = _Store({"list_active_generation_jobs_for_recovery_v1": [RuntimeError("down")]})
    non_list = _Store({"list_active_generation_jobs_for_recovery_v1": [None]})

    assert failing.list_generation_job_recovery_candidates(limit=7) == [{"id": "fallback-active"}]
    assert non_list.list_generation_job_recovery_candidates(limit=7) == [{"id": "fallback-active"}]
    assert failing.fallback_calls == [("active_jobs", 7)]
    assert non_list.fallback_calls == [("active_jobs", 7)]
