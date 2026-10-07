"""A dated camp generated today usually starts tomorrow.

Its weekly template is keyed by weekday, so before the plan's first card day
today's weekday slot used to resolve as today's session. With an injury
clearance in place that empty slot was held, and Today showed an untitled
"No training load" session to skip instead of the plan's first day as next.
"""

from datetime import date, timedelta

from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _seed_plan_starting_tomorrow(store, training_day: str) -> None:
    today = date.fromisoformat(training_day)
    first, second = today + timedelta(days=1), today + timedelta(days=2)
    fight = first + timedelta(days=28)
    calendar_days = [
        {"d_day": 28 - offset, "weekday": WEEKDAYS[(first + timedelta(days=offset)).weekday()]}
        for offset in range(7)
    ]
    store.plans[PLAN_ID] = {
        "id": PLAN_ID,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Camp",
        "created_at": f"{training_day}T23:36:00+00:00",
        "fight_date": fight.isoformat(),
        # The weekly template has work on today's weekday (a week from now).
        "planning_brief": {"weekly_role_map": {"weeks": [{
            "week_index": 1,
            "calendar_days": calendar_days,
            "session_roles": [{
                "category": "strength",
                "role_key": "primary_strength_day",
                "scheduled_day_hint": WEEKDAYS[today.weekday()].capitalize(),
                "athlete_facing_label": "Strength",
            }],
            "countdown_range": [28, 22],
        }]}},
        "structured_plan": {"weeks": [{"week_index": 1, "days": [
            {
                "date": first.isoformat(),
                "today_card": {"headline": "Joint prep"},
                "sessions": [{
                    "session_id": "ses-joint-prep",
                    "title": "Joint Prep",
                    "session_type": "recovery",
                    "blocks": [{"block_id": "b1", "block_type": "cooldown_recovery", "display_name": "CARs"}],
                }],
            },
            {
                "date": second.isoformat(),
                "today_card": {"headline": "Strength"},
                "sessions": [{"session_id": "ses-strength", "title": "Strength", "session_type": "strength", "blocks": []}],
            },
        ]}]},
    }
    store.set_active_plan_id("athlete-1", PLAN_ID)


def _training_day(client) -> str:
    return client.get("/api/today", headers=AUTH).json()["today"]["training_day"]


def test_the_day_before_a_dated_plan_shows_its_first_day_as_next() -> None:
    client, store, _ = _build_client()
    training_day = _training_day(client)
    _seed_plan_starting_tomorrow(store, training_day)
    # A cleared, monitored injury puts a clearance hold on any session today.
    store.create_injury_flag("athlete-1", {
        "body_area": "Chest", "description": "Chest: strain.", "severity": "mild", "status": "monitoring",
        "body_region": "chest", "injury_type": "strain", "source": "intake", "plan_id": PLAN_ID,
        "clinician_clearance": {"level": "train_no_contact"},
    })

    view = client.get("/api/today", headers=AUTH).json()

    assert view["today"]["session_scope"] == "next"
    assert view["today"]["next_session"]["session_id"] == "ses-joint-prep"
    assert view["today"]["next_session"]["calendar_date"] == (
        date.fromisoformat(training_day) + timedelta(days=1)
    ).isoformat()
    assert view.get("live_prescription") is None
