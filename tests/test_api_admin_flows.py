from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from api.auth import AuthenticatedUser
from api.models import ManualStage2SubmissionRequest
from support import (
    FakeAuthService,
    FakeStore,
    SYSTEM_SCENARIOS,
    FakeStage2Automator,
    _build_client,
    _build_request,
    _review_required_result,
    _start_generation,
    finalized_result,
    stage1_result,
)


def test_admin_endpoints_require_admin_role():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)

    forbidden = client.get("/api/admin/athletes", headers={"Authorization": "Bearer athlete-token"})
    allowed = client.get("/api/admin/athletes", headers={"Authorization": "Bearer admin-token"})

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_admin_get_athlete_by_id_returns_profile():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-profile-1",
        email="solo@example.com",
        full_name="Solo Fighter",
        metadata={},
    )
    store.ensure_profile(athlete)

    forbidden = client.get(
        "/api/admin/athletes/athlete-profile-1",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert forbidden.status_code == 403

    not_found = client.get(
        "/api/admin/athletes/nonexistent-id",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert not_found.status_code == 404

    response = client.get(
        "/api/admin/athletes/athlete-profile-1",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["athlete_id"] == "athlete-profile-1"
    assert data["email"] == "solo@example.com"
    assert data["full_name"] == "Solo Fighter"
    assert data["plan_count"] == 0


def test_admin_can_list_and_open_review_required_plan_for_resolution():
    review_result = _review_required_result(
        final_plan_text="## PHASE 2: SPP\n- Heavy Bag Sprint Rounds - 6 x 15 sec",
        warning_code="equipment_incongruent_selection",
    )
    client, _, _ = _build_client(FakeStage2Automator(result=review_result))

    _, job = _start_generation(
        client,
        _build_request(
            {
                "equipment_access": ["bands", "bodyweight"],
                "training_availability": ["Tuesday", "Thursday", "Saturday"],
            }
        ),
    )
    plan_id = job["plan_id"]

    admin_list = client.get("/api/admin/plans", headers={"Authorization": "Bearer admin-token"})
    assert admin_list.status_code == 200
    listed_plan = next(plan for plan in admin_list.json() if plan["plan_id"] == plan_id)
    assert listed_plan["status"] == "review_required"

    admin_detail = client.get(f"/api/plans/{plan_id}", headers={"Authorization": "Bearer admin-token"})
    assert admin_detail.status_code == 200
    assert admin_detail.json()["admin_outputs"]["stage2_retry_text"] == "repair prompt"


def test_admin_plans_support_limit_and_offset_query_params():
    client, _, _ = _build_client()

    _, first_job = _start_generation(client, _build_request({"athlete": {"full_name": "First Athlete"}}))
    _, second_job = _start_generation(client, _build_request({"athlete": {"full_name": "Second Athlete"}}))

    response = client.get(
        "/api/admin/plans?limit=1&offset=1",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["plan_id"] == first_job["plan_id"]
    assert body[0]["plan_id"] != second_job["plan_id"]


def test_admin_athletes_support_limit_and_offset_query_params():
    client, store, _ = _build_client()
    store.ensure_profile(
        AuthenticatedUser(
            user_id="athlete-extra-1",
            email="extra1@example.com",
            full_name="Extra One",
            metadata={},
        )
    )
    store.ensure_profile(
        AuthenticatedUser(
            user_id="athlete-extra-2",
            email="extra2@example.com",
            full_name="Extra Two",
            metadata={},
        )
    )

    response = client.get(
        "/api/admin/athletes?limit=1&offset=1",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1


def test_manual_stage2_submission_publishes_validated_admin_result():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="",
            stage2_status="stage2_failed",
            stage2_retry_text="repair prompt",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(final_plan_text="# Manual GPT Final").model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["outputs"]["plan_text"] == "# Manual GPT Final"
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_retry_pass"
    saved = store.get_plan(plan["id"])
    assert saved["plan_text"] == "# Manual GPT Final"
    assert saved["stage2_retry_text"] == ""


def test_manual_stage2_submission_generates_retry_prompt_when_output_needs_revision():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="",
            planning_brief={
                "phase_strategy": {"SPP": {"must_keep": ["rehab"]}},
                "candidate_pools": {
                    "SPP": {
                        "strength_slots": [],
                        "conditioning_slots": [],
                        "rehab_slots": [
                            {
                                "role": "rehab_ankle",
                                "selected": {"name": "Heel Raise"},
                                "alternates": [],
                            }
                        ],
                    }
                },
            },
            stage2_status="stage2_failed",
            stage2_retry_text="",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(
            final_plan_text="## PHASE 2: SPP\n- Air Bike Sprint - 6 x 6 sec"
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["outputs"]["plan_text"] == ""
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_retry_required"
    assert body["admin_outputs"]["stage2_retry_text"]


def test_manual_stage2_submission_publishes_when_only_non_blocking_review_flags_exist():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="",
            planning_brief={"athlete_model": {"sport": "boxing"}},
            stage2_status="stage2_failed",
            stage2_retry_text="",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(
            final_plan_text=(
                "## PHASE 2: SPP\n"
                "- Double-leg sprint entry - 6 x 6 sec\n"
            )
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["outputs"]["plan_text"]
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_pass"
    assert body["admin_outputs"]["stage2_validator_report"]["review_flag_count"] >= 1


def test_manual_stage2_submission_requires_admin_role():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer athlete-token"},
        json=ManualStage2SubmissionRequest(final_plan_text="# Manual GPT Final").model_dump(mode="json"),
    )

    assert response.status_code == 403


def test_admin_can_approve_review_required_plan_for_release():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="# Held Stage 2 Output",
            stage2_status="stage2_failed",
            stage2_retry_text="repair prompt",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/approve",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["outputs"]["plan_text"] == "# Held Stage 2 Output"
    assert body["admin_outputs"]["stage2_status"] == "admin_review_approved"


def test_admin_can_reject_approved_plan_back_to_review():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="ready",
            plan_text="# Released Stage 2 Output",
            final_plan_text="# Released Stage 2 Output",
            stage2_status="admin_review_approved",
            stage2_retry_text="repair prompt",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/reject",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["outputs"]["plan_text"] == ""
    assert body["admin_outputs"]["final_plan_text"] == "# Released Stage 2 Output"
    assert body["admin_outputs"]["stage2_status"] == "admin_review_rejected"


def test_needs_review_can_be_approved_and_resumed_with_normal_generation_flow():
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
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    stage2 = FakeStage2Automator(result=finalized_result())
    planner_calls: list[dict] = []

    def planner(payload: dict) -> dict:
        planner_calls.append(payload)
        return stage1_result()

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=planner,
            stage2_automator=stage2,
        )
    )

    resume_response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "injury details clarified"},
    )
    assert resume_response.status_code == 202
    job_id = resume_response.json()["job_id"]

    job_response = client.get(f"/api/generation-jobs/{job_id}", headers={"Authorization": "Bearer admin-token"})
    assert job_response.status_code == 200
    job = job_response.json()
    assert job["status"] == "completed"
    assert len(planner_calls) == 1
    assert len(stage2.calls) == 1
    assert stage2.calls[0]["plan_text"] == "# Stage 1 Draft"


def test_medical_hold_cannot_use_approve_and_resume_generation():
    client, store, _ = _build_client()
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
            why_log={"injury_triage": {"mode": "medical_hold", "should_block_stage2": True}},
        ),
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "should fail"},
    )

    assert response.status_code == 409


def test_curated_review_required_scenarios_are_fast_for_admin_to_resolve():
    for scenario in [item for item in SYSTEM_SCENARIOS if item.expected_resolution]:
        client, store, _ = _build_client(FakeStage2Automator(result=scenario.automator_result))
        _, job = _start_generation(client, _build_request(scenario.request_overrides))
        plan_id = job["plan_id"]

        if scenario.expected_resolution == "approve":
            resolved = client.post(
                f"/api/admin/plans/{plan_id}/approve",
                headers={"Authorization": "Bearer admin-token"},
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "ready"
            assert resolved.json()["admin_outputs"]["stage2_status"] == "admin_review_approved"
        elif scenario.expected_resolution == "manual_stage2":
            resolved = client.post(
                f"/api/admin/plans/{plan_id}/manual-stage2",
                headers={"Authorization": "Bearer admin-token"},
                json=ManualStage2SubmissionRequest(
                    final_plan_text=(
                        "## PHASE 3: TAPER\n"
                        "### Week 5\n"
                        "#### Neural primer\n"
                        "- Assault Bike Sprint - 4 x 6 sec\n"
                        "#### Recovery\n"
                        "- Walk + mobility\n"
                    )
                ).model_dump(mode="json"),
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "ready"
            assert resolved.json()["admin_outputs"]["stage2_status"] == "manual_stage2_retry_pass"
        else:
            raise AssertionError(f"Unexpected resolution strategy: {scenario.expected_resolution}")

        assert store.get_plan(plan_id)["status"] == "ready"
