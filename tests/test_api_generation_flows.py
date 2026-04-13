from __future__ import annotations

from fastapi import HTTPException, status
from fastapi.testclient import TestClient
import pytest

import api.app as app_module
from api.app import create_app
from api.auth import AuthenticatedUser
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
    assert store.get_latest_intake("athlete-1")["intake"]["fight_date"] == "2026-04-18"
    assert len(store.list_user_plans("athlete-1")) == 1
    saved = next(iter(store.plans.values()))
    assert saved["draft_plan_text"] == "# Stage 1 Draft"
    assert saved["final_plan_text"] == "# Final Plan"
    assert saved["stage2_status"] == "stage2_pass"
    assert saved["pdf_url"] is None
    assert stage2.calls[0]["stage2_handoff_text"] == "handoff"


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
    assert latest_intake["technical_skill_days"] == request.technical_skill_days
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