from __future__ import annotations

import asyncio

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
import pytest

import api.app as app_module
from api.app import create_app
from api.auth import AuthenticatedUser
from api.generation_runtime import run_generation_job, should_skip_stage2
from api.models import ProfileUpdateRequest
from api.stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError
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
    store.update_generation_job(created["id"], status="running", started_at=now_iso, heartbeat_at=now_iso)

    response = client.get(f"/api/generation-jobs/{created['id']}", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"


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


def test_stage1_preview_returns_draft_and_skips_generation_side_effects():
    client, store, stage2 = _build_client()

    response = client.post(
        "/api/plans/stage1-preview",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stage1_ready"
    assert body["stage2_skipped"] is True
    assert body["plan_text"] == "# Stage 1 Draft"
    assert body["coach_notes"] == "### Coach Review"
    assert body["why_log"] == {"strength": {}}
    assert body["planning_brief"]["main_limiter"] == "conditioning"
    assert body["stage2_payload"] == {"ok": True}
    assert body["stage2_handoff_text"] == "handoff"
    assert stage2.calls == []
    assert store.generation_jobs == {}
    assert store.plans == {}
    assert store.get_latest_intake("athlete-1") is None


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


def test_run_generation_job_updates_existing_plan_for_same_intake_after_resume():
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
        client_request_id="triage-resume-job",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
    )
    store.update_generation_job(job["id"], intake_id=str(intake["id"]))
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
    assert refreshed_job["plan_id"] == blocked_plan["id"]
    assert updated_plan["status"] == "ready"
    assert updated_plan["stage2_status"] == "stage2_pass"
    assert updated_plan["plan_text"] == "# Final Plan"
    assert updated_plan["final_plan_text"] == "# Final Plan"
    assert updated_plan["why_log"] == {"strength": {}}
    assert updated_plan["coach_notes"] == "### Coach Review"
    assert store.get_latest_plan(athlete.user_id)["id"] == blocked_plan["id"]
    assert len(store.list_user_plans(athlete.user_id)) == 1


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
    store.claim_generation_job(job["id"])

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
        def claim_generation_job(self, job_id: str, *, stale_after_seconds: int = 90) -> dict | None:
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
        def claim_generation_job(self, job_id: str, *, stale_after_seconds: int = 90) -> dict | None:
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
    store.update_generation_job(job["id"], status="running", started_at=_now(), heartbeat_at=_now())

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
