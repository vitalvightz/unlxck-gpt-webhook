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


def test_open_plan_carries_weekly_tactical_watch_rotation():
    payload = build_open_ongoing_payload(
        athlete_model={
            "sport": "boxing",
            "fighting_style": "counter striker",
            "days_until_fight": None,
        }
    )
    watch_spec = payload["open_plan_spec"]["tactical_watch"]
    assert watch_spec["label"] == "Tactical Focus"
    assert watch_spec["placement"] == "session_cards"
    assert watch_spec["zero_physical_load"] is True

    rotation = watch_spec["weekly_rotation"]
    assert [entry["week"] for entry in rotation] == [1, 2, 3, 4]
    # One distinct watch per week of the renewable block.
    assert len({entry["tactical_watch_key"] for entry in rotation}) == 4
    for entry in rotation:
        assert entry["zero_physical_load"] is True
        assert entry["duration_min"] > 0
        assert entry["display_text"].startswith("Why: ")
        assert entry["name"] in entry["display_text"]
        assert entry["tactical_watch"]["instructions"]


def test_open_plan_tactical_watch_hides_phase_and_camp_vocabulary():
    payload = build_open_ongoing_payload(
        athlete_model={"sport": "mma", "fighting_style": "pressure fighter"}
    )
    spec = payload["open_plan_spec"]
    forbidden = [term.lower() for term in spec["forbidden_terms"]]
    for entry in spec["tactical_watch"]["weekly_rotation"]:
        visible = entry["display_text"].lower()
        assert "camp" not in visible
        for term in forbidden:
            assert term not in visible
        block = entry["tactical_watch"]
        # Selection internals never travel with an athlete-facing open-plan card.
        for internal in ("key", "style", "phase", "sports", "fallback_reason"):
            assert internal not in block
        assert "context" not in block["mindset"]


def test_open_plan_render_rules_cover_tactical_watch():
    rules = " ".join(
        build_open_ongoing_payload(athlete_model={})["open_plan_spec"]["render_rules"]
    )
    assert "Week 1 Tactical Watch" in rules
    assert "zero physical load" in rules.lower()
