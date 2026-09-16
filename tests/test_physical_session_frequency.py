"""Physical-session frequency contract.

``training_frequency`` means one thing across the planner: the number of
*physical* training sessions the athlete plans to do in a week. The late-fight
taper may make those sessions cheaper — less volume, less contact, less
eccentric load, shorter — but it may not silently delete the sessions
themselves, and zero-load tactical/education support may never stand in for one.

The production regression these lock down: a frequency-5 boxer, 15 days out,
declaring Mon/Tue/Thu/Sat/Sun, whose SPP week rendered as
``D-14 nothing / D-12 primer / D-11 technical combat / D-10 nothing /
D-9 breathing reset`` — two empty declared days and a 3-minute breathing insert
standing in for a third.
"""

from __future__ import annotations

import pytest

from fightcamp.physical_session_frequency import (
    WARNING_FREQUENCY_UNMET,
    audit_physical_session_frequency,
    cadence_windows,
    count_physical_sessions,
    is_physical_session_role,
    physical_session_offsets,
    plan_physical_occupancy,
    plan_week_physical_occupancy,
    viable_declared_days,
)
from fightcamp.stage2_payload import build_planning_brief
from fightcamp.training_context import (
    allocate_sessions,
    candidate_role_capacity,
    physical_session_target,
)


PRODUCTION_TRAINING_DAYS = ["monday", "tuesday", "thursday", "saturday", "sunday"]


def _pools() -> dict:
    slots = {
        "strength_slots": [
            {
                "role": "primary_strength",
                "selected": {"name": "Trap Bar Deadlift"},
                "alternates": [{"name": "Goblet Squat"}],
            }
        ],
        "conditioning_slots": [
            {
                "role": "alactic",
                "selected": {"name": "Short Sprint Burst"},
                "alternates": [{"name": "Reactive Start"}],
            },
            {
                "role": "aerobic",
                "selected": {"name": "Tempo Run"},
                "alternates": [{"name": "Air Bike Flush"}],
            },
        ],
        "rehab_slots": [],
    }
    return {"GPP": dict(slots), "SPP": dict(slots), "TAPER": dict(slots)}


def _brief(
    *,
    days_until_fight: int,
    plan_creation_weekday: str,
    training_frequency: int = 5,
    training_days: list[str] | None = None,
    hard_sparring_days: list[str] | None = None,
    **overrides,
) -> dict:
    athlete_model = {
        "sport": "boxing",
        "status": "amateur",
        "camp_length_weeks": 3,
        "days_until_fight": days_until_fight,
        "short_notice": False,
        "fatigue": "low",
        "training_frequency": training_frequency,
        "training_preference": "balanced",
        "training_days": list(
            PRODUCTION_TRAINING_DAYS if training_days is None else training_days
        ),
        "hard_sparring_days": list(
            ["sunday"] if hard_sparring_days is None else hard_sparring_days
        ),
        "key_goals": ["power", "skill_refinement"],
        "weaknesses": ["footwork"],
        "equipment": ["bodyweight", "bands", "barbell", "dumbbells"],
        "injuries": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "readiness_flags": [],
        "plan_creation_weekday": plan_creation_weekday,
    }
    athlete_model.update(overrides)
    phase_briefs = {
        "SPP": {
            "objective": "",
            "emphasize": [],
            "deprioritize": [],
            "risk_flags": [],
            "session_counts": allocate_sessions(training_frequency, "SPP"),
            "selection_guardrails": {},
            "weeks": 2,
            "days": days_until_fight,
        }
    }
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=_pools(),
        omission_ledger={},
        rewrite_guidance={},
    )


def _week_containing(brief: dict, d_day: int) -> dict:
    for week in _weeks(brief):
        for entry in week.get("calendar_days") or []:
            if isinstance(entry, dict) and entry.get("d_day") == d_day:
                return week
    raise AssertionError(f"no week contains D-{d_day}")


def _weeks(brief: dict) -> list[dict]:
    return [
        week
        for week in brief["weekly_role_map"].get("weeks", []) or []
        if isinstance(week, dict)
    ]


def _week_day_slots(week: dict) -> list[tuple[int, str]]:
    return [
        (int(entry["d_day"]), str(entry.get("weekday") or ""))
        for entry in week.get("calendar_days") or []
        if isinstance(entry, dict) and isinstance(entry.get("d_day"), int)
    ]


def _week_plans(week: dict, athlete_model: dict):
    """Every seven-day cadence window in a planner week, earliest first."""
    return plan_week_physical_occupancy(
        day_slots=_week_day_slots(week),
        roles=[r for r in week.get("session_roles") or [] if isinstance(r, dict)],
        athlete_model=athlete_model,
    )


def _week_plan(week: dict, athlete_model: dict):
    """The first (earliest) cadence window of a planner week."""
    return _week_plans(week, athlete_model)[0]


def _athlete_of(brief: dict) -> dict:
    return brief["athlete_snapshot"]


# ── classification ──────────────────────────────────────────────────────────


def _role(role_key: str, category: str, offset: int) -> dict:
    return {"role_key": role_key, "category": category, "countdown_offset": offset}


def test_tactical_watch_contributes_zero_to_physical_frequency():
    """Test 4 — three sessions plus two Tactical Watches is three, not five."""
    roles = [
        _role("primary_strength_day", "strength", 12),
        _role("alactic_speed_day", "conditioning", 10),
        _role("light_combat_day", "sparring", 8),
        _role("tactical_watch", "support_insert", 6),
        _role("tactical_cue_card", "support_insert", 5),
    ]
    assert count_physical_sessions(roles) == 3
    assert physical_session_offsets(roles) == {12, 10, 8}


def test_tactical_support_on_a_training_day_does_not_double_count():
    roles = [
        _role("light_combat_day", "sparring", 11),
        _role("tactical_watch", "support_insert", 11),
    ]
    assert count_physical_sessions(roles) == 1


def test_breathing_only_insert_is_not_a_physical_session():
    """Test 5 — a 3-minute breathing reset cannot satisfy frequency."""
    assert is_physical_session_role(_role("breathing_reset", "support_insert", 9)) is False
    assert count_physical_sessions([_role("breathing_reset", "support_insert", 9)]) == 0


@pytest.mark.parametrize(
    "role_key",
    ["tactical_watch", "tactical_focus", "tactical_cue_card", "self_review",
     "neural_visualization", "breathing_reset", "sleep_downshift", "fight_day_protocol"],
)
def test_zero_load_support_never_counts(role_key):
    assert is_physical_session_role(_role(role_key, "support_insert", 5)) is False


def test_substantial_physical_recovery_counts_but_micro_reset_does_not():
    """Test 6 — recovery is not uniformly physical or uniformly not."""
    programmed = _role("recovery_reset_day", "recovery", 9)
    mobility = _role("mobility_rehab", "support_insert", 9)
    micro_reset = _role("recovery_reset", "support_insert", 9)

    assert is_physical_session_role(programmed) is True
    assert is_physical_session_role(mobility) is True
    assert is_physical_session_role(micro_reset) is False


def test_fight_day_protocol_is_not_training():
    """Test 7 (classification half) — D-0 contributes zero."""
    roles = [_role("fight_day_protocol", "fight_day", 0)]
    assert count_physical_sessions(roles) == 0


# ── target arithmetic ───────────────────────────────────────────────────────


def test_target_is_frequency_when_availability_allows():
    assert physical_session_target(5, 5) == 5


def test_fight_day_removes_one_training_opportunity():
    """Test 3 — five declared weekdays, one of which is D-0, targets four."""
    day_slots = [(5, "saturday"), (4, "sunday"), (3, "monday"), (2, "tuesday"), (0, "thursday")]
    athlete = {
        "training_frequency": 5,
        "training_days": ["saturday", "sunday", "monday", "tuesday", "thursday"],
    }
    assert viable_declared_days(day_slots, athlete) == [5, 4, 3, 2]
    assert plan_physical_occupancy(day_slots=day_slots, roles=[], athlete_model=athlete).target == 4


def test_availability_below_requested_frequency_caps_the_target():
    """Test 14 — three viable days means a target of three, not five."""
    day_slots = [(12, "saturday"), (11, "sunday"), (10, "monday"), (9, "tuesday")]
    athlete = {"training_frequency": 5, "training_days": ["saturday", "sunday", "monday"]}
    plan = plan_physical_occupancy(day_slots=day_slots, roles=[], athlete_model=athlete)
    assert plan.viable_offsets == [12, 11, 10]
    assert plan.target == 3


def test_undeclared_weekdays_are_never_scheduled_to_reach_frequency():
    day_slots = [(12, "saturday"), (11, "sunday"), (10, "monday"), (9, "tuesday")]
    athlete = {"training_frequency": 5, "training_days": ["saturday", "sunday", "monday"]}
    plan = plan_physical_occupancy(day_slots=day_slots, roles=[], athlete_model=athlete)
    assert 9 not in plan.viable_offsets
    assert 9 not in plan.fill_offsets


# ── upstream session-count semantics ────────────────────────────────────────


def test_candidate_capacity_and_physical_target_are_separate_concepts():
    """Test 12 — internal candidate depth may exceed the session target."""
    # allocate_sessions is candidate capacity: frequency + 1, capped at 6.
    assert candidate_role_capacity(5) == 6
    assert sum(allocate_sessions(5, "SPP").values()) == 6
    # The athlete-facing target is unaffected by that depth allowance.
    assert physical_session_target(5, 5) == 5


@pytest.mark.parametrize("frequency", [2, 3, 4, 5])
def test_persisted_phase_session_counts_never_exceed_frequency(frequency):
    """Test 12/13 — input N must not persist as an N+1 session week, at any D-day."""
    from fightcamp.stage2_planning_brief import _cap_session_counts_to_frequency
    from fightcamp.training_context import TrainingContext

    for days_until_fight in (40, 21, 15, 10):
        context = TrainingContext(
            fatigue="low",
            training_frequency=frequency,
            days_available=frequency,
            training_days=PRODUCTION_TRAINING_DAYS[:frequency],
            injuries=[],
            style_technical=[],
            style_tactical=[],
            weaknesses=[],
            equipment=["bodyweight"],
            weight_cut_risk=False,
            weight_cut_pct=0.0,
            fight_format="3x3",
            status="amateur",
            key_goals=[],
            training_preference="balanced",
            mental_block=[],
            age=None,
            weight=None,
            prev_exercises=[],
            recent_exercises=[],
            phase_weeks={},
            days_until_fight=days_until_fight,
        )
        for phase in ("GPP", "SPP", "TAPER"):
            counts = _cap_session_counts_to_frequency(
                allocate_sessions(frequency, phase), context
            )
            assert sum(counts.values()) <= frequency, (
                frequency, phase, days_until_fight, counts
            )


# ── end-to-end calendar shape ───────────────────────────────────────────────


def test_frequency_five_with_five_safe_days_produces_five_physical_sessions():
    """Test 1 — the production SPP week, healthy athlete, no cut.

    The reported calendar left D-14 Thursday and D-10 Monday empty and put a
    Breathing Reset on D-9 Tuesday. All five declared days in this cadence
    window must now carry physical work.
    """
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    athlete = _athlete_of(brief)
    spp_week = _week_containing(brief, 14)
    plan = _week_plan(spp_week, athlete)

    assert plan.requested_frequency == 5
    # The planner week spans D-14..D-7 — eight days, two Thursdays. The first
    # cadence window is D-14..D-8, so the trailing D-7 Thursday is a week later
    # and belongs to the next cadence, not this quota.
    assert plan.viable_offsets == [14, 12, 11, 10, 9]
    assert plan.target == 5
    assert plan.occupied_offsets == [14, 12, 11, 10, 9], plan
    assert plan.shortfall == 0
    assert plan.fill_offsets == []


def test_taper_pressure_keeps_occupancy_and_still_caps_meaningful_stress():
    """Test 2 / Test 11 — cheaper sessions, not fewer; stress stays capped."""
    brief = _brief(
        days_until_fight=15,
        plan_creation_weekday="wednesday",
        weight_cut_risk=True,
        weight_cut_pct=5.3,
        reduced_contact=True,
    )
    athlete = _athlete_of(brief)
    spp_week = _week_containing(brief, 14)
    plan = _week_plan(spp_week, athlete)
    assert plan.occupied_offsets == [14, 12, 11, 10, 9], plan
    assert plan.shortfall == 0, plan

    budget = spp_week.get("role_budget") or {}
    cap = budget.get("max_meaningful_stress_exposures")
    selected = budget.get("selected_meaningful_stress_exposures")
    if isinstance(cap, int) and isinstance(selected, int):
        assert selected <= cap

    # Occupancy repair never adds meaningful stress: every session it placed is a
    # low-cost support insert.
    for role in spp_week.get("session_roles") or []:
        if isinstance(role, dict) and role.get("physical_occupancy_fill"):
            assert role.get("category") == "support_insert"


def test_fight_week_targets_four_because_the_fifth_declared_day_is_d0():
    """Test 3 (end to end) — D-5/D-4/D-3/D-2 physical, D-0 fight protocol."""
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    athlete = _athlete_of(brief)
    fight_week = _week_containing(brief, 0)
    plan = _week_plan(fight_week, athlete)

    assert 0 not in plan.viable_offsets
    assert plan.target == 4
    assert plan.occupancy == 4, plan
    assert set(plan.occupied_offsets) == {5, 4, 3, 2}

    # D-0 still carries its own protocol, and it is not a training session.
    fight_day_roles = [
        role
        for role in fight_week.get("session_roles") or []
        if isinstance(role, dict) and role.get("role_key") == "fight_day_protocol"
    ]
    assert fight_day_roles
    assert count_physical_sessions(fight_day_roles) == 0


def test_d14_stays_normal_planner_owned_and_is_occupied():
    """Test 7 — D-14 belongs to the normal planner and no longer falls through."""
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    handoff = brief["weekly_role_map"]["late_fight_tail_handoff"]
    assert handoff["normal_planner_through_d"] == 14
    assert handoff["late_fight_planner_from_d"] == 13

    spp_week = _week_containing(brief, 14)
    d14_roles = [
        role
        for role in spp_week.get("session_roles") or []
        if isinstance(role, dict)
        and _offset(role) == 14
    ]
    assert d14_roles, "D-14 is a declared training day and must carry a session"
    assert any(is_physical_session_role(role) for role in d14_roles)
    # Still normal-planner owned: nothing at D-14 may be tagged as finished-tail.
    assert not any(role.get("late_fight_tail_owned") for role in d14_roles)


def test_d13_inward_remains_finished_tail_owned():
    """Test 8 — the D-13 handoff is untouched, with no stale dayless ghost."""
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    for week in _weeks(brief):
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            offset = _offset(role)
            if offset is None or not 1 <= offset <= 13:
                continue
            if role.get("role_key") == "fight_day_protocol":
                continue
            assert role.get("late_fight_tail_owned") or role.get("camp_week_filler"), role

    # No surviving normal-planner role without a resolved day.
    for week in _weeks(brief):
        for role in week.get("session_roles") or []:
            if isinstance(role, dict) and not role.get("late_fight_tail_owned"):
                assert str(role.get("scheduled_day_hint") or "").strip(), role


def test_no_unexplained_empty_declared_days():
    """Test 10 — an empty declared day must carry a recorded reason."""
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    findings = audit_physical_session_frequency(
        brief["weekly_role_map"], _athlete_of(brief)
    )
    assert findings == [], findings


def test_unused_declared_days_carry_a_deterministic_reason():
    """Test 9 — a day left unused is recorded, never silently dropped."""
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    athlete = _athlete_of(brief)
    for week in _weeks(brief):
        recorded = {
            entry.get("countdown_offset")
            for entry in week.get("intentionally_unused_days") or []
            if isinstance(entry, dict)
        }
        for plan in _week_plans(week, athlete):
            for offset in plan.fill_offsets:
                assert offset in recorded, (week.get("week_index"), offset)
        for entry in week.get("intentionally_unused_days") or []:
            if isinstance(entry, dict) and entry.get("physical_session_target_authority"):
                assert entry.get("reason_code")


def test_audit_reports_an_unexplained_empty_declared_day():
    """The QA check fails loudly when occupancy is short with no explanation."""
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "calendar_days": [
                    {"weekday": "thursday", "d_day": 14},
                    {"weekday": "saturday", "d_day": 12},
                    {"weekday": "sunday", "d_day": 11},
                    {"weekday": "monday", "d_day": 10},
                    {"weekday": "tuesday", "d_day": 9},
                ],
                "declared_training_days": PRODUCTION_TRAINING_DAYS,
                "session_roles": [
                    _role("primary_strength_day", "strength", 12),
                    _role("light_combat_day", "sparring", 11),
                    _role("breathing_reset", "support_insert", 9),
                    _role("tactical_watch", "support_insert", 11),
                ],
                "intentionally_unused_days": [],
            }
        ]
    }
    findings = audit_physical_session_frequency(
        weekly_role_map, {"training_frequency": 5, "training_days": PRODUCTION_TRAINING_DAYS}
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding["reason_code"] == WARNING_FREQUENCY_UNMET
    assert finding["actual_physical_sessions"] == 2
    assert finding["requested_physical_target"] == 5
    # The breathing reset does not close the D-9 gap, and D-14/D-10 are named.
    assert set(finding["unexplained_empty_days"]) == {14, 10, 9}


def test_zero_load_support_cannot_satisfy_the_validator():
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "calendar_days": [
                    {"weekday": "monday", "d_day": 10},
                    {"weekday": "tuesday", "d_day": 9},
                ],
                "declared_training_days": ["monday", "tuesday"],
                "session_roles": [
                    _role("tactical_watch", "support_insert", 10),
                    _role("tactical_cue_card", "support_insert", 9),
                ],
                "intentionally_unused_days": [],
            }
        ]
    }
    findings = audit_physical_session_frequency(
        weekly_role_map, {"training_frequency": 2, "training_days": ["monday", "tuesday"]}
    )
    assert findings and findings[0]["actual_physical_sessions"] == 0


@pytest.mark.parametrize("frequency", [2, 3, 4, 5])
def test_lower_frequencies_are_honoured_without_a_frequency_five_special_case(frequency):
    """Test 13 — no frequency-specific behaviour anywhere in the pipeline."""
    brief = _brief(
        days_until_fight=15,
        plan_creation_weekday="wednesday",
        training_frequency=frequency,
        training_days=PRODUCTION_TRAINING_DAYS[:frequency],
        hard_sparring_days=[],
    )
    athlete = _athlete_of(brief)
    for week in _weeks(brief):
        recorded = {
            entry.get("countdown_offset")
            for entry in week.get("intentionally_unused_days") or []
            if isinstance(entry, dict)
        }
        for plan in _week_plans(week, athlete):
            assert plan.target <= frequency
            assert plan.shortfall == 0 or all(
                offset in recorded for offset in plan.fill_offsets
            )


def _offset(role: dict):
    from fightcamp.physical_session_frequency import role_countdown_offset

    return role_countdown_offset(role)


def test_safety_leaves_a_declared_day_unused_with_an_explicit_reason():
    """Test 9 — when no legal physical option survives, say so; never fake filler."""
    from fightcamp.gap_fill_inserts import select_physical_occupancy_insert
    from fightcamp.physical_occupancy_fill import fill_physical_occupancy
    from fightcamp.physical_session_frequency import REASON_NO_LEGAL_PHYSICAL_OPTION

    athlete = {
        "sport": "boxing",
        "training_frequency": 3,
        "training_days": ["monday", "tuesday", "thursday"],
        "fatigue": "high",
        "readiness_flags": ["high_fatigue"],
        "injuries": [],
    }
    # High fatigue strips every physical option, cut relaxation included.
    assert select_physical_occupancy_insert(athlete, 9) is None

    added, unused = fill_physical_occupancy(
        day_slots=[(11, "monday"), (10, "tuesday"), (8, "thursday")],
        roles=[],
        athlete_model=athlete,
    )
    assert added == []
    assert {entry["countdown_offset"] for entry in unused} == {11, 10, 8}
    assert {entry["reason_code"] for entry in unused} == {REASON_NO_LEGAL_PHYSICAL_OPTION}


def test_d1_is_never_forced_to_carry_physical_work():
    """D-1 governance is untouched: occupancy repair does not reach it."""
    from fightcamp.gap_fill_inserts import select_physical_occupancy_insert

    athlete = {
        "sport": "boxing",
        "training_frequency": 5,
        "training_days": PRODUCTION_TRAINING_DAYS,
        "fatigue": "low",
        "injuries": [],
    }
    assert select_physical_occupancy_insert(athlete, 1) is None
    assert select_physical_occupancy_insert(athlete, 0) is None


def test_audit_is_attached_to_the_finished_weekly_role_map():
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    audit = brief["weekly_role_map"]["physical_session_frequency_audit"]
    assert audit["schema_version"] == "physical_session_frequency_audit.v1"
    assert audit["warnings"] == []


# ── seven-day cadence windows ───────────────────────────────────────────────


PRODUCTION_SPP_WEEK_SLOTS = [
    (14, "thursday"),
    (13, "friday"),
    (12, "saturday"),
    (11, "sunday"),
    (10, "monday"),
    (9, "tuesday"),
    (8, "wednesday"),
    (7, "thursday"),
]


def test_eight_day_planner_week_splits_into_real_seven_day_windows():
    windows = cadence_windows(PRODUCTION_SPP_WEEK_SLOTS)
    assert [[offset for offset, _wd in window] for window in windows] == [
        [14, 13, 12, 11, 10, 9, 8],
        [7],
    ]


def test_seven_day_week_is_a_single_window():
    slots = [(6, "friday"), (5, "saturday"), (4, "sunday"), (3, "monday"),
             (2, "tuesday"), (1, "wednesday"), (0, "thursday")]
    assert len(cadence_windows(slots)) == 1


def test_repeated_weekday_a_week_later_cannot_pay_the_earlier_weeks_quota():
    """The reported bug: D-7 Thursday absorbing D-9 Tuesday's fifth session.

    Treating the whole eight-day planner week as one bucket gave
    ``min(5, 6 viable) = 5``, which the trailing Thursday satisfied — so D-9
    stayed empty and read as intentional. Frequency is a per-seven-days
    quantity, so D-7 belongs to the next cadence and cannot close this one.
    """
    athlete = {"training_frequency": 5, "training_days": PRODUCTION_TRAINING_DAYS}
    roles = [
        _role("aerobic_support_day", "conditioning", 14),
        _role("strength_touch_day", "strength", 12),
        _role("light_combat_day", "sparring", 11),
        _role("joint_prep", "support_insert", 10),
        _role("neural_primer_day", "strength", 7),  # a full week after D-14
        _role("breathing_reset", "support_insert", 9),
    ]
    first, second = plan_week_physical_occupancy(
        day_slots=PRODUCTION_SPP_WEEK_SLOTS,
        roles=roles,
        athlete_model=athlete,
    )

    assert first.viable_offsets == [14, 12, 11, 10, 9]
    assert first.target == 5
    # D-9 holds only a Breathing Reset, so the window is one session short and
    # names D-9 — it does not borrow the D-7 Thursday session to look complete.
    assert first.occupied_offsets == [14, 12, 11, 10]
    assert first.shortfall == 1
    assert first.fill_offsets == [9]

    assert second.viable_offsets == [7]
    assert second.target == 1
    assert second.shortfall == 0


def test_audit_flags_a_window_that_borrowed_from_the_next_cadence():
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "calendar_days": [
                    {"weekday": weekday, "d_day": offset}
                    for offset, weekday in PRODUCTION_SPP_WEEK_SLOTS
                ],
                "declared_training_days": PRODUCTION_TRAINING_DAYS,
                "session_roles": [
                    _role("aerobic_support_day", "conditioning", 14),
                    _role("strength_touch_day", "strength", 12),
                    _role("light_combat_day", "sparring", 11),
                    _role("joint_prep", "support_insert", 10),
                    _role("neural_primer_day", "strength", 7),
                    _role("breathing_reset", "support_insert", 9),
                ],
                "intentionally_unused_days": [],
            }
        ]
    }
    findings = audit_physical_session_frequency(
        weekly_role_map,
        {"training_frequency": 5, "training_days": PRODUCTION_TRAINING_DAYS},
    )
    assert len(findings) == 1
    assert findings[0]["cadence_window"] == [14, 9]
    assert findings[0]["unexplained_empty_days"] == [9]


def test_production_spp_cadence_fills_every_declared_day_end_to_end():
    """The D-15 production regression: D-14/D-12/D-11/D-10/D-9 all physical."""
    brief = _brief(days_until_fight=15, plan_creation_weekday="wednesday")
    athlete = _athlete_of(brief)
    spp_week = _week_containing(brief, 14)
    first, second = _week_plans(spp_week, athlete)

    assert first.occupied_offsets == [14, 12, 11, 10, 9]
    # Nothing in this window is written off as "frequency already met".
    assert not [
        entry
        for entry in spp_week.get("intentionally_unused_days") or []
        if isinstance(entry, dict) and entry.get("countdown_offset") in {14, 12, 11, 10, 9}
    ]
    # D-7 Thursday still carries its own session in the next cadence.
    assert second.occupied_offsets == [7]


def test_repeated_weekday_unused_records_are_not_collapsed():
    """Two Thursdays in one planner week owe two explanations, not one.

    Deduplicating by weekday name alone discarded the second record, so a week
    that could fill neither D-14 nor D-7 reported only one of them — the exact
    repeated-weekday ambiguity this PR exists to remove.
    """
    from fightcamp.camp_week_fillers_impl import _merge_unused_day_records
    from fightcamp.physical_session_frequency import (
        REASON_NO_LEGAL_PHYSICAL_OPTION,
        unused_day_record,
    )

    week = {
        "calendar_days": [
            {"weekday": weekday, "d_day": offset}
            for offset, weekday in PRODUCTION_SPP_WEEK_SLOTS
        ],
        "intentionally_unused_days": [],
    }
    _merge_unused_day_records(
        week,
        [
            unused_day_record("thursday", 14, REASON_NO_LEGAL_PHYSICAL_OPTION),
            unused_day_record("thursday", 7, REASON_NO_LEGAL_PHYSICAL_OPTION),
        ],
    )
    assert [entry["countdown_offset"] for entry in week["intentionally_unused_days"]] == [14, 7]


def test_unused_record_for_an_already_explained_day_is_not_duplicated():
    from fightcamp.camp_week_fillers_impl import _merge_unused_day_records
    from fightcamp.physical_session_frequency import (
        REASON_NO_LEGAL_PHYSICAL_OPTION,
        unused_day_record,
    )

    week = {
        "calendar_days": [
            {"weekday": weekday, "d_day": offset}
            for offset, weekday in PRODUCTION_SPP_WEEK_SLOTS
        ],
        "intentionally_unused_days": [
            {"day": "Thursday", "countdown_offset": 14, "role": "recovery_only_day"}
        ],
    }
    _merge_unused_day_records(
        week,
        [
            unused_day_record("thursday", 14, REASON_NO_LEGAL_PHYSICAL_OPTION),
            unused_day_record("thursday", 7, REASON_NO_LEGAL_PHYSICAL_OPTION),
        ],
    )
    entries = week["intentionally_unused_days"]
    # D-14 keeps its original explanation; only D-7 is added.
    assert [entry.get("countdown_offset") for entry in entries] == [14, 7]
    assert entries[0]["role"] == "recovery_only_day"
    assert "reason_code" not in entries[0]


def test_legacy_weekday_only_unused_record_still_dedupes_against_its_offset():
    """A record with no offset resolves through the week's calendar."""
    from fightcamp.camp_week_fillers_impl import _merge_unused_day_records
    from fightcamp.physical_session_frequency import (
        REASON_NO_LEGAL_PHYSICAL_OPTION,
        unused_day_record,
    )

    week = {
        "calendar_days": [
            {"weekday": "monday", "d_day": 10},
            {"weekday": "tuesday", "d_day": 9},
        ],
        "intentionally_unused_days": [{"day": "Monday", "role": "off_day"}],
    }
    _merge_unused_day_records(
        week,
        [
            unused_day_record("monday", 10, REASON_NO_LEGAL_PHYSICAL_OPTION),
            unused_day_record("tuesday", 9, REASON_NO_LEGAL_PHYSICAL_OPTION),
        ],
    )
    assert [entry.get("day") for entry in week["intentionally_unused_days"]] == [
        "Monday",
        "Tuesday",
    ]
