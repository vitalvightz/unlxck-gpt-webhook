from fightcamp.stage2_payload import (
    _late_fight_assignment_is_unsafe,
    build_planning_brief,
)
from fightcamp.stage2_validator import validate_stage2_output


def _brief_with_scheduled_allowed_exercises() -> dict:
    return build_planning_brief(
        athlete_model={
            "sport": "boxing",
            "days_until_fight": 13,
            "plan_creation_weekday": "monday",
            "fatigue": "moderate",
            "readiness_flags": [],
            "training_days": ["monday", "wednesday", "friday"],
            "hard_sparring_days": [],
        },
        restrictions=[],
        phase_briefs={
            "TAPER": {
                "objective": "fresh sharpness",
                "emphasize": ["speed"],
                "deprioritize": [],
                "risk_flags": [],
                "selection_guardrails": {},
            }
        },
        candidate_pools={
            "TAPER": {
                "strength_slots": [
                    {
                        "slot_id": "taper_power_transfer",
                        "role": "rotational",
                        "anchor_capable": True,
                        "support_only": False,
                        "selected": {
                            "name": "Staggered-Stance Medicine-Ball Punch Throw",
                            "movement_patterns": ["power", "rotational", "rate_of_force"],
                            "quality_class": "anchor_power",
                            "anchor_capable": True,
                        },
                    },
                    {
                        "slot_id": "taper_final_neural_cue",
                        "role": "isometric",
                        "anchor_capable": True,
                        "support_only": False,
                        "selected": {
                            "name": "Punch-Specific Max Isometric Hold",
                            "movement_patterns": ["isometric", "neural_primer", "coordination"],
                            "quality_class": "anchor_force_isometric",
                            "anchor_capable": True,
                        },
                    },
                    {
                        "slot_id": "taper_mobility_reset",
                        "role": "mobility",
                        "anchor_capable": False,
                        "support_only": True,
                        "selected": {
                            "name": "Mobility Reset Flow",
                            "movement_patterns": ["mobility", "rehab", "reset"],
                            "quality_class": "rehab_support",
                            "support_only": True,
                        },
                    },
                ],
                "conditioning_slots": [
                    {
                        "slot_id": "taper_reactive_shuffle",
                        "role": "alactic",
                        "selected": {
                            "name": "Reactive Shuffle Repeats",
                            "movement_patterns": ["alactic", "sharpness", "footwork"],
                        },
                    }
                ],
                "rehab_slots": [
                    {
                        "slot_id": "taper_breathing_reset",
                        "role": "reset",
                        "selected": {"name": "Breathing Reset"},
                    }
                ],
            }
        },
        omission_ledger={},
        rewrite_guidance={},
    )


def test_allowed_exercises_by_day_uses_scheduled_roles_not_plan_wide_pool():
    brief = _brief_with_scheduled_allowed_exercises()

    allowed = brief["late_fight_plan_spec"]["allowed_exercises_by_day"]
    non_empty_lists = [tuple(names) for names in allowed.values() if names]

    assert len(set(non_empty_lists)) > 1
    assert allowed["D-13"] == ["Staggered-Stance Medicine-Ball Punch Throw"]
    assert allowed["D-6"] == ["Reactive Shuffle Repeats"]
    assert allowed["D-3"] == ["Mobility Reset Flow"]
    assert allowed["D-1"] == ["Punch-Specific Max Isometric Hold"]
    assert "Reactive Shuffle Repeats" not in allowed["D-1"]
    assert "Staggered-Stance Medicine-Ball Punch Throw" not in allowed["D-3"]
    assert "Band-Resisted Sprint Starts (ATP-PCr)" not in allowed["D-13"]


def test_d13_power_transfer_drill_is_blocked_on_freshness_day():
    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-3 - Freshness reset
        - Staggered-Stance Medicine-Ball Punch Throw - 2 x 3
        """,
    )

    blocking_codes = {warning["code"] for warning in report["warnings"] if warning.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_d7_or_d6_neural_sharpness_drill_is_blocked_on_d1_when_not_assigned():
    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-1 - Final cue
        - Reactive Shuffle Repeats - 3 x 6 sec
        """,
    )

    blocking_codes = {warning["code"] for warning in report["warnings"] if warning.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_freshness_days_do_not_inherit_strength_or_power_exercises():
    brief = _brief_with_scheduled_allowed_exercises()
    allowed = brief["late_fight_plan_spec"]["allowed_exercises_by_day"]

    assert "Staggered-Stance Medicine-Ball Punch Throw" not in allowed["D-3"]
    assert "Punch-Specific Max Isometric Hold" not in allowed["D-3"]


def test_unknown_exercise_is_blocked_for_that_specific_countdown_day():
    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-3 - Freshness reset
        - Mystery Power Drill - 2 x 3
        """,
    )

    blocking_codes = {warning["code"] for warning in report["warnings"] if warning.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" in blocking_codes


def test_late_fight_assignment_is_unsafe_guards_only_d1_loaded_work():
    # Loaded / strength / conditioning keywords are unsafe on D-1 only.
    assert _late_fight_assignment_is_unsafe("D-1", "Iso Deadlift Hold") is True
    assert _late_fight_assignment_is_unsafe("D-1", "Front Squat") is True
    assert _late_fight_assignment_is_unsafe("D-1", "Bag Sprint Repeats") is True
    # Separator variants of "trap bar" are all caught (hyphen / underscore / space).
    assert _late_fight_assignment_is_unsafe("D-1", "Trap-Bar Hold") is True
    assert _late_fight_assignment_is_unsafe("D-1", "trap_bar carry") is True
    # Safe primers / cues stay allowed on D-1.
    assert _late_fight_assignment_is_unsafe("D-1", "Punch-Specific Max Isometric Hold") is False
    assert _late_fight_assignment_is_unsafe("D-1", "Mobility Reset Flow") is False
    # Other countdown days are not guarded by this rule.
    assert _late_fight_assignment_is_unsafe("D-2", "Iso Deadlift Hold") is False
    assert _late_fight_assignment_is_unsafe("D-9", "Front Squat") is False


def test_d1_never_receives_loaded_strength_exercise():
    # Force the D-1-bound slot to carry a loaded (deadlift) exercise; the
    # allocator must drop it rather than place dangerous work on D-1.
    brief = build_planning_brief(
        athlete_model={
            "sport": "boxing",
            "days_until_fight": 13,
            "plan_creation_weekday": "monday",
            "fatigue": "moderate",
            "readiness_flags": [],
            "training_days": ["monday", "wednesday", "friday"],
            "hard_sparring_days": [],
        },
        restrictions=[],
        phase_briefs={
            "TAPER": {
                "objective": "fresh sharpness",
                "emphasize": ["speed"],
                "deprioritize": [],
                "risk_flags": [],
                "selection_guardrails": {},
            }
        },
        candidate_pools={
            "TAPER": {
                "strength_slots": [
                    {
                        "slot_id": "taper_power_transfer",
                        "role": "rotational",
                        "anchor_capable": True,
                        "support_only": False,
                        "selected": {
                            "name": "Staggered-Stance Medicine-Ball Punch Throw",
                            "movement_patterns": ["power", "rotational"],
                            "quality_class": "anchor_power",
                            "anchor_capable": True,
                        },
                    },
                    {
                        "slot_id": "taper_final_neural_cue",
                        "role": "isometric",
                        "anchor_capable": True,
                        "support_only": False,
                        "selected": {
                            # Loaded name that the validator hard-blocks on D-1.
                            "name": "Iso Deadlift Hold",
                            "movement_patterns": ["isometric", "neural_primer"],
                            "quality_class": "anchor_force_isometric",
                            "anchor_capable": True,
                        },
                    },
                ],
                "conditioning_slots": [],
                "rehab_slots": [
                    {
                        "slot_id": "taper_breathing_reset",
                        "role": "reset",
                        "selected": {"name": "Breathing Reset"},
                    }
                ],
            }
        },
        omission_ledger={},
        rewrite_guidance={},
    )

    allowed = brief["late_fight_plan_spec"]["allowed_exercises_by_day"]
    assert "Iso Deadlift Hold" not in allowed.get("D-1", [])
    # No D-1 exercise may match the validator's D-1 danger pattern.
    import re as _re

    danger = _re.compile(
        r"\b(strength|conditioning|sprints?|interval|heavy|loaded|deadlift|squat|trap bar|barbell)\b",
        _re.IGNORECASE,
    )
    assert not [name for name in allowed.get("D-1", []) if danger.search(name)]


def test_valid_late_fight_output_using_each_days_allowed_exercises_passes():
    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-13 (Monday) — Power transfer touch
        - Staggered-Stance Medicine-Ball Punch Throw - 2 x 3

        D-6 (Monday) — Fight-speed primer
        - Reactive Shuffle Repeats - 3 x 6 sec

        D-3 (Thursday) — Freshness reset
        - Mobility Reset Flow - 6 min
        - Breathing reset - 3 min

        D-1 (Saturday) — Final neural cue
        - Punch-Specific Max Isometric Hold - 2 x 5 sec
        - Technical shadowboxing - 2 light rounds
        """,
    )

    blocking_codes = {warning["code"] for warning in report["warnings"] if warning.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" not in blocking_codes
    assert not report["errors"]
