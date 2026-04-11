from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_session_sequence,
    _classify_declared_hard_days_for_late_window,
    _late_fight_session_roles,
    _split_declared_hard_day_instances,
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
        for role in _late_fight_session_roles(
            7,
            _athlete(7, plan_creation_weekday="monday", hard_sparring_days=["monday", "thursday"]),
        )
    ]

    assert role_keys[0] == "hard_sparring_day"
    assert role_keys[-1] == "fight_week_freshness_day"
    assert "declared_hard_day_technical_touch" in role_keys
    assert "neural_primer_day" in role_keys


def test_d9_midweek_submission_uses_only_surviving_declared_hard_day():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    roles = _late_fight_session_roles(9, athlete)
    hard_roles = [role for role in roles if role["role_key"] == "hard_sparring_day"]

    downgraded = [role for role in roles if role["role_key"] == "declared_hard_day_technical_touch"]

    assert len(hard_roles) == 1
    assert hard_roles[0]["locked_day"] == "saturday"
    assert hard_roles[0]["countdown_label"] == "D-8"
    assert all(role["locked_day"] != "friday" for role in hard_roles)
    assert [(role["locked_day"], role["countdown_label"]) for role in downgraded] == [
        ("tuesday", "D-5"),
        ("thursday", "D-3"),
        ("saturday", "D-1"),
    ]

    classified = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday="friday",
        days_until_fight=9,
        declared_weekdays=["tuesday", "thursday", "saturday"],
    )
    assert [(entry["weekday"], entry["status"], entry["countdown_label"]) for entry in classified] == [
        ("saturday", "hard_allowed", "D-8"),
        ("tuesday", "downgrade", "D-5"),
        ("thursday", "downgrade", "D-3"),
        ("saturday", "downgrade", "D-1"),
    ]


def test_countdown_classification_keeps_repeated_declared_occurrences():
    classified = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday="friday",
        days_until_fight=13,
        declared_weekdays=["tuesday", "thursday", "saturday"],
    )

    saturday_occurrences = [entry for entry in classified if entry["weekday"] == "saturday"]
    assert len(saturday_occurrences) == 2
    assert saturday_occurrences[0]["status"] == "hard_allowed"
    assert saturday_occurrences[1]["status"] == "downgrade"


def test_d11_spacing_prefers_first_and_last_surviving_declared_days():
    athlete = _athlete(
        11,
        plan_creation_weekday="monday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    hard_roles = [role for role in _late_fight_session_roles(11, athlete) if role["role_key"] == "hard_sparring_day"]

    assert [role["locked_day"] for role in hard_roles] == ["tuesday", "thursday"]
    assert {role["locked_day"] for role in hard_roles}.issubset({"tuesday", "thursday", "saturday"})
    assert abs(hard_roles[0]["countdown_offset"] - hard_roles[1]["countdown_offset"]) > 1


def test_d7_caps_to_one_hard_day_and_keeps_declared_lock():
    athlete = _athlete(
        7,
        plan_creation_weekday="monday",
        hard_sparring_days=["monday", "thursday", "saturday"],
    )
    hard_roles = [role for role in _late_fight_session_roles(7, athlete) if role["role_key"] == "hard_sparring_day"]

    assert len(hard_roles) == 1
    assert hard_roles[0]["locked_day"] in {"monday", "thursday", "saturday"}
    assert hard_roles[0]["declared_day_locked"] is True
    downgraded = [role for role in _late_fight_session_roles(7, athlete) if role["role_key"] == "declared_hard_day_technical_touch"]
    assert downgraded
    assert all(role["declared_day_locked"] is True for role in downgraded)


def test_d6_and_below_have_no_true_hard_sparring_roles():
    athlete = _athlete(
        6,
        plan_creation_weekday="monday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    roles = _late_fight_session_roles(6, athlete)

    assert all(role["role_key"] != "hard_sparring_day" for role in roles)
    classified = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday="monday",
        days_until_fight=6,
        declared_weekdays=["tuesday", "thursday", "saturday"],
    )
    assert classified
    assert all(entry["status"] == "downgrade" for entry in classified)
    downgraded_roles = [role for role in roles if role["role_key"] == "declared_hard_day_technical_touch"]
    assert [(role["locked_day"], role["countdown_label"]) for role in downgraded_roles] == [
        ("tuesday", "D-5"),
        ("thursday", "D-3"),
        ("saturday", "D-1"),
    ]


def test_sequence_allocates_non_hard_roles_to_remaining_countdown_days():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    sequence = _build_late_fight_session_sequence(9, athlete)
    countdown_labels = [entry["countdown_label"] for entry in sequence if entry.get("countdown_label")]
    role_by_key = {entry["role_key"]: entry for entry in sequence}

    assert len(countdown_labels) == len(set(countdown_labels))
    assert role_by_key["hard_sparring_day"]["countdown_label"] == "D-8"
    technical = [entry for entry in sequence if entry["role_key"] == "declared_hard_day_technical_touch"]
    assert any(entry["countdown_label"] == "D-5" and entry["real_weekday"] == "tuesday" for entry in technical)


def test_split_declared_hard_day_instances_returns_surviving_and_downgraded():
    classified = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday="friday",
        days_until_fight=9,
        declared_weekdays=["tuesday", "thursday", "saturday"],
    )

    surviving, downgraded = _split_declared_hard_day_instances(classified)

    assert [(entry["weekday"], entry["countdown_label"]) for entry in surviving] == [("saturday", "D-8")]
    assert [(entry["weekday"], entry["countdown_label"]) for entry in downgraded] == [
        ("tuesday", "D-5"),
        ("thursday", "D-3"),
        ("saturday", "D-1"),
    ]


def test_d8_saturday_generation_preserves_downgraded_declared_days_and_avoids_two_role_collapse():
    athlete = _athlete(
        8,
        plan_creation_weekday="saturday",
        hard_sparring_days=["monday", "wednesday", "friday"],
        readiness_flags=["injury_management"],
        fatigue="moderate",
        fatigue_level="moderate",
    )

    roles = _late_fight_session_roles(8, athlete)
    hard_roles = [role for role in roles if role["role_key"] == "hard_sparring_day"]
    downgraded_roles = [role for role in roles if role["role_key"] == "declared_hard_day_technical_touch"]

    assert not hard_roles
    assert [(role["locked_day"], role["countdown_label"]) for role in downgraded_roles] == [
        ("monday", "D-6"),
        ("wednesday", "D-4"),
        ("friday", "D-2"),
    ]
    assert all(role["declared_day_locked"] is True for role in downgraded_roles)
    assert len(roles) > 2


def test_d6_to_d0_keeps_d0_protocol_and_preserves_downgraded_declared_touches_when_applicable():
    transition_roles = _late_fight_session_roles(
        6,
        _athlete(6, plan_creation_weekday="monday", hard_sparring_days=["tuesday", "thursday", "saturday"]),
    )
    session_roles = _late_fight_session_roles(
        4,
        _athlete(4, plan_creation_weekday="monday", hard_sparring_days=["tuesday", "wednesday", "friday"]),
    )
    day_before_roles = _late_fight_session_roles(
        1,
        _athlete(1, plan_creation_weekday="friday", hard_sparring_days=["friday"]),
    )
    fight_day_roles = _late_fight_session_roles(
        0,
        _athlete(0, plan_creation_weekday="friday", hard_sparring_days=["saturday"]),
    )

    assert all(role["role_key"] != "hard_sparring_day" for role in transition_roles + session_roles + day_before_roles)
    assert any(role["role_key"] == "declared_hard_day_technical_touch" for role in transition_roles)
    assert any(role["role_key"] == "declared_hard_day_technical_touch" for role in session_roles)
    assert any(role["role_key"] == "declared_hard_day_technical_touch" for role in day_before_roles)
    assert fight_day_roles == []
