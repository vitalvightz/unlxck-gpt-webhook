import pytest

from fightcamp.stage2_payload import (
    _late_fight_assignment_is_unsafe,
    build_planning_brief,
)
from fightcamp.stage2_validator import (
    _late_fight_line_is_exercise_like,
    validate_stage2_output,
)


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
    # The allocator distributes each scheduled role onto its own legitimate
    # countdown day (mon/wed/fri training days for a D-13 monday start): the
    # power anchor at D-13 (mon), the alactic sharpness touch at D-4 (wed), the
    # mobility reset at D-2 (fri). D-6 (mon) is a training day but legitimately
    # stays empty — availability is permission, not obligation. The invariant is
    # that an exercise is only renderable on the day it was actually approved
    # for, not that any given exercise must always land on a fixed day.
    assert allowed["D-13"] == ["Staggered-Stance Medicine-Ball Punch Throw"]
    assert allowed["D-4"] == ["Reactive Shuffle Repeats"]
    assert allowed["D-2"] == ["Mobility Reset Flow"]
    assert allowed["D-6"] == []
    # D-1 is equipment-free: the equipment-requiring isometric hold is dropped
    # rather than assigned, leaving D-1 to breathing/mobility/shadowboxing.
    assert allowed["D-1"] == []
    assert "Reactive Shuffle Repeats" not in allowed["D-1"]
    assert "Staggered-Stance Medicine-Ball Punch Throw" not in allowed["D-2"]
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
    # Bank exercises that require equipment are unsafe on D-1 even when their
    # names carry no loaded keyword (D-1 is equipment-free).
    assert _late_fight_assignment_is_unsafe("D-1", "Punch-Specific Max Isometric Hold") is True
    assert _late_fight_assignment_is_unsafe("D-1", "Band Face Pull") is True
    # Safe bodyweight primers / cues stay allowed on D-1.
    assert _late_fight_assignment_is_unsafe("D-1", "Technical Shadowboxing Tempo") is False
    assert _late_fight_assignment_is_unsafe("D-1", "Mobility Reset Flow") is False
    # Other countdown days are not guarded by this rule.
    assert _late_fight_assignment_is_unsafe("D-2", "Iso Deadlift Hold") is False
    assert _late_fight_assignment_is_unsafe("D-9", "Front Squat") is False


def test_duplicate_bank_names_cannot_downgrade_equipment_requirement(monkeypatch):
    # The same exercise name can appear in multiple banks with different
    # equipment. If any version requires equipment, the name must stay
    # equipment-required on D-1 regardless of bank iteration order.
    from fightcamp import stage2_payload

    equipment_version = {"name": "Reactive Cue Drill", "equipment": ["bands"]}
    bodyweight_version = {"name": "Reactive Cue Drill", "equipment": ["bodyweight"]}
    bodyweight_only = {"name": "Easy Mobility Walkthrough", "equipment": ["bodyweight"]}

    # Equipment version first, bodyweight duplicate later must not downgrade.
    monkeypatch.setattr("fightcamp.strength.get_exercise_bank", lambda: [equipment_version])
    monkeypatch.setattr("fightcamp.conditioning.get_conditioning_bank", lambda: [bodyweight_version, bodyweight_only])
    monkeypatch.setattr("fightcamp.conditioning.get_coordination_bank", lambda: [])
    monkeypatch.setattr(stage2_payload, "_D1_EQUIPMENT_BY_NAME", None)

    assert _late_fight_assignment_is_unsafe("D-1", "Reactive Cue Drill") is True
    assert _late_fight_assignment_is_unsafe("D-1", "Easy Mobility Walkthrough") is False

    # Reversed order: bodyweight first, equipment duplicate later still blocks.
    monkeypatch.setattr("fightcamp.strength.get_exercise_bank", lambda: [bodyweight_version])
    monkeypatch.setattr("fightcamp.conditioning.get_conditioning_bank", lambda: [equipment_version, bodyweight_only])
    monkeypatch.setattr(stage2_payload, "_D1_EQUIPMENT_BY_NAME", None)

    assert _late_fight_assignment_is_unsafe("D-1", "Reactive Cue Drill") is True
    assert _late_fight_assignment_is_unsafe("D-1", "Easy Mobility Walkthrough") is False


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


@pytest.mark.parametrize(
    "line",
    [
        # Rationale / "Why today" annotations (word after the label + a colon).
        "Why today: prepare ankles before the punch speed touch.",
        # Regression / stop annotations in the order actually rendered by the
        # generator, including a parenthetical qualifier before the colon.
        "Regression/stop: if you can't finish notes in 12 min, stop and keep only the top two cues.",
        "Regression/stop: if unclear after 8 min, pick the simplest cue and stop.",
        "Regression/stop (D-13+ rule — regressions/stop only): Replace with 3 x 6 shadow punch accelerations if med-ball causes soreness; stop if any delayed DOMS appears.",
        "Regression/stop (D-13+ rule): shorten to 2 sets x 4 each side if any soreness; stop if balance fails on >2 reps.",
        "Progression/regression/stop: hold the cue if it feels clean, otherwise stop.",
        # Dose-carrying annotation labels are not new exercise selections.
        "Duration: 5-8 min.",
        "Prescription: 3 x 6.",
        "Intensity: RPE 5-6.",
        # Cue-writing tasks are tactical/mental notes, not exercises.
        "Write one clear cue only (entry / exit / counter / guard reaction / foot position) — 5–8 min.",
        "Session: 5–8 min — write one fight cue (entry, exit, counter, foot position, or guard reaction). Keep it <8 words.",
    ],
)
def test_annotation_and_instruction_lines_are_not_exercise_selections(line):
    # These lines carry dose tokens ("12 min", "3 x 6", "5–8 min") but are
    # annotations / tactical tasks, not rendered exercises. They must not be
    # read as unapproved exercise selections.
    assert _late_fight_line_is_exercise_like(line) is False


@pytest.mark.parametrize(
    "line",
    [
        "Reactive Shuffle Repeats - 3 x 6 sec",
        "Short pallof-style anti-rotation hold: 2 x 8–10 sec each side (light), RPE 2–3.",
        "Mystery Power Drill - 2 x 3",
    ],
)
def test_genuine_exercise_lines_are_still_detected(line):
    # The annotation carve-outs must not swallow real exercise selections.
    assert _late_fight_line_is_exercise_like(line) is True


def test_annotation_lines_do_not_raise_unapproved_exercise_blocker():
    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-4 (Wednesday) — Fight-speed primer
        - Reactive Shuffle Repeats - 3 x 6 sec
        - Why today: prepare ankles before the punch speed touch.
        - Regression/stop: if unclear after 8 min, pick the simplest cue and stop.
        - Duration: 5-8 min.
        - Write one clear cue only (entry / exit / counter / guard reaction / foot position) — 5–8 min.
        """,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    assert "late_fight_unapproved_exercise_rendered" not in warning_codes


def test_unapproved_exercise_is_flagged_but_no_longer_hard_blocks_the_plan():
    from fightcamp.stage2_policy import is_hard_stage2_blocker

    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-3 - Freshness reset
        - Mystery Power Drill - 2 x 3
        """,
    )

    warning_codes = {warning["code"] for warning in report["warnings"]}
    # The finding is still surfaced (so the generator can prefer allowlisted
    # work)...
    assert "late_fight_unapproved_exercise_rendered" in warning_codes
    # ...but it is no longer a hard blocker, so it does not hold the plan.
    assert not is_hard_stage2_blocker("late_fight_unapproved_exercise_rendered")


def test_valid_late_fight_output_using_each_days_allowed_exercises_passes():
    brief = _brief_with_scheduled_allowed_exercises()

    report = validate_stage2_output(
        planning_brief=brief,
        final_plan_text="""
        D-13 (Monday) — Power transfer touch
        - Staggered-Stance Medicine-Ball Punch Throw - 2 x 3

        D-4 (Wednesday) — Fight-speed primer
        - Reactive Shuffle Repeats - 3 x 6 sec

        D-2 (Friday) — Freshness reset
        - Mobility Reset Flow - 6 min
        - Breathing reset - 3 min

        D-1 (Saturday) — Final neural cue
        - Technical shadowboxing - 2 light rounds
        - Breathing reset - 3 min
        """,
    )

    blocking_codes = {warning["code"] for warning in report["warnings"] if warning.get("blocking")}
    assert "late_fight_unapproved_exercise_rendered" not in blocking_codes
    assert not report["errors"]
