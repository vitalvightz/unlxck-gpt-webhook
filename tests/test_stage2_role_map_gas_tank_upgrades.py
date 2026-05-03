from fightcamp.stage2_role_map import _upgrade_recovery_days_to_gas_tank, _upgrade_unused_days_to_gas_tank


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


def test_recovery_upgrade_does_not_default_on_without_explicit_signal():
    week = {"phase": "SPP", "calendar_days": [{"weekday": "thursday", "d_day": 27}]}
    session_roles = [
        {"session_index": 1, "category": "recovery", "role_key": "recovery_reset_day", "scheduled_day_hint": "thursday"}
    ]
    athlete_model = {"fatigue": "moderate", "cut_severity_bucket": "moderate"}

    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete_model)
    assert upgraded[0]["role_key"] == "recovery_reset_day"


def test_recovery_upgrade_stays_recovery_on_high_cut_plus_high_fatigue_without_explicit_signal():
    week = {"phase": "SPP", "calendar_days": [{"weekday": "thursday", "d_day": 27}]}
    session_roles = [
        {"session_index": 1, "category": "recovery", "role_key": "recovery_reset_day", "scheduled_day_hint": "thursday"}
    ]
    athlete_model = {
        "fatigue": "high",
        "cut_severity_bucket": "high",
        "readiness_flags": ["high_fatigue", "active_weight_cut"],
    }

    upgraded = _upgrade_recovery_days_to_gas_tank(week, session_roles, athlete_model)
    assert upgraded[0]["role_key"] == "recovery_reset_day"


def test_unused_day_priority_touch_precedes_gas_tank_when_both_signals_exist():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}, {"weekday": "saturday", "d_day": 25}],
        "intentionally_unused_days": [
            {"day": "thursday", "role": "off_day"},
            {"day": "saturday", "role": "off_day"},
        ],
    }
    athlete_model = {"key_goals": ["speed", "conditioning"]}

    upgraded = _upgrade_unused_days_to_gas_tank(week, [], athlete_model)
    assert upgraded[0]["role_key"] == "converted_priority_speed_touch_day"
    assert upgraded[1]["role_key"] == "converted_low_aerobic_gas_tank_day"


def test_unused_day_upgrade_can_force_one_low_load_speed_touch():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}],
    }
    athlete_model = {
        "fatigue": "high",
        "cut_severity_bucket": "high",
        "readiness_flags": ["high_fatigue", "active_weight_cut"],
        "key_goals": ["speed"],
    }

    upgraded = _upgrade_unused_days_to_gas_tank(week, [], athlete_model)
    assert upgraded[0]["role_key"] == "converted_priority_speed_touch_day"
    assert upgraded[0]["preferred_system"] == "alactic"
    assert upgraded[0]["athlete_facing_label"] == "Low-load speed touch"
    assert upgraded[0]["preferred_exercise_names"][0] == "Band-Resisted Snap-Step + Reset"


def test_speed_only_profile_gets_one_priority_touch_not_fake_second_gas_tank_touch():
    week = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "thursday", "d_day": 27}, {"weekday": "saturday", "d_day": 25}],
        "intentionally_unused_days": [{"day": "thursday", "role": "off_day"}, {"day": "saturday", "role": "off_day"}],
    }
    athlete_model = {"key_goals": ["speed"]}

    upgraded = _upgrade_unused_days_to_gas_tank(week, [], athlete_model)
    assert len(upgraded) == 1
    assert upgraded[0]["role_key"] == "converted_priority_speed_touch_day"
