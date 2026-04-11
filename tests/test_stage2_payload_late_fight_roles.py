from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_plan_spec,
    _build_late_fight_session_sequence,
    _late_fight_session_roles,
    _select_spaced_hard_days,
)


_MINIMAL_ATHLETE = {
    "full_name": "Test Athlete",
    "sport": "boxing",
    "status": "amateur",
    "rounds_format": "3x3",
    "camp_length_weeks": 6,
    "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
    "hard_sparring_days": ["tuesday", "thursday"],
    "technical_skill_days": ["friday"],
    "fatigue": "moderate",
    "fatigue_level": "moderate",
    "weight_cut_risk": False,
    "weight_cut_pct": 0.0,
    "readiness_flags": [],
    "injuries": [],
    "plan_creation_weekday": "monday",
}


def _athlete(days_until_fight, **overrides):
    athlete = dict(_MINIMAL_ATHLETE)
    athlete["days_until_fight"] = days_until_fight
    athlete.update(overrides)
    return athlete


def test_select_spaced_hard_days_keeps_first_and_last_when_capped_to_two():
    assert _select_spaced_hard_days(["monday", "thursday", "saturday"], 2) == ["monday", "saturday"]


def test_pre_fight_compressed_caps_effective_hard_sparring_roles_at_two():
    roles = _late_fight_session_roles(
        8,
        _athlete(8, hard_sparring_days=["monday", "thursday", "saturday"]),
    )

    assert [role["role_key"] for role in roles].count("hard_sparring_day") == 2


def test_pre_fight_compressed_suppresses_standalone_glycolytic_with_two_hard_days():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(8, _athlete(8, hard_sparring_days=["monday", "thursday"]))
    ]

    assert role_keys.count("hard_sparring_day") == 2
    assert "light_fight_pace_touch_day" not in role_keys


def test_pre_fight_compressed_allows_strength_touch_and_light_fight_rhythm_with_one_hard_day():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(
            10,
            _athlete(10, hard_sparring_days=["thursday"], fatigue="low", fatigue_level="low", readiness_flags=[]),
        )
    ]

    assert role_keys.count("hard_sparring_day") == 1
    assert role_keys.count("strength_touch_day") == 1
    assert role_keys.count("light_fight_pace_touch_day") == 1
    assert role_keys.count("fight_week_freshness_day") == 1


def test_d7_role_list_remains_unchanged():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(7, _athlete(7, hard_sparring_days=["monday", "thursday"]))
    ]

    assert role_keys == ["hard_sparring_day", "neural_primer_day", "fight_week_freshness_day"]


def test_pre_fight_compressed_surfaces_downgraded_hard_day_as_technical_touch_suppression():
    spec = _build_late_fight_plan_spec(
        8,
        _athlete(8, hard_sparring_days=["monday", "thursday", "saturday"]),
    )

    suppressed_technical = [
        item for item in spec["suppressed_roles"]
        if item["role_key"] == "technical_touch_day"
    ]

    assert suppressed_technical
    assert suppressed_technical[0]["downgraded_from_role_key"] == "hard_sparring_day"


def test_d5_permission_policy_marks_declared_hard_day_as_technical_touch_only():
    spec = _build_late_fight_plan_spec(
        5,
        _athlete(5, hard_sparring_days=["thursday"], plan_creation_weekday="monday"),
    )

    actions = spec["permission_policy"]["declared_hard_day_actions"]

    assert actions == [
        {
            "day": "thursday",
            "outcome": "technical_touch_day",
            "locked": False,
            "downgraded_from_role_key": "hard_sparring_day",
        }
    ]


def test_freshness_lands_latest_when_multiple_legal_countdown_days_exist():
    sequence = _build_late_fight_session_sequence(
        5,
        _athlete(5, plan_creation_weekday="monday"),
    )

    freshness = next(role for role in sequence if role["role_key"] == "fight_week_freshness_day")
    sharpness = next(role for role in sequence if role["role_key"] == "alactic_sharpness_day")

    assert freshness["scheduled_countdown_label"] == "D-1"
    assert sharpness["scheduled_countdown_label"] == "D-5"


def test_session_sequence_exposes_allocator_metadata_fields():
    sequence = _build_late_fight_session_sequence(
        5,
        _athlete(5, plan_creation_weekday="monday"),
    )

    first = sequence[0]

    assert "scheduled_countdown_label" in first
    assert "placement_source" in first
    assert "day_assignment_reason" in first
