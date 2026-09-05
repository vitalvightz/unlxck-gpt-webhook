from fightcamp.calendar_integrity import apply_final_calendar_integrity
from fightcamp.declared_combat_ownership import build_declared_light_combat_role


def test_final_governor_never_moves_declared_light_combat_when_low_load_is_first():
    low_aerobic = {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "aerobic_support_day",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "Wednesday",
        "stress_class": "support",
        "cost_class": "low",
        "meaningful_stress": False,
    }
    light_combat = build_declared_light_combat_role(
        "Wednesday",
        session_index=2,
        scheduled_countdown_label="D-22",
    )
    week = {
        "week_index": 1,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "Monday", "d_day": 24},
            {"weekday": "Tuesday", "d_day": 23},
            {"weekday": "Wednesday", "d_day": 22},
            {"weekday": "Thursday", "d_day": 21},
            {"weekday": "Friday", "d_day": 20},
        ],
        "declared_training_days": [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
        ],
        # Deliberately put low-load S&C before the coach-owned contact role. This
        # reproduces the governor evaluation order that previously made the light
        # combat candidate look forbidden against an already-physical day.
        "session_roles": [low_aerobic, light_combat],
        "hard_sparring_plan": [],
        "suppressed_roles": [],
        "session_count_summary": {
            "reduced_from_planned": False,
            "reduction_reasons": [],
        },
    }
    weekly = {"weeks": [week]}

    apply_final_calendar_integrity(weekly)

    assert light_combat in week["session_roles"]
    assert light_combat["scheduled_day_hint"] == "wednesday"
    assert "calendar_integrity_relocation" not in light_combat
    assert low_aerobic in week["session_roles"]
    assert low_aerobic["scheduled_day_hint"] == "Wednesday"
    assert weekly["calendar_integrity"]["suppressed_roles"] == 0
    assert weekly["calendar_integrity"]["relocated_roles"] == 0
    assert weekly["calendar_integrity"]["unresolved_forbidden"] == 0
