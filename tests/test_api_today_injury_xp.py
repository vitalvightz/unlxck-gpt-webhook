"""Regression coverage for injury-update XP on the Today endpoint."""

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


def test_injury_checkin_awards_ten_xp_once_for_the_athlete_day():
    client, store, _ = _build_client()
    _seed_plan(store)

    first = client.post(
        "/api/today/injury-checkin",
        headers=ATHLETE,
        json={"injuries": [{"body_area": "left knee", "status": "ongoing"}]},
    )
    second = client.post(
        "/api/today/injury-checkin",
        headers=ATHLETE,
        json={"injuries": [{"body_area": "right wrist", "status": "ongoing"}]},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    awards = [
        award
        for award in store.xp_awards.get("athlete-1", [])
        if award["action"] == "injury_update_completed"
    ]
    assert len(awards) == 1
    award = awards[0]
    assert award["amount"] == 10
    assert award["calendar_date"]
    assert award["idempotency_key"] == (
        f"injury-update:athlete-1:{award['calendar_date']}"
    )
