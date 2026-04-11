from fightcamp.stage2_payload_late_fight import _build_late_fight_session_sequence


_BASE = {
    "full_name": "Spacing Athlete",
    "sport": "boxing",
    "status": "amateur",
    "rounds_format": "3x3",
    "camp_length_weeks": 6,
    "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
    "technical_skill_days": ["friday"],
    "fatigue": "low",
    "fatigue_level": "low",
    "weight_cut_risk": False,
    "weight_cut_pct": 0.0,
    "readiness_flags": [],
    "injuries": [],
}


def _athlete(days_until_fight, **overrides):
    athlete = dict(_BASE)
    athlete["days_until_fight"] = days_until_fight
    athlete.update(overrides)
    return athlete


def _offset(label: str) -> int:
    return int(label.replace("D-", ""))


def test_sparse_d10_window_uses_spaced_days_not_earliest_consecutive_fill():
    athlete = _athlete(
        10,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday"],
    )

    sequence = _build_late_fight_session_sequence(10, athlete)
    labels = [entry["countdown_label"] for entry in sequence]
    offsets = sorted((_offset(label) for label in labels), reverse=True)

    assert labels != ["D-10", "D-9", "D-8", "D-7"]
    assert any((offsets[idx] - offsets[idx + 1]) >= 2 for idx in range(len(offsets) - 1))
    assert not any(
        offsets[idx] - offsets[idx + 1] == 1 and offsets[idx + 1] - offsets[idx + 2] == 1
        for idx in range(len(offsets) - 2)
    )


def test_d8_saturday_generation_keeps_downgraded_locks_and_places_other_roles_around_them():
    athlete = _athlete(
        8,
        plan_creation_weekday="saturday",
        hard_sparring_days=["monday", "wednesday", "friday"],
        readiness_flags=["injury_management"],
        fatigue="moderate",
        fatigue_level="moderate",
    )

    sequence = _build_late_fight_session_sequence(8, athlete)
    downgraded = [entry for entry in sequence if entry["role_key"] == "declared_hard_day_technical_touch"]

    assert [(entry["locked_day"], entry["countdown_label"]) for entry in downgraded] == [
        ("monday", "D-6"),
        ("wednesday", "D-4"),
        ("friday", "D-2"),
    ]
    role_keys = [entry["role_key"] for entry in sequence]
    assert "strength_touch_day" in role_keys
    assert "fight_week_freshness_day" in role_keys
    assert len(role_keys) == len(set((entry["role_key"], entry["countdown_label"]) for entry in sequence))


def test_locked_countdown_labels_are_never_moved_by_spacing_allocator():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )

    sequence = _build_late_fight_session_sequence(9, athlete)
    hard = next(entry for entry in sequence if entry["role_key"] == "hard_sparring_day")
    downgraded = [entry for entry in sequence if entry["role_key"] == "declared_hard_day_technical_touch"]

    assert hard["declared_day_locked"] is True
    assert hard["countdown_label"] == "D-8"
    assert [(entry["locked_day"], entry["countdown_label"]) for entry in downgraded] == [
        ("tuesday", "D-5"),
        ("thursday", "D-3"),
        ("saturday", "D-1"),
    ]


def test_two_high_cost_unlocked_roles_do_not_stack_consecutively_when_window_allows():
    athlete = _athlete(
        10,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday"],
    )

    sequence = _build_late_fight_session_sequence(10, athlete)
    by_role = {entry["role_key"]: _offset(entry["countdown_label"]) for entry in sequence}

    assert abs(by_role["strength_touch_day"] - by_role["light_fight_pace_touch_day"]) > 1


def test_freshness_is_placed_as_structural_gap_or_taper_not_first_available_slot():
    athlete = _athlete(
        10,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday"],
    )

    sequence = _build_late_fight_session_sequence(10, athlete)
    freshness = next(entry for entry in sequence if entry["role_key"] == "fight_week_freshness_day")
    strength = next(entry for entry in sequence if entry["role_key"] == "strength_touch_day")

    assert freshness["countdown_label"] != "D-9"
    assert _offset(freshness["countdown_label"]) <= 2 or abs(_offset(strength["countdown_label"]) - _offset(freshness["countdown_label"])) >= 2
