from __future__ import annotations

from api_test_support import _build_client, _build_request


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
                "technical_skill_days": [],
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
            "technical_skill_days": ["Tuesday"],
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
