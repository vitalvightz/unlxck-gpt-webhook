from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_session_sequence,
    _classify_declared_hard_days_for_late_window,
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


def test_d9_midweek_submission_uses_only_surviving_declared_hard_day():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    roles = _late_fight_session_roles(9, athlete)
    hard_roles = [role for role in roles if role["role_key"] == "hard_sparring_day"]

    assert len(hard_roles) == 1
    assert hard_roles[0]["locked_day"] == "saturday"
    assert hard_roles[0]["countdown_label"] == "D-8"
    assert all(role["locked_day"] != "friday" for role in hard_roles)

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


def test_sequence_allocates_non_hard_roles_to_remaining_countdown_days():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    sequence = _build_late_fight_session_sequence(9, athlete)
    countdown_labels = [entry["countdown_label"] for entry in sequence if entry.get("countdown_label")]

    # All labels unique
    assert len(countdown_labels) == len(set(countdown_labels))

    # Hard sparring must stay locked to its declared D-8 slot regardless of position in sequence
    hard_spar = next(e for e in sequence if e["role_key"] == "hard_sparring_day")
    assert hard_spar["countdown_label"] == "D-8"
    assert hard_spar.get("declared_day_locked") is True


# ---------------------------------------------------------------------------
# Placement layer tests
# Tests for late_fight_placement.place_roles_in_countdown
# ---------------------------------------------------------------------------

from fightcamp.late_fight_placement import (
    place_roles_in_countdown,
    role_cost,
    countdown_offset,
)


def test_placement_locked_roles_keep_their_label():
    """Locked hard-sparring roles must never be moved."""
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["saturday"],
    )
    sequence = _build_late_fight_session_sequence(9, athlete)
    hard = next(e for e in sequence if e["role_key"] == "hard_sparring_day")
    assert hard["countdown_label"] == "D-8"
    assert hard.get("declared_day_locked") is True
    assert hard["placement_basis"] == "locked"


def test_placement_labels_are_unique():
    """No two roles in the sequence may share a countdown label."""
    for days in (13, 10, 8, 7, 5, 4, 3, 2):
        athlete = _athlete(days, hard_sparring_days=["tuesday", "thursday"])
        sequence = _build_late_fight_session_sequence(days, athlete)
        labels = [e["countdown_label"] for e in sequence if e.get("countdown_label")]
        assert len(labels) == len(set(labels)), f"Duplicate labels at D-{days}: {labels}"


def test_placement_d0_never_assigned():
    """D-0 is fight day and must never receive a role."""
    for days in (13, 9, 7, 5, 3, 2, 1):
        athlete = _athlete(days)
        sequence = _build_late_fight_session_sequence(days, athlete)
        labels = [e.get("countdown_label") for e in sequence]
        assert "D-0" not in labels, f"D-0 was assigned at D-{days}"


def test_placement_high_cost_before_low_cost():
    """
    High-cost roles must be placed in earlier countdown slots (higher D-offset)
    than low-cost freshness/recovery roles.
    """
    athlete = _athlete(
        10,
        plan_creation_weekday="monday",
        hard_sparring_days=["thursday"],
        fatigue="low",
        fatigue_level="low",
        readiness_flags=[],
    )
    sequence = _build_late_fight_session_sequence(10, athlete)

    high_offsets = [
        countdown_offset(e["countdown_label"])
        for e in sequence
        if e.get("placement_basis") in {"high", "locked"}
        and e.get("countdown_label")
    ]
    low_offsets = [
        countdown_offset(e["countdown_label"])
        for e in sequence
        if e.get("placement_basis") == "low"
        and e.get("countdown_label")
    ]

    if high_offsets and low_offsets:
        min_high = min(high_offsets)
        max_low = max(low_offsets)
        assert min_high > max_low, (
            f"High-cost role placed at D-{min_high} but low-cost role at D-{max_low} "
            f"— high-cost should always be earlier (higher D-offset)"
        )


def test_placement_sequence_sorted_earliest_first():
    """Sequence must be ordered earliest-first (highest D-offset first)."""
    for days in (13, 9, 7, 5, 3):
        athlete = _athlete(days, hard_sparring_days=["tuesday", "thursday"])
        sequence = _build_late_fight_session_sequence(days, athlete)
        offsets = [
            countdown_offset(e["countdown_label"])
            for e in sequence
            if e.get("countdown_label")
        ]
        assert offsets == sorted(offsets, reverse=True), (
            f"Sequence not sorted earliest-first at D-{days}: {offsets}"
        )


def test_placement_no_consecutive_active_days_when_avoidable():
    """
    When the window is wide enough, placement must leave at least 1 day gap
    between consecutive active sessions.
    """
    # D-13: 6 available slots before D-0, plenty of room for spacing
    athlete = _athlete(
        13,
        plan_creation_weekday="monday",
        hard_sparring_days=["tuesday", "thursday"],
        fatigue="low",
        fatigue_level="low",
        readiness_flags=[],
    )
    sequence = _build_late_fight_session_sequence(13, athlete)
    offsets = sorted(
        [countdown_offset(e["countdown_label"]) for e in sequence if e.get("countdown_label")],
        reverse=True,
    )
    consecutive_pairs = [
        (offsets[i], offsets[i + 1])
        for i in range(len(offsets) - 1)
        if abs(offsets[i] - offsets[i + 1]) < 2
    ]
    assert not consecutive_pairs, (
        f"Consecutive active days found at D-13 when spacing was possible: {consecutive_pairs}"
    )


def test_placement_freshness_role_in_later_half():
    """Freshness / recovery roles must land in the later half of the window."""
    athlete = _athlete(
        10,
        plan_creation_weekday="monday",
        hard_sparring_days=["thursday"],
        fatigue="low",
        fatigue_level="low",
        readiness_flags=[],
    )
    sequence = _build_late_fight_session_sequence(10, athlete)

    all_offsets = [countdown_offset(e["countdown_label"]) for e in sequence if e.get("countdown_label")]
    if not all_offsets:
        return

    midpoint = sum(all_offsets) / len(all_offsets)

    freshness = [
        e for e in sequence
        if e.get("role_key") == "fight_week_freshness_day" and e.get("countdown_label")
    ]
    for entry in freshness:
        off = countdown_offset(entry["countdown_label"]) or 0
        assert off <= midpoint, (
            f"Freshness role placed at D-{off} but midpoint is D-{midpoint:.1f} "
            f"— freshness should be in the later (lower D-offset) half"
        )


def test_role_cost_classifies_correctly():
    """role_cost() must return correct bucket for known anchor types."""
    assert role_cost({"anchor": "highest_neural_day"}) == "high"
    assert role_cost({"anchor": "highest_glycolytic_day"}) == "high"
    assert role_cost({"anchor": "support_day"}) == "medium"
    assert role_cost({"anchor": "lowest_load_day"}) == "low"
    assert role_cost({"anchor": "unknown_anchor"}) == "medium"   # safe default
    assert role_cost({}) == "medium"                              # missing anchor
