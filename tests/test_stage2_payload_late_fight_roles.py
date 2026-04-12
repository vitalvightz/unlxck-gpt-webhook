from fightcamp.stage2_payload_late_fight import (
    _build_late_fight_plan_spec,
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


def test_pre_fight_compressed_does_not_auto_collapse_to_two_visible_sessions_for_moderate_manageable_context():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
        fatigue="moderate",
        fatigue_level="moderate",
        readiness_flags=["injury_management", "weight_cut_active"],
        weekly_training_frequency=5,
        weight_cut_risk=True,
        weight_cut_pct=2.2,
    )

    role_keys = [role["role_key"] for role in _late_fight_session_roles(9, athlete)]
    assert role_keys.count("hard_sparring_day") == 1
    assert "light_fight_pace_touch_day" in role_keys

    spec = _build_late_fight_plan_spec(9, athlete)
    assert spec["visible_session_cap"] == 3
    assert set(spec["visible_session_roles"]) == {
        "strength_touch_day",
        "light_fight_pace_touch_day",
        "fight_week_freshness_day",
    }


def test_pre_fight_compressed_allows_two_visible_sessions_when_context_truly_requires_suppression():
    athlete = _athlete(
        9,
        hard_sparring_days=["thursday"],
        fatigue="high",
        fatigue_level="high",
        readiness_flags=["injury_management", "aggressive_weight_cut"],
        weekly_training_frequency=3,
        weight_cut_risk=True,
        weight_cut_pct=6.0,
    )

    role_keys = [role["role_key"] for role in _late_fight_session_roles(9, athlete)]
    assert "light_fight_pace_touch_day" not in role_keys
    spec = _build_late_fight_plan_spec(9, athlete)
    assert spec["visible_session_cap"] == 2


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


def test_placement_preserves_semantic_role_metadata_from_budget_layer():
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "hard_sparring_day",
            "preferred_pool": "declared_hard_sparring_days",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_glycolytic_day",
            "countdown_label": "D-8",
            "declared_day_locked": True,
            "scheduled_day_hint": "saturday",
            "locked_day": "saturday",
            "day_assignment_reason": "Declared hard day survives",
            "countdown_offset": 8,
            "downgraded_from_hard_sparring": True,
            "governance": {"late_fight_payload": True},
            "coach_notes": ["keep it technical"],
        }
    ]
    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=9,
        countdown_weekday_map={"D-8": "saturday"},
    )
    assert len(sequence) == 1
    entry = sequence[0]
    assert entry["declared_day_locked"] is True
    assert entry["scheduled_day_hint"] == "saturday"
    assert entry["locked_day"] == "saturday"
    assert entry["day_assignment_reason"] == "Declared hard day survives"
    assert entry["countdown_offset"] == 8
    assert entry["downgraded_from_hard_sparring"] is True
    assert entry["governance"] == {"late_fight_payload": True}
    assert entry["coach_notes"] == ["keep it technical"]


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


def test_placement_regression_same_day_is_not_default_for_non_high_cost_roles():
    """
    Regression proof: allocator must not default to D-N for every first role.
    A medium-cost only allocation should pick a cleaner taper target than
    blindly taking the earliest slot.
    """
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "technical_touch_day",
            "preferred_pool": "late_fight_pool",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "support_day",
        }
    ]

    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=6,
        countdown_weekday_map={},
    )
    assert len(sequence) == 1
    assert sequence[0]["countdown_label"] != "D-6"
    assert sequence[0]["countdown_label"] == "D-4"


def test_placement_regression_same_day_still_allowed_when_high_cost_best():
    """
    Regression proof: we did NOT add an anti-today rule.
    A single high-cost role can still legitimately land on D-N.
    """
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "alactic_sharpness_day",
            "preferred_pool": "late_fight_pool",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_neural_day",
        }
    ]

    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=5,
        countdown_weekday_map={},
    )
    assert len(sequence) == 1
    assert sequence[0]["countdown_label"] == "D-5"
    assert sequence[0]["placement_basis"] == "high"


def test_placement_regression_tomorrow_or_later_wins_when_spacing_is_cleaner():
    """
    Regression proof: even with high-cost work, the allocator should pick a
    tomorrow-or-later slot when spacing quality is better than a consecutive
    follow-up day.
    """
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "first_stress_day",
            "preferred_pool": "late_fight_pool",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_neural_day",
        },
        {
            "session_index": 2,
            "category": "conditioning",
            "role_key": "second_stress_day",
            "preferred_pool": "late_fight_pool",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_neural_day",
        },
    ]

    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=6,
        countdown_weekday_map={},
    )

    labels_by_role = {entry["role_key"]: entry["countdown_label"] for entry in sequence}
    assert labels_by_role["first_stress_day"] == "D-6"
    assert labels_by_role["second_stress_day"] == "D-4"


def test_placement_context_penalizes_hard_spar_collision_neighbors():
    roles = [
        {
            "session_index": 1,
            "category": "strength",
            "role_key": "strength_touch_day",
            "preferred_pool": "strength_slots",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_neural_day",
        }
    ]
    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=6,
        countdown_weekday_map={},
        placement_context={
            "declared_hard_spar_offsets": [5],  # D-5 collision owner day
            "today_offset": 6,
            "fatigue": "low",
            "readiness_flags": [],
        },
    )
    # Avoid D-6 (day before hard spar) and D-4 (day after hard spar) when cleaner D-3 exists.
    assert sequence[0]["countdown_label"] == "D-3"


def test_placement_context_readiness_penalizes_same_day_medium_role():
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "technical_touch_day",
            "preferred_pool": "conditioning_slots",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "support_day",
        }
    ]
    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=6,
        countdown_weekday_map={},
        placement_context={
            "declared_hard_spar_offsets": [],
            "today_offset": 6,
            "fatigue": "high",
            "readiness_flags": ["injury_watch"],
        },
    )
    assert sequence[0]["countdown_label"] != "D-6"


def test_placement_context_freshness_prefers_latest_clean_slot():
    roles = [
        {
            "session_index": 1,
            "category": "recovery",
            "role_key": "fight_week_freshness_day",
            "preferred_pool": "rehab_slots_or_recovery_only",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "lowest_load_day",
        }
    ]
    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=6,
        countdown_weekday_map={},
        placement_context={"today_offset": 6, "fatigue": "moderate", "readiness_flags": []},
    )
    assert sequence[0]["countdown_label"] == "D-2"


def test_placement_context_downgraded_technical_touch_holds_declared_offset():
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "light_fight_pace_touch_day",
            "preferred_pool": "declared_technical_skill_days_or_conditioning_slots",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "support_day",
            "downgraded_from_hard_sparring": True,
            "countdown_offset": 5,
        }
    ]
    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=6,
        countdown_weekday_map={},
        placement_context={
            "declared_hard_spar_offsets": [6],
            "declared_technical_offsets": [5],
            "today_offset": 6,
            "fatigue": "moderate",
            "readiness_flags": [],
        },
    )
    assert sequence[0]["countdown_label"] == "D-5"


def test_non_surviving_declared_hard_days_do_not_repel_neighbor_slots():
    """
    Regression: collision penalties should only use capped surviving hard-spar
    instances. A dropped declared hard day (for example D-11) must not repel
    adjacent placement like D-10.
    """
    roles = [
        {
            "session_index": 1,
            "category": "conditioning",
            "role_key": "hard_sparring_day",
            "preferred_pool": "declared_hard_sparring_days",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_glycolytic_day",
            "countdown_label": "D-13",
            "countdown_offset": 13,
            "declared_day_locked": True,
        },
        {
            "session_index": 2,
            "category": "conditioning",
            "role_key": "hard_sparring_day",
            "preferred_pool": "declared_hard_sparring_days",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_glycolytic_day",
            "countdown_label": "D-8",
            "countdown_offset": 8,
            "declared_day_locked": True,
        },
        {
            "session_index": 3,
            "category": "strength",
            "role_key": "strength_touch_day",
            "preferred_pool": "strength_slots",
            "selection_rule": "rule",
            "placement_rule": "rule",
            "anchor": "highest_neural_day",
        },
    ]
    sequence = place_roles_in_countdown(
        roles=roles,
        days_until_fight=13,
        countdown_weekday_map={},
        placement_context={
            "declared_hard_spar_offsets": [13, 8],  # surviving capped hard days only
            "today_offset": 13,
            "fatigue": "low",
            "readiness_flags": [],
        },
    )
    strength = next(entry for entry in sequence if entry["role_key"] == "strength_touch_day")
    assert strength["countdown_label"] == "D-10"


def test_role_cost_classifies_correctly():
    """role_cost() must return correct bucket for known anchor types."""
    assert role_cost({"anchor": "highest_neural_day"}) == "high"
    assert role_cost({"anchor": "highest_glycolytic_day"}) == "high"
    assert role_cost({"anchor": "support_day"}) == "medium"
    assert role_cost({"anchor": "lowest_load_day"}) == "low"
    assert role_cost({"anchor": "unknown_anchor"}) == "medium"   # safe default
    assert role_cost({}) == "medium"                              # missing anchor
