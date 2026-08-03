from support import _build_client


ATHLETE = {"Authorization": "Bearer athlete-token"}


def test_newer_held_plan_does_not_hide_an_older_ready_plan_from_activation_xp():
    client, store, _ = _build_client()
    assert client.get("/api/me", headers=ATHLETE).status_code == 200

    store.profiles["athlete-1"].update(
        {
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
        }
    )
    store.intakes["athlete-1"] = [
        {
            "id": "intake-1",
            "athlete_id": "athlete-1",
            "intake": {},
            "created_at": "2026-08-01T00:00:00Z",
        }
    ]
    store.plans["ready-plan"] = {
        "id": "ready-plan",
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Ready plan",
        "created_at": "2026-08-01T00:00:00Z",
    }
    store.plans["newer-held-plan"] = {
        "id": "newer-held-plan",
        "athlete_id": "athlete-1",
        "status": "held_for_review",
        "plan_name": "Held plan",
        "created_at": "2026-08-02T00:00:00Z",
    }

    response = client.get("/api/me", headers=ATHLETE)

    assert response.status_code == 200
    assert response.json()["latest_plan"]["id"] == "newer-held-plan"
    assert [award["action"] for award in store.xp_awards["athlete-1"]] == [
        "profile_completed",
        "first_intake_completed",
        "first_plan_ready",
    ]
