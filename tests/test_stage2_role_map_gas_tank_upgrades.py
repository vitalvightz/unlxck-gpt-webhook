from fightcamp.stage2_role_map import _upgrade_recovery_days_to_gas_tank


def test_recovery_upgrade_adds_gas_tank_preferences_and_label():
    week = {
        "phase": "GPP",
        "calendar_days": [{"weekday": "tuesday", "d_day": 36}],
    }
    session_roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "recovery_reset_day",
            "scheduled_day_hint": "tuesday",
        }
    ]
    athlete_model = {
        "key_goals": ["conditioning"],
        "weaknesses": ["gas_tank"],
    }

    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete_model)
    assert upgraded[0]["category"] == "conditioning"
    assert upgraded[0]["role_key"] == "recovery_aerobic_gas_tank_day"
    assert upgraded[0]["athlete_facing_label"] == "Low aerobic gas-tank flush"
    assert upgraded[0]["preferred_exercise_names"] == [
        "Assault Bike Easy Gas Tank Ride",
        "Rower Nasal Aerobic Base",
        "Nasal Shadowboxing Flow (Gas Tank)",
        "Nasal Walk with Boxing Posture",
    ]
