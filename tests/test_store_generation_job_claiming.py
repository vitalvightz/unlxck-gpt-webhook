from types import SimpleNamespace
from unittest.mock import MagicMock

from api.store import SupabaseAppStore, _should_recover_stalled_job


def _build_store_with_rows(
    *,
    queued_rows,
    running_heartbeat_rows,
    running_started_rows,
    null_status_rows=None,
    blank_status_rows=None,
):
    store = SupabaseAppStore(client=MagicMock(), admin_emails=set())

    def _run_with_transient_retry(*, operation, fn):
        del fn
        if operation == "list_claimable_generation_jobs:select_queued":
            return SimpleNamespace(data=queued_rows)
        if operation == "list_claimable_generation_jobs:select_null_status":
            return SimpleNamespace(data=null_status_rows or [])
        if operation == "list_claimable_generation_jobs:select_blank_status":
            return SimpleNamespace(data=blank_status_rows or [])
        if operation == "list_claimable_generation_jobs:select_running_stale_heartbeat":
            return SimpleNamespace(data=running_heartbeat_rows)
        if operation == "list_claimable_generation_jobs:select_running_stale_started":
            return SimpleNamespace(data=running_started_rows)
        raise AssertionError(f"unexpected operation: {operation}")

    store._run_with_transient_retry = _run_with_transient_retry  # type: ignore[attr-defined]
    return store


def test_supabase_list_claimable_generation_jobs_includes_normal_queued_rows():
    queued_job = {"id": "queued-1", "status": "queued", "created_at": "2026-01-01T00:00:00+00:00"}
    store = _build_store_with_rows(
        queued_rows=[queued_job],
        running_heartbeat_rows=[],
        running_started_rows=[],
    )

    claimable = store.list_claimable_generation_jobs(limit=20, stale_after_seconds=90)

    assert [job["id"] for job in claimable] == ["queued-1"]


def test_supabase_list_claimable_generation_jobs_includes_legacy_blank_status_rows():
    null_status_job = {"id": "legacy-null", "status": None, "created_at": "2026-01-01T00:00:00+00:00"}
    blank_status_job = {"id": "legacy-blank", "status": "", "created_at": "2026-01-01T00:00:01+00:00"}
    store = _build_store_with_rows(
        queued_rows=[],
        null_status_rows=[null_status_job],
        blank_status_rows=[blank_status_job],
        running_heartbeat_rows=[],
        running_started_rows=[],
    )

    claimable = store.list_claimable_generation_jobs(limit=20, stale_after_seconds=90)

    assert [job["id"] for job in claimable] == ["legacy-null", "legacy-blank"]


def test_supabase_list_claimable_generation_jobs_filters_running_by_startup_stale_only():
    fresh_running = {
        "id": "running-fresh",
        "status": "running",
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "3026-01-01T00:00:00+00:00",
        "heartbeat_at": "3026-01-01T00:00:00+00:00",
        "progress_milestones": [{"code": "job_loaded"}],
        "stage1_result": None,
        "final_result": None,
        "completed_at": None,
    }
    startup_stale_running = {
        "id": "running-startup-stale",
        "status": "running",
        "created_at": "2026-01-01T00:00:01+00:00",
        "started_at": "2026-01-01T00:00:01+00:00",
        "heartbeat_at": "2026-01-01T00:00:01+00:00",
        "progress_milestones": [{"code": "job_loaded"}],
        "stage1_result": None,
        "final_result": None,
        "completed_at": None,
    }
    mid_pipeline_stale_running = {
        "id": "running-mid-pipeline",
        "status": "running",
        "created_at": "2026-01-01T00:00:02+00:00",
        "started_at": "2026-01-01T00:00:02+00:00",
        "heartbeat_at": "2026-01-01T00:00:02+00:00",
        "progress_milestones": [{"code": "job_loaded"}, {"code": "stage1_planner_starting"}],
        "stage1_result": {"status": "ready"},
        "final_result": None,
        "completed_at": None,
    }

    store = _build_store_with_rows(
        queued_rows=[],
        running_heartbeat_rows=[fresh_running, startup_stale_running, mid_pipeline_stale_running],
        running_started_rows=[],
    )

    claimable = store.list_claimable_generation_jobs(limit=20, stale_after_seconds=1)

    assert "running-startup-stale" in [job["id"] for job in claimable]
    assert "running-fresh" not in [job["id"] for job in claimable]
    assert "running-mid-pipeline" not in [job["id"] for job in claimable]


def test_should_recover_stalled_job_when_final_result_present():
    assert _should_recover_stalled_job({"final_result": {"status": "ready"}}) is True


def test_should_recover_stalled_job_when_plan_id_present():
    assert _should_recover_stalled_job({"plan_id": "plan_123", "final_result": None}) is True


def test_should_recover_stalled_job_when_terminal_milestone_present():
    assert (
        _should_recover_stalled_job(
            {
                "progress_milestones": [
                    {"code": "request_payload_parsed"},
                    {"code": "final_result_persisted", "meta": {"plan_id": "plan_from_meta"}},
                ]
            }
        )
        is True
    )


def test_should_not_recover_stalled_job_without_outputs_or_terminal_milestone():
    assert _should_recover_stalled_job({"progress_milestones": [{"code": "final_result_persisted"}]}) is False
    assert _should_recover_stalled_job({"progress_milestones": [{"code": "stage1_planner_invoked"}]}) is False
