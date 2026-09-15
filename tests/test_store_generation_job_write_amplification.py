"""Regression tests for the 2026-09-15 generation-job write amplification.

A single generation drove ~280 PATCHes and ~285 full-row GETs against
generation_jobs in five minutes, saturating a nano Postgres instance. The reads
were the expensive half: ``select="*"`` on a table that is ~97% TOAST, so every
read-back pulled request_payload/stage1_result/final_result out of TOAST
storage.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.store import (
    GENERATION_JOB_ADMIN_ACTIVE_SELECT,
    GENERATION_JOB_ADMIN_LIST_SELECT,
    GENERATION_JOB_ADMIN_TRIAGE_SELECT,
    GENERATION_JOB_STATUS_GUARD_SELECT,
    SupabaseAppStore,
)

_HEAVY_COLUMNS = ("stage1_result", "final_result", "request_payload", "progress_milestones")


class _RecordingClient:
    """MagicMock-backed client that records every ``.select(...)`` projection."""

    def __init__(self, row: dict | None = None) -> None:
        self.selects: list[str] = []
        self.updates: list[dict] = []
        self._row = row if row is not None else {"id": "job-1", "status": "running"}

    def table(self, _name: str):
        client = self

        class _Query:
            def select(self, projection: str):
                client.selects.append(projection)
                return self

            def update(self, payload: dict):
                client.updates.append(dict(payload))
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def limit(self, *_args, **_kwargs):
                return self

            def execute(self):
                return SimpleNamespace(data=[client._row])

        return _Query()


def _store(client) -> SupabaseAppStore:
    store = SupabaseAppStore(client=client, admin_emails=set())
    store._run_with_transient_retry = lambda *, operation, fn: fn()  # type: ignore[attr-defined]
    return store


def test_status_guard_read_does_not_select_heavy_columns():
    """The transition guard only needs the current status."""
    client = _RecordingClient()
    store = _store(client)

    store.update_generation_job("job-1", refresh=False, status="failed")

    assert client.selects == [GENERATION_JOB_STATUS_GUARD_SELECT]
    projection = client.selects[0]
    assert "*" not in projection
    for heavy in _HEAVY_COLUMNS:
        assert heavy not in projection


def test_update_with_refresh_false_performs_no_read_back():
    client = _RecordingClient()
    store = _store(client)

    result = store.update_generation_job("job-1", refresh=False, heartbeat_at="2026-09-15T00:00:00Z")

    assert result == {}
    assert client.selects == []  # no status guard, no read-back
    assert client.updates == [{"heartbeat_at": "2026-09-15T00:00:00Z"}]


def test_update_defaults_to_refreshing_for_callers_that_need_the_row():
    """Admin cancel and stale-job recovery use the returned row."""
    client = _RecordingClient()
    store = _store(client)

    result = store.update_generation_job("job-1", heartbeat_at="2026-09-15T00:00:00Z")

    assert result == {"id": "job-1", "status": "running"}
    assert client.selects  # the read-back still happens by default


def test_update_missing_job_still_404s_through_the_narrow_guard():
    client = _RecordingClient()
    client._row = None

    class _EmptyClient(_RecordingClient):
        def table(self, name: str):
            query = super().table(name)
            query.execute = lambda: SimpleNamespace(data=[])  # type: ignore[method-assign]
            return query

    empty = _EmptyClient()
    store = _store(empty)

    with pytest.raises(Exception) as excinfo:
        store.update_generation_job("job-1", refresh=False, status="failed")

    assert getattr(excinfo.value, "status_code", None) == 404


def test_fake_store_matches_the_real_update_generation_job_contract():
    """FakeStore backs most generation tests; a divergent contract hides bugs.

    Taking ``refresh`` through **changes persisted {"refresh": False} into the
    in-memory row and returned that row, where SupabaseAppStore treats refresh
    as control data and returns {}.
    """
    from support import FakeStore

    store = FakeStore()
    store.generation_jobs["job-1"] = {"id": "job-1", "status": "running"}

    result = store.update_generation_job("job-1", refresh=False, heartbeat_at="2026-09-15T00:00:00Z")

    assert result == {}, "refresh=False must return {} like SupabaseAppStore"
    stored = store.generation_jobs["job-1"]
    assert "refresh" not in stored, "refresh is control data, never a column"
    assert stored["heartbeat_at"] == "2026-09-15T00:00:00Z"

    refreshed = store.update_generation_job("job-1", heartbeat_at="2026-09-15T00:01:00Z")
    assert refreshed["id"] == "job-1"
    assert "refresh" not in refreshed


@pytest.mark.parametrize(
    ("projection", "required"),
    [
        (GENERATION_JOB_ADMIN_ACTIVE_SELECT, ("request_payload", "progress_milestones", "status")),
        (
            GENERATION_JOB_ADMIN_TRIAGE_SELECT,
            ("request_payload", "final_result", "progress_milestones"),
        ),
        (GENERATION_JOB_ADMIN_LIST_SELECT, ("request_payload", "final_result", "id", "error")),
    ],
)
def test_admin_projections_still_carry_the_fields_admin_views_need(projection, required):
    """Narrowing the runtime path must not strip the admin/triage payloads."""
    columns = {column.strip() for column in projection.split(",")}
    for column in required:
        assert column in columns
