from __future__ import annotations

from api.auth import AuthenticatedUser
from api.models import PlanRenameRequest
from support import advisory_planning_brief, _build_client, _build_request, finalized_result, stage1_result


def _weekly_schedule_planning_brief() -> dict:
    return {
        "schema_version": "planning_brief.v1",
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "declared_hard_sparring_days": ["Monday", "Wednesday"],
                    "declared_support_work_days": ["Tuesday"],
                    "hard_sparring_plan": [
                        {
                            "day": "Monday",
                            "hard_day_class": "primary_hard",
                            "effective_load": "hard",
                            "status": "hard_as_planned",
                            "reason": "",
                            "reason_codes": [],
                        },
                        {
                            "day": "Wednesday",
                            "hard_day_class": "managed_hard",
                            "effective_load": "reduced",
                            "status": "deload_suggested",
                            "reason": "high fatigue",
                            "reason_codes": ["high_fatigue"],
                            "coach_note": "Keep the rounds controlled.",
                        },
                    ],
                }
            ]
        },
    }


def test_athlete_cannot_read_another_athlete_plan():
    client, store, _ = _build_client()
    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    store.ensure_profile(other_user)
    plan = store.create_plan(
        athlete_id="athlete-2",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 403


def test_athlete_can_read_weekly_schedule_for_their_plan_and_latest_plan():
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
        result=finalized_result(planning_brief=_weekly_schedule_planning_brief()),
    )

    response = client.get(
        f"/api/plans/{plan['id']}/weekly-schedule",
        headers={"Authorization": "Bearer athlete-token"},
    )
    latest_response = client.get(
        "/api/plans/latest/weekly-schedule",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    assert latest_response.status_code == 200
    body = response.json()
    assert body["plan_id"] == plan["id"]
    assert body["week_index"] == 0
    assert body["week_count"] == 1
    assert body["phase"] == "SPP"
    assert [day["weekday"] for day in body["days"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert body["days"][0]["sparring_day_class"] == "primary_hard"
    assert body["days"][1]["sparring_day_class"] == "none"
    assert body["days"][2]["sparring_day_class"] == "managed_hard"
    assert body["days"][2]["coach_note"] == "Keep the rounds controlled."
    assert latest_response.json() == body


def test_athlete_cannot_read_another_athlete_weekly_schedule():
    client, store, _ = _build_client()
    owner = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    store.ensure_profile(owner)
    store.ensure_profile(other_user)
    client.app.state.auth_service.users_by_token["other-token"] = other_user
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(planning_brief=_weekly_schedule_planning_brief()),
    )

    response = client.get(
        f"/api/plans/{plan['id']}/weekly-schedule",
        headers={"Authorization": "Bearer other-token"},
    )

    assert response.status_code == 403


def test_weekly_schedule_returns_404_for_plan_without_weekly_role_map():
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
        result=finalized_result(planning_brief={"schema_version": "planning_brief.v1"}),
    )

    response = client.get(
        f"/api/plans/{plan['id']}/weekly-schedule",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 404


def test_archived_plan_weekly_schedule_is_hidden_from_athlete():
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
            status="archived",
            stage2_status="admin_archived",
            planning_brief=_weekly_schedule_planning_brief(),
        ),
    )

    response = client.get(
        f"/api/plans/{plan['id']}/weekly-schedule",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 404


def test_admin_can_view_internal_plan_outputs():
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
            stage2_retry_text="repair prompt",
            planning_brief={"schema_version": "planning_brief.v1"},
            parsing_metadata={"athlete_timezone": {"source": "defaulted_missing"}},
        ),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    admin_outputs = response.json()["admin_outputs"]
    assert admin_outputs["stage2_payload"] == {"ok": True}
    assert admin_outputs["draft_plan_text"] == "# Stage 1 Draft"
    assert admin_outputs["stage2_retry_text"] == "repair prompt"
    assert admin_outputs["stage2_status"] == "stage2_pass"
    assert admin_outputs["parsing_metadata"] == {"athlete_timezone": {"source": "defaulted_missing"}}


def test_legacy_rows_with_only_plan_text_remain_readable():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    legacy = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=stage1_result(),
    )

    response = client.get(
        f"/api/plans/{legacy['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    assert response.json()["outputs"]["plan_text"] == "# Stage 1 Draft"


def test_plan_detail_returns_public_sparring_advisory_without_changing_saved_plan_text():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    original_text = "# Final Plan\n- Keep the saved plan untouched."
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            plan_text=original_text,
            final_plan_text=original_text,
            planning_brief=advisory_planning_brief(
                readiness_flags=["fight_week"],
                injuries=["mild stable shoulder soreness"],
                hard_sparring_days=["Tuesday", "Thursday"],
            ),
        ),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outputs"]["plan_text"] == original_text
    assert len(body["advisories"]) == 1
    # days_until_fight=6 falls inside the D-17 → D-0 countdown override, so the
    # planner converts each declared hard sparring day to technical rather than
    # merely deloading it.
    assert body["advisories"][0]["action"] == "convert"
    assert body["advisories"][0]["days"] == ["Tuesday", "Thursday"]
    assert body["advisories"][0]["title"] == "Coach note"
    assert body["advisories"][0]["disclaimer"] == "Treat this as a flag, not an automatic change to your saved plan."
    assert store.get_plan(plan["id"])["plan_text"] == original_text


def test_plan_detail_advisory_is_derived_from_structured_context_not_saved_plan_text():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    planning_brief = advisory_planning_brief(
        readiness_flags=["fight_week", "active_weight_cut"],
        fatigue="high",
        injuries=["worsening ankle instability"],
        weight_cut_pct=5.4,
        hard_sparring_days=["Tuesday", "Thursday"],
    )
    first = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_1",
        request=_build_request(),
        result=finalized_result(
            plan_text="# Final Plan A\n- Preserve this text.",
            final_plan_text="# Final Plan A\n- Preserve this text.",
            planning_brief=planning_brief,
        ),
    )
    second = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_2",
        request=_build_request(),
        result=finalized_result(
            plan_text="# Final Plan B\n- Different saved wording.",
            final_plan_text="# Final Plan B\n- Different saved wording.",
            planning_brief=planning_brief,
        ),
    )

    first_response = client.get(
        f"/api/plans/{first['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    second_response = client.get(
        f"/api/plans/{second['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["outputs"]["plan_text"] != second_response.json()["outputs"]["plan_text"]
    assert first_response.json()["advisories"] == second_response.json()["advisories"]


def test_latest_plan_endpoint_returns_latest_saved_plan():
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    latest = client.get("/api/plans/latest", headers={"Authorization": "Bearer athlete-token"})

    assert latest.status_code == 200
    assert latest.json()["plan_id"] == next(iter(store.plans.values()))["id"]


def test_athlete_can_rename_their_saved_plan():
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

    response = client.patch(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
        json=PlanRenameRequest(plan_name="April Fight Camp").model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan_name"] == "April Fight Camp"
    assert store.get_plan(plan["id"])["plan_name"] == "April Fight Camp"


def test_athlete_can_rename_their_saved_plan_via_documented_name_route():
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

    response = client.patch(
        f"/api/plans/{plan['id']}/name",
        headers={"Authorization": "Bearer athlete-token"},
        json=PlanRenameRequest(plan_name="Camp A").model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["plan_name"] == "Camp A"
    assert store.get_plan(plan["id"])["plan_name"] == "Camp A"


def test_archived_plan_is_hidden_from_athlete_routes():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    visible_plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_visible",
        request=_build_request({"fight_date": "2026-05-01"}),
        result=finalized_result(status="ready", plan_text="# Visible", final_plan_text="# Visible"),
    )
    archived_plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_archived",
        request=_build_request({"fight_date": "2026-06-01"}),
        result=finalized_result(
            status="archived",
            plan_text="",
            final_plan_text="# Archived copy",
            stage2_status="admin_archived",
        ),
    )

    list_response = client.get("/api/plans", headers={"Authorization": "Bearer athlete-token"})
    latest_response = client.get("/api/plans/latest", headers={"Authorization": "Bearer athlete-token"})
    me_response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    archived_detail_response = client.get(
        f"/api/plans/{archived_plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    admin_detail_response = client.get(
        f"/api/plans/{archived_plan['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert list_response.status_code == 200
    assert [plan["plan_id"] for plan in list_response.json()] == [visible_plan["id"]]
    assert latest_response.status_code == 200
    assert latest_response.json()["plan_id"] == visible_plan["id"]
    assert me_response.status_code == 200
    assert me_response.json()["latest_plan"]["plan_id"] == visible_plan["id"]
    assert me_response.json()["plan_count"] == 1
    assert archived_detail_response.status_code == 404
    assert admin_detail_response.status_code == 200
    assert admin_detail_response.json()["status"] == "archived"


def test_athlete_can_delete_their_saved_plan():
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

    response = client.delete(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 204
    assert store.get_plan(plan["id"]) is None


def test_athlete_cannot_delete_someone_elses_plan():
    client, store, _ = _build_client()
    owner = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    store.ensure_profile(owner)
    store.ensure_profile(other_user)
    client.app.state.auth_service.users_by_token["other-token"] = other_user
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(),
    )

    response = client.delete(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer other-token"},
    )

    assert response.status_code == 403
    assert store.get_plan(plan["id"]) is not None


def test_generation_job_endpoint_requires_same_athlete_or_admin():
    client, _, _ = _build_client()
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    app_store = client.app.state.store
    client.app.state.auth_service.users_by_token["other-token"] = other_user
    app_store.ensure_profile(other_user)

    forbidden = client.get(
        f"/api/generation-jobs/{job_id}",
        headers={"Authorization": "Bearer other-token"},
    )
    allowed = client.get(
        f"/api/generation-jobs/{job_id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_admin_can_list_athlete_generation_jobs_with_sanitized_summary_and_retry_flags():
    client, store, _ = _build_client()
    request_payload = _build_request().model_dump(mode="json")
    request_payload["api_key"] = "should-not-return"
    failed = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="cli_failed",
        source="admin_latest_intake",
        request_payload=request_payload,
    )
    store.update_generation_job(
        failed["id"],
        status="failed",
        error="Stage 2 timeout",
        completed_at="2026-05-01T12:00:00+00:00",
    )
    response = client.get(
        "/api/admin/athletes/athlete-1/generation-jobs",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    first = body[0]
    assert first["status"] in {"failed", "queued", "running", "completed"}
    assert "created_at" in first
    assert "source" in first
    assert first["error"] == "Stage 2 timeout"
    assert first["client_request_id"] == "cli_failed"
    assert first["can_retry"] is True
    summary = first["request_payload_summary"]
    assert summary["athlete_name"] == request_payload["athlete"]["full_name"]
    assert summary["fight_date"] == request_payload["fight_date"]
    assert summary["fight_format"] == request_payload["rounds_format"]
    assert summary["fatigue_level"] == request_payload["fatigue_level"]
    assert summary["goals"] == request_payload["key_goals"]
    assert summary["weaknesses"] == request_payload["weak_areas"]
    assert summary["injuries"]
    assert summary["training_availability"] == ", ".join(request_payload["training_availability"])
    assert "api_key" not in summary
    assert "token" not in summary
    assert "authorization" not in summary
    assert "supabase_key" not in summary


def test_non_admin_cannot_list_admin_generation_jobs_and_stale_job_is_flagged():
    client, store, _ = _build_client()
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="retry_old_job_123",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    store.update_generation_job(
        job["id"],
        status="running",
        started_at="2026-01-01T00:00:00+00:00",
        heartbeat_at="2026-01-01T00:00:00+00:00",
    )
    forbidden = client.get(
        "/api/admin/athletes/athlete-1/generation-jobs",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert forbidden.status_code == 403
    allowed = client.get(
        "/api/admin/athletes/athlete-1/generation-jobs",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert allowed.status_code == 200
    stale = allowed.json()[0]
    assert stale["is_stale"] is True
    assert stale["stale_reason"]
    assert stale["retry_of"] == "old_job"
