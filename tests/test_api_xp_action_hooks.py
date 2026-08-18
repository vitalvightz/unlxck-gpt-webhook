"""Route-level regression coverage for XP-bearing Today actions."""

from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"


def _seed_plan(store) -> None:
    store.plans[PLAN_ID] = {
        "id": PLAN_ID,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    store.set_active_plan_id("athlete-1", PLAN_ID)


def test_checkin_route_awards_first_and_daily_xp_once_for_repeated_same_day_saves():
    client, store, _ = _build_client()
    _seed_plan(store)
    payload = {
        "plan_id": PLAN_ID,
        "sleep": "good",
        "body": "normal",
        "pain": "none",
        "phase": "GPP",
    }

    first = client.post("/api/today/checkin", headers=ATHLETE, json=payload)
    repeated = client.post("/api/today/checkin", headers=ATHLETE, json=payload)

    assert first.status_code == 201
    assert repeated.status_code == 201
    awards = store.xp_awards.get("athlete-1", [])
    assert sorted((award["action"], award["amount"]) for award in awards) == [
        ("first_checkin_completed", 25),
        ("readiness_checkin_completed", 10),
    ]


def test_terminal_session_route_awards_training_and_planned_xp_once():
    client, store, _ = _build_client()
    _seed_plan(store)
    payload = {
        "plan_id": PLAN_ID,
        "session_id": "session-1",
        "status": "done",
        "session_rpe": 7,
        "pain_after": 1,
    }

    first = client.post("/api/today/session-completion", headers=ATHLETE, json=payload)
    repeated = client.post("/api/today/session-completion", headers=ATHLETE, json=payload)

    assert first.status_code == 201
    assert repeated.status_code == 201
    awards = [
        award
        for award in store.xp_awards.get("athlete-1", [])
        if award["action"] in {"training_logged", "planned_session_completed"}
    ]
    assert sorted((award["action"], award["amount"]) for award in awards) == [
        ("planned_session_completed", 50),
        ("training_logged", 25),
    ]
    assert len({award["idempotency_key"] for award in awards}) == 2
