from fightcamp.stage2_payload_open_ongoing import (
    _uses_open_ongoing_payload,
    build_open_ongoing_payload,
)


def test_open_ongoing_route_when_no_fight_date():
    athlete = {"sport": "boxing", "days_until_fight": None, "fight_date": None, "next_fight_date": None}
    assert _uses_open_ongoing_payload(athlete) is True
    payload = build_open_ongoing_payload(athlete_model=athlete)
    assert payload["payload_mode"] == "open_ongoing_payload"
    assert payload["render_mode"] == "open_ongoing_system"
    assert isinstance(payload.get("open_plan_spec"), dict)


def test_open_ongoing_spec_required_sections_and_banned_terms():
    payload = build_open_ongoing_payload(athlete_model={"days_until_fight": None})
    spec = payload["open_plan_spec"]
    required = [
        "Immediate Coach Summary",
        "Current Training Rules",
        "Weekly Rhythm",
        "Session Cards",
        "4-Week Development Block",
        "Progression Rules",
        "Priority Hierarchy",
        "Adjustment Rules",
        "Rehab / Red Flags",
        "4-Week Reassessment Gate",
    ]
    assert spec.get("structure") == required
    forbidden = set(spec.get("forbidden_terms") or [])
    for token in ("GPP", "SPP", "TAPER", "D-", "fight week", "fight-day", "countdown"):
        assert token in forbidden


def test_no_scheduled_fight_does_not_override_real_fight_date():
    athlete = {
        "no_scheduled_fight": True,
        "fight_date": "2026-06-01",
        "days_until_fight": 17,
    }
    assert _uses_open_ongoing_payload(athlete) is False


def test_numeric_string_days_until_fight_does_not_route_open():
    athlete = {
        "days_until_fight": "17",
        "fight_date": "",
        "next_fight_date": "",
    }
    assert _uses_open_ongoing_payload(athlete) is False
