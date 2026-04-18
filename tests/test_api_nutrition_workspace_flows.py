from __future__ import annotations

from fastapi import HTTPException, status

from support import _build_client, _build_request


def _get_current_workspace(client) -> dict:
    response = client.get("/api/nutrition/current", headers={"Authorization": "Bearer athlete-token"})
    assert response.status_code == 200
    return response.json()


def test_nutrition_workspace_update_adds_visible_sparring_days_to_hidden_training_availability():
    client, store, _ = _build_client()
    client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    store.create_intake(
        "athlete-1",
        _build_request(
            {
                "training_availability": ["Monday", "Wednesday"],
                "hard_sparring_days": ["Wednesday"],
        "support_work_days": [],
            }
        ),
    )

    workspace = _get_current_workspace(client)
    update = {
        "nutrition_profile": workspace["nutrition_profile"],
        "shared_camp_context": {
            **workspace["shared_camp_context"],
            "training_availability": [],
            "hard_sparring_days": ["Friday"],
        "support_work_days": ["Tuesday"],
        },
        "s_and_c_preferences": workspace["s_and_c_preferences"],
        "nutrition_readiness": workspace["nutrition_readiness"],
        "nutrition_monitoring": workspace["nutrition_monitoring"],
        "nutrition_coach_controls": workspace["nutrition_coach_controls"],
    }

    response = client.put(
        "/api/nutrition/current",
        headers={"Authorization": "Bearer athlete-token"},
        json=update,
    )

    assert response.status_code == 200
    shared = response.json()["shared_camp_context"]
    assert shared["training_availability"] == ["Monday", "Wednesday", "Friday", "Tuesday"]
    assert shared["session_types_by_day"]["friday"] == "hard_spar"
    assert shared["session_types_by_day"]["tuesday"] == "technical"


def test_nutrition_workspace_missing_required_fields_do_not_include_training_availability():
    client, _, _ = _build_client()
    client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})

    workspace = _get_current_workspace(client)

    assert "training_availability" not in workspace["derived"]["missing_required_fields"]


def test_nutrition_workspace_update_retries_profile_update_without_nutrition_profile():
    client, store, _ = _build_client()
    client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    store.create_intake("athlete-1", _build_request({}))

    original_update_profile = store.update_profile
    update_calls: list[dict] = []

    def flaky_update_profile(athlete_id, update):
        payload = update.model_dump(mode="json", exclude_none=True)
        update_calls.append(payload)
        if payload.get("nutrition_profile") is not None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to update profile")
        return original_update_profile(athlete_id, update)

    store.update_profile = flaky_update_profile  # type: ignore[assignment]

    workspace = _get_current_workspace(client)
    update = {
        "nutrition_profile": workspace["nutrition_profile"],
        "shared_camp_context": workspace["shared_camp_context"],
        "s_and_c_preferences": workspace["s_and_c_preferences"],
        "nutrition_readiness": workspace["nutrition_readiness"],
        "nutrition_monitoring": {
            "daily_bodyweight_log": [
                {"date": "2026-04-11", "weight_kg": 72.4, "time": "07:00", "is_fasted": True, "notes": "am"},
            ],
        },
        "nutrition_coach_controls": workspace["nutrition_coach_controls"],
    }

    response = client.put(
        "/api/nutrition/current",
        headers={"Authorization": "Bearer athlete-token"},
        json=update,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["nutrition_monitoring"]["daily_bodyweight_log"][0]["weight_kg"] == 72.4
    assert len(update_calls) == 2
    assert "nutrition_profile" in update_calls[0]
    assert "nutrition_profile" not in update_calls[1]


def test_nutrition_workspace_update_retries_profile_update_without_nutrition_profile_for_any_5xx_detail():
    client, store, _ = _build_client()
    client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    store.create_intake("athlete-1", _build_request({}))

    original_update_profile = store.update_profile
    update_calls: list[dict] = []

    def flaky_update_profile(athlete_id, update):
        payload = update.model_dump(mode="json", exclude_none=True)
        update_calls.append(payload)
        if payload.get("nutrition_profile") is not None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="database write failed")
        return original_update_profile(athlete_id, update)

    store.update_profile = flaky_update_profile  # type: ignore[assignment]

    workspace = _get_current_workspace(client)
    update = {
        "nutrition_profile": workspace["nutrition_profile"],
        "shared_camp_context": workspace["shared_camp_context"],
        "s_and_c_preferences": workspace["s_and_c_preferences"],
        "nutrition_readiness": workspace["nutrition_readiness"],
        "nutrition_monitoring": {
            "daily_bodyweight_log": [
                {"date": "2026-04-12", "weight_kg": 71.9, "time": "07:05", "is_fasted": True, "notes": "am"},
            ],
        },
        "nutrition_coach_controls": workspace["nutrition_coach_controls"],
    }

    response = client.put(
        "/api/nutrition/current",
        headers={"Authorization": "Bearer athlete-token"},
        json=update,
    )

    assert response.status_code == 200
    assert len(update_calls) == 2
    assert "nutrition_profile" in update_calls[0]
    assert "nutrition_profile" not in update_calls[1]


def test_athlete_nutrition_workspace_update_ignores_coach_control_fields():
    client, _, _ = _build_client()
    client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})

    workspace = _get_current_workspace(client)
    update = {
        "nutrition_profile": workspace["nutrition_profile"],
        "shared_camp_context": workspace["shared_camp_context"],
        "s_and_c_preferences": workspace["s_and_c_preferences"],
        "nutrition_readiness": workspace["nutrition_readiness"],
        "nutrition_monitoring": workspace["nutrition_monitoring"],
        "nutrition_coach_controls": {
            **workspace["nutrition_coach_controls"],
            "coach_override_enabled": True,
            "do_not_reduce_below_calories": 2400,
            "protein_floor_g_per_kg": 2.2,
        },
    }

    response = client.put(
        "/api/nutrition/current",
        headers={"Authorization": "Bearer athlete-token"},
        json=update,
    )

    assert response.status_code == 200
    controls = response.json()["nutrition_coach_controls"]
    assert controls == workspace["nutrition_coach_controls"]


def test_admin_nutrition_workspace_update_allows_coach_control_fields():
    client, _, _ = _build_client()
    client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    client.get("/api/me", headers={"Authorization": "Bearer admin-token"})

    get_response = client.get(
        "/api/admin/athletes/athlete-1/nutrition/current",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert get_response.status_code == 200
    workspace = get_response.json()
    update = {
        "nutrition_profile": workspace["nutrition_profile"],
        "shared_camp_context": workspace["shared_camp_context"],
        "s_and_c_preferences": workspace["s_and_c_preferences"],
        "nutrition_readiness": workspace["nutrition_readiness"],
        "nutrition_monitoring": workspace["nutrition_monitoring"],
        "nutrition_coach_controls": {
            **workspace["nutrition_coach_controls"],
            "coach_override_enabled": True,
            "athlete_override_enabled": True,
            "do_not_reduce_below_calories": 2500,
            "protein_floor_g_per_kg": 2.0,
            "fight_week_manual_mode": True,
            "water_cut_locked_to_manual": True,
        },
    }

    response = client.put(
        "/api/admin/athletes/athlete-1/nutrition/current",
        headers={"Authorization": "Bearer admin-token"},
        json=update,
    )

    assert response.status_code == 200
    controls = response.json()["nutrition_coach_controls"]
    assert controls["coach_override_enabled"] is True
    assert controls["athlete_override_enabled"] is True
    assert controls["do_not_reduce_below_calories"] == 2500
    assert controls["protein_floor_g_per_kg"] == 2.0
    assert controls["fight_week_manual_mode"] is True
    assert controls["water_cut_locked_to_manual"] is True
