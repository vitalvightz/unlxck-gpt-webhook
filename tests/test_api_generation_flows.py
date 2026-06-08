from __future__ import annotations

import asyncio
import concurrent.futures
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import pytest

import api.app as app_module
from api.generation import persistence
from api.app import create_app
from api.auth import AuthenticatedUser
from api.generation_job_helpers import daily_generation_cap_window
from api.generation_runtime import run_generation_job, schedule_generation_job_if_needed, should_skip_stage2
from api.models import ProfileUpdateRequest
from api.stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError
from api.store import (
    is_job_loaded_stalled_generation_job,
    is_stage1_planner_stalled_generation_job,
    is_worker_start_stale_generation_job,
)
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


def _override_aware_planner_for_test(payload: dict, *, progress_callback=None) -> dict:
    override = payload.get("_triage_resume_override") or {}
    assert override.get("approved") is True, "worker must forward _triage_resume_override to the planner"
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


def _slow_stage1_planner_for_test(payload: dict, *, progress_callback=None) -> dict:
    if progress_callback is not None:
        progress_callback("planner_work_started", "Planner work started", "", {})
    time.sleep(0.05)
    if progress_callback is not None:
        progress_callback("planner_late_emit", "Planner late emit", "", {})
    return stage1_result()


def _under_threshold_stage1_planner_for_test(payload: dict, *, progress_callback=None) -> dict:
    time.sleep(0.2)
    return stage1_result()


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


def test_generate_plan_reuses_existing_terminal_job_for_same_payload():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    payload = request.model_dump(mode="json")
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_existing",
        request=request,
        result=finalized_result(),
    )
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="existing-completed-same-payload",
        source="self_serve",
        request_payload=payload,
        plan_id=plan["id"],
    )
    store.update_generation_job(existing["id"], status="running", started_at=_now(), heartbeat_at=_now())
    store.update_generation_job(existing["id"], status="completed", completed_at=_now())

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "new-client-request-id",
        },
        json=payload,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing["id"]
    assert body["plan_id"] == plan["id"]
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 1


def _seed_athlete_profile(store) -> None:
    store.ensure_profile(
        AuthenticatedUser(
            user_id="athlete-1",
            email="ari@example.com",
            full_name="Ari Mensah",
            metadata={},
        )
    )


def _claim_job_for_test(store: FakeStore, job: dict) -> dict:
    claimed = store.claim_generation_job_start(job["id"])
    assert claimed is not None
    return claimed


def _complete_job_for_test(
    store: FakeStore,
    job: dict,
    *,
    final_status: str = "completed",
    final_result: dict[str, Any] | None = None,
    plan_id: str | None = None,
) -> dict:
    claimed = _claim_job_for_test(store, job)
    return store.complete_generation_job(
        job["id"],
        expected_attempt_count=int(claimed.get("attempt_count") or 0),
        final_status=final_status,
        final_result=final_result,
        plan_id=plan_id,
        completed_at=_now(),
        heartbeat_at=_now(),
    )


def _fail_job_for_test(
    store: FakeStore,
    job: dict,
    *,
    error: str = "Stage 2 model request failed",
    plan_id: str | None = None,
) -> dict:
    claimed = _claim_job_for_test(store, job)
    return store.fail_generation_job(
        job["id"],
        expected_attempt_count=int(claimed.get("attempt_count") or 0),
        error=error,
        plan_id=plan_id,
        failed_at=_now(),
        heartbeat_at=_now(),
    )


def _seed_completed_same_payload_job(store, *, plan_id: str | None, client_request_id: str):
    request = _build_request()
    payload = request.model_dump(mode="json")
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=client_request_id,
        source="self_serve",
        request_payload=payload,
        plan_id=plan_id,
    )
    _complete_job_for_test(store, job, plan_id=plan_id)
    return job, payload


def test_generate_plan_allows_fresh_generation_after_athlete_archives_plan():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_archived",
        request=request,
        result=finalized_result(),
    )
    existing, payload = _seed_completed_same_payload_job(
        store, plan_id=plan["id"], client_request_id="completed-then-archived"
    )
    store.archive_plan(plan["id"])

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "fresh-after-archive",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != existing["id"]
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 2


def test_generate_plan_allows_fresh_generation_after_plan_hard_deleted():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_deleted",
        request=request,
        result=finalized_result(),
    )
    existing, payload = _seed_completed_same_payload_job(
        store, plan_id=plan["id"], client_request_id="completed-then-deleted"
    )
    store.delete_plan(plan["id"])

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "fresh-after-delete",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != existing["id"]
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 2


def test_generate_plan_allows_fresh_generation_when_terminal_job_has_no_plan_id():
    client, store, _ = _build_client(enable_in_process_generation=False)
    existing, payload = _seed_completed_same_payload_job(
        store, plan_id=None, client_request_id="completed-no-plan"
    )

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "fresh-after-no-plan",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != existing["id"]
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 2


def test_generate_plan_blocks_duplicate_for_active_triage_blocked_plan():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_triage",
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    existing, payload = _seed_completed_same_payload_job(
        store, plan_id=plan["id"], client_request_id="completed-triage-blocked"
    )

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "retry-triage-blocked",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing["id"]
    assert body["requires_admin_resume"] is True
    # Terminal triage-blocked plans must not be framed as "your plan is ready"
    # — the UI must be steered to the protected admin-review flow.
    assert "ready" not in (body.get("message") or "").lower()
    assert "admin" in (body.get("message") or "").lower() or "review" in (body.get("message") or "").lower()
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 1


def test_generate_plan_does_not_return_old_triage_blocked_job_after_resume_approval():
    """After admin approves resume for a triage-blocked plan, the stale
    same-payload terminal job must not be returned as a completed
    duplicate — otherwise generation loops back into the old blocked
    decision instead of letting the resume flow drive a new plan."""
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_triage_approved",
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    existing, payload = _seed_completed_same_payload_job(
        store, plan_id=plan["id"], client_request_id="completed-pre-approval"
    )

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "fresh-after-resume-approval",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != existing["id"]
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 2


def test_generate_plan_blocks_duplicate_for_active_triage_blocked_job_without_plan_id():
    """A new-style triage outcome (no plan row, final_result on the job)
    must still block duplicate self-serve generation and return the
    existing triage job with `requires_admin_resume=True`."""
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    payload = request.model_dump(mode="json")
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="completed-triage-no-plan",
        source="self_serve",
        request_payload=payload,
    )
    store.update_generation_job(
        existing["id"],
        status="running",
        started_at=_now(),
        heartbeat_at=_now(),
    )
    store.update_generation_job(
        existing["id"],
        status="review_required",
        completed_at=_now(),
        final_result={
            "status": "triage_blocked",
            "stage2_status": "triage_blocked",
            "why_log": {"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        },
    )

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "retry-triage-no-plan",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing["id"]
    assert body["requires_admin_resume"] is True
    assert body.get("plan_id") in (None, "")
    # Message must steer to admin review, not "plan ready".
    message = (body.get("message") or "").lower()
    assert "ready" not in message
    assert "admin" in message or "paused" in message


def test_generate_plan_ignores_old_triage_blocked_job_after_resume_approval_marker():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    payload = request.model_dump(mode="json")
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="completed-triage-no-plan-approved",
        source="self_serve",
        request_payload=payload,
    )
    store.update_generation_job(existing["id"], status="running", started_at=_now(), heartbeat_at=_now())
    store.update_generation_job(
        existing["id"],
        status="review_required",
        completed_at=_now(),
        final_result={
            "status": "triage_blocked",
            "stage2_status": "triage_resume_approved",
            "why_log": {"triage_resume_approval": {"approved_by_email": "ops@unlxck.test"}},
        },
    )

    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "fresh-after-job-resume-approval",
        },
        json=payload,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != existing["id"]
    assert body["client_request_id"] == "fresh-after-job-resume-approval"
    jobs = store.list_generation_jobs_for_athlete("athlete-1", limit=25)
    assert len(jobs) == 2


def test_triage_job_has_resume_approval_detects_markers_on_job_final_result():
    from api.app import _triage_job_has_resume_approval

    job_with_marker = {
        "final_result": {
            "status": "triage_blocked",
            "stage2_status": "triage_resume_approved",
        }
    }
    assert _triage_job_has_resume_approval(job_with_marker) is True

    job_with_why_log = {
        "final_result": {
            "status": "triage_blocked",
            "why_log": {"triage_regeneration_cleared": True},
        }
    }
    assert _triage_job_has_resume_approval(job_with_why_log) is True

    job_without_marker = {
        "final_result": {
            "status": "triage_blocked",
            "why_log": {"injury_triage": {"mode": "needs_review"}},
        }
    }
    assert _triage_job_has_resume_approval(job_without_marker) is False
    assert _triage_job_has_resume_approval({}) is False
    assert _triage_job_has_resume_approval(None) is False


def test_triage_plan_has_resume_approval_detects_all_documented_markers():
    from api.app import _triage_plan_has_resume_approval

    # stage2_status marker
    assert _triage_plan_has_resume_approval({"stage2_status": "triage_resume_approved"}) is True
    # why_log.triage_regeneration_cleared marker
    assert (
        _triage_plan_has_resume_approval({"why_log": {"triage_regeneration_cleared": True}})
        is True
    )
    # why_log.triage_resume_approval marker
    assert (
        _triage_plan_has_resume_approval(
            {"why_log": {"triage_resume_approval": {"approved_by_email": "ops@unlxck.test"}}}
        )
        is True
    )
    # why_log.injury_triage_resume_override.bypassed_blocking marker
    assert (
        _triage_plan_has_resume_approval(
            {
                "why_log": {
                    "injury_triage_resume_override": {
                        "bypassed_blocking": True,
                        "triage_mode": "needs_review",
                    }
                }
            }
        )
        is True
    )
    # why_log.injury_triage_original.triage_resume_approved marker
    assert (
        _triage_plan_has_resume_approval(
            {
                "why_log": {
                    "injury_triage_original": {
                        "mode": "needs_review",
                        "triage_resume_approved": True,
                    }
                }
            }
        )
        is True
    )
    # No markers
    assert _triage_plan_has_resume_approval({"stage2_status": "triage_blocked"}) is False
    assert (
        _triage_plan_has_resume_approval({"why_log": {"injury_triage": {"mode": "needs_review"}}})
        is False
    )
    assert _triage_plan_has_resume_approval(None) is False
    assert _triage_plan_has_resume_approval({}) is False


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
    if status_value != "failed":
        store.update_generation_job(
            created["id"],
            status="running",
            started_at="2026-01-01T00:00:00+00:00",
            heartbeat_at="2026-01-01T00:00:00+00:00",
        )
    store.update_generation_job(created["id"], status=status_value, started_at="2026-01-01T00:00:00+00:00", heartbeat_at="2026-01-01T00:00:00+00:00")

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == status_value


def test_get_generation_job_is_a_pure_read_for_stale_running_jobs():
    # get_generation_job must never mutate; recovery is the explicit job of
    # recover_generation_job_if_stale.
    _client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="pure-read-stale",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"],
        status="running",
        attempt_count=1,
        started_at=old_iso,
        heartbeat_at=old_iso,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}],
    )

    read = store.get_generation_job(created["id"])
    assert read["status"] == "running"
    # A second read still sees running: the first read changed nothing.
    assert store.get_generation_job(created["id"])["status"] == "running"

    recovered = store.recover_generation_job_if_stale(read)
    assert recovered["status"] == "queued"
    assert store.get_generation_job(created["id"])["status"] == "queued"


def test_recover_generation_job_if_stale_is_noop_for_non_running_jobs():
    _client, store, _ = _build_client()
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="recover-noop",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    failed = store.update_generation_job(
        created["id"],
        status="failed",
        error="boom",
        completed_at="2026-01-01T00:00:00+00:00",
    )

    assert store.recover_generation_job_if_stale(failed) == failed
    assert store.recover_generation_job_if_stale(None) is None


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


def test_get_active_generation_job_returns_queued_job_after_previous_terminal_job():
    client, store, _ = _build_client(enable_in_process_generation=False)
    old_job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="old-completed",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    _complete_job_for_test(store, old_job)
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
    if terminal_status == "failed":
        _fail_job_for_test(store, created)
    else:
        _complete_job_for_test(store, created, final_status=terminal_status)

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


def test_get_latest_generation_job_returns_latest_failed_after_active_null():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="latest-failed",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status="failed", error="Plan generation failed unexpectedly", completed_at=_now())

    active = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert active.status_code == 200
    assert active.json() is None

    latest = client.get("/api/generation-jobs/latest", headers={"Authorization": "Bearer athlete-token"})
    assert latest.status_code == 200
    body = latest.json()
    assert body["job_id"] == created["id"]
    assert body["status"] == "failed"


def test_get_latest_generation_job_returns_review_required_with_plan_id():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="latest-review-required",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    request = _build_request()
    intake = store.create_intake("athlete-1", request)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(status="held_for_review", stage2_status="stage2_failed"),
    )
    _complete_job_for_test(store, created, final_status="review_required", plan_id=plan["id"])

    response = client.get("/api/generation-jobs/latest", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["plan_id"] == plan["id"]


def test_job_response_does_not_backfill_plan_id_when_job_has_no_intake_id():
    """Regression: `_job_response` previously fell back to the athlete's
    latest non-archived plan even when the job had no intake_id, which
    silently surfaced an unrelated plan_id (e.g., the most recent plan from
    a different intake). The fallback must require an explicit intake_id
    match to prevent cross-job association.
    """
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    # Seed an unrelated successful plan (different intake).
    other_intake = store.create_intake("athlete-1", _build_request())
    other_plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(other_intake["id"]),
        request=_build_request(),
        result=finalized_result(),
    )
    # Create a terminal job with NO intake_id (legacy state).
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="terminal-no-intake-id",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(job["id"], status="running", started_at=_now(), heartbeat_at=_now())
    store.update_generation_job(job["id"], status="completed", completed_at=_now())

    response = client.get(
        f"/api/generation-jobs/{job['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert response.status_code == 200
    body = response.json()
    # Without an intake_id link, we cannot prove `other_plan` belongs to this
    # job, so we must not surface it as plan_id or latest_plan_id.
    assert body["plan_id"] is None
    assert body["latest_plan_id"] is None
    # Sanity: the unrelated plan still exists in the store; the API just
    # refuses to back-fill it without a verifiable link.
    assert store.get_plan(other_plan["id"]) is not None


def test_job_response_backfills_plan_id_when_intake_id_matches():
    """The intake_id-gated fallback still works when the job and the latest
    plan share an intake_id — this preserves the existing recovery path for
    jobs whose plan_id was dropped but whose intake linkage is intact.
    """
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    intake = store.create_intake("athlete-1", _build_request())
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(intake["id"]),
        request=_build_request(),
        result=finalized_result(),
    )
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="terminal-matching-intake",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
        intake_id=str(intake["id"]),
    )
    store.update_generation_job(job["id"], status="running", started_at=_now(), heartbeat_at=_now())
    store.update_generation_job(job["id"], status="completed", completed_at=_now())

    response = client.get(
        f"/api/generation-jobs/{job['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_id"] == plan["id"]
    assert body["latest_plan_id"] == plan["id"]


def test_get_latest_generation_job_does_not_leak_other_athlete_job():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="other-athlete-latest",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    response = client.get("/api/generation-jobs/latest", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json() is None


def test_get_latest_generation_job_failed_exposes_can_retry():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="failed-can-retry",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(created["id"], status="failed", error="Stage 1 planner timed out", completed_at=_now())
    response = client.get("/api/generation-jobs/latest", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["can_retry"] is True


def test_get_latest_generation_job_failed_with_plan_does_not_expose_can_retry():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="failed-with-plan-no-retry",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    request = _build_request()
    intake = store.create_intake("athlete-1", request)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(),
    )
    _fail_job_for_test(store, created, error="Stage 1 planner timed out", plan_id=plan["id"])
    response = client.get("/api/generation-jobs/latest", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["plan_id"] == plan["id"]
    assert body["can_retry"] is False


@pytest.mark.parametrize(
    ("raw_status", "expected_status"),
    [
        ("held_for_review", "review_required"),
        ("publishable_with_flags", "completed"),
        ("ready", "completed"),
    ],
)
def test_get_latest_generation_job_normalizes_legacy_status_values(raw_status: str, expected_status: str):
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=f"legacy-status-{raw_status}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.generation_jobs[created["id"]].update(
        {"status": raw_status, "completed_at": _now(), "plan_id": "plan_legacy_1"}
    )

    response = client.get("/api/generation-jobs/latest", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["status"] in {"queued", "running", "completed", "review_required", "failed"}


@pytest.mark.parametrize("plan_status", ["held_for_review", "publishable_with_flags", "ready"])
def test_fake_store_update_generation_job_rejects_plan_status_values(plan_status: str):
    _, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=f"invalid-job-status-{plan_status}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    with pytest.raises(HTTPException) as exc_info:
        store.update_generation_job(created["id"], status=plan_status)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert "unknown generation job status" in str(exc_info.value.detail)


def test_repeated_generation_job_get_requests_do_not_schedule_or_duplicate_jobs():
    client, store, _ = _build_client(enable_in_process_generation=True)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="repeated-get-no-schedule",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    first = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    second = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "queued"
    assert second.json()["status"] == "queued"
    assert len(store.generation_jobs) == 1
    assert store.get_generation_job(created["id"])["status"] == "queued"


def test_repeated_active_generation_job_get_requests_do_not_recover_or_duplicate_jobs():
    client, store, _ = _build_client(enable_in_process_generation=True)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="repeated-active-get-no-recovery",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"],
        status="running",
        attempt_count=1,
        started_at=old_iso,
        heartbeat_at=old_iso,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}],
    )

    first = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    second = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "running"
    assert second.json()["status"] == "running"
    assert len(store.generation_jobs) == 1
    persisted = store.get_generation_job(created["id"])
    assert persisted["status"] == "running"
    assert all(
        milestone.get("code") != "worker_claim_stalled_requeued"
        for milestone in persisted.get("progress_milestones", [])
    )


def test_get_active_generation_job_reads_startup_stale_running_without_requeueing():
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
    assert body["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_active_generation_job_returns_visible_stale_running_status_without_mutation():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-running-never-visible",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(created["id"], status="running", started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[])

    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["job_id"] == created["id"]
    assert body["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_active_generation_job_does_not_fail_mid_pipeline_stale_running():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="mid-pipeline-stale",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=old_iso,
        heartbeat_at=old_iso,
        stage1_result=stage1_result(),
    )
    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["id"]
    assert body["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_active_generation_job_does_not_fail_stale_stage1_planner_invoked_running():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage1-invoked-stale",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=old_iso,
        heartbeat_at=_now(),
        progress_milestones=[{"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": old_iso}],
    )
    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"
    assert store.get_generation_job(created["id"])["error"] is None


def test_get_generation_job_reads_stale_stage1_planner_invoked_running_without_mutation():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage1-invoked-stale-direct",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=old_iso,
        heartbeat_at=old_iso,
        progress_milestones=[{"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": old_iso}],
    )
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_active_generation_job_keeps_fresh_stage1_planner_invoked_running():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage1-invoked-fresh",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=now_iso,
        heartbeat_at=now_iso,
        progress_milestones=[{"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": now_iso}],
    )
    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_stage1_planner_stalled_helper_respects_stale_threshold():
    stale_at_120s = (time.time() - 120)
    stale_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(stale_at_120s))
    job = {
        "status": "running",
        "completed_at": None,
        "stage1_result": None,
        "final_result": None,
        "progress_milestones": [
            {"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": stale_iso}
        ],
    }
    assert is_stage1_planner_stalled_generation_job(job, stale_after_seconds=90) is True
    assert is_stage1_planner_stalled_generation_job(job, stale_after_seconds=180) is False


def test_job_loaded_stalled_helper_respects_milestones_and_stale_threshold():
    old_iso = "2026-01-01T00:00:00+00:00"
    job = {
        "status": "running",
        "progress_milestones": [{"code": "job_loaded", "at": old_iso}],
        "stage1_result": None,
        "final_result": None,
        "completed_at": None,
    }
    assert is_job_loaded_stalled_generation_job(job, stale_after_seconds=90) is True
    job["progress_milestones"].append({"code": "request_payload_parsed", "at": _now()})
    assert is_job_loaded_stalled_generation_job(job, stale_after_seconds=90) is False


def test_classify_running_job_staleness_prioritizes_job_loaded_stalled_over_startup_stale():
    _, store, _ = _build_client(enable_in_process_generation=False)
    old_iso = "2026-01-01T00:00:00+00:00"
    job = {
        "status": "running",
        "started_at": old_iso,
        "heartbeat_at": old_iso,
        "progress_milestones": [{"code": "job_loaded", "at": old_iso}],
        "stage1_result": None,
        "final_result": None,
        "completed_at": None,
    }
    assert store._classify_running_job_staleness(job, stale_after_seconds=90) == "job_loaded_stalled"


def test_get_generation_job_keeps_stage1_invoked_running_before_configured_stage1_timeout(monkeypatch):
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "180")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage1-invoked-120s-old",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    invoked_at_seconds = time.time() - 120
    invoked_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(invoked_at_seconds))
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=invoked_at_iso,
        heartbeat_at=invoked_at_iso,
        progress_milestones=[{"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": invoked_at_iso}],
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_generation_job_reads_stage1_invoked_after_configured_stage1_timeout(monkeypatch):
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "180")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage1-invoked-181s-old",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    invoked_at_seconds = time.time() - 181
    invoked_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(invoked_at_seconds))
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=invoked_at_iso,
        heartbeat_at=invoked_at_iso,
        progress_milestones=[{"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": invoked_at_iso}],
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    unchanged = store.get_generation_job(created["id"])
    assert unchanged["error"] is None
    timeout_codes = [m.get("code") for m in unchanged.get("progress_milestones", []) if isinstance(m, dict)]
    assert timeout_codes.count("stage1_planner_timeout") == 0


def test_get_generation_job_reads_stage1_invoked_after_timeout_even_with_fresh_heartbeat(monkeypatch):
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "180")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage1-invoked-old-fresh-heartbeat",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    invoked_at_seconds = time.time() - 181
    invoked_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(invoked_at_seconds))
    fresh_heartbeat_iso = _now()
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=invoked_at_iso,
        heartbeat_at=fresh_heartbeat_iso,
        progress_milestones=[{"code": "stage1_planner_invoked", "label": "Stage 1 planner invoked", "detail": "", "at": invoked_at_iso}],
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_create_generation_job_blocks_different_client_request_id_when_active_exists():
    store = FakeStore()
    store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="first-active",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    with pytest.raises(HTTPException) as exc:
        store.create_or_get_generation_job(
            athlete_id="athlete-1",
            client_request_id="second-active",
            source="self_serve",
            request_payload=_build_request().model_dump(mode="json"),
        )
    assert exc.value.status_code == status.HTTP_409_CONFLICT


def test_claimable_jobs_excludes_mid_pipeline_stale_running():
    store = FakeStore()
    queued = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="claimable-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    running = store.create_or_get_generation_job(
        athlete_id="athlete-2",
        client_request_id="claimable-running-mid-stale",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        running["id"],
        status="running",
        started_at=old_iso,
        heartbeat_at=old_iso,
        stage1_result=stage1_result(),
    )
    claimable = store.list_claimable_generation_jobs(stale_after_seconds=1)
    ids = {row["id"] for row in claimable}
    assert queued["id"] in ids
    assert running["id"] not in ids


def test_create_generation_job_allows_new_request_after_mid_pipeline_stale_is_failed():
    store = FakeStore()
    old = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="old-running",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        old["id"],
        status="running",
        started_at=old_iso,
        heartbeat_at=old_iso,
        stage1_result=stage1_result(),
    )
    new_job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="new-request",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    refreshed_old = store.get_generation_job(old["id"])
    assert refreshed_old["status"] == "failed"
    assert new_job["status"] == "queued"
    assert new_job["id"] != old["id"]


def test_claimable_jobs_include_startup_stale_with_null_heartbeat():
    store = FakeStore()
    running = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stale-null-heartbeat",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        running["id"],
        status="running",
        started_at=old_iso,
        heartbeat_at=None,
        stage1_result=None,
        final_result=None,
        progress_milestones=[],
    )
    claimable = store.list_claimable_generation_jobs(stale_after_seconds=1)
    assert any(row["id"] == running["id"] for row in claimable)


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
            stale_job_checker=app_module._is_stale_job,
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
            stale_job_checker=app_module._is_stale_job,
            stale_after_seconds=90,
        )
    )

    assert scheduled["status"] == "queued"
    assert scheduled["started_at"] is None
    assert scheduled["heartbeat_at"] is None


def test_generate_plan_worker_only_mode_returns_queue_metadata_and_does_not_schedule():
    client, store, _ = _build_client(enable_in_process_generation=False)
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["status_url"] == f"/api/generation-jobs/{body['job_id']}"
    assert "queued" in str(body.get("message") or "").lower()
    persisted = store.get_generation_job(body["job_id"])
    assert persisted is not None
    assert persisted["status"] == "queued"
    assert persisted["completed_at"] is None


def test_generate_plan_in_process_mode_still_schedules_and_completes():
    client, store, _ = _build_client(enable_in_process_generation=True)
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status_url"] == f"/api/generation-jobs/{body['job_id']}"
    job = store.get_generation_job(body["job_id"])
    assert job is not None
    assert job["status"] in {"running", "completed"}


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


def test_retry_failed_job_with_saved_plan_is_blocked_for_self_serve():
    client, store, _ = _build_client(enable_in_process_generation=False)
    failed = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="failed-with-plan-retry-blocked",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
        plan_id="plan_abc",
    )
    store.update_generation_job(failed["id"], status="failed", error="failed after save", completed_at=_now())

    retried = client.post(
        f"/api/generation-jobs/{failed['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert retried.status_code == 409
    assert retried.json()["detail"] == "generation job already produced a saved plan"


def test_retry_failed_job_with_saved_plan_is_allowed_for_admin_triage_resume():
    client, store, _ = _build_client(enable_in_process_generation=False)
    failed = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="failed-admin-triage-retry",
        source="admin_triage_resume",
        request_payload=_build_request().model_dump(mode="json"),
        plan_id="plan_triage",
        intake_id="intake_triage",
    )
    store.update_generation_job(failed["id"], status="failed", error="needs triage retry", completed_at=_now())

    retried = client.post(
        f"/api/generation-jobs/{failed['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert retried.status_code == 202
    body = retried.json()
    assert body["status"] in {"queued", "running", "completed"}


@pytest.mark.parametrize(
    ("heartbeat_at", "started_at"),
    [
        ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        (None, "2026-01-01T00:00:00+00:00"),
    ],
)
def test_get_generation_job_reads_stale_running_job_without_failing(heartbeat_at: str | None, started_at: str):
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
    assert body["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_active_job_reads_stale_job_loaded_without_requeueing():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="job-loaded-stale-active",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"], status="running", attempt_count=1, started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}]
    )
    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["started_at"] == old_iso
    assert body["heartbeat_at"] == old_iso
    assert all(m["code"] != "worker_claim_stalled_requeued" for m in body["progress_milestones"])
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_generation_job_reads_stale_job_loaded_without_requeueing():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(athlete_id="athlete-1", client_request_id="job-loaded-stale-direct", source="self_serve", request_payload=_build_request().model_dump(mode="json"))
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(created["id"], status="running", attempt_count=1, started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}])
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_generation_job_reads_job_loaded_stall_after_max_attempts_without_failing():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(athlete_id="athlete-1", client_request_id="job-loaded-stale-fail", source="self_serve", request_payload=_build_request().model_dump(mode="json"))
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(created["id"], status="running", attempt_count=2, started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}])
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["error"] is None
    assert all(m["code"] != "worker_claim_stalled_failed" for m in body["progress_milestones"])
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_get_generation_job_reads_job_loaded_stall_when_attempt_count_hits_env_max(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_STARTUP_MAX_ATTEMPTS", "3")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(athlete_id="athlete-1", client_request_id="job-loaded-stale-fail-env-max", source="self_serve", request_payload=_build_request().model_dump(mode="json"))
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(created["id"], status="running", attempt_count=3, started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}])
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert all(m["code"] != "worker_claim_stalled_failed" for m in body["progress_milestones"])
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_worker_reclaim_fails_job_loaded_stall_at_attempt_cap():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-reclaim-cap",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"], status="running", attempt_count=2, started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}]
    )
    # The worker re-claim path must refuse + fail rather than bump attempt_count to 3,
    # otherwise a repeatedly-dying worker re-grabs the same job forever.
    result = store.claim_generation_job_start(created["id"], stale_after_seconds=90)
    assert result is None
    job = store.get_generation_job(created["id"])
    assert job["status"] == "failed"
    assert job["attempt_count"] == 2
    assert any(m["code"] == "worker_claim_stalled_failed" for m in job["progress_milestones"])


def test_worker_reclaim_allows_job_loaded_stall_under_attempt_cap():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-reclaim-allow",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"], status="running", attempt_count=1, started_at=old_iso, heartbeat_at=old_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}]
    )
    # Still within the attempt budget: the worker reclaims and gets one more pass.
    result = store.claim_generation_job_start(created["id"], stale_after_seconds=90)
    assert result is not None
    assert result["status"] == "running"
    assert result["attempt_count"] == 2


def test_get_generation_job_keeps_recent_job_loaded_running():
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(athlete_id="athlete-1", client_request_id="job-loaded-fresh", source="self_serve", request_payload=_build_request().model_dump(mode="json"))
    now_iso = _now()
    store.update_generation_job(created["id"], status="running", attempt_count=1, started_at=now_iso, heartbeat_at=now_iso, progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": now_iso}])
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_generation_job_keeps_running_within_configured_stale_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "300")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="running-within-timeout",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(seconds=120)).isoformat()
    heartbeat_at = (now - timedelta(seconds=120)).isoformat()
    store.update_generation_job(created["id"], status="running", started_at=started_at, heartbeat_at=heartbeat_at)
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_get_active_generation_job_keeps_running_within_configured_stale_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "300")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="active-running-within-timeout",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now = datetime.now(timezone.utc)
    started_at = (now - timedelta(seconds=120)).isoformat()
    heartbeat_at = (now - timedelta(seconds=120)).isoformat()
    store.update_generation_job(created["id"], status="running", started_at=started_at, heartbeat_at=heartbeat_at)
    response = client.get("/api/generation-jobs/active", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["id"]
    assert body["status"] == "running"


def test_get_generation_job_reads_stale_running_when_timeout_lower_than_job_age(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_GENERATION_JOB_STALE_AFTER_SECONDS", "60")
    client, store, _ = _build_client(enable_in_process_generation=False)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="running-over-timeout",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now = datetime.now(timezone.utc)
    store.update_generation_job(
        created["id"],
        status="running",
        started_at=(now - timedelta(seconds=120)).isoformat(),
        heartbeat_at=(now - timedelta(seconds=120)).isoformat(),
    )
    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


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
        json=_build_request().model_dump(mode="json"),
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
    assert reset_job["request_payload"]["fight_date"] == "2026-04-18"


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
        json=_build_request().model_dump(mode="json"),
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
    assert reset_job["request_payload"]["fight_date"] == "2026-04-18"


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
        json=_build_request().model_dump(mode="json"),
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
    request_payload = _build_request().model_dump(mode="json")
    existing = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="same-stale-request",
        source="admin_triage_resume",
        request_payload=request_payload,
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
        request_payload=request_payload,
        plan_id="plan-123",
        intake_id="intake-123",
    )

    assert len(store.generation_jobs) == 1
    assert reset_job["status"] == "queued"
    assert reset_job["plan_id"] == "plan-123"
    assert reset_job["intake_id"] == "intake-123"


def test_status_endpoint_reads_pre_start_stale_job_without_mutation():
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
    assert response.json()["status"] == "running"
    assert store.get_generation_job(created["id"])["status"] == "running"


def test_stale_failed_job_can_retry_via_existing_retry_endpoint():
    client, store, _ = _build_client()
    created = _seed_failed_job(store, client_request_id="stale-then-retry")

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
    old_iso = "2026-01-01T00:00:00+00:00"
    store.update_generation_job(
        created["id"],
        status="running",
        attempt_count=1,
        started_at=old_iso,
        heartbeat_at=old_iso,
        progress_milestones=[{"code": "job_loaded", "label": "Generation job loaded", "detail": "", "at": old_iso}],
    )

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 403
    # Recovery runs only after the ownership check, so a non-owner's read must
    # not mutate another athlete's stale job.
    untouched = store.get_generation_job(created["id"])
    assert untouched["status"] == "running"


def test_get_generation_job_reads_stale_running_when_in_process_generation_disabled():
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
    assert body["status"] == "running"
    assert body["error"] is None
    assert store.get_generation_job(created["id"])["status"] == "running"


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
    store.update_generation_job(completed["id"], status="running", started_at=_now(), heartbeat_at=_now())
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


def test_generation_fails_when_stage2_final_result_persistence_fails(monkeypatch: pytest.MonkeyPatch):
    stage2_result = finalized_result(
        status="review_required",
        plan_text="",
        final_plan_text="# Failed Stage 2 Output",
        stage2_status="stage2_failed",
        stage2_retry_text="repair prompt",
        stage2_validator_report={"errors": [{"code": "restriction_violation"}], "warnings": []},
        stage2_attempt_count=2,
    )
    client, store, _ = _build_client(FakeStage2Automator(result=stage2_result))
    original_update = store.update_generation_job

    def failing_update_generation_job(job_id: str, **changes: dict) -> dict:
        if "final_result" in changes:
            raise RuntimeError("simulated persistence failure")
        return original_update(job_id, **changes)

    monkeypatch.setattr(store, "update_generation_job", failing_update_generation_job)

    _, job = _start_generation(client)

    assert job["status"] == "failed"
    assert job["error"] == "Stage 2 result persistence failed after plan persistence."
    assert job["completed_at"] is not None
    persisted_job = store.get_generation_job(job["job_id"])
    assert persisted_job is not None
    assert persisted_job["final_result"] is None


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




def _triage_blocked_planner(payload: dict, *, progress_callback=None) -> dict:
    return {
        "status": "triage_blocked",
        "ok": False,
        "plan_text": "## Injury Triage: Medical Hold",
        "coach_notes": "medical_hold",
        "pdf_url": None,
        "why_log": {"injury_triage": {"mode": "medical_hold", "should_block_stage2": True}},
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


def test_generation_pipeline_does_not_persist_triage_blocked_plan_row():
    """Stage-1-skipped triage outcomes live only on the generation job.

    No plan row is created. The job reaches review_required and carries
    the triage state on `final_result`, so the admin "Approve & Resume"
    flow can drive the next generation without a fake plan anchor.
    """
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    stage2 = FakeStage2Automator(result=finalized_result())

    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-no-plan",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_triage_blocked_planner,
            stage2=stage2,
            active_tasks=set(),
        )
    )

    refreshed = store.get_generation_job(job["id"])
    assert stage2.calls == []
    assert store.plans == {}
    assert store.list_user_plans(athlete.user_id) == []
    assert refreshed["status"] == "review_required"
    assert refreshed.get("plan_id") in (None, "")
    final_result = refreshed.get("final_result") or {}
    assert final_result.get("status") == "triage_blocked"
    assert final_result.get("stage2_status") == "triage_blocked"
    # The triage why_log must be preserved on the job so admin resume can
    # gate approval without needing a plan row.
    assert isinstance(final_result.get("why_log"), dict)
    assert final_result["why_log"].get("injury_triage", {}).get("mode") == "medical_hold"

    milestone_codes = [entry.get("code") for entry in refreshed.get("progress_milestones", []) if isinstance(entry, dict)]
    assert "stage1_planner_finished" in milestone_codes
    assert "stage2_skipped" in milestone_codes
    assert "triage_review_required" in milestone_codes
    assert "plan_persisting" not in milestone_codes
    assert "plan_persisted" not in milestone_codes
    assert "plan_saved" not in milestone_codes
    assert "stage2_drafting" not in milestone_codes




def test_admin_latest_intake_creates_new_plan_per_generation_job_and_triage_resume_still_updates_existing_plan():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)

    job_a = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="admin-latest-a",
        source="admin_latest_intake",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
    )
    asyncio.run(run_generation_job(job_id=job_a["id"], store=store, planner_fn=_planner, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    refreshed_a = store.get_generation_job(job_a["id"])
    plan_a_id = str(refreshed_a.get("plan_id") or "")
    assert refreshed_a["status"] == "completed"
    assert plan_a_id

    job_b = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="admin-latest-b",
        source="admin_latest_intake",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
    )
    asyncio.run(run_generation_job(job_id=job_b["id"], store=store, planner_fn=_planner, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    refreshed_b = store.get_generation_job(job_b["id"])
    plan_b_id = str(refreshed_b.get("plan_id") or "")
    assert refreshed_b["status"] == "completed"
    assert plan_b_id

    assert plan_b_id != plan_a_id
    assert store.get_plan(plan_a_id) is not None
    assert store.get_plan(plan_b_id) is not None
    assert refreshed_a["plan_id"] == plan_a_id
    assert refreshed_b["plan_id"] == plan_b_id

    triage_request_payload = request.model_dump(mode="json")
    triage_request_payload["_triage_resume_override"] = {"approved": True, "allowed_modes": ["needs_review"]}
    triage_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="admin-triage-resume-same-plan",
        source="admin_triage_resume",
        request_payload=triage_request_payload,
        intake_id=str(intake["id"]),
        plan_id=plan_b_id,
    )
    asyncio.run(run_generation_job(job_id=triage_job["id"], store=store, planner_fn=_planner, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    refreshed_triage = store.get_generation_job(triage_job["id"])

    assert refreshed_triage["status"] == "completed"
    assert refreshed_triage["plan_id"] == plan_b_id
    assert len(store.list_user_plans(athlete.user_id)) == 2

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

    assert refreshed_job["status"] == "completed"
    assert refreshed_job["plan_id"] is not None
    assert refreshed_job["plan_id"] != blocked_plan["id"]
    assert updated_plan["status"] == "triage_blocked"
    assert updated_plan["stage2_status"] == "triage_blocked"
    assert len(store.list_user_plans(athlete.user_id)) == 2


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
    class DeleteLinkedPlanAfterStage1Store(FakeStore):
        def update_generation_job(self, job_id: str, **changes: dict) -> dict:
            updated = super().update_generation_job(job_id, **changes)
            if "stage1_result" in changes:
                self.delete_plan(str(blocked_plan["id"]))
            return updated

    store = DeleteLinkedPlanAfterStage1Store()
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


def test_admin_triage_resume_without_plan_id_creates_real_plan_only_after_stage2_pass():
    """Resume-from-job: an admin_triage_resume job without plan_id is the
    new entry point for resuming a triage outcome that lives only on the
    generation job. The resume runs Stage 1 + Stage 2 and creates a real
    plan row only when Stage 2 actually produces a plan."""
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-from-job",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
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
    assert refreshed_job["status"] == "completed"
    assert refreshed_job.get("plan_id")
    plans = store.list_user_plans(athlete.user_id)
    assert len(plans) == 1
    assert plans[0]["status"] == "ready"


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


def test_run_generation_job_warns_when_profile_refresh_fails_but_generation_continues():
    class ProfileFailingStore(FakeStore):
        def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict:
            raise RuntimeError("profile write unavailable")

    store = ProfileFailingStore()
    _seed_athlete_profile(store)
    request = _build_request()
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="profile-refresh-fails",
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

    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "completed"
    assert refreshed_job["plan_id"]
    warning = "Profile refresh failed; plan generated from submitted intake only."
    warning_milestones = [
        milestone
        for milestone in refreshed_job.get("progress_milestones", [])
        if milestone.get("code") == "profile_refresh_failed_warning"
    ]
    assert len(warning_milestones) == 1
    assert warning_milestones[0]["detail"] == warning
    assert warning_milestones[0]["meta"] == {"warning": True}
    response = app_module._job_response(refreshed_job, store=store)
    diagnostic = app_module._admin_generation_job_diagnostic(refreshed_job, stale_after_seconds=90)
    assert response.warnings == [warning]
    assert diagnostic.warnings == [warning]


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

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_override_aware_planner_for_test,
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
    expected_prefix_order = [
        "job_loaded",
        "admin_resume_linkage_validated",
        "request_payload_parsed",
        "profile_update_started",
        "profile_update_finished",
        "stage1_planner_starting",
        "stage1_planner_invoked",
        "stage1_planner_finished",
    ]
    assert [milestone_codes.index(code) for code in expected_prefix_order] == sorted(
        milestone_codes.index(code) for code in expected_prefix_order
    )
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


def test_admin_triage_resume_with_override_can_transition_blocked_plan_to_held_for_review():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(status="triage_blocked", stage2_status="triage_blocked", plan_text="", final_plan_text=""),
    )
    request_payload = request.model_dump(mode="json")
    request_payload["_triage_resume_override"] = {"approved": True}
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-to-held-for-review",
        source="admin_triage_resume",
        request_payload=request_payload,
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(
                result=finalized_result(status="held_for_review", stage2_status="stage2_failed", plan_text="", final_plan_text="")
            ),
            active_tasks=set(),
        )
    )

    refreshed_job = store.get_generation_job(job["id"])
    updated_plan = store.get_plan(blocked_plan["id"])
    assert refreshed_job["status"] == "review_required"
    assert updated_plan["status"] == "held_for_review"


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


def test_admin_triage_resume_missing_plan_id_does_not_reuse_legacy_blocked_plan():
    """Resume-from-job must not back-fill plan_id from an unrelated legacy
    triage_blocked plan row. The resume creates a new plan row only after
    Stage 2 succeeds; legacy rows remain untouched."""
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
    legacy_blocked = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_blocked",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )

    def fail_get_latest_plan(athlete_id: str) -> dict | None:
        raise AssertionError("latest_plan fallback used")

    store.get_latest_plan = fail_get_latest_plan

    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="triage-resume-from-job-no-legacy-reuse",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
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
    new_plan_id = str(refreshed_job.get("plan_id") or "")
    assert refreshed_job["status"] == "completed"
    assert new_plan_id and new_plan_id != legacy_blocked["id"]
    # Legacy blocked plan remains untouched.
    assert store.get_plan(legacy_blocked["id"])["status"] == "triage_blocked"
    # Resume produced a new plan row.
    assert store.get_plan(new_plan_id)["status"] == "ready"


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
    stage2 = FakeStage2Automator(result=finalized_result())

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_slow_stage1_planner_for_test,
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
    assert "stage1_planner_timeout" in milestone_codes
    assert milestone_codes.count("stage1_planner_timeout") == 1
    assert "stage1_planner_finished" not in milestone_codes
    assert stage2.calls == []
    assert "planner_late_emit" not in milestone_codes
    assert len(store.plans) == 1
    assert updated_plan["id"] == blocked_plan["id"]
    assert updated_plan["status"] == "triage_blocked"
    assert updated_plan["stage2_status"] == "triage_resume_approved"
    assert updated_plan["why_log"]["triage_resume_approval"] == {"approved_by_email": "ops@unlxck.test"}

    # The planner thread keeps running briefly after timeout; late callbacks
    # must be ignored so the failed job cannot be mutated after return.
    time.sleep(0.06)
    post_timeout_job = store.get_generation_job(job["id"])
    post_timeout_codes = [entry["code"] for entry in post_timeout_job.get("progress_milestones", [])]
    assert "planner_late_emit" not in post_timeout_codes
    assert post_timeout_job["status"] == "failed"


def test_runtime_generation_stage1_planner_does_not_fail_before_configured_timeout(monkeypatch):
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "10")
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="athlete@example.com",
        full_name="Athlete",
        metadata={},
    )
    store.ensure_profile(athlete)
    request = _build_request()
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="stage1-timeout-under-threshold",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )
    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_under_threshold_stage1_planner_for_test,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )
    refreshed_job = store.get_generation_job(job["id"])
    assert refreshed_job["status"] == "completed"


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


def test_runtime_generation_marks_review_required_job_terminal_after_final_result_persisted():
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
        client_request_id="runtime-job-review-required",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result(status="review_required", stage2_status="stage2_failed")),
            active_tasks=set(),
        )
    )

    terminal_job = store.get_generation_job(job["id"])
    milestone_codes = [entry.get("code") for entry in terminal_job.get("progress_milestones", []) if isinstance(entry, dict)]
    assert "plan_persisted" in milestone_codes
    assert "final_result_persisted" in milestone_codes
    assert terminal_job["status"] == "review_required"
    assert terminal_job["completed_at"] is not None
    assert terminal_job["error"] is None


def test_runtime_generation_fails_when_created_plan_cannot_be_reloaded():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="athlete@example.com", full_name="Athlete One", metadata={})
    store.ensure_profile(athlete)
    request = _build_request({"fight_date": "2026-08-15"})
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="runtime-job-plan-verify-missing",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    created_plan_id: str | None = None
    original_create_plan = store.create_plan
    original_get_plan = store.get_plan

    def _create_plan(*args: Any, **kwargs: Any) -> dict:
        nonlocal created_plan_id
        row = original_create_plan(*args, **kwargs)
        created_plan_id = row["id"]
        return row

    def _get_plan(plan_id: str) -> dict | None:
        if created_plan_id and plan_id == created_plan_id:
            return None
        return original_get_plan(plan_id)

    store.create_plan = _create_plan
    store.get_plan = _get_plan

    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_planner, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))

    failed_job = store.get_generation_job(job["id"])
    milestone_codes = [entry.get("code") for entry in failed_job.get("progress_milestones", []) if isinstance(entry, dict)]
    assert failed_job["status"] == "failed"
    assert failed_job["error"] == "Plan persistence verification failed after create_plan."
    assert failed_job["completed_at"] is not None
    assert "plan_persisted" not in milestone_codes


def test_runtime_generation_fails_when_created_plan_has_wrong_athlete():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="athlete@example.com", full_name="Athlete One", metadata={})
    store.ensure_profile(athlete)
    request = _build_request({"fight_date": "2026-08-15"})
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="runtime-job-plan-verify-athlete-mismatch",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    original_get_plan = store.get_plan

    def _get_plan(plan_id: str) -> dict | None:
        row = original_get_plan(plan_id)
        if row:
            return {**row, "athlete_id": "athlete-other"}
        return row

    store.get_plan = _get_plan

    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_planner, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))

    failed_job = store.get_generation_job(job["id"])
    assert failed_job["status"] == "failed"
    assert failed_job["error"] == "Plan persistence verification failed after create_plan."


def test_runtime_generation_fails_when_created_plan_has_wrong_intake():
    store = FakeStore()
    athlete = AuthenticatedUser(user_id="athlete-1", email="athlete@example.com", full_name="Athlete One", metadata={})
    store.ensure_profile(athlete)
    request = _build_request({"fight_date": "2026-08-15"})
    job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="runtime-job-plan-verify-intake-mismatch",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    original_get_plan = store.get_plan

    def _get_plan(plan_id: str) -> dict | None:
        row = original_get_plan(plan_id)
        if row:
            return {**row, "intake_id": "intake-other"}
        return row

    store.get_plan = _get_plan

    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_planner, stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))

    failed_job = store.get_generation_job(job["id"])
    assert failed_job["status"] == "failed"
    assert failed_job["error"] == "Plan persistence verification failed after create_plan."


def test_runtime_generation_emits_plan_saved_and_marks_completed_terminal():
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
        client_request_id="runtime-job-completed-plan-saved",
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

    terminal_job = store.get_generation_job(job["id"])
    milestone_codes = [entry.get("code") for entry in terminal_job.get("progress_milestones", []) if isinstance(entry, dict)]
    assert "plan_saved" in milestone_codes
    assert terminal_job["status"] == "completed"
    assert terminal_job["completed_at"] is not None


def test_runtime_generation_cleanup_failure_does_not_block_terminal_status(monkeypatch):
    monkeypatch.setattr(persistence, "_POST_PERSIST_CLEANUP_TIMEOUT_SECONDS", 0.01)
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
        client_request_id="runtime-job-cleanup-timeout",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
    )

    original_clear = store.clear_onboarding_draft

    def _slow_clear_onboarding_draft(athlete_id: str) -> None:
        time.sleep(0.05)
        original_clear(athlete_id)

    monkeypatch.setattr(store, "clear_onboarding_draft", _slow_clear_onboarding_draft)

    asyncio.run(
        run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    terminal_job = store.get_generation_job(job["id"])
    assert terminal_job["status"] == "completed"
    assert terminal_job["completed_at"] is not None
    assert terminal_job["status"] != "running"


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


def test_generate_plan_rate_limits_repeat_requests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_RATE_LIMIT", "1")
    monkeypatch.setenv("APP_PLAN_GENERATE_RATE_LIMIT_WINDOW_SECONDS", "60")
    client, _, _ = _build_client()

    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "rate-first"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "rate-second"},
        json=_build_request({"fight_date": "2026-05-09"}).model_dump(mode="json"),
    )

    assert first.status_code == 202
    assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second.json()["detail"]["retry_after_seconds"] == 60


def test_generate_plan_idempotent_retry_does_not_consume_short_window_quota(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_RATE_LIMIT", "2")
    monkeypatch.setenv("APP_PLAN_GENERATE_RATE_LIMIT_WINDOW_SECONDS", "60")
    client, store, _ = _build_client(enable_in_process_generation=False)
    payload = _build_request().model_dump(mode="json")

    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "short-idem"},
        json=payload,
    )
    retry = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "short-idem"},
        json=payload,
    )
    assert first.status_code == 202
    assert retry.status_code == 202
    assert retry.json()["job_id"] == first.json()["job_id"]

    # Finish the first job explicitly so this test is about short-window quota,
    # not the one-active-job guard.
    store.update_generation_job(first.json()["job_id"], status="running", started_at=_now(), heartbeat_at=_now())
    store.update_generation_job(first.json()["job_id"], status="completed", completed_at=_now())

    new_request = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "short-new"},
        json=_build_request({"fight_date": "2026-05-10"}).model_dump(mode="json"),
    )

    assert new_request.status_code == 202
    assert new_request.json()["job_id"] != first.json()["job_id"]
    assert len(store._plan_generation_limit_events["athlete-1"]) == 2


def test_generate_plan_reused_client_request_id_with_different_payload_conflicts():
    client, _, _ = _build_client(enable_in_process_generation=False)
    first = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "payload-mismatch"},
        json=_build_request().model_dump(mode="json"),
    )
    second = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token", "X-Client-Request-Id": "payload-mismatch"},
        json=_build_request({"fight_date": "2026-05-11"}).model_dump(mode="json"),
    )

    assert first.status_code == 202
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["detail"] == "This request id has already been used for a different generation payload."
    assert second.json()["code"] == "client_request_id_payload_mismatch"


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
    assert (
        second.json()["detail"]
        == "Daily generation limit reached. Try again after midnight in your athlete timezone."
    )


def test_fake_store_daily_limit_create_is_atomic_for_concurrent_requests():
    store = FakeStore()
    day_start_iso = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )

    def create(client_request_id: str) -> tuple[int, str]:
        try:
            job = store.create_or_get_generation_job_with_daily_limit(
                athlete_id="athlete-1",
                client_request_id=client_request_id,
                source="self_serve",
                request_payload=_build_request().model_dump(mode="json"),
                daily_limit=1,
                day_start_iso=day_start_iso,
                limit_reached_detail=(
                    "Daily generation limit reached. "
                    "Try again after midnight in your athlete timezone."
                ),
                counted_sources={"self_serve", "admin", "admin_triage_resume"},
            )
            return status.HTTP_202_ACCEPTED, str(job["id"])
        except HTTPException as exc:
            return exc.status_code, str(exc.detail)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, ["daily-race-a", "daily-race-b"]))

    assert sorted(code for code, _ in results) == [
        status.HTTP_202_ACCEPTED,
        status.HTTP_429_TOO_MANY_REQUESTS,
    ]
    assert (
        sum(1 for job in store.generation_jobs.values() if job["athlete_id"] == "athlete-1")
        == 1
    )
    assert any(
        detail
        == "Daily generation limit reached. Try again after midnight in your athlete timezone."
        for code, detail in results
        if code == status.HTTP_429_TOO_MANY_REQUESTS
    )


def test_daily_limit_create_conflicts_when_client_request_id_payload_differs():
    store = FakeStore()
    day_start_iso = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    first = store.create_or_get_generation_job_with_daily_limit(
        athlete_id="athlete-1",
        client_request_id="daily-payload-mismatch",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
        daily_limit=5,
        day_start_iso=day_start_iso,
        limit_reached_detail="Daily generation limit reached.",
        counted_sources={"self_serve", "admin", "admin_triage_resume"},
    )

    with pytest.raises(HTTPException) as exc_info:
        store.create_or_get_generation_job_with_daily_limit(
            athlete_id="athlete-1",
            client_request_id="daily-payload-mismatch",
            source="self_serve",
            request_payload=_build_request({"fight_date": "2026-05-12"}).model_dump(mode="json"),
            daily_limit=5,
            day_start_iso=day_start_iso,
            limit_reached_detail="Daily generation limit reached.",
            counted_sources={"self_serve", "admin", "admin_triage_resume"},
        )

    assert first["client_request_id"] == "daily-payload-mismatch"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "This request id has already been used for a different generation payload."
    assert getattr(exc_info.value, "code") == "client_request_id_payload_mismatch"


@pytest.mark.parametrize("legacy_hash", [None, "missing"])
def test_daily_limit_create_preserves_legacy_missing_or_null_payload_hash_behaviour(legacy_hash: str | None):
    store = FakeStore()
    day_start_iso = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )
    existing = store.create_or_get_generation_job_with_daily_limit(
        athlete_id="athlete-1",
        client_request_id=f"daily-legacy-{legacy_hash}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
        daily_limit=5,
        day_start_iso=day_start_iso,
        limit_reached_detail="Daily generation limit reached.",
        counted_sources={"self_serve", "admin", "admin_triage_resume"},
    )
    if legacy_hash == "missing":
        store.generation_jobs[existing["id"]].pop("payload_hash")
    else:
        store.generation_jobs[existing["id"]]["payload_hash"] = None

    retry = store.create_or_get_generation_job_with_daily_limit(
        athlete_id="athlete-1",
        client_request_id=f"daily-legacy-{legacy_hash}",
        source="self_serve",
        request_payload=_build_request({"fight_date": "2026-05-13"}).model_dump(mode="json"),
        daily_limit=5,
        day_start_iso=day_start_iso,
        limit_reached_detail="Daily generation limit reached.",
        counted_sources={"self_serve", "admin", "admin_triage_resume"},
    )

    assert retry["id"] == existing["id"]
    if legacy_hash == "missing":
        assert "payload_hash" not in retry
    else:
        assert retry["payload_hash"] is None


def test_daily_generation_cap_exemptions_default_to_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_DAILY_GENERATION_CAP_EXEMPT_EMAILS", raising=False)
    assert app_module._daily_generation_cap_exempt_emails() == frozenset()
    assert app_module._is_exempt_from_daily_generation_cap("michaelokaforjr@gmail.com") is False


def test_daily_generation_cap_exemptions_use_env_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_DAILY_GENERATION_CAP_EXEMPT_EMAILS", "test@example.com")
    assert app_module._is_exempt_from_daily_generation_cap("test@example.com") is True


def test_daily_generation_cap_exemptions_normalize_case_and_whitespace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_DAILY_GENERATION_CAP_EXEMPT_EMAILS", " Test@Example.com , other@example.com ")
    assert app_module._is_exempt_from_daily_generation_cap("test@example.com") is True
    assert app_module._is_exempt_from_daily_generation_cap("OTHER@example.com") is True


def test_generate_plan_daily_limit_allows_env_configured_exempt_email(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    monkeypatch.setenv("APP_DAILY_GENERATION_CAP_EXEMPT_EMAILS", "test@example.com")
    client, _, _ = _build_client()
    exempt_user = AuthenticatedUser(
        user_id="athlete-exempt",
        email="test@example.com",
        full_name="Test Exempt",
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


def test_generate_plan_daily_limit_allows_env_configured_exempt_email_case_insensitive(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "1")
    monkeypatch.setenv("APP_DAILY_GENERATION_CAP_EXEMPT_EMAILS", "test@example.com")
    client, _, _ = _build_client()
    exempt_user = AuthenticatedUser(
        user_id="athlete-exempt-upper",
        email="Test@Example.com",
        full_name="Test Exempt",
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


def _seed_failed_job(
    store: FakeStore,
    *,
    athlete_id: str = "athlete-1",
    source: str = "self_serve",
    client_request_id: str | None = None,
    request_payload: dict[str, Any] | None = None,
    plan_id: str | None = None,
    intake_id: str | None = None,
) -> dict:
    request_payload = request_payload or _build_request().model_dump(mode="json")
    job = store.create_or_get_generation_job(
        athlete_id=athlete_id,
        client_request_id=client_request_id or f"orig-{athlete_id}",
        source=source,
        request_payload=request_payload,
        plan_id=plan_id,
        intake_id=intake_id,
    )
    _fail_job_for_test(store, job, plan_id=plan_id)
    return store.get_generation_job(job["id"])


def test_retry_generation_job_route_delegates_to_retry_service(monkeypatch: pytest.MonkeyPatch):
    client, _, _ = _build_client()
    calls: dict[str, Any] = {}

    async def fake_retry_service(**kwargs):
        calls.update(kwargs)
        now = _now()
        return {
            "job_id": "service-job",
            "athlete_id": "athlete-1",
            "client_request_id": "retry-from-service",
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }

    monkeypatch.setattr(app_module, "retry_generation_job_service", fake_retry_service)

    response = client.post(
        "/api/generation-jobs/original-job/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 202
    assert response.json()["job_id"] == "service-job"
    assert calls["job_id"] == "original-job"
    assert calls["profile"].athlete_id == "athlete-1"
    assert calls["schedule_generation_job_if_needed"] is schedule_generation_job_if_needed
    assert calls["plan_generate_daily_limit_per_user"] is app_module._plan_generate_daily_limit_per_user
    assert calls["is_exempt_from_daily_generation_cap"] is app_module._is_exempt_from_daily_generation_cap


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


def test_retry_generation_job_rejects_failed_job_missing_request_payload():
    client, store, _ = _build_client()
    _seed_athlete_profile(store)
    original = _seed_failed_job(store)
    store.generation_jobs[original["id"]]["request_payload"] = None

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "original job request payload is missing"
    assert len(store.generation_jobs) == 1


def test_retry_generation_job_rejects_saved_plan_for_normal_generation_job():
    client, store, _ = _build_client()
    _seed_athlete_profile(store)
    request = _build_request()
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_saved_plan_retry",
        request=request,
        result=finalized_result(),
    )
    original = _seed_failed_job(
        store,
        request_payload=request.model_dump(mode="json"),
        plan_id=plan["id"],
    )

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "generation job already produced a saved plan"
    assert len(store.generation_jobs) == 1


def test_retry_generation_job_allows_job_based_admin_triage_resume_without_plan_linkage():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    original = _seed_failed_job(
        store,
        source="admin_triage_resume",
        client_request_id="triage_resume_job_original",
        intake_id="intake_triage_resume_job",
    )

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] != original["id"]
    retried = store.get_generation_job(body["job_id"])
    assert retried is not None
    assert retried["source"] == "admin_triage_resume"
    assert retried["client_request_id"].startswith(f"retry_{original['id']}_")
    assert retried["intake_id"] == "intake_triage_resume_job"
    assert retried.get("plan_id") is None


def test_retry_generation_job_rejects_plan_based_admin_triage_resume_without_plan_linkage():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    original = _seed_failed_job(
        store,
        source="admin_triage_resume",
        client_request_id="triage_resume_plan_original",
        intake_id="intake_triage_resume_plan",
    )

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "admin triage resume retry is missing plan linkage"
    assert len(store.generation_jobs) == 1


def test_retry_generation_job_allows_admin_triage_resume_with_saved_plan_linkage():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _seed_athlete_profile(store)
    request = _build_request()
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_triage_resume_plan",
        request=request,
        result=finalized_result(
            status="triage_blocked",
            stage2_status="triage_resume_approved",
            why_log={"triage_resume_approval": {"approved_by_email": "ops@unlxck.test"}},
        ),
    )
    original = _seed_failed_job(
        store,
        source="admin_triage_resume",
        client_request_id="triage_resume_plan_with_link",
        request_payload=request.model_dump(mode="json"),
        plan_id=plan["id"],
        intake_id="intake_triage_resume_plan",
    )

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 202
    retried = store.get_generation_job(response.json()["job_id"])
    assert retried is not None
    assert retried["source"] == "admin_triage_resume"
    assert retried["plan_id"] == plan["id"]
    assert retried["intake_id"] == "intake_triage_resume_plan"


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


def test_retry_generation_job_blocks_when_different_queued_job_exists():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.ensure_profile(AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={}))
    original = _seed_failed_job(store)
    store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="other-active-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    response = client.post(f"/api/generation-jobs/{original['id']}/retry", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "A generation job is already queued or running for this account."
    assert len(store.generation_jobs) == 2


def test_retry_generation_job_blocks_when_different_running_job_exists():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.ensure_profile(AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={}))
    original = _seed_failed_job(store)
    running = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="other-active-running",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    now_iso = _now()
    store.update_generation_job(running["id"], status="running", started_at=now_iso, heartbeat_at=now_iso)

    response = client.post(f"/api/generation-jobs/{original['id']}/retry", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "A generation job is already queued or running for this account."
    assert len(store.generation_jobs) == 2


def test_retry_generation_job_idempotent_for_same_retry_client_request_id():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.ensure_profile(AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={}))
    original = _seed_failed_job(store)
    headers = {
        "Authorization": "Bearer athlete-token",
        "X-Client-Request-Id": "fixed-retry-id-1",
    }

    first = client.post(f"/api/generation-jobs/{original['id']}/retry", headers=headers)
    second = client.post(f"/api/generation-jobs/{original['id']}/retry", headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert len(store.generation_jobs) == 2


def test_generate_plan_rejects_invalid_client_request_id_header():
    client, _, _ = _build_client(enable_in_process_generation=False)
    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "invalid request id with spaces",
        },
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid X-Client-Request-Id"


def test_generate_plan_uses_fallback_for_whitespace_client_request_id_header():
    client, _, _ = _build_client(enable_in_process_generation=False)
    response = client.post(
        "/api/plans/generate",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "   ",
        },
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 202
    assert response.json()["client_request_id"].startswith("cli_")


def test_retry_generation_job_rejects_invalid_client_request_id_header():
    client, store, _ = _build_client(enable_in_process_generation=False)
    store.ensure_profile(AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={}))
    original = _seed_failed_job(store)

    response = client.post(
        f"/api/generation-jobs/{original['id']}/retry",
        headers={
            "Authorization": "Bearer athlete-token",
            "X-Client-Request-Id": "invalid/retry/id",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid X-Client-Request-Id"


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
    _fail_job_for_test(store, original, error="failed run", plan_id=str(blocked_plan["id"]))
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
    _, expected_detail = daily_generation_cap_window("Europe/London")
    assert response.json()["detail"] == expected_detail


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


def test_generate_plan_rejects_overlong_profile_and_injury_fields_with_422():
    client, _, _ = _build_client()
    payload = _build_request().model_dump(mode="json")
    payload["athlete"]["full_name"] = "A" * 121
    payload["injuries"] = "x" * 2001

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=payload,
    )

    assert response.status_code == 422
    assert "full_name" in str(response.json()["detail"])
    assert "injuries" in str(response.json()["detail"])


def test_generate_plan_rejects_overlong_list_item_with_422():
    client, _, _ = _build_client()
    payload = _build_request().model_dump(mode="json")
    payload["key_goals"] = ["x" * 121]

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=payload,
    )

    assert response.status_code == 422
    assert "key_goals" in str(response.json()["detail"])
