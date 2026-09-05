"""Regressions for the two remaining declared-light-combat merge blockers."""

from fightcamp.combat_load_policy import (
    CalendarEvent,
    LoadClass,
    PlacementDirective,
    contact_load_profile,
    evaluate_candidate_at_position,
    role_load_profile,
)
from fightcamp.declared_combat_ownership import LIGHT_COMBAT_ROLE_KEY
from fightcamp.stage2_role_map import _build_weekly_role_map


TRAINING_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def test_downgraded_hard_sparring_technical_remains_strict():
    low_aerobic = role_load_profile(
        {
            "category": "conditioning",
            "role_key": "aerobic_support_day",
            "preferred_system": "aerobic",
            "allowed_on_recovery_day": True,
        }
    )
    assert low_aerobic is not None

    resolved_hard_day = contact_load_profile(
        {
            "effective_load": "technical",
            "status": "convert_to_technical_suggested",
        }
    )
    assert resolved_hard_day is not None
    assert resolved_hard_day.load_class is LoadClass.TECHNICAL_CONTACT
    assert resolved_hard_day.allows_light_combat_stack is False

    strict = evaluate_candidate_at_position(
        low_aerobic,
        candidate_position=2,
        events=[CalendarEvent(2, resolved_hard_day, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert strict.directive is PlacementDirective.FORBID

    declared_light = role_load_profile({"role_key": LIGHT_COMBAT_ROLE_KEY})
    assert declared_light is not None
    assert declared_light.allows_light_combat_stack is True
    permissive = evaluate_candidate_at_position(
        low_aerobic,
        candidate_position=2,
        events=[CalendarEvent(2, declared_light, ("normal_week", 1))],
        candidate_scope=("normal_week", 1),
    )
    assert permissive.directive is not PlacementDirective.FORBID


def _progression(weeks: int) -> dict:
    return {
        "weeks": [
            {
                "week_index": idx + 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {
                    "strength": 1,
                    "conditioning": 2,
                    "recovery": 1,
                },
                "conditioning_sequence": ["aerobic", "aerobic"],
            }
            for idx in range(weeks)
        ]
    }


def _physical_training_days(week: dict) -> set[str]:
    days: set[str] = set()
    for role in week.get("session_roles", []) or []:
        day = str(role.get("scheduled_day_hint") or "").strip().lower()
        if not day or role.get("role_key") == "fight_day_protocol":
            continue
        if role.get("role_key") == "hard_sparring_day":
            days.add(day)
            continue
        profile = role_load_profile(role)
        if profile is None or profile.load_class in {LoadClass.OFF, LoadClass.ZERO_LOAD}:
            continue
        days.add(day)
    return days


def test_five_available_days_with_frequency_four_keeps_four_physical_days():
    athlete = {
        "sport_style": "mma",
        "sport": "mma",
        "training_days": list(TRAINING_DAYS),
        "training_frequency": 4,
        "hard_sparring_days": ["tuesday", "friday"],
        "support_work_days": ["wednesday"],
        "key_goals": ["speed", "strength"],
        "weaknesses": ["footwork", "power"],
        "fatigue_level": "low",
        "fight_date": "2027-07-21",
        "days_until_fight": 28,
    }
    role_map = _build_weekly_role_map(
        athlete,
        _progression(4),
        {"key": "conditioning_endurance"},
    )

    normal_weeks_with_light_combat = [
        week
        for week in role_map["weeks"]
        if any(
            role.get("role_key") == LIGHT_COMBAT_ROLE_KEY
            and str(role.get("scheduled_day_hint") or "").strip().lower() == "wednesday"
            for role in week.get("session_roles", []) or []
        )
    ]
    assert normal_weeks_with_light_combat
    for week in normal_weeks_with_light_combat:
        physical_days = _physical_training_days(week)
        assert len(physical_days) <= athlete["training_frequency"], physical_days
        assert "wednesday" in physical_days
