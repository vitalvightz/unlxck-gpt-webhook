from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import HTTPException, status
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import pytest

import api.app as app_module
from api.app import create_app
from api.auth import AuthenticatedUser
from api.generation_runtime import run_generation_job, schedule_generation_job_if_needed, should_skip_stage2
from api.models import ProfileUpdateRequest
from api.stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError
from api.store import is_worker_start_stale_generation_job
from support import (
    SYSTEM_SCENARIOS,
    FakeAuthService,
    FakeStage2Automator,
    FakeStore,
    SystemScenario,
    _build_client,
    _build_request,
    _now,
    _planner,
    _start_generation,
    finalized_result,
    stage1_result,
)


def test_generate_plan_persists_validated_final_plan_and_history():
    client, store, stage2 = _build_client()
    payload = _build_request().model_dump(mode="json")

    _, job = _start_generation(client)
    detail = client.get(
        f"/api/plans/{job['plan_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert detail.status_code == 200
    body = detail.json()
    assert payload["fight_date"] == "2026-04-18"
    assert job["status"] == "completed"
    saved = store.get_plan(job["plan_id"])
    assert saved["plan_text"] == "# Final Plan"
    assert saved["pdf_url"] is None
    assert saved["status"] == "ready"
    assert body["admin_outputs"] is None
    assert body["safety_state"]["state"] == "plan_ready"
    assert body["safety_state"]["status_chip"] == "PLAN READY"
    assert store.get_latest_intake("athlete-1")["intake"]["fight_date"] == "2026-04-18"
    assert len(store.list_user_plans("athlete-1")) == 1
    saved = next(iter(store.plans.values()))
    assert saved["draft_plan_text"] == "# Stage 1 Draft"
    assert saved["final_plan_text"] == "# Final Plan"
    assert saved["stage2_status"] == "stage2_pass"
    assert saved["pdf_url"] is None
    assert stage2.calls[0]["stage2_handoff_text"] == "handoff"


@pytest.mark.parametrize("status_value", ["completed", "review_required", "failed"])
def test_get_generation_job_does_not_mutate_terminal_non_running_statuses(status_value: str):
    # Queued jobs are intentionally schedulable when polled; stale recovery should
    # leave terminal non-running statuses alone.
    client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=f"job-{status_value}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status=status_value, started_at="2026-01-01T00:00:00+00:00", heartbeat_at="2026-01-01T00:00:00+00:00")

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == status_value


def test_get_generation_job_keeps_running_when_heartbeat_is_fresh():
    client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="fresh-running",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=now_iso,
        heartbeat_at=now_iso,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_active_generation_job_returns_latest_queued_job_for_logged_in_athlete():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="old-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    latest = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="latest-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == latest["id"]
    assert body["status"] == "queued"


def test_get_active_generation_job_returns_running_job_for_logged_in_athlete():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="running-active",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(created["id"], status="running", started_at=now_iso, heartbeat_at=now_iso)

    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["id"]
    assert body["status"] == "running"


@pytest.mark.parametrize("terminal_status", ["completed", "failed", "review_required"])
def test_get_active_generation_job_excludes_terminal_statuses(terminal_status: str):
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=f"terminal-{terminal_status}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status=terminal_status, completed_at=_now())

    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json() is None


def test_get_active_generation_job_does_not_return_other_athlete_job():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="other-athlete-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json() is None


def test_get_active_generation_job_recovers_startup_stale_running_to_queued():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-running-active",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(created["id"], status="running", started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[])

    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["id"]
    assert body["status"] == "queued"


def test_get_active_generation_job_schedules_queued_job_without_creating_new_job():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="schedule-active-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    before_count = len(store.generation_jobs)

    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["id"]
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == before_count


def test_self_serve_generation_job_is_created_queued_before_worker_claim():
    client, store, _ = _build_client(enable_in_process_generation=False)

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "queued-before-claim"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    stored = store.get_generation_job(body["job_id"])
    assert stored["status"] == "queued"
    assert stored["started_at"] is None
    assert stored["heartbeat_at"] is None
    assert stored["progress_milestones"] == []


def test_worker_claim_adds_job_loaded_milestone_and_fresh_heartbeat():
    store = FakeStore()
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="claim-start",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    claimed = store.claim_generation_job_start(job["id"])

    assert claimed["status"] == "running"
    assert claimed["started_at"] is not None
    assert claimed["heartbeat_at"] is not None
    assert claimed["progress_milestones"][0]["code"] == "job_loaded"
    assert claimed["progress_milestones"][0]["label"] == "Generation job loaded"


def test_scheduler_keeps_queued_job_until_worker_claims_and_processes():
    store = FakeStore()
    stage2 = FakeStage2Automator(result=finalized_result())
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="scheduler-does-not-claim",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    active_tasks: set[str] = set()

    scheduled = asyncio.run(
        schedule_generation_job_if_needed(
            job=created,
            background_tasks=BackgroundTasks(),
            store=store,
            planner_fn=_planner,
            stage2=stage2,
            active_tasks=active_tasks,
            enable_in_process_generation=True,
            stale_job_checker=app_module.is_stale_job,
            stale_after_seconds=90,
        )
    )

    assert scheduled["status"] == "queued"
    before_worker = store.get_generation_job(created["id"])
    assert before_worker["status"] == "queued"
    assert before_worker["progress_milestones"] == []
    assert created["id"] in active_tasks

    asyncio.run(
        run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=_planner,
            stage2=stage2,
            active_tasks=active_tasks,
        )
    )

    after_worker = store.get_generation_job(created["id"])
    milestone_codes = [entry.get("code") for entry in after_worker["progress_milestones"]]
    assert after_worker["status"] == "completed"
    assert "job_loaded" in milestone_codes
    assert "request_payload_parsed" in milestone_codes
    assert after_worker["heartbeat_at"] is not None


def test_worker_start_stale_helper_does_not_mark_fresh_equal_heartbeat_and_started_as_stale():
    now_iso = _now()
    job = {
        "status": "running",
        "completed_at": None,
        "stage1_result": None,
        "final_result": None,
        "started_at": now_iso,
        "heartbeat_at": now_iso,
        "progress_milestones": [{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
    }
    assert is_worker_start_stale_generation_job(job, stale_after_seconds=90) is False


def test_worker_start_stale_helper_marks_old_equal_heartbeat_and_started_as_stale():
    job = {
        "status": "running",
        "completed_at": None,
        "stage1_result": None,
        "final_result": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "heartbeat_at": "2026-01-01T00:00:00+00:00",
        "progress_milestones": [{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
    }
    assert is_worker_start_stale_generation_job(job, stale_after_seconds=90) is True


def test_scheduler_returns_recovered_queued_row_for_stale_running_job():
    store = FakeStore()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-running-returns-queued-row",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    stale_started = "2026-01-01T00:00:00+00:00"
    stale_running = store.update_generation_job(
        created["id"],
        status="running",
        started_at=stale_started,
        heartbeat_at=stale_started,
        progress_milestones=[],
    )

    scheduled = asyncio.run(
        schedule_generation_job_if_needed(
            job=stale_running,
            background_tasks=BackgroundTasks(),
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
            enable_in_process_generation=False,
            stale_job_checker=app_module.is_stale_job,
            stale_after_seconds=90,
        )
    )

    assert scheduled["status"] == "queued"
    assert scheduled["started_at"] is None
    assert scheduled["heartbeat_at"] is None


def test_retry_requeues_pre_start_stale_running_job_instead_of_leaving_running():
    client, store, _ = _build_client(enable_in_process_generation=False)
    stale = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="prestart-stale-retry",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    stale_started = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        stale["id"],
        status="running",
        started_at=stale_started,
        heartbeat_at=stale_started,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
    )

    retried = client.post(
        f"/api/generation-jobs/{stale['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
        json={"reason": "retry pre-start stale"},
    )

    assert retried.status_code == 202
    body = retried.json()
    assert body["job_id"] == stale["id"]
    assert body["status"] == "queued"
    refreshed = store.get_generation_job(stale["id"])
    assert refreshed["status"] == "queued"
    assert refreshed["started_at"] is None
    assert refreshed["heartbeat_at"] is None


def test_retry_requeues_worker_start_stale_running_job_with_only_job_loaded():
    client, store, _ = _build_client(enable_in_process_generation=False)
    stale = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-start-stale-retry",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    stale_started = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        stale["id"],
        status="running",
        started_at=stale_started,
        heartbeat_at=stale_started,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
        stage1_result=None,
        final_result=None,
    )

    retried = client.post(
        f"/api/generation-jobs/{stale['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
        json={"reason": "retry worker-start stale"},
    )

    assert retried.status_code == 202
    body = retried.json()
    assert body["job_id"] == stale["id"]
    assert body["status"] == "queued"
    refreshed = store.get_generation_job(stale["id"])
    assert refreshed["status"] == "queued"
    assert refreshed["started_at"] is None
    assert refreshed["heartbeat_at"] is None
    assert refreshed["progress_milestones"] == []


def test_retry_does_not_requeue_worker_start_job_loaded_when_heartbeat_is_fresh():
    client, store, _ = _build_client(enable_in_process_generation=False)
    running = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-start-fresh-retry",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(
        running["id"],
        status="running",
        started_at=now_iso,
        heartbeat_at=now_iso,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
        stage1_result=None,
        final_result=None,
    )

    retried = client.post(
        f"/api/generation-jobs/{running['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
        json={"reason": "retry worker-start fresh should block"},
    )

    assert retried.status_code == 409
    assert retried.json()["detail"] == "only failed generation jobs can be retried"


@pytest.mark.parametrize(
    ("heartbeat_at", "started_at"),
    [
        ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        (None, "2026-01-01T00:00:00+00:00"),
    ],
)
def test_get_generation_job_marks_stale_running_job_failed(heartbeat_at: str | None, started_at: str):
    client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=f"stale-running-{heartbeat_at or 'none'}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status="running", started_at=started_at, heartbeat_at=heartbeat_at)

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "Generation job stalled. Please try again."
    assert body["completed_at"] is not None


def test_create_with_same_client_request_resets_pre_start_stale_job_without_duplicate():
    client, store, _ = _build_client(enable_in_process_generation=False)
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="same-stale-request",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        existing["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
        progress_milestones=[],
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "same-stale-request"},
        json=_build_request({"fight_date": "2026-05-01"}).model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing["id"]
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == 1
    reset_job = store.get_generation_job(existing["id"])
    assert reset_job["status"] == "queued"
    assert reset_job["started_at"] is None
    assert reset_job["heartbeat_at"] is None
    assert reset_job["request_payload"]["fight_date"] == "2026-05-01"


def test_create_with_same_client_request_resets_worker_start_stale_job_without_duplicate():
    client, store, _ = _build_client(enable_in_process_generation=False)
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="same-worker-start-stale-request",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    stale_started = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        existing["id"],
        status="running",
        started_at=stale_started,
        heartbeat_at=stale_started,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
        stage1_result=None,
        final_result=None,
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "same-worker-start-stale-request"},
        json=_build_request({"fight_date": "2026-05-02"}).model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing["id"]
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == 1
    reset_job = store.get_generation_job(existing["id"])
    assert reset_job["status"] == "queued"
    assert reset_job["started_at"] is None
    assert reset_job["heartbeat_at"] is None
    assert reset_job["progress_milestones"] == []
    assert reset_job["request_payload"]["fight_date"] == "2026-05-02"


def test_create_with_same_client_request_does_not_reset_fresh_worker_start_job():
    client, store, _ = _build_client(enable_in_process_generation=False)
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="same-worker-start-fresh-request",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(
        existing["id"],
        status="running",
        started_at=now_iso,
        heartbeat_at=now_iso,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
        stage1_result=None,
        final_result=None,
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "same-worker-start-fresh-request"},
        json=_build_request({"fight_date": "2026-05-03"}).model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing["id"]
    assert body["status"] == "running"
    assert len(store.generation_jobs) == 1
    unchanged = store.get_generation_job(existing["id"])
    assert unchanged["status"] == "running"
    assert unchanged["progress_milestones"] == [{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}]
    assert unchanged["request_payload"]["fight_date"] == "2026-04-18"


def test_create_or_get_generation_job_preserves_plan_and_intake_when_resetting_pre_start_stale_job():
    store = FakeStore()
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="same-stale-request",
        source="admin_triage_resume",
        request_payload=_build_request().model_dump(mode="json"),
        plan_id="plan-123",
        intake_id="intake-123",
    )
    store.update_generation_job(
        existing["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
        progress_milestones=[],
    )

    reset_job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="same-stale-request",
        source="admin_triage_resume",
        request_payload=_build_request({"fight_date": "2026-05-01"}).model_dump(mode="json"),
        plan_id="plan-123",
        intake_id="intake-123",
    )

    assert len(store.generation_jobs) == 1
    assert reset_job["status"] == "queued"
    assert reset_job["plan_id"] == "plan-123"
    assert reset_job["intake_id"] == "intake-123"


def test_status_endpoint_does_not_treat_pre_start_stale_job_as_active_running():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="pre-start-status",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        created["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
        progress_milestones=[],
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["status"] != "running"


def test_stale_failed_job_can_retry_via_existing_retry_endpoint():
    client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-then-retry",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status="running", started_at="2026-01-01T00:00:00+00:00", heartbeat_at=None)
    polled = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert polled.status_code == 200
    assert polled.json()["status"] == "failed"

    retried = client.post(f"/api/generation-jobs/{created['id']}/retry", headers={"Authorization": "Bearer athlete-token"})
    assert retried.status_code == 202


def test_non_owner_cannot_trigger_stale_recovery_on_another_users_job():
    client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="other-athlete-running",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status="running", started_at="2026-01-01T00:00:00+00:00", heartbeat_at=None)

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 403


def test_get_generation_job_marks_stale_running_failed_when_in_process_generation_disabled():
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = FakeStore()
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-with-in-process-disabled",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        created["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at=None,
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"] == "Generation job stalled. Please try again."


def test_generate_plan_persists_retry_pass_result():
    client, store, _ = _build_client(
        FakeStage2Automator(
            result=finalized_result(
                plan_text="# Final Retry Plan",
                final_plan_text="# Final Retry Plan",
                stage2_status="stage2_retry_pass",
                stage2_retry_text="repair prompt",
                stage2_attempt_count=2,
            )
        )
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    saved = next(iter(store.plans.values()))
    assert saved["plan_text"] == "# Final Retry Plan"
    assert saved["stage2_status"] == "stage2_retry_pass"
    assert saved["stage2_retry_text"] == "repair prompt"
    assert saved["stage2_attempt_count"] == 2


def test_generation_job_starts_when_running_count_below_concurrency_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "2")
    client, store, _ = _build_client()
    running = store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="running-cap-check",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(running["id"], status="running", started_at=now_iso, heartbeat_at=now_iso)

    body, job = _start_generation(client)
    assert body["status"] in {"queued", "running", "completed"}
    assert job["status"] == "completed"


def test_generation_job_remains_queued_when_running_count_hits_concurrency_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1")
    client, store, _ = _build_client()
    running = store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="running-at-cap",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(running["id"], status="running", started_at=now_iso, heartbeat_at=now_iso)

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    queued = store.get_generation_job(body["job_id"])
    assert queued["status"] == "queued"


def test_failed_completed_and_stale_running_jobs_do_not_count_against_concurrency_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1")
    client, store, _ = _build_client()
    stale = store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="stale-running",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        stale["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
    )
    completed = store.create_or_get_generation_job(
        athlete_id="athlete-3",
        client_request_id="completed-job",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(completed["id"], status="completed", completed_at=_now())
    failed = store.create_or_get_generation_job(
        athlete_id="athlete-4",
        client_request_id="failed-job",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(failed["id"], status="failed", completed_at=_now(), error="fail")

    body, job = _start_generation(client)
    assert body["status"] in {"queued", "running", "completed"}
    assert job["status"] == "completed"


def test_admin_generation_respects_same_global_concurrency_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1")
    client, store, _ = _build_client()
    # Seed latest intake so admin generate-from-latest-intake can schedule a job.
    _start_generation(client)
    running = store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="running-admin-cap",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(running["id"], status="running", started_at=now_iso, heartbeat_at=now_iso)

    response = client.post(
        "/api/admin/athletes/athlete-1/plans/generate-from-latest-intake",
        headers={"Authorization": "Bearer admin-token", "X-Client-Request-Id": "admin-cap"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"


def test_generate_plan_request_payload_strips_quick_build_only_metadata():
    client, store, _ = _build_client()
    payload = _build_request().model_dump(mode="json")
    payload.update(
        {
            "plan_source": "quick_build",
            "setup_source": "wizard",
            "equipment_preset": "minimal",
            "training_preset": "balanced",
            "focus_preset": "conditioning",
        }
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=payload,
    )

    assert response.status_code == 202
    job = next(iter(store.generation_jobs.values()))
    assert "plan_source" not in job["request_payload"]
    assert "setup_source" not in job["request_payload"]
    assert "equipment_preset" not in job["request_payload"]
    assert "training_preset" not in job["request_payload"]
    assert "focus_preset" not in job["request_payload"]


def test_generate_plan_returns_review_required_when_stage2_needs_manual_review():
    client, store, _ = _build_client(
        FakeStage2Automator(
            result=finalized_result(
                status="review_required",
                plan_text="",
                final_plan_text="# Failed Stage 2 Output",
                stage2_status="stage2_failed",
                stage2_retry_text="repair prompt",
                stage2_validator_report={"errors": [{"code": "restriction_violation"}], "warnings": []},
                stage2_attempt_count=2,
            )
        )
    )

    _, job = _start_generation(client)

    assert job["status"] == "review_required"
    milestone_details = [
        milestone["detail"]
        for milestone in job["progress_milestones"]
        if milestone["code"].startswith("stage2_")
    ]
    assert (
        "First-pass finalizer output did not pass validation. No automatic retry was sent."
        in milestone_details
    )
    assert "Validator passed. Final coach-voice plan ready for handoff." not in milestone_details
    saved = next(iter(store.plans.values()))
    assert saved["final_plan_text"] == "# Failed Stage 2 Output"
    assert saved["stage2_status"] == "stage2_failed"


@pytest.mark.parametrize("scenario", SYSTEM_SCENARIOS, ids=lambda scenario: scenario.key)
def test_curated_system_scenarios_cover_generation_and_hold_behavior(scenario: SystemScenario):
    client, store, _ = _build_client(FakeStage2Automator(result=scenario.automator_result))
    request = _build_request(scenario.request_overrides)

    _, job = _start_generation(client, request)

    saved = next(iter(store.plans.values()))
    latest_intake = store.get_latest_intake("athlete-1")["intake"]

    assert job["status"] == ("completed" if scenario.expected_status == "ready" else scenario.expected_status)
    assert latest_intake["fight_date"] == request.fight_date
    assert latest_intake["injuries"] == request.injuries
    assert latest_intake["equipment_access"] == request.equipment_access
    assert latest_intake["training_availability"] == request.training_availability
    assert latest_intake["hard_sparring_days"] == request.hard_sparring_days
    assert latest_intake["support_work_days"] == request.support_work_days
    assert store.profiles["athlete-1"]["onboarding_draft"] is None

    if scenario.expected_status == "ready":
        assert scenario.support_marker in saved["plan_text"]
        assert "Primary:" not in saved["plan_text"]
        assert "Fallback:" not in saved["plan_text"]
        assert saved["stage2_status"] == "stage2_pass"
    else:
        assert saved["plan_text"] == ""
        warning_codes = [warning["code"] for warning in saved["stage2_validator_report"]["warnings"]]
        assert scenario.expected_review_code in warning_codes
        assert saved["stage2_status"] == "stage2_failed"
        assert saved["stage2_retry_text"] == "repair prompt"




def test_generation_pipeline_persists_triage_blocked_without_stage2_call():
    stage2 = FakeStage2Automator(result=finalized_result())

    def triage_blocked_planner(payload: dict) -> dict:
        return {
            "status": "triage_blocked",
            "ok": False,
            "plan_text": "## Injury Triage: Medical Hold",
            "coach_notes": "medical_hold",
            "pdf_url": None,
            "why_log": {"injury_triage": {"mode": "medical_hold"}},
            "stage2_payload": None,
            "planning_brief": None,
            "stage2_handoff_text": "",
            "stage2_status": "triage_blocked",
            "injury_triage": {
                "mode": "medical_hold",
                "should_block_stage2": True,
            },
            "parsing_metadata": {},
        }

    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = FakeStore()
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=triage_blocked_planner,
            stage2_automator=stage2,
        )
    )

    _, job = _start_generation(client)
    saved = next(iter(store.plans.values()))

    assert stage2.calls == []
    assert job["status"] == "completed"
    assert saved["status"] == "triage_blocked"
    assert saved["stage2_status"] == "triage_blocked"
    assert saved["stage2_payload"] is None
    detail = client.get(
        f"/api/plans/{saved['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert detail.status_code == 200
    safety = detail.json()["safety_state"]
    assert safety["state"] == "medical_hold"
    assert safety["status_chip"] == "MEDICAL HOLD"
    assert safety["stage2_skipped"] is True


def test_admin_triage_resume_without_plan_id_does_not_fall_back_to_latest_plan_for_same_intake():
    class NoLatestPlanFallbackStore(FakeStore):
        def get_latest_plan(self, athlete_id: str) -> dict | None:
            raise AssertionError("admin_triage_resume must not use latest_plan fallback")

    store = NoLatestPlanFallbackStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            plan_text="",
            final_plan_text="",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-job",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=blocked_plan["id"],
        intake_id=str(intake["id"]),
    )
    stage2 = FakeStage2Automator(result=finalized_result())

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=stage2,
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    updated_plan = store.get_plan(blocked_plan["id"])

    assert refreshed_job["status"] == "failed"
    assert "missing plan_id" in str(refreshed_job["error"])
    assert refreshed_job["plan_id"] is None
    assert updated_plan["status"] == "triage_blocked"
    assert updated_plan["stage2_status"] == "triage_blocked"
    assert len(store.list_user_plans(athlete.user_id)) == 1


def test_triage_blocked_plans_are_hidden_from_athlete_archive_but_visible_to_admin():
    """A triage block is a screening decision, not a plan — it must not
    surface in athlete-facing lists (`/api/me`, `/api/plans`,
    `/api/plans/latest`). Admin views must still see the row so the ops
    team can review and approve-and-resume it."""
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = FakeStore()
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            plan_text="",
            final_plan_text="",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    athlete_me = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert athlete_me.status_code == 200
    assert athlete_me.json()["latest_plan"] is None
    assert athlete_me.json()["plan_count"] == 0

    athlete_list = client.get("/api/plans", headers={"Authorization": "Bearer athlete-token"})
    assert athlete_list.status_code == 200
    assert athlete_list.json() == []

    athlete_latest = client.get("/api/plans/latest", headers={"Authorization": "Bearer athlete-token"})
    assert athlete_latest.status_code == 404

    # The plan is still in storage and admin can fetch it directly by id so
    # the approve-and-resume workflow remains available.
    assert store.get_plan(blocked_plan["id"]) is not None
    admin_detail = client.get(
        f"/api/plans/{blocked_plan['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert admin_detail.status_code == 200


def test_admin_triage_resume_without_linked_plan_fails_without_creating_duplicate():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(status="triage_blocked", stage2_status="triage_blocked"),
    )
    store.plans.pop(blocked_plan["id"], None)
    # Mirror the production hazard: an admin_triage_resume job whose linked
    # plan no longer exists (and there is no non-archived plan to fall back
    # to via intake_id). The worker must refuse to create a new plan.
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-job",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "refusing to create a duplicate plan" in str(refreshed_job["error"])
    assert refreshed_job["plan_id"] == str(blocked_plan["id"])
    assert store.list_user_plans(athlete.user_id) == []


def test_admin_triage_resume_fails_if_linked_plan_deleted_after_stage1():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(status="triage_blocked", stage2_status="triage_blocked"),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-delete-during-run",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )

    def planner(payload: dict) -> dict:
        store.delete_plan(str(blocked_plan["id"]))
        return stage1_result(status="ready")

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "linked plan was deleted while generation was running" in str(refreshed_job["error"])

def test_admin_triage_resume_linked_plan_for_different_athlete_fails_before_planner():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    other_athlete = AuthenticatedUser(
        user_id="athlete-2",
        email="bea@example.com",
        full_name="Bea Santos",
        metadata={},
    )
    store.ensure_profile(athlete)
    store.ensure_profile(other_athlete)
    request = _build_request()
    other_intake = store.create_intake(other_athlete.user_id, request)
    other_plan = store.create_plan(
        athlete_id=other_athlete.user_id,
        intake_id=str(other_intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-cross-athlete-plan",
        source="admin_triage_resume",
        request_payload={"invalid": "would fail if parsed"},
        intake_id=str(other_intake["id"]),
        plan_id=str(other_plan["id"]),
    )
    planner_calls = []

    def planner(payload: dict) -> dict:
        planner_calls.append(payload)
        return stage1_result()

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert refreshed_job["error"] == "admin triage resume job linked plan belongs to a different athlete"
    assert planner_calls == []
    assert store.get_plan(other_plan["id"])["status"] == "triage_blocked"


def test_admin_triage_resume_without_plan_id_fails_before_planner():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-missing-plan-id",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
    )
    planner_called = False

    def _planner_should_not_run(payload: dict) -> dict:
        nonlocal planner_called
        planner_called = True
        return _planner(payload)

    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_planner_should_not_run, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "missing plan_id" in str(refreshed_job["error"])
    assert planner_called is False


def test_admin_triage_resume_without_intake_id_fails_before_planner():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(athlete_id=athlete.user_id, intake_id=str(intake["id"]), request=request, result=finalized_result(status="triage_blocked", stage2_status="triage_blocked"))
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-missing-intake-id",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=str(blocked_plan["id"]),
    )
    planner_called = False

    def _planner_should_not_run(payload: dict) -> dict:
        nonlocal planner_called
        planner_called = True
        return _planner(payload)

    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_planner_should_not_run, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "missing intake_id" in str(refreshed_job["error"])
    assert planner_called is False


def test_admin_triage_resume_mismatched_intake_fails_before_planner():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake_a = store.create_intake(athlete.user_id, request)
    intake_b = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(athlete_id=athlete.user_id, intake_id=str(intake_a["id"]), request=request, result=finalized_result(status="triage_blocked", stage2_status="triage_blocked"))
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-mismatch-intake",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake_b["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    planner_called = False

    def _planner_should_not_run(payload: dict) -> dict:
        nonlocal planner_called
        planner_called = True
        return _planner(payload)

    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_planner_should_not_run, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "intake_id does not match linked plan intake_id" in str(refreshed_job["error"])
    assert planner_called is False


def test_admin_triage_resume_with_override_updates_blocked_plan_in_place():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            plan_text="",
            final_plan_text="",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    request_payload = request.model_dump(mode="json")
    request_payload["_triage_resume_override"] = {
        "approved": True,
        "allowed_modes": ["needs_review", "restricted_rehab_only"],
        "approved_by": {"user_id": "admin-1", "email": "ops@unlxck.test"},
        "reason": "injury details clarified",
    }
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-with-override",
        source="admin_triage_resume",
        request_payload=request_payload,
    )
    store.update_generation_job(
        job["id"],
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )

    def _override_aware_planner(payload: dict) -> dict:
        override = payload.get("_triage_resume_override") or {}
        assert override.get("approved") is True, (
            "worker must forward _triage_resume_override to the planner"
        )
        result = dict(stage1_result())
        result["why_log"] = {
            "strength": {},
            "injury_triage_resume_override": {
                "bypassed_blocking": True,
                "triage_mode": "needs_review",
                "runtime_triage_mode": "full_plan",
            },
            "injury_triage_original": {
                "mode": "needs_review",
                "should_block_stage2": True,
            },
        }
        return result

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_override_aware_planner,
            stage2=FakeStage2Automator(
                result=finalized_result(
                    why_log={
                        "strength": {},
                        "injury_triage_resume_override": {
                            "bypassed_blocking": True,
                            "triage_mode": "needs_review",
                            "runtime_triage_mode": "full_plan",
                        },
                        "injury_triage_original": {
                            "mode": "needs_review",
                            "should_block_stage2": True,
                        },
                    },
                )
            ),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    updated_plan = store.get_plan(blocked_plan["id"])

    assert refreshed_job["status"] == "completed"
    assert refreshed_job["plan_id"] == blocked_plan["id"]
    milestone_codes = [entry["code"] for entry in refreshed_job.get("progress_milestones", [])]
    assert milestone_codes[:8] == [
        "job_loaded",
        "admin_resume_linkage_validated",
        "request_payload_parsed",
        "profile_update_started",
        "profile_update_finished",
        "stage1_planner_starting",
        "stage1_planner_invoked",
        "stage1_planner_finished",
    ]
    assert updated_plan["status"] != "triage_blocked"
    assert updated_plan["status"] == "ready"
    why_log = updated_plan["why_log"]
    assert why_log["injury_triage_resume_override"]["bypassed_blocking"] is True
    assert why_log["injury_triage_original"]["mode"] == "needs_review"
    # Audit markers placed on the plan by the approve-and-resume endpoint
    # must survive the in-place update.
    assert why_log["triage_resume_approval"] == {"approved_by_email": "ops@unlxck.test"}
    assert why_log["triage_regeneration_cleared"] is True
    assert len(store.list_user_plans(athlete.user_id)) == 1

    milestone_codes = [
        milestone.get("code")
        for milestone in refreshed_job.get("progress_milestones", [])
        if isinstance(milestone, dict)
    ]
    assert "job_loaded" in milestone_codes
    assert "admin_resume_linkage_validated" in milestone_codes


def test_admin_triage_resume_source_case_normalization_and_linkage_milestone():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            plan_text="",
            final_plan_text="",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-case-normalization",
        source="Admin_Triage_Resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=blocked_plan["id"],
        intake_id=str(intake["id"]),
    )
    stage2 = FakeStage2Automator(result=finalized_result())

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=stage2,
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "completed"
    assert refreshed_job["plan_id"] == blocked_plan["id"]
    milestone_codes = [
        milestone.get("code")
        for milestone in refreshed_job.get("progress_milestones", [])
        if isinstance(milestone, dict)
    ]
    assert "job_loaded" in milestone_codes
    assert "admin_resume_linkage_validated" in milestone_codes


def test_admin_triage_resume_missing_plan_id_fails_before_stage1():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-missing-plan",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
    )

    def fail_planner(payload: dict) -> dict:
        raise AssertionError("planner should not be called")

    def fail_get_latest_plan(athlete_id: str) -> dict | None:
        raise AssertionError("latest_plan fallback used")

    def fail_create_plan(*args: Any, **kwargs: Any) -> dict:
        raise AssertionError("create_plan should not be called")

    store.get_latest_plan = fail_get_latest_plan
    store.create_plan = fail_create_plan

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=fail_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "plan_id" in (refreshed_job["error"] or "")
    assert refreshed_job["stage1_result"] is None


def test_admin_triage_resume_missing_intake_id_fails_before_stage1():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-missing-intake",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=blocked_plan["id"],
    )

    def fail_planner(payload: dict) -> dict:
        raise AssertionError("planner should not be called")

    def fail_get_latest_plan(athlete_id: str) -> dict | None:
        raise AssertionError("latest_plan fallback used")

    def fail_create_plan(*args: Any, **kwargs: Any) -> dict:
        raise AssertionError("create_plan should not be called")

    store.get_latest_plan = fail_get_latest_plan
    store.create_plan = fail_create_plan

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=fail_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "intake_id" in (refreshed_job["error"] or "")
    assert refreshed_job["stage1_result"] is None


def test_admin_triage_resume_linked_plan_mismatch_fails_before_stage1():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    other_athlete = AuthenticatedUser(
        user_id="other-athlete",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    store.ensure_profile(other_athlete)
    other_plan = store.create_plan(
        athlete_id="other-athlete",
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-athlete-mismatch",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=other_plan["id"],
        intake_id=str(intake["id"]),
    )

    def fail_planner(payload: dict) -> dict:
        raise AssertionError("planner should not be called")

    def fail_get_latest_plan(athlete_id: str) -> dict | None:
        raise AssertionError("latest_plan fallback used")

    def fail_create_plan(*args: Any, **kwargs: Any) -> dict:
        raise AssertionError("create_plan should not be called")

    store.get_latest_plan = fail_get_latest_plan
    store.create_plan = fail_create_plan

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=fail_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "athlete" in (refreshed_job["error"] or "")
    assert refreshed_job["stage1_result"] is None


def test_admin_triage_resume_linked_intake_mismatch_fails_before_stage1():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    other_intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-intake-mismatch",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=blocked_plan["id"],
        intake_id=str(other_intake["id"]),
    )

    def fail_planner(payload: dict) -> dict:
        raise AssertionError("planner should not be called")

    def fail_get_latest_plan(athlete_id: str) -> dict | None:
        raise AssertionError("latest_plan fallback used")

    def fail_create_plan(*args: Any, **kwargs: Any) -> dict:
        raise AssertionError("create_plan should not be called")

    store.get_latest_plan = fail_get_latest_plan
    store.create_plan = fail_create_plan

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=fail_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "failed"
    assert "intake" in (refreshed_job["error"] or "")
    assert refreshed_job["stage1_result"] is None


def test_admin_triage_resume_never_falls_back_to_latest_plan_or_create_plan():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-no-fallback",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=blocked_plan["id"],
        intake_id=str(intake["id"]),
    )

    def fail_get_latest_plan(athlete_id: str) -> dict | None:
        raise AssertionError("latest_plan fallback used")

    def fail_create_plan(*args: Any, **kwargs: Any) -> dict:
        raise AssertionError("create_plan should not be called")

    store.get_latest_plan = fail_get_latest_plan
    store.create_plan = fail_create_plan

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    updated_plan = store.get_plan(blocked_plan["id"])

    assert refreshed_job["status"] == "completed"
    assert refreshed_job["plan_id"] == blocked_plan["id"]
    assert updated_plan["status"] == "ready"
    assert len(store.list_user_plans(athlete.user_id)) == 1


def test_admin_triage_resume_stage1_planner_timeout_fails_without_touching_plan(monkeypatch):
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "0.01")

    class NoLatestPlanFallbackStore(FakeStore):
        def get_latest_plan(self, athlete_id: str) -> dict | None:
            raise AssertionError("admin_triage_resume must not use latest_plan fallback")

    store = NoLatestPlanFallbackStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_resume_approved",
            plan_text="",
            final_plan_text="",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    client_request_id = f"triage_resume_{blocked_plan['id']}"
    request_payload = request.model_dump(mode="json")
    request_payload["_triage_resume_override"] = {
        "approved": True,
        "allowed_modes": ["needs_review", "restricted_rehab_only"],
        "approved_by": {"user_id": "admin-1", "email": "ops@unlxck.test"},
        "reason": "retry after review",
    }
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload=request_payload,
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    now_iso = _now()
    store.update_generation_job(
        job["id"],
        status="running",
        started_at=now_iso,
        heartbeat_at=now_iso,
    )
    stage2 = FakeStage2Automator(result=finalized_result())

    def _slow_planner(payload: dict, *, progress_callback=None) -> dict:
        time.sleep(0.05)
        return stage1_result()

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_slow_planner,
            stage2=stage2,
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    updated_plan = store.get_plan(blocked_plan["id"])

    assert refreshed_job["status"] == "failed"
    assert refreshed_job["error"] == "Stage 1 planner timed out before producing a result."
    assert refreshed_job["stage1_result"] is None
    assert refreshed_job["final_result"] is None
    assert refreshed_job["completed_at"] is not None
    assert refreshed_job["heartbeat_at"] is not None
    assert refreshed_job["plan_id"] == str(blocked_plan["id"])
    assert refreshed_job["intake_id"] == str(intake["id"])
    assert refreshed_job["client_request_id"] == client_request_id
    milestone_codes = [entry["code"] for entry in refreshed_job.get("progress_milestones", [])]
    assert "stage1_planner_starting" in milestone_codes
    assert "stage1_planner_invoked" in milestone_codes
    assert "stage1_planner_finished" not in milestone_codes
    assert stage2.calls == []
    assert len(store.plans) == 1
    assert updated_plan["id"] == blocked_plan["id"]
    assert updated_plan["status"] == "triage_blocked"
    assert updated_plan["stage2_status"] == "triage_resume_approved"
    assert updated_plan["why_log"]["triage_resume_approval"] == {"approved_by_email": "ops@unlxck.test"}


def test_runtime_generation_saves_completed_plan():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="athlete@example.com",
        full_name="Athlete One",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request({"fight_date": "2026-08-15"})
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="runtime-job",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    completed_job = store.get_generation_job(job["id"])
    plans = store.list_user_plans(athlete.user_id)

    assert completed_job["status"] == "completed"
    assert completed_job["plan_id"]
    assert len(plans) == 1
    assert plans[0]["status"] == "ready"
    assert plans[0]["parsing_metadata"] == {}


def test_run_generation_job_does_not_reuse_archived_latest_plan_for_same_intake():
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="athlete@example.com",
        full_name="Athlete One",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request({"fight_date": "2026-08-15"})
    intake = store.create_intake(athlete.user_id, request)
    archived = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(status="archived", stage2_status="admin_archived"),
    )
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="runtime-job-archived-latest",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )
    store.update_generation_job(job["id"], intake_id=str(intake["id"]))

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    completed_job = store.get_generation_job(job["id"])
    assert completed_job["status"] == "completed"
    assert completed_job["plan_id"] != archived["id"]
    assert store.get_plan(archived["id"])["status"] == "archived"
    assert len(store.list_user_plans(athlete.user_id)) == 2


def test_should_skip_stage2_when_triage_blocked_status_has_no_nested_flag():
    assert (
        should_skip_stage2(
            {
                "status": "triage_blocked",
                "injury_triage": {},
            }
        )
        is True
    )


def test_should_skip_stage2_when_why_log_carries_needs_review_mode():
    assert (
        should_skip_stage2(
            {
                "status": "generated",
                "why_log": {"injury_triage": {"mode": "needs_review"}},
            }
        )
        is True
    )

def test_should_not_skip_stage2_when_triage_resume_override_is_approved():
    assert (
        should_skip_stage2(
            {
                "status": "generated",
                "why_log": {"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
            },
            allow_triage_resume_override=True,
        )
        is False
    )


def test_stage2_unavailable_returns_failed_job_without_persisting_plan():
    client, store, _ = _build_client(
        FakeStage2Automator(
            error=Stage2AutomationUnavailableError("OPENAI_API_KEY is required for automated Stage 2 finalization.")
        )
    )

    _, job = _start_generation(client)

    assert job["status"] == "failed"
    assert "OPENAI_API_KEY" in job["error"]
    assert len(store.plans) == 0


def test_stage2_gateway_failure_returns_failed_job_without_persisting_plan():
    client, store, _ = _build_client(
        FakeStage2Automator(error=Stage2AutomationError("Stage 2 model request failed"))
    )

    _, job = _start_generation(client)

    assert job["status"] == "failed"
    assert "Stage 2 model request failed" in job["error"]
    assert len(store.plans) == 0


def test_stage2_insufficient_quota_masks_athlete_error_and_preserves_admin_detail():
    client, store, _ = _build_client(
        FakeStage2Automator(
            error=Stage2AutomationError(
                'Error code: 429 - {"error":{"message":"You exceeded your current quota","code":"insufficient_quota"}}'
            )
        )
    )

    _, job = _start_generation(client)
    assert job["status"] == "failed"
    assert job["error"] == "Generation is temporarily unavailable. Please try again later."
    assert len(store.plans) == 0

    saved = store.get_generation_job(job["job_id"])
    assert saved is not None
    assert saved["status"] == "failed"
    assert saved["error"] == "OpenAI quota exceeded. Check API billing, credits, project budget, or organization limits."

    admin_job = client.get(
        f"/api/generation-jobs/{job['job_id']}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert admin_job.status_code == 200
    assert (
        admin_job.json()["error"]
        == "OpenAI quota exceeded. Check API billing, credits, project budget, or organization limits."
    )


def test_generate_plan_returns_existing_active_job_for_same_athlete():
    client, store, _ = _build_client()

    existing_job = {
        "id": "job_existing123",
        "athlete_id": "athlete-1",
        "client_request_id": "same-attempt",
        "source": "self_serve",
        "request_payload": _build_request().model_dump(mode="json"),
        "status": "running",
        "created_at": _now(),
        "updated_at": _now(),
        "started_at": _now(),
        "heartbeat_at": _now(),
        "completed_at": None,
        "attempt_count": 1,
        "error": None,
        "intake_id": None,
        "stage1_result": None,
        "final_result": None,
        "plan_id": None,
        "progress_milestones": [{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
    }
    store.generation_jobs[existing_job["id"]] = dict(existing_job)

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "same-attempt",
        },
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == existing_job["id"]
    assert response.json()["client_request_id"] == "same-attempt"
    assert response.json()["status"] == "running"
    assert store.get_latest_intake("athlete-1") is None
    assert len(store.plans) == 0


def test_generate_plan_returns_queued_job_when_claim_is_temporarily_unavailable():
    class ClaimTemporarilyUnavailableStore(FakeStore):
        def claim_generation_job_start(self, job_id: str, *, stale_after_seconds: int = 90) -> dict | None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="generation job service temporarily unavailable",
            )

    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = ClaimTemporarilyUnavailableStore()
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert store.get_generation_job(body["job_id"])["status"] == "queued"
    assert len(store.plans) == 0


def test_generation_job_poll_returns_current_job_when_claim_is_temporarily_unavailable():
    class ClaimTemporarilyUnavailableStore(FakeStore):
        def claim_generation_job_start(self, job_id: str, *, stale_after_seconds: int = 90) -> dict | None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="generation job service temporarily unavailable",
            )

    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = ClaimTemporarilyUnavailableStore()
    existing_job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="queued-attempt",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    response = client.get(
        f"/api/generation-jobs/{existing_job['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == existing_job["id"]
    assert response.json()["status"] == "queued"


def test_generate_plan_response_shape_is_preserved_with_deferred_writes():
    client, _, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("job_")
    assert body["status"] in {"queued", "running", "completed"}
    assert body["athlete_id"] == "athlete-1"


def test_generate_plan_rate_limits_repeat_requests():
    client, _, _ = _build_client()
    client.app.state.plan_generate_rate_limiter = app_module.SlidingWindowRateLimiter(
        max_requests=1,
        window_seconds=60.0,
        time_fn=lambda: 100.0,
    )

    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert first.status_code == 202
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["detail"]["retry_after_seconds"] == 60


def test_generate_plan_daily_limit_allows_request_below_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "2")
    client, _, _ = _build_client()
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "daily-1"},
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 202


def test_generate_plan_daily_limit_blocks_request_at_limit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    client, _, _ = _build_client()
    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "daily-first"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "daily-second"},
        json=_build_request().model_dump(mode="json"),
    )
    assert first.status_code == 202
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["detail"] == "Daily generation limit reached. Try again tomorrow."


def test_generate_plan_daily_limit_excludes_exempt_email(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    client, _, _ = _build_client()
    exempt_user = AuthenticatedUser(
        user_id="athlete-exempt",
        email="michaelokaforjr@gmail.com",
        full_name="Michael Okafor Jr",
        metadata={},
    )
    client.app.state.auth_service.users_by_token["exempt-token"] = exempt_user

    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer exempt-token", "X-Client-Request-Id": "exempt-1"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer exempt-token", "X-Client-Request-Id": "exempt-2"},
        json=_build_request().model_dump(mode="json"),
    )
    assert first.status_code == 202
    assert second.status_code == 202


def test_generate_plan_daily_limit_excludes_exempt_email_case_insensitive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    client, _, _ = _build_client()
    exempt_user = AuthenticatedUser(
        user_id="athlete-exempt-upper",
        email="MichaelOkaforJr@Gmail.com",
        full_name="Michael Okafor Jr",
        metadata={},
    )
    client.app.state.auth_service.users_by_token["exempt-token-upper"] = exempt_user

    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer exempt-token-upper", "X-Client-Request-Id": "exempt-upper-1"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer exempt-token-upper", "X-Client-Request-Id": "exempt-upper-2"},
        json=_build_request().model_dump(mode="json"),
    )
    assert first.status_code == 202
    assert second.status_code == 202


def test_generate_plan_daily_limit_idempotent_retry_same_client_request_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    client, _, _ = _build_client()
    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "idem-1"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "idem-1"},
        json=_build_request().model_dump(mode="json"),
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]


def test_generate_plan_essential_writes_happen_synchronously():
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    assert store.get_latest_intake("athlete-1") is not None
    job_body = response.json()
    assert job_body["job_id"].startswith("job_")
    assert len(store.plans) == 1
    plan_id = next(iter(store.plans.values()))["id"]
    assert store.get_plan(plan_id) is not None


def test_generate_plan_deferred_writes_run_but_do_not_block_response():
    client, store, _ = _build_client()

    store.profiles.setdefault("athlete-1", {})
    store.ensure_profile(AuthenticatedUser(
        user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={}
    ))
    store.profiles["athlete-1"]["onboarding_draft"] = {"current_step": 3}

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    assert store.profiles["athlete-1"]["full_name"] == "Ari Mensah"
    assert store.profiles["athlete-1"]["onboarding_draft"] is None


def test_generate_plan_deferred_write_failure_does_not_fail_main_response():
    class FailingNonEssentialStore(FakeStore):
        def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict:
            raise RuntimeError("simulated update_profile failure")

        def clear_onboarding_draft(self, athlete_id: str) -> None:
            raise RuntimeError("simulated clear_onboarding_draft failure")

    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = FailingNonEssentialStore()
    stage2 = FakeStage2Automator(result=finalized_result())
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=stage2,
        ),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("job_")
    job_response = client.get(
        f"/api/generation-jobs/{body['job_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "completed"
    assert store.get_latest_intake("athlete-1") is not None
    assert len(store.plans) == 1


def test_generate_plan_returns_job_payload_and_status_endpoint_resolves_completed_plan():
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("job_")

    job_response = client.get(
        f"/api/generation-jobs/{body['job_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["status"] == "completed"
    assert job_body["plan_id"]
    assert job_body["latest_plan_id"] == job_body["plan_id"]
    assert store.get_plan(job_body["plan_id"]) is not None


def test_generation_job_status_reports_review_required_result():
    client, _, _ = _build_client(
        FakeStage2Automator(
            result=finalized_result(
                status="review_required",
                plan_text="",
                final_plan_text="# Failed Stage 2 Output",
                stage2_status="stage2_failed",
                stage2_retry_text="repair prompt",
                stage2_validator_report={"errors": [{"code": "restriction_violation"}], "warnings": []},
                stage2_attempt_count=2,
            )
        )
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job_response = client.get(
        f"/api/generation-jobs/{job_id}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert job_response.status_code == 200
    assert job_response.json()["status"] == "review_required"


def _seed_failed_job(store: FakeStore, *, athlete_id: str = "athlete-1", source: str = "self_serve") -> dict:
    request_payload = _build_request().model_dump(mode="json")
    job = store.create_or_get_generation_job(
        athlete_id=athlete_id,
        client_request_id=f"orig-{athlete_id}",
        source=source,
        request_payload=request_payload,
    )
    store.update_generation_job(
        job["id"],
        status="failed",
        error="Stage 2 model request failed",
        completed_at=_now(),
    )
    return store.get_generation_job(job["id"])


def test_retry_generation_job_allows_owner_to_retry_failed_job():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    original = _seed_failed_job(store)

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != original["id"]
    assert body["athlete_id"] == "athlete-1"
    assert body["client_request_id"].startswith(f"retry_{original['id']}_")
    # Original failed job is preserved as history.
    assert store.get_generation_job(original["id"])["status"] == "failed"


def test_retry_pre_start_stale_job_reuses_client_request_id_and_does_not_create_duplicate_plan():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    original = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-original-client",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        original["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
        progress_milestones=[],
    )

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == original["id"]
    assert body["client_request_id"] == "stale-original-client"
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == 1
    assert len(store.plans) == 0


def test_retry_generation_job_allows_admin_to_retry_any_job():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    store.ensure_profile(
        AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
    )
    original = _seed_failed_job(store)

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["athlete_id"] == "athlete-1"
    assert body["job_id"] != original["id"]


def test_retry_generation_job_rejects_non_owner_non_admin():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    other_athlete = AuthenticatedUser(
        user_id="athlete-2",
        email="bo@example.com",
        full_name="Bo Tran",
        metadata={},
    )
    store.ensure_profile(other_athlete)
    original = _seed_failed_job(store)

    client.app.state.auth_service.users_by_token["other-token"] = other_athlete

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer other-token"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_retry_generation_job_rejects_non_failed_status():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="running-job",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        job["id"],
        status="running",
        started_at=_now(),
        heartbeat_at=_now(),
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": ""}],
    )

    running_response = client.post(
        f"/api/generation-jobs/{job['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert running_response.status_code == status.HTTP_409_CONFLICT

    store.update_generation_job(job["id"], status="completed", completed_at=_now())
    completed_response = client.post(
        f"/api/generation-jobs/{job['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert completed_response.status_code == status.HTTP_409_CONFLICT


def test_retry_generation_job_returns_404_for_unknown_id():
    client, _, _ = _build_client()
    response = client.post(
        "/api/generation-jobs/job_does_not_exist/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_retry_generation_job_creates_new_job_with_original_request_payload():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    original = _seed_failed_job(store)

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 202
    new_job = store.get_generation_job(response.json()["job_id"])
    assert new_job is not None
    assert new_job["request_payload"] == original["request_payload"]
    assert new_job["source"] == original["source"]
    assert new_job["status"] in {"queued", "running", "completed", "review_required", "failed"}


def test_retry_admin_triage_resume_preserves_plan_and_intake_linkage():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    store.ensure_profile(
        AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
    )
    request = _build_request()
    intake = store.create_intake("athlete-1", request)
    blocked_plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    original = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="orig-admin-triage-resume",
        source="admin_triage_resume",
        request_payload={**request.model_dump(mode="json"), "_triage_resume_override": {"approved": True}},
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    store.update_generation_job(original["id"], status="failed", error="failed run", completed_at=_now())
    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 202
    retried = store.get_generation_job(response.json()["job_id"])
    assert retried is not None
    assert retried["source"] == "admin_triage_resume"
    assert retried["intake_id"] == str(intake["id"])
    assert retried["plan_id"] == str(blocked_plan["id"])


def test_retry_generation_job_respects_daily_limit_for_self_serve(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    original = _seed_failed_job(store)

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["detail"] == "Daily generation limit reached. Try again tomorrow."


def test_retry_generation_job_bypasses_daily_limit_for_admin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    )
    store.ensure_profile(
        AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
    )
    original = _seed_failed_job(store)

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 202
