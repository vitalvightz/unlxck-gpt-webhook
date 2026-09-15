from __future__ import annotations

import fightcamp.camp_week_fillers as fillers
from fightcamp.camp_week_fillers import _role_d_day, _splice_late_fight_tail


def _week(calendar_days, roles):
    return {
        "calendar_days": calendar_days,
        "session_roles": roles,
        "intentionally_unused_days": [],
        "phase": "TAPER",
    }


def _role(role_key: str, d_day: int, weekday: str, *, category: str = "strength"):
    return {
        "role_key": role_key,
        "category": category,
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_day_hint": weekday,
    }


def test_d30_keeps_d14_normal_and_splices_finished_d13_tail(monkeypatch):
    weekly_role_map = {
        "weeks": [
            _week(
                [
                    {"weekday": "monday", "d_day": 15},
                    {"weekday": "tuesday", "d_day": 14},
                    {"weekday": "wednesday", "d_day": 13},
                    {"weekday": "thursday", "d_day": 12},
                ],
                [
                    _role("normal_d14", 14, "tuesday"),
                    _role("normal_d13", 13, "wednesday"),
                    _role("normal_d12", 12, "thursday"),
                ],
            ),
            _week(
                [
                    {"weekday": "monday", "d_day": 8},
                    {"weekday": "tuesday", "d_day": 7},
                    {"weekday": "wednesday", "d_day": 6},
                    {"weekday": "thursday", "d_day": 5},
                    {"weekday": "friday", "d_day": 4},
                ],
                [_role("normal_d7", 7, "tuesday")],
            ),
            _week(
                [
                    {"weekday": "monday", "d_day": 3},
                    {"weekday": "tuesday", "d_day": 2},
                    {"weekday": "wednesday", "d_day": 1},
                    {"weekday": "thursday", "d_day": 0},
                ],
                [
                    _role("normal_d1", 1, "wednesday"),
                    _role("fight_day_protocol", 0, "thursday", category="protocol"),
                ],
            ),
        ]
    }
    athlete_model = {
        "days_until_fight": 30,
        "plan_creation_weekday": "monday",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    }

    calls = []

    def fake_finished_tail(days_until_fight, model, *, start_day):
        calls.append((days_until_fight, start_day, model["days_until_fight"]))
        roles = [
            _role("late_d13", 13, "wednesday"),
            _role("late_d7", 7, "tuesday"),
            _role("late_d1", 1, "wednesday"),
        ]
        return {
            "session_sequence": roles,
            "day_metadata": {
                13: {"stage_key": "d13_to_d8", "payload_mode": "pre_fight_compressed_payload"},
                7: {"stage_key": "d7", "payload_mode": "late_fight_week_payload"},
                1: {"stage_key": "d1", "payload_mode": "pre_fight_day_payload"},
            },
            "segments": [
                {
                    "stage_key": "d13_to_d8",
                    "payload_mode": "pre_fight_compressed_payload",
                    "countdown_span": {"start_day": 13, "end_day": 8},
                    "intentional_compression": {"active": True},
                    "role_budget": {"max_active_roles": 3},
                },
                {
                    "stage_key": "d7",
                    "payload_mode": "late_fight_week_payload",
                    "countdown_span": {"start_day": 7, "end_day": 7},
                    "intentional_compression": {"active": True},
                    "role_budget": {"max_active_roles": 2},
                },
                {
                    "stage_key": "d1",
                    "payload_mode": "pre_fight_day_payload",
                    "countdown_span": {"start_day": 1, "end_day": 1},
                    "intentional_compression": {"active": True},
                    "role_budget": {"max_active_roles": 1},
                },
            ],
        }

    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", fake_finished_tail)

    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is True
    assert calls == [(30, 13, 30)]

    placed = {
        role["role_key"]: (_role_d_day(week, role), role)
        for week in weekly_role_map["weeks"]
        for role in week["session_roles"]
        if isinstance(role, dict)
    }

    # D-14 remains physically owned by the normal planner.
    assert placed["normal_d14"][0] == 14

    # Normal-planner roles inside D-13 -> D-1 are gone.
    for role_key in ("normal_d13", "normal_d12", "normal_d7", "normal_d1"):
        assert role_key not in placed

    # Finished late-fight roles own the tail and carry their real window metadata.
    assert placed["late_d13"][0] == 13
    assert placed["late_d13"][1]["governance"]["authority"] == "finished_late_fight_tail"
    assert placed["late_d13"][1]["late_fight_payload_mode"] == "pre_fight_compressed_payload"
    assert placed["late_d7"][1]["late_fight_payload_mode"] == "late_fight_week_payload"
    assert placed["late_d1"][1]["late_fight_payload_mode"] == "pre_fight_day_payload"

    # D-0 remains the existing deterministic fight-day protocol.
    assert placed["fight_day_protocol"][0] == 0

    # Mixed weeks carry segment metadata without changing D-14 ownership.
    first_week = weekly_role_map["weeks"][0]
    assert 14 not in first_week["late_fight_tail_days"]
    assert 13 in first_week["late_fight_tail_days"]
    assert first_week["late_fight_tail_segments"][0]["stage_key"] == "d13_to_d8"

    assert weekly_role_map["late_fight_tail_handoff"] == {
        "active": True,
        "normal_planner_through_d": 14,
        "late_fight_planner_from_d": 13,
        "source": "finished_existing_late_fight_path",
    }


def test_finished_tail_tactical_watches_are_not_reselected_or_collapsed(monkeypatch):
    watch_a = {
        **_role("tactical_watch", 10, "monday", category="support_insert"),
        "late_fight_tail_owned": True,
        "tactical_watch_key": "direct-tail-a",
        "display_text": "Direct D-13-path watch A",
    }
    watch_b = {
        **_role("tactical_watch", 7, "thursday", category="support_insert"),
        "late_fight_tail_owned": True,
        "tactical_watch_key": "direct-tail-b",
        "display_text": "Direct D-13-path watch B",
    }
    week = _week(
        [
            {"weekday": "monday", "d_day": 10},
            {"weekday": "thursday", "d_day": 7},
        ],
        [watch_a, watch_b],
    )
    week["late_fight_tail_days"] = [10, 7]

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("normal camp watch selector must not rewrite the finished tail")

    monkeypatch.setattr(fillers._impl, "_ensure_tactical_watch", should_not_run)
    used_watch_keys: set[str] = set()
    usage_ledger = fillers._new_usage_ledger()

    assert fillers._ensure_tactical_watch(
        week,
        {"days_until_fight": 30},
        "TAPER",
        used_watch_keys,
        usage_ledger,
    ) is True
    assert [role["display_text"] for role in week["session_roles"]] == [
        "Direct D-13-path watch A",
        "Direct D-13-path watch B",
    ]
    assert used_watch_keys == {"direct-tail-a", "direct-tail-b"}


def test_d13_generated_plan_is_not_spliced_again(monkeypatch):
    weekly_role_map = {"weeks": []}
    athlete_model = {"days_until_fight": 13}

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("direct D-13 plan must keep its existing late-fight route")

    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", should_not_run)
    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is False
    assert "late_fight_tail_handoff" not in weekly_role_map


# ── unplaced normal roles at the D-14 / D-13 ownership handoff ───────────────
#
# Production failure: a D-16 boxing plan kept a normal-camp ``alactic_speed_day``
# alive with no scheduled_day_hint, no countdown and no realised workload,
# because the handoff only removed roles whose D-day resolved into D-13..D-1.
# A dayless role resolves to ``None``, slipped the filter, and was then composed
# and validated as a physical session — raising
# ``conditioning_role_workload_underfilled`` for a session with no day at all.


def _dayless_role(role_key: str, *, category: str = "conditioning", **extra):
    role = {"role_key": role_key, "category": category, "preferred_system": "alactic"}
    role.update(extra)
    return role


def _tail_stub(roles, metadata=None):
    def fake_finished_tail(days_until_fight, model, *, start_day):
        return {
            "session_sequence": [dict(role) for role in roles],
            "day_metadata": metadata or {},
            "segments": [],
        }

    return fake_finished_tail


def _mixed_week_map():
    """A week spanning D-14 into the finished tail, plus a dayless normal role."""
    return {
        "weeks": [
            _week(
                [
                    {"weekday": "thursday", "d_day": 14},
                    {"weekday": "friday", "d_day": 13},
                    {"weekday": "saturday", "d_day": 12},
                    {"weekday": "sunday", "d_day": 11},
                    {"weekday": "tuesday", "d_day": 9},
                ],
                [
                    _role("primary_strength_day", 14, "thursday"),
                    _role("transfer_strength_day", 12, "saturday"),
                    _dayless_role("alactic_speed_day"),
                ],
            )
        ]
    }


def test_dayless_normal_role_is_suppressed_at_the_tail_handoff(monkeypatch):
    weekly_role_map = _mixed_week_map()
    athlete_model = {
        "days_until_fight": 16,
        "plan_creation_weekday": "tuesday",
        "training_days": ["monday", "tuesday", "thursday", "saturday", "sunday"],
    }
    monkeypatch.setattr(
        fillers,
        "build_finished_late_fight_tail",
        _tail_stub(
            [_role("alactic_sharpness_day", 12, "saturday", category="conditioning")],
            {12: {"stage_key": "d13_to_d8", "payload_mode": "pre_fight_compressed_payload"}},
        ),
    )

    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is True

    week = weekly_role_map["weeks"][0]
    active = {role["role_key"]: role for role in week["session_roles"]}

    # D-14 normal work is untouched.
    assert "primary_strength_day" in active
    assert _role_d_day(week, active["primary_strength_day"]) == 14

    # A normal role scheduled inside the tail is removed exactly as before.
    assert "transfer_strength_day" not in active

    # The dayless normal role is no longer active...
    assert "alactic_speed_day" not in active

    # ...and it is recorded with the explicit handoff reason, not as compression.
    suppressed = [
        row
        for row in week["suppressed_roles"]
        if row.get("role_key") == "alactic_speed_day"
    ]
    assert len(suppressed) == 1
    record = suppressed[0]
    assert record["reason_code"] == "late_fight_tail_handoff_unplaced_normal_role"
    assert record["authority"] == "late_fight_tail_handoff"
    assert record["late_fight_tail_handoff"] is True
    assert record["category"] == "conditioning"
    assert record["preferred_system"] == "alactic"
    assert record["original_role"]["role_key"] == "alactic_speed_day"
    assert "normal placement completed" in record["reason"].lower()
    assert "D-13 inward has transferred" in record["reason"]
    # Not readiness compression and not weight-cut suppression.
    assert "compression_reason_codes" not in record

    # The finished tail still owns its own sharpness exposure.
    sharpness = active["alactic_sharpness_day"]
    assert sharpness["late_fight_tail_owned"] is True
    assert sharpness["governance"]["authority"] == "finished_late_fight_tail"


def test_no_active_normal_physical_ghost_remains_in_a_tail_week(monkeypatch):
    weekly_role_map = _mixed_week_map()
    weekly_role_map["weeks"][0]["session_roles"].extend(
        [
            _dayless_role("primary_strength_day", category="strength"),
            _dayless_role(
                "recovery_reset_day",
                category="recovery",
                preferred_pool="rehab_slots_or_recovery_only",
            ),
        ]
    )
    monkeypatch.setattr(
        fillers,
        "build_finished_late_fight_tail",
        _tail_stub([_role("alactic_sharpness_day", 12, "saturday", category="conditioning")]),
    )

    assert _splice_late_fight_tail(
        weekly_role_map, {"days_until_fight": 16, "plan_creation_weekday": "tuesday"}
    ) is True

    week = weekly_role_map["weeks"][0]
    ghosts = [
        role
        for role in week["session_roles"]
        if isinstance(role, dict)
        and not role.get("late_fight_tail_owned")
        and not str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
        and _role_d_day(week, role) is None
        and fillers._is_unplaced_normal_physical_session(role)
    ]
    assert ghosts == []


def test_handoff_leaves_undated_support_and_metadata_alone(monkeypatch):
    """Only real normal-planner session work is suppressed, never support state."""
    weekly_role_map = _mixed_week_map()
    week = weekly_role_map["weeks"][0]
    week["session_roles"].extend(
        [
            # An undated support insert is not a stale training session.
            _dayless_role("tactical_cue_card", category="support_insert"),
            _dayless_role("breathing_reset", category="support_insert"),
            # A coach-owned combat lock is never the handoff's to remove.
            _dayless_role("light_combat_day", category="technical", coach_owned=True),
            # Tail-owned roles are out of scope by construction.
            _dayless_role(
                "alactic_sharpness_day", category="conditioning", late_fight_tail_owned=True
            ),
        ]
    )
    monkeypatch.setattr(
        fillers,
        "build_finished_late_fight_tail",
        _tail_stub([_role("neural_primer_day", 11, "sunday", category="strength")]),
    )

    assert _splice_late_fight_tail(
        weekly_role_map, {"days_until_fight": 16, "plan_creation_weekday": "tuesday"}
    ) is True

    active = {role["role_key"] for role in week["session_roles"]}
    for preserved in (
        "tactical_cue_card",
        "breathing_reset",
        "light_combat_day",
        "alactic_sharpness_day",
    ):
        assert preserved in active, preserved
    suppressed_keys = {row.get("role_key") for row in week.get("suppressed_roles") or []}
    assert suppressed_keys == {"alactic_speed_day"}


def test_dayless_normal_role_outside_a_tail_week_is_untouched(monkeypatch):
    """A week that owns no tail day is not this handoff's business."""
    weekly_role_map = {
        "weeks": [
            _week(
                [{"weekday": "monday", "d_day": 22}, {"weekday": "thursday", "d_day": 19}],
                [_role("primary_strength_day", 22, "monday"), _dayless_role("alactic_speed_day")],
            ),
            _week(
                [{"weekday": "saturday", "d_day": 13}, {"weekday": "sunday", "d_day": 12}],
                [_role("normal_d13", 13, "saturday")],
            ),
        ]
    }
    monkeypatch.setattr(
        fillers,
        "build_finished_late_fight_tail",
        _tail_stub([_role("alactic_sharpness_day", 12, "sunday", category="conditioning")]),
    )

    assert _splice_late_fight_tail(
        weekly_role_map, {"days_until_fight": 24, "plan_creation_weekday": "tuesday"}
    ) is True

    far_week = weekly_role_map["weeks"][0]
    assert any(role["role_key"] == "alactic_speed_day" for role in far_week["session_roles"])
    assert not far_week.get("suppressed_roles")


def test_handoff_suppression_is_never_restored_into_the_tail_by_goal_repair():
    """Goal preservation may not reclaim the handoff's window."""
    from fightcamp.camp_week_fillers import (
        HANDOFF_UNPLACED_REASON_CODE,
        _handoff_unplaced_suppression,
    )
    from fightcamp.goal_preservation import _restore_goal_roles

    candidate = {
        "role_key": "alactic_speed_day",
        "category": "conditioning",
        "preferred_system": "alactic",
        "preferred_tags": ["speed"],
    }
    brief = {
        "athlete_snapshot": {"training_frequency": 5},
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 1,
                    "phase": "SPP",
                    "declared_training_days": ["monday", "tuesday", "thursday", "saturday", "sunday"],
                    "calendar_days": [
                        {"weekday": "thursday", "d_day": 14},
                        {"weekday": "saturday", "d_day": 12},
                        {"weekday": "monday", "d_day": 10},
                    ],
                    "session_roles": [],
                    "intentionally_unused_days": [],
                    "goal_repair_candidates": [candidate],
                    "suppressed_roles": [_handoff_unplaced_suppression(dict(candidate))],
                }
            ]
        },
    }

    audit = _restore_goal_roles(brief, {"goal": "speed", "state": "build"})

    week = brief["weekly_role_map"]["weeks"][0]
    # Nothing restored anywhere, and certainly not onto a tail day.
    assert [role.get("role_key") for role in week["session_roles"]] == []
    assert any(
        row.get("result") == "authority_preserved"
        and HANDOFF_UNPLACED_REASON_CODE in (row.get("reason_codes") or [])
        for row in audit
    )


# ── production-shape regression ─────────────────────────────────────────────


def _production_d16_brief():
    """The reported D-16 boxing plan, through the deterministic Stage 1 pipeline.

    D-16 / 5 sessions / low fatigue / Mon-Tue-Thu-Sat-Sun availability / Sunday
    declared hard sparring / 5.3% cut / power + skill refinement / footwork. The
    creation weekday puts D-11 on the declared Sunday contact day, matching the
    production calendar.
    """
    from fightcamp.stage2_payload import build_planning_brief

    athlete_model = {
        "sport": "boxing",
        "camp_length_weeks": 3,
        "days_until_fight": 16,
        "short_notice": False,
        "fatigue": "low",
        "training_frequency": 5,
        "training_preference": "balanced",
        "training_days": ["monday", "tuesday", "thursday", "saturday", "sunday"],
        "hard_sparring_days": ["sunday"],
        "key_goals": ["power", "skill_refinement"],
        "weaknesses": ["footwork"],
        "equipment": ["bodyweight", "bands", "barbell", "dumbbells"],
        "injuries": [],
        "weight_cut_risk": True,
        "weight_cut_pct": 5.3,
        "readiness_flags": [],
        "plan_creation_weekday": "tuesday",
    }
    candidate_pools = {
        "SPP": {
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
    }
    phase_briefs = {
        "SPP": {
            "objective": "power transfer and skill refinement",
            "emphasize": ["sport speed"],
            "deprioritize": [],
            "risk_flags": [],
            "session_counts": {"strength": 2, "conditioning": 3, "recovery": 1},
            "selection_guardrails": {},
            "weeks": 2,
            "days": 16,
        }
    }
    return build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs=phase_briefs,
        candidate_pools=candidate_pools,
        omission_ledger={},
        rewrite_guidance={},
    )


def test_production_d16_plan_has_no_dayless_normal_ghost():
    from fightcamp.stage2_validator import _underfilled_conditioning_errors

    brief = _production_d16_brief()
    weeks = brief["weekly_role_map"]["weeks"]
    assert brief["weekly_role_map"]["late_fight_tail_handoff"]["active"] is True

    active = [
        (week, role)
        for week in weeks
        for role in week.get("session_roles") or []
        if isinstance(role, dict)
    ]

    # 1. No active dayless normal alactic_speed_day (the reported ghost), and no
    #    dayless normal physical session of any class.
    dayless_normal = [
        role["role_key"]
        for week, role in active
        if not role.get("late_fight_tail_owned")
        and not str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
        and _role_d_day(week, role) is None
        and fillers._is_unplaced_normal_physical_session(role)
    ]
    assert dayless_normal == []
    assert "alactic_speed_day" not in {role["role_key"] for _, role in active}

    # ...and it is accounted for, not silently dropped.
    handoff_rows = [
        row
        for week in weeks
        for row in week.get("suppressed_roles") or []
        if row.get("reason_code") == "late_fight_tail_handoff_unplaced_normal_role"
    ]
    assert {row["role_key"] for row in handoff_rows} == {"alactic_speed_day"}

    # 2. The finished tail still carries its own alactic/sharpness exposure, so
    #    the removed ghost was not the sole owner of that adaptation.
    tail_sharpness = [
        role["role_key"]
        for _, role in active
        if role.get("late_fight_tail_owned")
        and role["role_key"] in {"alactic_sharpness_day", "neural_primer_day"}
    ]
    assert tail_sharpness

    # 3. No conditioning workload blocker is raised by the removed ghost.
    underfilled = _underfilled_conditioning_errors(brief)
    assert "alactic_speed_day" not in {row.get("role_key") for row in underfilled}

    # 4. D-10 is not reclaimed by the normal planner: every tail day belongs to
    #    the finished allocator.
    for week, role in active:
        d_day = _role_d_day(week, role)
        if isinstance(d_day, int) and 1 <= d_day <= 13:
            assert role.get("late_fight_tail_owned") is True, role["role_key"]

    # 5. D-14 normal work survives intact and is still normal-planner owned.
    d14 = [
        role["role_key"]
        for week, role in active
        if _role_d_day(week, role) == 14 and not role.get("late_fight_tail_owned")
    ]
    assert d14
