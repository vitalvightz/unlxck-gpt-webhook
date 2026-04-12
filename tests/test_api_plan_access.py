from __future__ import annotations

from api.auth import AuthenticatedUser
from api.models import PlanRenameRequest
from support import advisory_planning_brief, _build_client, _build_request, _start_generation, finalized_result, stage1_result


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
    assert body["advisories"][0]["action"] == "deload"
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
