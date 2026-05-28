from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def _old_iso(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


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


def test_admin_routes_use_env_allowlist_not_stored_role():
    """A profile with role='admin' in storage must be denied if the email is
    no longer in UNLXCK_ADMIN_EMAILS (which FakeStore models via admin_emails
    and the @unlxck.test pattern)."""
    store = FakeStore()  # admin_emails empty; only @unlxck.test pattern admits
    stale_admin = AuthenticatedUser(
        user_id="stale-admin-1",
        email="former-admin@example.com",
        full_name="Former Admin",
        metadata={},
    )
    # Pre-populate the profile with a stale admin role (as if env was removed).
    profile = store.ensure_profile(stale_admin)
    profile["role"] = "admin"
    store.profiles[stale_admin.user_id] = profile

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"stale-admin-token": stale_admin}),
            planner=lambda payload, progress_callback=None: {"plan_text": ""},
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    response = client.get(
        "/api/admin/athletes",
        headers={"Authorization": "Bearer stale-admin-token"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "admin access required"


def test_ensure_profile_demotes_stale_admin_role_when_email_removed_from_allowlist():
    store = FakeStore(admin_emails={"admin@example.com"})
    user = AuthenticatedUser(
        user_id="admin-demote-1",
        email="admin@example.com",
        full_name="Admin Demote",
        metadata={},
    )
    profile = store.ensure_profile(user)
    assert profile["role"] == "admin"

    store.admin_emails = set()
    refreshed = store.ensure_profile(user)
    assert refreshed["role"] == "athlete"


def test_admin_routes_allow_email_in_env_allowlist_even_if_stored_role_is_athlete():
    """A profile with role='athlete' in storage must be allowed if the email
    is in the env allowlist."""
    store = FakeStore(admin_emails={"newadmin@example.com"})
    new_admin = AuthenticatedUser(
        user_id="new-admin-1",
        email="newadmin@example.com",
        full_name="New Admin",
        metadata={},
    )
    profile = store.ensure_profile(new_admin)
    # Storage still has the stale "athlete" role.
    profile["role"] = "athlete"
    store.profiles[new_admin.user_id] = profile

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"new-admin-token": new_admin}),
            planner=lambda payload, progress_callback=None: {"plan_text": ""},
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    response = client.get(
        "/api/admin/athletes",
        headers={"Authorization": "Bearer new-admin-token"},
    )
    assert response.status_code == 200


def test_normal_athlete_denied_from_admin_routes():
    """Athletes with no admin allowlist entry must get 403."""
    store = FakeStore()
    athlete = AuthenticatedUser(
        user_id="athlete-only-1",
        email="athlete-only@example.com",
        full_name="Athlete Only",
        metadata={},
    )
    store.ensure_profile(athlete)

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-only-token": athlete}),
            planner=lambda payload, progress_callback=None: {"plan_text": ""},
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    response = client.get(
        "/api/admin/athletes",
        headers={"Authorization": "Bearer athlete-only-token"},
    )
    assert response.status_code == 403


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


def test_admin_can_archive_plan_and_remove_athlete_facing_output():
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
        f"/api/admin/plans/{plan['id']}/archive",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "archived"
    assert body["outputs"]["plan_text"] == ""
    assert body["admin_outputs"]["final_plan_text"] == "# Released Stage 2 Output"
    assert body["admin_outputs"]["stage2_status"] == "admin_archived"

    athlete_response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert athlete_response.status_code == 404


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
    assert planner_calls[0]["_triage_resume_override"]["approved"] is True
    assert planner_calls[0]["_triage_resume_override"]["reason"] == "injury details clarified"
    assert planner_calls[0]["_triage_resume_override"]["allowed_modes"] == ["needs_review", "restricted_rehab_only"]
    assert "_triage_resume_override" not in intake["intake"]
    assert len(stage2.calls) == 1
    assert stage2.calls[0]["plan_text"] == "# Stage 1 Draft"
    refreshed_plan = client.get(
        f"/api/plans/{blocked_plan['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert refreshed_plan.status_code == 200
    # The resumed generation updates the original blocked plan in place, so the
    # stage2_status reflects the new finalized run. The triage approval audit
    # marker (triage_regeneration_cleared) must still be preserved on why_log.
    assert refreshed_plan.json()["admin_outputs"]["stage2_status"] == "stage2_pass"
    assert refreshed_plan.json()["admin_outputs"]["why_log"]["triage_regeneration_cleared"] is True


def test_approve_and_resume_generation_blocks_duplicate_after_successful_resume():
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
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    first_response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "injury details clarified"},
    )
    assert first_response.status_code == 202

    second_response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "repeat click"},
    )
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "this blocked plan has already been approved and resumed"


def test_approve_and_resume_generation_does_not_reset_live_running_resume_job():
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    admin = AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=f"triage_resume_{blocked_plan['id']}",
        source="admin_triage_resume",
        request_payload={"existing": True, "_triage_resume_override": {"approved": True}},
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    store.update_generation_job(
        existing_job["id"],
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        heartbeat_at=datetime.now(timezone.utc).isoformat(),
        stage1_result={"status": "ready"},
        final_result={"status": "working"},
    )
    client = TestClient(create_app(store=store, auth_service=FakeAuthService({"admin-token": admin})))
    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "keep polling"},
    )
    assert response.status_code == 202
    assert response.json()["job_id"] == existing_job["id"]
    refreshed = store.get_generation_job(existing_job["id"])
    assert refreshed["status"] == "running"
    assert refreshed["stage1_result"] == {"status": "ready"}
    assert refreshed["final_result"] == {"status": "working"}
    assert refreshed["request_payload"] == {"existing": True, "_triage_resume_override": {"approved": True}}


def test_approve_and_resume_generation_rejects_live_running_resume_job_with_unsafe_linkage():
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    admin = AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
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
            stage2_status="triage_resume_approved",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        ),
    )
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=f"triage_resume_{blocked_plan['id']}",
        source="admin_triage_resume",
        request_payload={"existing": True},
    )
    store.update_generation_job(
        existing_job["id"],
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        heartbeat_at=datetime.now(timezone.utc).isoformat(),
        intake_id=None,
        plan_id=None,
    )
    client = TestClient(create_app(store=store, auth_service=FakeAuthService({"admin-token": admin})))
    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "keep polling"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "existing triage resume job has unsafe linkage; create a new resume request"


def test_approve_and_resume_generation_requeues_completed_triage_blocked_resume_job():
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    admin = AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
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
            stage2_status="triage_resume_approved",
            why_log={"injury_triage": {"mode": "needs_review", "should_block_stage2": True}, "triage_regeneration_cleared": True},
        ),
    )
    existing = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=f"triage_resume_{blocked_plan['id']}",
        source="admin_triage_resume",
        request_payload=request.to_payload(),
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    store.update_generation_job(existing["id"], status="running", started_at=datetime.now(timezone.utc).isoformat(), heartbeat_at=datetime.now(timezone.utc).isoformat())
    store.update_generation_job(existing["id"], status="completed", final_result={"status": "triage_blocked"}, completed_at=datetime.now(timezone.utc).isoformat())
    client = TestClient(create_app(store=store, auth_service=FakeAuthService({"admin-token": admin})))
    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "retry blocked resume"},
    )
    assert response.status_code == 202
    job = store.get_generation_job(response.json()["job_id"])
    assert job["id"] == existing["id"]
    assert job["request_payload"]["_triage_resume_override"]["approved"] is True


def test_approve_and_resume_generation_creates_job_with_intake_and_plan_linked():
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
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "injury details clarified"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = store.get_generation_job(job_id)
    assert job is not None
    assert job["intake_id"] == str(intake["id"])
    assert job["plan_id"] == str(blocked_plan["id"])


def _seed_triage_blocked_job(store, *, athlete_id: str, intake_id: str, request) -> dict:
    """Seed a generation_jobs row that represents a new-style triage outcome
    (no plan row, final_result carries the triage state on the job)."""
    job = store.create_or_get_generation_job(
        athlete_id=athlete_id,
        client_request_id=f"triage_seed_{intake_id}",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
        intake_id=intake_id,
    )
    store.update_generation_job(
        job["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
    )
    store.update_generation_job(
        job["id"],
        status="review_required",
        final_result={
            "status": "triage_blocked",
            "stage2_status": "triage_blocked",
            "why_log": {"injury_triage": {"mode": "needs_review", "should_block_stage2": True}},
        },
        heartbeat_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:00+00:00",
    )
    return store.get_generation_job(job["id"])


def test_approve_and_resume_generation_from_job_creates_resume_job_without_plan_id():
    """The new endpoint takes a generation_job_id (not a plan_id). It must
    create an admin_triage_resume job linked to the intake but NOT to any
    plan row — the resume produces a real plan only when Stage 2 succeeds."""
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    admin = AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
    store = FakeStore()
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    triage_job = _seed_triage_blocked_job(
        store, athlete_id=athlete.user_id, intake_id=str(intake["id"]), request=request
    )

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/generation-jobs/{triage_job['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "intake reviewed"},
    )
    assert response.status_code == 202
    body = response.json()
    resume_job = store.get_generation_job(body["job_id"])
    assert resume_job is not None
    assert resume_job["id"] != triage_job["id"]
    assert resume_job["source"] == "admin_triage_resume"
    assert resume_job["intake_id"] == str(intake["id"])
    # New endpoint must NOT pre-link a plan_id — the resume runtime creates
    # a real plan only after Stage 2 succeeds.
    assert resume_job.get("plan_id") in (None, "")
    # No plan row exists yet (no Stage 2 has run).
    assert store.plans == {}
    # Source job got the approval marker so a second approval is rejected.
    source_after = store.get_generation_job(triage_job["id"])
    final_after = source_after.get("final_result") or {}
    assert final_after.get("stage2_status") == "triage_resume_approved"
    assert isinstance(final_after.get("why_log", {}).get("triage_resume_approval"), dict)


def test_approve_and_resume_generation_from_job_rejects_non_triage_job():
    """The new endpoint refuses jobs that are not in a protected triage state."""
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    admin = AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
    store = FakeStore()
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    plain_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="not-triage",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
        intake_id=str(intake["id"]),
    )
    store.update_generation_job(
        plain_job["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
    )
    store.update_generation_job(plain_job["id"], status="completed", final_result={"status": "ready"})

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/generation-jobs/{plain_job['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "n/a"},
    )
    assert response.status_code == 409
    assert "protected triage" in response.json().get("detail", "")


def test_approve_and_resume_generation_from_job_rejects_already_approved():
    """A second approval on the same triage job is rejected with a clear conflict."""
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    admin = AuthenticatedUser(user_id="admin-1", email="ops@unlxck.test", full_name="Ops Admin", metadata={})
    store = FakeStore()
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    triage_job = _seed_triage_blocked_job(
        store, athlete_id=athlete.user_id, intake_id=str(intake["id"]), request=request
    )
    # Mark as already approved.
    final_result = triage_job["final_result"]
    final_result["stage2_status"] = "triage_resume_approved"
    store.update_generation_job(triage_job["id"], final_result=final_result)

    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/generation-jobs/{triage_job['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "duplicate approval"},
    )
    assert response.status_code == 409
    assert "already" in response.json().get("detail", "")


def test_approve_and_resume_generation_requeues_stale_running_resume_job_without_duplicate():
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    client_request_id = f"triage_resume_{blocked_plan['id']}"
    request_payload = request.model_dump(mode="json")
    request_payload["_triage_resume_override"] = {"approved": True}
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload=request_payload,
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    store.update_generation_job(
        existing_job["id"],
        status="running",
        attempt_count=1,
        heartbeat_at=_old_iso(),
        started_at=_old_iso(),
        stage1_result=None,
        final_result=None,
        completed_at=None,
        error="old stall",
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "retry stalled resume"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing_job["id"]
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == 1
    refreshed = store.get_generation_job(existing_job["id"])
    assert refreshed["status"] == "queued"
    assert refreshed["error"] is None
    assert refreshed["stage1_result"] is None
    assert refreshed["final_result"] is None
    assert refreshed["completed_at"] is None
    assert refreshed["plan_id"] == str(blocked_plan["id"])
    assert refreshed["intake_id"] == str(intake["id"])
    assert refreshed["client_request_id"] == client_request_id
    assert refreshed["heartbeat_at"]


def test_approve_and_resume_generation_requeues_failed_resume_job_without_duplicate():
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    client_request_id = f"triage_resume_{blocked_plan['id']}"
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload={
            **request.model_dump(mode="json"),
            "_triage_resume_override": {"approved": True},
        },
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    store.update_generation_job(
        existing_job["id"],
        status="failed",
        attempt_count=1,
        heartbeat_at=_old_iso(),
        completed_at=_old_iso(),
        stage1_result=None,
        final_result=None,
        error="planner crashed before Stage 1",
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "retry failed resume"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing_job["id"]
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == 1
    refreshed = store.get_generation_job(existing_job["id"])
    assert refreshed["status"] == "queued"
    assert refreshed["error"] is None
    assert refreshed["stage1_result"] is None
    assert refreshed["final_result"] is None
    assert refreshed["completed_at"] is None
    assert refreshed["plan_id"] == str(blocked_plan["id"])
    assert refreshed["intake_id"] == str(intake["id"])
    assert refreshed["client_request_id"] == client_request_id


def test_approve_and_resume_generation_requeues_stage1_timeout_resume_job_without_duplicate():
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    client_request_id = f"triage_resume_{blocked_plan['id']}"
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload={
            **request.model_dump(mode="json"),
            "_triage_resume_override": {"approved": True},
        },
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    store.update_generation_job(
        existing_job["id"],
        status="failed",
        attempt_count=1,
        heartbeat_at=_old_iso(),
        completed_at=_old_iso(),
        stage1_result=None,
        final_result=None,
        error="Stage 1 planner timed out before producing a result.",
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "retry timed out resume"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing_job["id"]
    assert body["status"] == "queued"
    assert len(store.generation_jobs) == 1
    refreshed = store.get_generation_job(existing_job["id"])
    assert refreshed["status"] == "queued"
    assert refreshed["error"] is None
    assert refreshed["stage1_result"] is None
    assert refreshed["final_result"] is None
    assert refreshed["completed_at"] is None
    assert refreshed["plan_id"] == str(blocked_plan["id"])
    assert refreshed["intake_id"] == str(intake["id"])
    assert refreshed["client_request_id"] == client_request_id
    assert refreshed["request_payload"]["_triage_resume_override"]["approved"] is True
    assert refreshed["request_payload"]["_triage_resume_override"]["reason"] == "retry timed out resume"
    assert store.get_plan(blocked_plan["id"])["stage2_status"] == "triage_resume_approved"


def test_approve_and_resume_generation_returns_non_stale_running_resume_job_as_is():
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    client_request_id = f"triage_resume_{blocked_plan['id']}"
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=client_request_id,
        source="admin_triage_resume",
        request_payload={
            **request.model_dump(mode="json"),
            "_triage_resume_override": {"approved": True},
        },
        intake_id=str(intake["id"]),
        plan_id=str(blocked_plan["id"]),
    )
    heartbeat_at = datetime.now(timezone.utc).isoformat()
    store.update_generation_job(
        existing_job["id"],
        status="running",
        attempt_count=1,
        heartbeat_at=heartbeat_at,
        started_at=heartbeat_at,
        stage1_result=None,
        final_result=None,
        completed_at=None,
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "repeat click"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == existing_job["id"]
    assert body["status"] == "running"
    refreshed = store.get_generation_job(existing_job["id"])
    assert refreshed["status"] == "running"
    assert refreshed["heartbeat_at"] == heartbeat_at
    assert len(store.generation_jobs) == 1


def test_approve_and_resume_generation_rejects_wrongly_linked_existing_resume_job_after_approval():
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"approved_by_email": "ops@unlxck.test"},
                "triage_regeneration_cleared": True,
            },
        ),
    )
    existing_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=f"triage_resume_{blocked_plan['id']}",
        source="admin_triage_resume",
        request_payload={
            **request.model_dump(mode="json"),
            "_triage_resume_override": {"approved": True},
        },
        intake_id=str(intake["id"]),
        plan_id=None,
    )
    store.update_generation_job(existing_job["id"], status="queued")
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "repeat click"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "existing triage resume job has unsafe linkage; create a new resume request"
    assert len(store.generation_jobs) == 1
    assert store.get_generation_job(existing_job["id"])["plan_id"] is None


def test_approve_and_resume_full_flow_updates_plan_in_place_with_override_metadata():
    """End-to-end (HTTP -> worker -> plan update) lock: a `needs_review` plan
    approved via `/approve-and-resume-generation` must result in the SAME
    plan id being updated in place (no duplicate row), the resulting plan
    status must NOT be `triage_blocked`, and the why_log must carry both the
    override markers from the planner and the approval audit trail from the
    endpoint."""
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

    def override_aware_planner(payload: dict) -> dict:
        override = payload.get("_triage_resume_override") or {}
        # Mirror fightcamp.main: with an approved override, the planner
        # continues past the triage block and decorates why_log with both
        # the override marker and the preserved original triage decision.
        result = dict(stage1_result())
        if override.get("approved") is True:
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
        else:
            result["status"] = "triage_blocked"
            result["why_log"] = {"injury_triage": {"mode": "needs_review", "should_block_stage2": True}}
        return result

    stage2 = FakeStage2Automator(
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
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=override_aware_planner,
            stage2_automator=stage2,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "injury details clarified"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job = store.get_generation_job(job_id)
    assert job["status"] == "completed"
    assert job["plan_id"] == str(blocked_plan["id"])
    assert job["request_payload"]["_triage_resume_override"]["approved"] is True
    assert str(job["final_result"]["status"]) != "triage_blocked"

    plans = store.list_user_plans(athlete.user_id)
    assert len(plans) == 1, "approve-and-resume must update in place, not create a duplicate plan"
    refreshed = store.get_plan(blocked_plan["id"])
    assert refreshed["status"] != "triage_blocked"
    why_log = refreshed["why_log"]
    assert why_log["injury_triage_resume_override"]["bypassed_blocking"] is True
    assert why_log["injury_triage_original"]["mode"] == "needs_review"
    assert why_log["triage_resume_approval"]["approved_by_email"] == "ops@unlxck.test"
    assert why_log["triage_regeneration_cleared"] is True


def test_admin_triage_resume_pre_start_stale_job_preserves_plan_and_intake_links():
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
            stage2_status="triage_resume_approved",
            why_log={
                "injury_triage": {"mode": "needs_review", "should_block_stage2": True},
                "triage_resume_approval": {"reason": "first approval"},
            },
        ),
    )
    stale_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=f"triage_resume_{blocked_plan['id']}",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
    )
    store.update_generation_job(
        stale_job["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
        progress_milestones=[],
        plan_id=blocked_plan["id"],
        intake_id=intake["id"],
    )
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=lambda payload: stage1_result(),
            stage2_automator=FakeStage2Automator(result=finalized_result()),
            enable_in_process_generation=False,
        )
    )

    response = client.post(
        f"/api/admin/plans/{blocked_plan['id']}/approve-and-resume-generation",
        headers={"Authorization": "Bearer admin-token"},
        json={"reason": "retry stale pre-start job"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"] == stale_job["id"]
    assert body["status"] == "queued"
    reset_job = store.get_generation_job(stale_job["id"])
    assert reset_job["plan_id"] == blocked_plan["id"]
    assert reset_job["intake_id"] == intake["id"]
    assert len(store.generation_jobs) == 1


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


def test_admin_state_integrity_diagnostics_reports_orphans_and_failed_resume_markers():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(user_id="athlete-diag-1", email="a1@example.com", full_name="A One", metadata={})
    store.ensure_profile(athlete)
    request = _build_request()
    intake = store.create_intake(athlete.user_id, request)
    blocked_plan = store.create_plan(
        athlete_id=athlete.user_id,
        intake_id=str(intake["id"]),
        request=request,
        result=finalized_result(status="triage_blocked", stage2_status="triage_resume_approved"),
    )
    resume_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id=f"triage_resume_{blocked_plan['id']}",
        source="admin_triage_resume",
        request_payload=request.model_dump(mode="json"),
        plan_id=blocked_plan["id"],
        intake_id=str(intake["id"]),
    )
    store.update_generation_job(resume_job["id"], status="failed", error="failed resume")
    orphan_job = store.create_or_get_generation_job(
        athlete_id=athlete.user_id,
        client_request_id="orphan-terminal-diag",
        source="self_serve",
        request_payload=request.model_dump(mode="json"),
        plan_id="",
        intake_id=str(intake["id"]),
    )
    store.update_generation_job(orphan_job["id"], status="completed")

    response = client.get(
        "/api/admin/diagnostics/state-integrity?limit=25",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 25
    assert body["orphaned_terminal_job_count"] >= 1
    assert body["failed_resume_with_approved_marker_count"] >= 1


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

def test_admin_can_patch_latest_intake_focus_fields_and_persist():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(user_id="athlete-intake-1", email="a1@example.com", full_name="A One", metadata={})
    store.ensure_profile(athlete)
    intake = store.create_intake("athlete-intake-1", _build_request())

    response = client.patch(
        "/api/admin/athletes/athlete-intake-1/latest-intake",
        headers={"Authorization": "Bearer admin-token"},
        json={"key_goals": ["power"], "weak_areas": ["conditioning"]},
    )
    assert response.status_code == 200
    saved = store.get_intake(intake["id"])
    assert saved["intake"]["key_goals"] == ["power"]
    assert saved["intake"]["weak_areas"] == ["conditioning"]


def test_admin_patch_latest_intake_rejects_over_cap_focus():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(user_id="athlete-intake-2", email="a2@example.com", full_name="A Two", metadata={})
    store.ensure_profile(athlete)
    base = _build_request({"fight_date": (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()})
    store.create_intake("athlete-intake-2", base)

    response = client.patch(
        "/api/admin/athletes/athlete-intake-2/latest-intake",
        headers={"Authorization": "Bearer admin-token"},
        json={"key_goals": ["power", "conditioning"], "weak_areas": ["defense"]},
    )
    assert response.status_code == 409


def test_admin_patch_latest_intake_rejects_wrong_athlete_linkage():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(user_id="athlete-intake-3", email="a3@example.com", full_name="A Three", metadata={})
    store.ensure_profile(athlete)
    store.create_intake("athlete-intake-3", _build_request())
    store.intakes["athlete-intake-3"][-1]["athlete_id"] = "other-athlete"

    response = client.patch(
        "/api/admin/athletes/athlete-intake-3/latest-intake",
        headers={"Authorization": "Bearer admin-token"},
        json={"key_goals": ["power"]},
    )
    assert response.status_code == 409


def test_admin_patch_latest_intake_uses_store_update_intake():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(user_id="athlete-intake-4", email="a4@example.com", full_name="A Four", metadata={})
    store.ensure_profile(athlete)
    intake = store.create_intake("athlete-intake-4", _build_request())
    calls: list[str] = []
    original = store.update_intake

    def tracking_update_intake(intake_id: str, *, intake: dict, fight_date: str | None, technical_style: list[str]) -> dict:
        calls.append(intake_id)
        return original(intake_id, intake=intake, fight_date=fight_date, technical_style=technical_style)

    store.update_intake = tracking_update_intake  # type: ignore[assignment]

    response = client.patch(
        "/api/admin/athletes/athlete-intake-4/latest-intake",
        headers={"Authorization": "Bearer admin-token"},
        json={"key_goals": ["power"]},
    )
    assert response.status_code == 200
    assert calls == [intake["id"]]
