"""Fields the web app read that the API never sent (found by web/lib/api-contract.ts)."""

from tests.support import _build_client, _build_request, finalized_result

ATHLETE = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}


def _ensure_athlete(client) -> None:
    assert client.get("/api/me", headers=ATHLETE).status_code == 200


def _held_plan(store, *, triage: bool = True) -> dict:
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-held",
        request=_build_request(),
        result=finalized_result(),
    )
    if triage:
        store.plans[plan["id"]]["why_log"] = {"injury_triage": {"mode": "medical_hold", "reasons": ["suspected fracture"]}}
    store.intakes.setdefault("athlete-1", []).append(
        {
            "id": "intake-held",
            "athlete_id": "athlete-1",
            "intake": {
                "injuries": "Left wrist - swollen after a fall",
                "guided_injury": {"area": "Left wrist", "injury_type": "bone_joint", "notes": "fell on it"},
                "guided_injuries": [{"area": "Right knee", "infection_signs": ["redness"]}],
            },
            "created_at": "2026-08-04T00:00:00+00:00",
        }
    )
    return plan


def test_admin_sees_the_intake_injuries_behind_a_triage_held_plan():
    client, store, _ = _build_client()
    _ensure_athlete(client)
    plan = _held_plan(store)

    response = client.get(f"/api/plans/{plan['id']}", headers=ADMIN)

    assert response.status_code == 200
    assert response.json()["admin_outputs"]["intake_injuries"] == {
        "injuries": "Left wrist - swollen after a fall",
        "guided_injuries": [
            {"area": "Left wrist", "injury_type": "bone_joint", "notes": "fell on it"},
            {"area": "Right knee", "infection_signs": ["redness"]},
        ],
    }


def test_intake_injuries_are_not_read_for_plans_triage_did_not_hold():
    client, store, _ = _build_client()
    _ensure_athlete(client)
    plan = _held_plan(store, triage=False)

    response = client.get(f"/api/plans/{plan['id']}", headers=ADMIN)

    assert response.json()["admin_outputs"]["intake_injuries"] is None


def test_athletes_never_receive_admin_intake_injuries():
    client, store, _ = _build_client()
    _ensure_athlete(client)
    plan = _held_plan(store, triage=False)

    response = client.get(f"/api/plans/{plan['id']}", headers=ATHLETE)

    assert response.status_code == 200
    assert response.json()["admin_outputs"] is None


def test_the_athletes_job_response_says_how_the_job_was_started():
    client, store, _ = _build_client(enable_in_process_generation=False)
    _ensure_athlete(client)
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="resume-1",
        source="admin_triage_resume",
        request_payload=_build_request().model_dump(mode="json"),
    )

    response = client.get(f"/api/generation-jobs/{job['id']}", headers=ATHLETE)

    assert response.status_code == 200
    assert response.json()["source"] == "admin_triage_resume"
