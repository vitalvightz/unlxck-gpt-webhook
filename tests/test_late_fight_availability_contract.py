from fightcamp.gap_fill_inserts import apply_gap_fill_inserts
from fightcamp.stage2_payload_late_fight import (
    _countdown_weekday_map,
    _late_fight_countdown_context,
    _visible_calendar_session_sequence,
    can_render_late_taper_day,
    ensure_declared_coach_combat_spine,
)


TRAINING_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _late_role(offset: int) -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": "strength_touch_day",
        "scheduled_day_hint": "friday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _athlete() -> dict:
    return {
        "sport": "boxing",
        "days_until_fight": 14,
        "plan_creation_weekday": "friday",
        "training_days": TRAINING_DAYS,
        "hard_sparring_days": [],
        "support_work_days": ["Wednesday"],
        "fatigue": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": ["gas_tank"],
        "key_goals": ["conditioning"],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }


def test_fight_week_app_work_still_respects_declared_availability():
    assert not can_render_late_taper_day(
        countdown_offset=5,
        weekday="sunday",
        training_days=TRAINING_DAYS,
    )


def test_fight_day_remains_legal_outside_normal_training_availability():
    assert can_render_late_taper_day(
        countdown_offset=0,
        weekday="saturday",
        training_days=TRAINING_DAYS,
    )


def test_countdown_context_does_not_remap_weekdays_to_nearest_available_day():
    context = _late_fight_countdown_context(14, _athlete())

    raw_map = context["raw_countdown_weekday_map"]
    resolved_map = context["countdown_weekday_map"]

    assert raw_map["D-12"] == "sunday"
    assert "D-12" not in resolved_map
    assert raw_map["D-9"] == "wednesday"
    assert resolved_map["D-9"] == "wednesday"


def test_gap_fill_does_not_manufacture_unavailable_weekend_sessions():
    athlete = _athlete()
    sequence = apply_gap_fill_inserts([_late_role(14), _late_role(8)], athlete)
    countdown_map = _countdown_weekday_map("friday", 14)
    available = {day.lower() for day in TRAINING_DAYS}

    for role in sequence:
        if role.get("category") != "support_insert":
            continue
        offset = int(role["countdown_offset"])
        assert countdown_map[f"D-{offset}"] in available


def test_declared_light_combat_days_survive_as_coach_owned_calendar_context():
    athlete = _athlete()
    countdown_map = _countdown_weekday_map("friday", 14)
    spine = ensure_declared_coach_combat_spine([], athlete, countdown_map)
    visible = _visible_calendar_session_sequence(spine)

    light_combat = [
        role
        for role in visible
        if role.get("coach_owned") is True
        and role.get("role_key") == "technical_touch_day"
    ]
    assert {int(role["countdown_offset"]) for role in light_combat} == {9, 2}
    assert all(role["scheduled_day_hint"] == "wednesday" for role in light_combat)
    assert all(role["athlete_facing_label"] == "Light Combat / Technical" for role in light_combat)
