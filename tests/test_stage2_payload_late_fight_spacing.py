from fightcamp.stage2_payload_late_fight import _build_late_fight_session_sequence


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


def _offsets(sequence):
    offsets = []
    for entry in sequence:
        label = str(entry.get("countdown_label") or "")
        if label.startswith("D-"):
            offsets.append(int(label[2:]))
    return sorted(offsets, reverse=True)


def test_sparse_late_window_does_not_collapse_into_consecutive_earliest_days():
    athlete = _athlete(
        8,
        plan_creation_weekday="saturday",
        hard_sparring_days=["friday"],
        fatigue="moderate",
        fatigue_level="moderate",
    )

    sequence = _build_late_fight_session_sequence(8, athlete)
    offsets = _offsets(sequence)

    # Not naive earliest-fill (D-8, D-7, D-6, D-5).
    assert offsets != [8, 7, 6, 5]
    gaps = [offsets[idx] - offsets[idx + 1] for idx in range(len(offsets) - 1)]
    assert any(gap >= 2 for gap in gaps)
    assert not any(gaps[idx] == 1 and gaps[idx + 1] == 1 for idx in range(len(gaps) - 1))


def test_d8_saturday_generation_keeps_locked_downgraded_days_and_spreads_unlocked_roles():
    athlete = _athlete(
        8,
        plan_creation_weekday="saturday",
        hard_sparring_days=["monday", "wednesday", "friday"],
        readiness_flags=["injury_management"],
        fatigue="moderate",
        fatigue_level="moderate",
    )

    sequence = _build_late_fight_session_sequence(8, athlete)
    by_key = {}
    for entry in sequence:
        by_key.setdefault(entry["role_key"], []).append(entry)

    technical_touches = by_key["declared_hard_day_technical_touch"]
    assert [(e["locked_day"], e["countdown_label"]) for e in technical_touches] == [
        ("monday", "D-6"),
        ("wednesday", "D-4"),
        ("friday", "D-2"),
    ]
    assert all(e.get("declared_day_locked") for e in technical_touches)
    assert by_key["strength_touch_day"]
    assert by_key["fight_week_freshness_day"]


def test_locked_days_remain_immutable_when_spacing_allocator_runs():
    athlete = _athlete(
        9,
        plan_creation_weekday="friday",
        hard_sparring_days=["tuesday", "thursday", "saturday"],
    )

    sequence = _build_late_fight_session_sequence(9, athlete)
    hard = [e for e in sequence if e["role_key"] == "hard_sparring_day"]
    technical = [e for e in sequence if e["role_key"] == "declared_hard_day_technical_touch"]

    assert [(e["locked_day"], e["countdown_label"]) for e in hard] == [("saturday", "D-8")]
    assert [(e["locked_day"], e["countdown_label"]) for e in technical] == [
        ("tuesday", "D-5"),
        ("thursday", "D-3"),
        ("saturday", "D-1"),
    ]


def test_high_cost_unlocked_roles_do_not_stack_consecutively_when_window_allows():
    athlete = _athlete(
        10,
        plan_creation_weekday="monday",
        hard_sparring_days=[],
        fatigue="low",
        fatigue_level="low",
    )

    sequence = _build_late_fight_session_sequence(10, athlete)
    high_offsets = [
        int(entry["countdown_label"][2:])
        for entry in sequence
        if entry["role_key"] in {"strength_touch_day", "light_fight_pace_touch_day"}
    ]

    assert len(high_offsets) == 2
    assert abs(high_offsets[0] - high_offsets[1]) > 1


def test_freshness_role_is_structural_not_just_first_free_slot():
    athlete = _athlete(
        10,
        plan_creation_weekday="monday",
        hard_sparring_days=[],
        fatigue="low",
        fatigue_level="low",
    )

    sequence = _build_late_fight_session_sequence(10, athlete)
    freshness = next(entry for entry in sequence if entry["role_key"] == "fight_week_freshness_day")
    freshness_offset = int(freshness["countdown_label"][2:])

    # Earliest-free filling would place freshness near D-9/D-8; spacing keeps it as taper support.
    assert freshness_offset <= 2
