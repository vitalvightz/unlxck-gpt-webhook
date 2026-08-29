from fightcamp.stage2_payload_late_fight import (
    CANONICAL_HARD_SPARRING_NOTE,
    CANONICAL_TECHNICAL_ONLY_NOTE,
    _coach_owned_context_session_sequence,
    _build_late_fight_plan_spec,
    _build_late_fight_session_sequence,
    _build_late_fight_weekly_role_map,
    _countdown_weekday_map,
    _classify_declared_hard_days_for_late_window,
    _late_fight_active_role_count,
    _late_fight_best_assignment,
    _late_fight_session_roles,
    _late_fight_support_role_count,
    _planned_sessions_per_week,
    _select_spaced_hard_days,
    _space_bridge_countdown_roles,
    _visible_calendar_session_sequence,
    ensure_declared_coach_combat_spine,
    is_low_cost_coexistable_filler,
)


_MINIMAL_ATHLETE = {
    "full_name": "Test Athlete",
    "sport": "boxing",
    "status": "amateur",
    "rounds_format": "3x3",
    "camp_length_weeks": 6,
    "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
    "hard_sparring_days": ["tuesday", "thursday"],
        "support_work_days": ["friday"],
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


def test_pre_fight_compressed_converts_declared_hard_sparring_to_technical_only():
    roles = _late_fight_session_roles(
        8,
        _athlete(8, hard_sparring_days=["monday", "thursday", "saturday"]),
    )

    assert [role["role_key"] for role in roles].count("hard_sparring_day") == 0


def test_pre_fight_compressed_does_not_treat_declared_hard_days_as_effective_hard():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(8, _athlete(8, hard_sparring_days=["monday", "thursday"]))
    ]

    assert role_keys.count("hard_sparring_day") == 0
    assert "light_fight_pace_touch_day" in role_keys


def test_pre_fight_compressed_allows_strength_touch_and_light_fight_rhythm_with_one_hard_day():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(
            10,
            _athlete(10, hard_sparring_days=["thursday"], fatigue="low", fatigue_level="low", readiness_flags=[]),
        )
    ]

    assert role_keys.count("hard_sparring_day") == 0
    assert role_keys.count("strength_touch_day") == 1
    assert role_keys.count("light_fight_pace_touch_day") == 1
    assert role_keys.count("fight_week_freshness_day") == 1


def test_pre_fight_compressed_high_fatigue_flag_suppresses_light_fight_pace():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(
            10,
            _athlete(10, hard_sparring_days=["thursday"], fatigue="", fatigue_level="", readiness_flags=["high_fatigue"]),
        )
    ]

    assert role_keys.count("hard_sparring_day") == 0
    assert "light_fight_pace_touch_day" not in role_keys


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
    assert role_keys.count("hard_sparring_day") == 0
    assert "light_fight_pace_touch_day" in role_keys

    spec = _build_late_fight_plan_spec(9, athlete)
    assert spec["visible_session_cap"] == 3
    assert set(spec["visible_session_roles"]) == {
        "strength_touch_day",
        "alactic_sharpness_day",
        "fight_week_freshness_day",
    }


def test_pre_fight_compressed_suppresses_light_fight_pace_without_lowering_visible_cap():
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
    assert spec["visible_session_cap"] == 4


def test_planned_sessions_fallback_caps_day_availability_at_five_when_intent_missing():
    athlete = _athlete(
        10,
        training_days=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    )
    athlete.pop("weekly_training_frequency", None)
    athlete.pop("training_frequency", None)
    athlete.pop("weekly_sessions", None)
    assert _planned_sessions_per_week(athlete) == 5


def test_planned_sessions_uses_explicit_frequency_when_present():
    athlete = _athlete(10, training_days=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"])
    athlete["weekly_training_frequency"] = 3
    assert _planned_sessions_per_week(athlete) == 3


def test_d7_role_list_remains_unchanged():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(7, _athlete(7, hard_sparring_days=["monday", "thursday"]))
    ]

    assert role_keys == ["neural_primer_day", "alactic_sharpness_day", "fight_week_freshness_day"]


# NOTE: D-14..D-21 (the old "bridge" window) now use the normal camp planner,
# so the late-fight session-role allocator no longer produces roles there. The
# "last clean fight-pace touch at D-18" and "moderate cut keeps the D-18 pressure
# touch" behaviours are now expressed by the normal camp architecture + the
# scheduled-day countdown overlay, and are covered by the routing/real-calendar
# regression suites (see test_late_camp_architecture_cliff.py).


def test_d20_declared_friday_counts_as_final_hard_pressure_without_snc_stack():
    athlete = _athlete(
        20,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "friday"],
        fatigue="low",
        fatigue_level="low",
        readiness_flags=[],
    )
    role_map = _build_late_fight_weekly_role_map(20, athlete)
    bridge_week = role_map["weeks"][0]

    friday = next(entry for entry in bridge_week["hard_sparring_plan"] if entry["day"] == "friday")
    assert friday["d_day"] == 20
    assert friday["effective_load"] == "hard"
    assert friday["status"] == "hard_as_planned"
    assert "friday" in bridge_week["effective_hard_sparring_days"]

    same_day_app_roles = [
        role
        for role in bridge_week["session_roles"]
        if role.get("scheduled_day_hint") == "friday"
        and role.get("role_key") != "hard_sparring_day"
    ]
    assert same_day_app_roles == []


def test_bridge_d18_extreme_cut_blocks_light_fight_rhythm_touch():
    role_keys = [
        role["role_key"]
        for role in _late_fight_session_roles(
            18,
            _athlete(
                18,
                hard_sparring_days=[],
                fatigue="low",
                fatigue_level="low",
                weight_cut_risk=True,
                weight_cut_pct=6.0,
                readiness_flags=["aggressive_weight_cut"],
            ),
        )
    ]

    assert "light_fight_pace_touch_day" not in role_keys


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
    primer = next(role for role in sequence if role["role_key"] == "neural_primer_day")

    assert freshness["scheduled_countdown_label"] == "D-3"
    assert primer["scheduled_countdown_label"] == "D-1"


def test_session_sequence_exposes_allocator_metadata_fields():
    sequence = _build_late_fight_session_sequence(
        5,
        _athlete(5, plan_creation_weekday="monday"),
    )

    first = sequence[0]

    assert "scheduled_countdown_label" in first
    assert "placement_source" in first
    assert "day_assignment_reason" in first

def test_d9_midweek_submission_converts_all_declared_hard_days():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    roles = _late_fight_session_roles(9, athlete)
    hard_roles = [role for role in roles if role["role_key"] == "hard_sparring_day"]

    assert hard_roles == []

    classified = _classify_declared_hard_days_for_late_window(
        plan_creation_weekday="friday",
        days_until_fight=9,
        declared_weekdays=["tuesday", "thursday", "saturday"],
    )
    assert [(entry["weekday"], entry["status"], entry["countdown_label"]) for entry in classified] == [
        ("saturday", "downgrade", "D-8"),
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
    assert saturday_occurrences[0]["status"] == "downgrade"
    assert saturday_occurrences[1]["status"] == "downgrade"


def test_d11_declared_hard_days_do_not_survive_as_effective_hard():
    athlete = _athlete(
        11,
        plan_creation_weekday="monday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )
    hard_roles = [role for role in _late_fight_session_roles(11, athlete) if role["role_key"] == "hard_sparring_day"]

    assert hard_roles == []


def test_d7_converts_declared_hard_days_and_keeps_no_declared_lock():
    athlete = _athlete(
        7,
        plan_creation_weekday="monday",
        hard_sparring_days=["monday", "thursday", "saturday"],
    )
    hard_roles = [role for role in _late_fight_session_roles(7, athlete) if role["role_key"] == "hard_sparring_day"]

    assert hard_roles == []


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

    assert all(entry["role_key"] != "hard_sparring_day" for entry in sequence)


# ---------------------------------------------------------------------------
# Placement layer tests
# Tests for late_fight_placement.place_roles_in_countdown
# ---------------------------------------------------------------------------

from fightcamp.late_fight_placement import (  # noqa: E402
    place_roles_in_countdown,
    role_cost,
    countdown_offset,
)


def test_late_window_does_not_emit_locked_hard_sparring_roles():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["saturday"],
    )
    sequence = _build_late_fight_session_sequence(9, athlete)
    assert all(entry["role_key"] != "hard_sparring_day" for entry in sequence)


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
    role_by_offset = {
        countdown_offset(entry["countdown_label"]): entry["role_key"]
        for entry in sequence
        if entry.get("countdown_label")
    }
    consecutive_pairs = [
        (offsets[i], offsets[i + 1])
        for i in range(len(offsets) - 1)
        if abs(offsets[i] - offsets[i + 1]) < 2
        and not {
            role_by_offset.get(offsets[i]),
            role_by_offset.get(offsets[i + 1]),
        } == {"strength_touch_day", "hard_sparring_day"}
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


def test_low_cost_filler_can_share_locked_coach_combat_label():
    roles = [
        {
            "_candidate_id": 1,
            "role_key": "hard_sparring_day",
            "category": "sparring",
            "locked_day": "tuesday",
            "legal_countdown_labels": ["D-9"],
        },
        {
            "_candidate_id": 2,
            "role_key": "tactical_watch",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "legal_countdown_labels": ["D-9"],
        },
    ]
    assignment = _late_fight_best_assignment(
        roles,
        ["D-9"],
        {"D-9": "tuesday"},
        hard_weekdays={"tuesday"},
    )

    assert assignment is not None
    _, assigned = assignment
    assert is_low_cost_coexistable_filler(assigned[1]) is True
    assert [role["countdown_label"] for role in assigned] == ["D-9", "D-9"]


def test_low_cost_filler_can_share_technical_touch_label():
    roles = [
        {
            "_candidate_id": 1,
            "role_key": "technical_touch_day",
            "category": "technical",
            "stress_class": "support",
            "cost_class": "low",
            "legal_countdown_labels": ["D-9"],
        },
        {
            "_candidate_id": 2,
            "role_key": "tactical_watch",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "legal_countdown_labels": ["D-9"],
            "governance": {"meaningful_stress": False},
        },
    ]

    assignment = _late_fight_best_assignment(
        roles,
        ["D-9"],
        {"D-9": "tuesday"},
    )

    assert assignment is not None
    _, assigned = assignment
    assert is_low_cost_coexistable_filler(assigned[0]) is False
    assert is_low_cost_coexistable_filler(assigned[1]) is True
    assert [role["countdown_label"] for role in assigned] == ["D-9", "D-9"]


def test_multiple_low_cost_fillers_can_share_countdown_label():
    roles = [
        {
            "_candidate_id": 1,
            "role_key": "tactical_watch",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "legal_countdown_labels": ["D-9"],
            "governance": {"meaningful_stress": False},
        },
        {
            "_candidate_id": 2,
            "role_key": "tactical_cue_card",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "legal_countdown_labels": ["D-9"],
            "governance": {"meaningful_stress": False},
        },
    ]

    assignment = _late_fight_best_assignment(
        roles,
        ["D-9"],
        {"D-9": "tuesday"},
    )

    assert assignment is not None
    _, assigned = assignment
    assert all(is_low_cost_coexistable_filler(role) for role in assigned)
    assert [role["countdown_label"] for role in assigned] == ["D-9", "D-9"]


def test_stressor_cannot_share_locked_coach_combat_label():
    roles = [
        {
            "_candidate_id": 1,
            "role_key": "hard_sparring_day",
            "category": "sparring",
            "locked_day": "tuesday",
            "legal_countdown_labels": ["D-9"],
        },
        {
            "_candidate_id": 2,
            "role_key": "strength_touch_day",
            "category": "strength",
            "stress_class": "meaningful_stress",
            "cost_class": "medium",
            "legal_countdown_labels": ["D-9"],
        },
    ]

    assert _late_fight_best_assignment(
        roles,
        ["D-9"],
        {"D-9": "tuesday"},
        hard_weekdays={"tuesday"},
    ) is None


def test_low_cost_filler_does_not_consume_active_or_support_budget():
    roles = [
        {
            "role_key": "technical_touch_day",
            "category": "technical",
            "stress_class": "support",
            "cost_class": "low",
        },
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "governance": {"meaningful_stress": False},
        },
    ]

    assert _late_fight_active_role_count(roles) == 1
    assert _late_fight_support_role_count(roles) == 1


def test_composite_search_keeps_technical_session_when_filler_shares_label():
    roles = [
        {
            "role_key": "technical_touch_day",
            "category": "technical",
            "stress_class": "support",
            "cost_class": "low",
            "countdown_offset": 9,
            "countdown_label": "D-9",
            "scheduled_countdown_label": "D-9",
            "legal_countdown_labels": ["D-9"],
            "selection_priority": 90,
            "composite_segment_index": 1,
            "composite_segment_stage_key": "d8_to_d2",
        },
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "countdown_offset": 9,
            "countdown_label": "D-9",
            "scheduled_countdown_label": "D-9",
            "legal_countdown_labels": ["D-9"],
            "selection_priority": 10,
            "composite_segment_index": 1,
            "composite_segment_stage_key": "d8_to_d2",
            "governance": {"meaningful_stress": False},
        },
    ]

    sequence = _space_bridge_countdown_roles(
        roles,
        days_until_fight=13,
        athlete_model=_athlete(13, hard_sparring_days=[]),
    )

    roles_by_key = {role["role_key"]: role for role in sequence}
    assert {"technical_touch_day", "tactical_watch"} <= set(roles_by_key)
    assert roles_by_key["technical_touch_day"]["countdown_label"] == "D-9"
    assert roles_by_key["tactical_watch"]["countdown_label"] == "D-9"


def test_low_cost_filler_does_not_cause_meaningful_role_to_drop():
    roles = [
        {
            "role_key": "strength_touch_day",
            "category": "strength",
            "stress_class": "meaningful_stress",
            "cost_class": "medium",
            "countdown_offset": 9,
            "countdown_label": "D-9",
            "scheduled_countdown_label": "D-9",
            "legal_countdown_labels": ["D-9"],
            "selection_priority": 100,
            "composite_segment_index": 1,
            "composite_segment_stage_key": "d8_to_d2",
        },
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "stress_class": "support",
            "cost_class": "low",
            "countdown_offset": 9,
            "countdown_label": "D-9",
            "scheduled_countdown_label": "D-9",
            "legal_countdown_labels": ["D-9"],
            "selection_priority": 10,
            "composite_segment_index": 1,
            "composite_segment_stage_key": "d8_to_d2",
            "governance": {"meaningful_stress": False},
        },
    ]

    sequence = _space_bridge_countdown_roles(
        roles,
        days_until_fight=13,
        athlete_model=_athlete(13, hard_sparring_days=[]),
    )

    assert [role["role_key"] for role in sequence] == ["strength_touch_day", "tactical_watch"]
    assert {role["countdown_label"] for role in sequence} == {"D-9"}


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


def test_countdown_weekday_map_truth():
    # The countdown -> weekday map is pure calendar arithmetic used by both the
    # normal camp and late-fight paths; it must resolve each countdown offset to
    # its true weekday. (The D-14..D-21 session-sequence availability filtering
    # that used to accompany this now lives in the normal camp planner and is
    # covered by the real-calendar routing regression suite.)
    countdown_map = _countdown_weekday_map("saturday", 15)
    assert countdown_map["D-15"] == "saturday"
    assert countdown_map["D-7"] == "sunday"
    assert countdown_map["D-1"] == "saturday"
    assert countdown_map["D-0"] == "sunday"


def test_permission_policy_exposes_eligible_countdown_labels():
    athlete = _athlete(
        15,
        plan_creation_weekday="saturday",
        training_days=["tuesday", "wednesday", "thursday"],
    )
    spec = _build_late_fight_plan_spec(15, athlete)
    policy = spec["permission_policy"]

    assert "eligible_countdown_labels" in policy
    assert "D-15" not in policy["eligible_countdown_labels"]
    assert "D-14" not in policy["eligible_countdown_labels"]
    assert "D-12" in policy["eligible_countdown_labels"]
    assert "D-7" not in policy["eligible_countdown_labels"]
    assert "D-6" not in policy["eligible_countdown_labels"]


# NOTE: composite late-fight availability filtering for a D-14 start moved to
# the normal camp planner (D-14 now routes to camp). App-owned work never lands
# on an unavailable day or a declared coach-owned combat day — this invariant is
# exercised against the production calendar geometry (no-Saturday availability,
# Monday support, Thursday contact) in test_late_camp_architecture_cliff.py.


def test_bridge_mode_continuity_through_d1_does_not_place_on_d0_or_outside_label_set():
    athlete = _athlete(
        14,
        plan_creation_weekday="saturday",
        training_days=["tuesday", "wednesday", "thursday"],
        hard_sparring_days=[],
    )
    sequence = _build_late_fight_session_sequence(14, athlete)
    labels = [str(role.get("scheduled_countdown_label") or "") for role in sequence]
    assert all(label.startswith("D-") for label in labels)
    assert "D-0" not in labels
    assert all(1 <= int(label.split("-")[1]) <= 14 for label in labels)


def test_coach_owned_context_sequence_keeps_downgraded_declared_hard_day():
    sessions = [
        {
            "role_key": "technical_touch_day",
            "downgraded_from_role_key": "hard_sparring_day",
            "scheduled_day_hint": "monday",
            "countdown_offset": 5,
        },
        {
            "role_key": "neural_primer_day",
            "scheduled_day_hint": "tuesday",
            "countdown_offset": 4,
        },
    ]
    context = _coach_owned_context_session_sequence(sessions)
    assert len(context) == 1
    assert context[0]["role_key"] == "technical_touch_day"
    assert context[0]["downgraded_from_role_key"] == "hard_sparring_day"
    assert context[0]["athlete_facing_label"] == "Technical-only combat"
    # A technical-only (D-17+ ban) day must carry the technical note, never the
    # hard-sparring note — it must not tell the athlete to spar hard.
    assert context[0]["display_text"] == "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority."


def test_coach_owned_context_sequence_forces_default_hard_spar_label_and_note():
    sessions = [
        {
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "friday",
            "countdown_offset": 20,
        }
    ]
    context = _coach_owned_context_session_sequence(sessions)
    assert len(context) == 1
    assert context[0]["role_key"] == "hard_sparring_day"
    assert context[0]["athlete_facing_label"] == "Hard sparring — controlled hard contact"
    assert context[0]["display_text"] == "Your declared hard-sparring/contact session — no extra S&C. Keep freshness priority."


def test_coach_owned_context_sequence_downgraded_hard_spar_gets_ban_label():
    sessions = [
        {
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "friday",
            "countdown_offset": 6,
            "downgraded": True,
            "downgraded_to_role_key": "technical_touch_day",
        }
    ]
    context = _coach_owned_context_session_sequence(sessions)
    assert len(context) == 1
    assert context[0]["athlete_facing_label"] == "Technical-only combat"
    # Downgraded (D-17+ ban) day gets the technical note, never the hard-sparring note.
    assert context[0]["display_text"] == "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority."


def test_technical_only_context_never_carries_hard_sparring_note():
    # Regression: the technical-only (D-17+ ban) label and the hard-sparring label
    # must use distinct notes, so a technical-only card never tells the athlete to
    # perform their hard sparring/contact work.
    assert CANONICAL_HARD_SPARRING_NOTE != CANONICAL_TECHNICAL_ONLY_NOTE
    hard = [{"role_key": "hard_sparring_day", "scheduled_day_hint": "friday", "countdown_offset": 20}]
    technical = [
        {
            "role_key": "hard_sparring_day",
            "scheduled_day_hint": "friday",
            "countdown_offset": 6,
            "downgraded": True,
            "downgraded_to_role_key": "technical_touch_day",
        }
    ]
    hard_note = _coach_owned_context_session_sequence(hard)[0]["display_text"]
    technical_note = _coach_owned_context_session_sequence(technical)[0]["display_text"]

    assert hard_note == CANONICAL_HARD_SPARRING_NOTE
    assert technical_note == CANONICAL_TECHNICAL_ONLY_NOTE
    # The technical note only ever *negates* hard sparring ("no hard sparring"); it
    # never prescribes it the way the hard note does ("your declared hard-sparring...").
    assert "no hard sparring" in technical_note.lower()
    assert "your declared hard-sparring" not in technical_note.lower()


def test_declared_coach_combat_spine_keeps_tuesday_friday_thursday_fight_visible():
    athlete = _athlete(
        20,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "friday"],
    )

    spec = _build_late_fight_plan_spec(20, athlete)
    coach_roles = [
        role
        for role in spec["visible_session_sequence"]
        if role.get("role_key") == "hard_sparring_day"
    ]
    roles_by_label = {role["countdown_label"]: role for role in coach_roles}

    assert set(roles_by_label) >= {"D-20", "D-16", "D-13", "D-9", "D-6", "D-2"}
    assert roles_by_label["D-20"].get("downgraded") is not True
    for label in ["D-16", "D-13", "D-9", "D-6", "D-2"]:
        assert roles_by_label[label].get("downgraded") is True
        assert "technical-only combat" in roles_by_label[label].get("athlete_facing_label", "").lower()


def test_declared_coach_combat_spine_coexists_with_same_day_fillers():
    athlete = _athlete(
        20,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "friday"],
    )
    sequence = ensure_declared_coach_combat_spine(
        [
            {
                "role_key": "tactical_cue_card",
                "category": "support_insert",
                "stress_class": "support",
                "cost_class": "low",
                "scheduled_countdown_label": "D-13",
                "countdown_label": "D-13",
                "countdown_offset": 13,
                "scheduled_day_hint": "friday",
                "governance": {"meaningful_stress": False},
            },
            {
                "role_key": "neural_visualization",
                "category": "support_insert",
                "stress_class": "support",
                "cost_class": "low",
                "scheduled_countdown_label": "D-6",
                "countdown_label": "D-6",
                "countdown_offset": 6,
                "scheduled_day_hint": "friday",
                "governance": {"meaningful_stress": False},
            },
        ],
        athlete,
        _countdown_weekday_map("friday", 20),
    )
    visible = _visible_calendar_session_sequence(sequence)

    roles_by_label = {}
    for role in visible:
        roles_by_label.setdefault(role.get("countdown_label"), set()).add(role.get("role_key"))

    assert {"hard_sparring_day", "tactical_cue_card"} <= roles_by_label["D-13"]
    assert {"hard_sparring_day", "neural_visualization"} <= roles_by_label["D-6"]


def test_declared_coach_combat_spine_removes_app_stressor_from_coach_day():
    athlete = _athlete(
        13,
        plan_creation_weekday="friday",
        hard_sparring_days=["friday"],
    )
    sequence = ensure_declared_coach_combat_spine(
        [
            {
                "role_key": "strength_touch_day",
                "category": "strength",
                "stress_class": "meaningful_stress",
                "cost_class": "medium",
                "scheduled_countdown_label": "D-13",
                "countdown_label": "D-13",
                "countdown_offset": 13,
                "scheduled_day_hint": "friday",
            }
        ],
        athlete,
        _countdown_weekday_map("friday", 13),
    )

    d13_roles = [role["role_key"] for role in sequence if role.get("countdown_label") == "D-13"]
    assert "hard_sparring_day" in d13_roles
    assert "strength_touch_day" not in d13_roles
