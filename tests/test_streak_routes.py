"""Streaks run end to end through the API against the in-memory store.

Streak persistence used to pick a backend at runtime (a store method, the raw
Supabase client, or ad hoc dicts on the store). FakeStore had none of the
methods, so every streak call through the API fell through to ``store.client``,
raised, and was swallowed by the route's error handling: these paths had no
route-level coverage at all. They now call AppStore methods that FakeStore
implements, so the real code runs here.
"""

import logging

from api.services.today_service import resolve_training_day
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


def test_app_activity_records_one_day_and_returns_the_login_streak():
    client, store, _ = _build_client()

    first = client.post("/api/xp/activity", headers=ATHLETE)
    repeated = client.post("/api/xp/activity", headers=ATHLETE)

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert first.json()["login"]["current"] == 1
    assert repeated.json()["login"] == first.json()["login"]
    assert len(store.daily_activity["athlete-1"]) == 1


def test_completing_todays_scheduled_session_advances_both_streaks(caplog):
    client, store, _ = _build_client()
    today = resolve_training_day(None)  # the fake athlete's (empty) timezone
    _seed_plan(store)
    store.plans[PLAN_ID]["structured_plan"] = {
        "weeks": [
            {
                "phase_label": "GPP",
                "days": [
                    {
                        "date": today,
                        "day_type": "hard",
                        "sessions": [
                            {
                                "session_id": "session-1",
                                "session_type": "strength",
                                "title": "Lower body strength",
                                "blocks": [{"name": "Back squat", "sets": 3, "reps": "5"}],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    with caplog.at_level(logging.ERROR):
        response = client.post(
            "/api/today/session-completion",
            headers=ATHLETE,
            json={"plan_id": PLAN_ID, "session_id": "session-1", "status": "done"},
        )

    assert response.status_code == 201
    assert not [record for record in caplog.records if "[streak]" in record.getMessage()]
    streak_row = store.get_athlete_streaks("athlete-1")
    assert streak_row["training_current"] == 1
    assert streak_row["adherence_current"] == 1


def test_an_unscheduled_completion_leaves_both_streaks_at_zero():
    client, store, _ = _build_client()
    _seed_plan(store)

    response = client.post(
        "/api/today/session-completion",
        headers=ATHLETE,
        json={"plan_id": PLAN_ID, "session_id": "session-1", "status": "done"},
    )

    assert response.status_code == 201
    streak_row = store.get_athlete_streaks("athlete-1")
    assert streak_row["training_current"] == 0
    assert streak_row["adherence_current"] == 0
