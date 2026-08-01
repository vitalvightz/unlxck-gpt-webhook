from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from api.xp import XP_REWARD_AMOUNTS, claim_daily_login_reward, resolve_xp_calendar_date
from tests.support import FakeStore, _build_client


ATHLETE = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}


def test_reward_configuration_contains_every_planned_action():
    assert XP_REWARD_AMOUNTS == {
        "daily_login": 10,
        "training_logged": 25,
        "planned_session_completed": 50,
        "recommended_fighter_content_watched": 10,
        "full_training_week_completed": 100,
    }


def test_calendar_date_uses_account_timezone_and_falls_back_to_utc():
    instant = datetime(2026, 8, 1, 23, 30, tzinfo=timezone.utc)
    assert resolve_xp_calendar_date("America/New_York", now=instant).isoformat() == "2026-08-01"
    assert resolve_xp_calendar_date("Asia/Tokyo", now=instant).isoformat() == "2026-08-02"
    assert resolve_xp_calendar_date("Not/A_Real_Zone", now=instant).isoformat() == "2026-08-01"
    assert resolve_xp_calendar_date("", now=instant).isoformat() == "2026-08-01"


def test_daily_login_endpoint_awards_once_and_returns_account_scoped_state():
    client, store, _ = _build_client()

    first = client.post("/api/xp/daily-login", headers=ATHLETE)
    repeated = client.post("/api/xp/daily-login", headers=ATHLETE)

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert first.json()["awarded"] is True
    assert first.json()["previous_total_xp"] == 0
    assert first.json()["state"]["total_xp"] == 10
    assert first.json()["award"]["action"] == "daily_login"
    assert repeated.json()["awarded"] is False
    assert repeated.json()["award"] is None
    assert repeated.json()["state"]["total_xp"] == 10
    assert len(store.xp_awards["athlete-1"]) == 1
    assert "athlete_id" not in first.json()["award"]
    assert "idempotency_key" not in first.json()["award"]


def test_daily_login_next_account_day_awards_again():
    store = FakeStore()
    first = claim_daily_login_reward(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        now=datetime(2026, 8, 1, 23, 59, tzinfo=timezone.utc),
    )
    next_day = claim_daily_login_reward(
        store,
        athlete_id="athlete-1",
        athlete_timezone="UTC",
        now=datetime(2026, 8, 2, 0, 1, tzinfo=timezone.utc),
    )

    assert first["awarded"] is True
    assert next_day["awarded"] is True
    assert next_day["state"]["total_xp"] == 20
    assert next_day["state"]["last_daily_login_date"] == "2026-08-02"


def test_xp_is_isolated_by_authenticated_account():
    store = FakeStore()
    for athlete_id in ("athlete-1", "athlete-2"):
        claim_daily_login_reward(
            store,
            athlete_id=athlete_id,
            athlete_timezone="UTC",
            now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
        )

    assert store.xp_accounts["athlete-1"]["total_xp"] == 10
    assert store.xp_accounts["athlete-2"]["total_xp"] == 10
    assert store.xp_awards["athlete-1"][0]["athlete_id"] == "athlete-1"
    assert store.xp_awards["athlete-2"][0]["athlete_id"] == "athlete-2"


def test_duplicate_concurrent_awards_are_idempotent():
    store = FakeStore()

    def claim():
        return store.award_xp(
            "athlete-1",
            action="daily_login",
            idempotency_key="daily-login:2026-08-01",
            calendar_date="2026-08-01",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: claim(), range(16)))

    assert sum(result["awarded"] for result in results) == 1
    assert store.xp_accounts["athlete-1"]["total_xp"] == 10
    assert len(store.xp_awards["athlete-1"]) == 1


def test_future_actions_are_configured_and_server_idempotent():
    store = FakeStore()
    first = store.award_xp(
        "athlete-1",
        action="planned_session_completed",
        idempotency_key="planned-session:session-42",
    )
    duplicate = store.award_xp(
        "athlete-1",
        action="planned_session_completed",
        idempotency_key="planned-session:session-42",
    )

    assert first["state"]["total_xp"] == 50
    assert first["award"]["amount"] == 50
    assert duplicate["awarded"] is False
    assert duplicate["state"]["total_xp"] == 50


def test_xp_endpoint_requires_an_approved_athlete_account():
    client, _store, _ = _build_client()
    assert client.post("/api/xp/daily-login").status_code in (401, 403)
    assert client.post("/api/xp/daily-login", headers=ADMIN).status_code == 403
