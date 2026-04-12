from __future__ import annotations

from api.auth import AuthenticatedUser
from api.models import ProfileUpdateRequest
from support import FakeStore, _build_client, _build_request


def test_admin_athlete_profile_includes_latest_intake_details():
    client, store, _ = _build_client()

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": ["pressure_fighter"],
            "stance": "orthodox",
            "professional_status": "amateur",
            "record": "5-1",
            "athlete_timezone": "Europe/London",
            "athlete_locale": "en-GB",
        },
    )
    assert response.status_code == 200

    generate_response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json={
            "athlete": {
                "full_name": "Ari Mensah",
                "age": 29,
                "height_cm": 178,
                "weight_kg": 74,
                "target_weight_kg": 72,
                "technical_style": ["boxing"],
                "tactical_style": ["pressure_fighter"],
                "stance": "orthodox",
                "professional_status": "amateur",
                "record": "5-1",
                "athlete_timezone": "Europe/London",
                "athlete_locale": "en-GB",
            },
            "fight_date": "2026-04-18",
            "rounds_format": "3 x 3",
            "weekly_training_frequency": 5,
            "fatigue_level": "moderate",
            "equipment_access": ["heavy_bag", "weights"],
            "training_availability": ["Monday", "Wednesday"],
            "hard_sparring_days": ["Friday"],
            "technical_skill_days": ["Tuesday"],
            "injuries": "Left shoulder management",
            "key_goals": ["conditioning", "fight_sharpness"],
            "weak_areas": ["defense", "gas_tank"],
            "training_preference": "Short, intense pads and bag rounds.",
            "mindset_challenges": "Starts too fast in the first round.",
            "notes": "Loved reactive defense work in the last camp.",
        },
    )
    assert generate_response.status_code == 202

    admin_response = client.get(
        "/api/admin/athletes/athlete-1",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert admin_response.status_code == 200
    payload = admin_response.json()
    assert payload["technical_style"] == ["boxing"]
    assert payload["tactical_style"] == ["pressure_fighter"]
    assert payload["stance"] == "orthodox"
    assert payload["professional_status"] == "amateur"
    assert payload["record"] == "5-1"
    assert payload["athlete_locale"] == "en-GB"
    assert payload["latest_intake"]["athlete"]["age"] == 29
    assert payload["latest_intake"]["equipment_access"] == ["heavy_bag", "weights"]
    assert payload["latest_intake"]["training_preference"] == "Short, intense pads and bag rounds."


def test_admin_can_generate_new_plan_from_latest_intake():
    client, _, _ = _build_client()

    generate_response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )
    assert generate_response.status_code == 202

    response = client.post(
        "/api/admin/athletes/athlete-1/plans/generate-from-latest-intake",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 202
    assert response.json()["athlete_id"] == "athlete-1"


def test_admin_generate_from_latest_intake_requires_existing_intake():
    client, _, _ = _build_client()
    me_response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert me_response.status_code == 200

    response = client.post(
        "/api/admin/athletes/athlete-1/plans/generate-from-latest-intake",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "latest intake not found for athlete"


def test_self_serve_generation_rejects_focus_picks_above_cap():
    client, _, _ = _build_client()
    request = _build_request(
        {
            "fight_date": "2099-08-20",
            "key_goals": ["power", "conditioning", "fight_sharpness", "volume"],
            "weak_areas": ["defense", "gas_tank", "timing", "footwork"],
        }
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This camp allows 7 total focus picks. Remove 1 goal or weak-area selection before generating."


def test_admin_generation_from_latest_intake_rejects_focus_picks_above_cap():
    client, store, _ = _build_client()
    me_response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert me_response.status_code == 200
    store.create_intake(
        "athlete-1",
        _build_request(
            {
                "fight_date": "2099-08-20",
                "key_goals": ["power", "conditioning", "fight_sharpness", "volume"],
                "weak_areas": ["defense", "gas_tank", "timing", "footwork"],
            }
        ),
    )

    response = client.post(
        "/api/admin/athletes/athlete-1/plans/generate-from-latest-intake",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This camp allows 7 total focus picks. Remove 1 goal or weak-area selection before generating."


def test_admin_generation_from_latest_intake_rejects_invalid_saved_payload():
    client, store, _ = _build_client()
    me_response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert me_response.status_code == 200

    invalid_payload = _build_request().model_dump(mode="json")
    invalid_payload["athlete"] = "not-an-object"
    store.intakes.setdefault("athlete-1", []).append(
        {
            "id": "intake_invalid_payload",
            "athlete_id": "athlete-1",
            "fight_date": invalid_payload["fight_date"],
            "technical_style": [],
            "intake": invalid_payload,
            "created_at": "2026-04-01T00:00:00+00:00",
        }
    )

    response = client.post(
        "/api/admin/athletes/athlete-1/plans/generate-from-latest-intake",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "latest intake is invalid and cannot be used for generation"


def test_auth_is_required_for_draft_save():
    client, _, _ = _build_client()

    response = client.put(
        "/api/me",
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            onboarding_draft={"current_step": 5, "injuries": "left shoulder"},
        ).model_dump(mode="json"),
    )

    assert response.status_code == 401


def test_review_stage_draft_save_persists_step_and_form():
    client, store, _ = _build_client()
    request = _build_request()
    draft_payload = {
        **request.model_dump(mode="json"),
        "current_step": 5,
    }

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name=request.athlete.full_name,
            technical_style=request.athlete.technical_style,
            record=request.athlete.record,
            onboarding_draft=draft_payload,
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["onboarding_draft"]["current_step"] == 5
    assert profile["onboarding_draft"]["fight_date"] == request.fight_date
    assert store.profiles["athlete-1"]["onboarding_draft"]["current_step"] == 5


def test_review_stage_invalid_record_returns_422_not_network_error():
    client, _, _ = _build_client()

    for bad_record in ("5-", "-1", "5", "5-1-2-3", "abc"):
        response = client.put(
            "/api/me",
            headers={"Authorization": "Bearer athlete-token"},
            json={"record": bad_record},
        )
        assert response.status_code == 422, f"expected 422 for record={bad_record!r}"


def test_review_stage_empty_record_is_accepted_during_draft_save():
    client, _, _ = _build_client()

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            record="",
            onboarding_draft={"current_step": 5},
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200


def test_saved_onboarding_draft_round_trips_through_me_and_clears_after_generation():
    client, store, _ = _build_client()

    draft_response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            technical_style=["boxing"],
            onboarding_draft={"current_step": 4, "injuries": "heel soreness"},
        ).model_dump(mode="json"),
    )

    assert draft_response.status_code == 200
    assert draft_response.json()["profile"]["onboarding_draft"]["current_step"] == 4

    me_response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert me_response.status_code == 200
    assert me_response.json()["profile"]["onboarding_draft"]["injuries"] == "heel soreness"

    generate_response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert generate_response.status_code == 202
    assert store.profiles["athlete-1"]["onboarding_draft"] is None
    refreshed_me = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert refreshed_me.json()["profile"]["onboarding_draft"] is None
    assert refreshed_me.json()["latest_intake"]["fight_date"] == "2026-04-18"


def test_me_route_defaults_profile_appearance_mode_to_dark():
    client, _, _ = _build_client()

    response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})

    assert response.status_code == 200
    assert response.json()["profile"]["appearance_mode"] == "dark"


def test_update_me_persists_profile_appearance_mode():
    client, store, _ = _build_client()

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            appearance_mode="light",
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["profile"]["appearance_mode"] == "light"
    assert store.profiles["athlete-1"]["appearance_mode"] == "light"
