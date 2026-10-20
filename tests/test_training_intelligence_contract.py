"""Cross-owner regressions: actual stimulus, recurring cadence and card dose."""
from copy import deepcopy

import pytest

from api.structured_plan_deterministic_fallback import _source_block, _preserve_unrepresented_dose
from fightcamp.goal_preservation import _requirements, selected_goals, _trunk_capacity_reasons
from fightcamp.exercise_coaching import exercise_coaching
from fightcamp.strength_session_quality import strength_adaptation_relevance
from fightcamp.strength import get_exercise_bank, _classify_prescription_type
from fightcamp.stage2_validator import (
    _goal_witness_dose_matches, _late_camp_effective_prescription_warnings,
    _late_fight_line_is_exercise_like,
    _extract_leading_count,
)
from fightcamp.stage2_validator_postprocess import postprocess_stage2_validator_report


def _calendar_brief():
    return {"athlete_snapshot": {"days_until_fight": 27}, "weekly_role_map": {"weeks": [
        {"week_index": n + 1, "phase": "SPP" if n < 3 else "TAPER",
         "calendar_days": [{"d_day": d} for d in range(high, max(-1, high - 7), -1)]}
        for n, high in enumerate((26, 19, 12, 5))
    ]}}


@pytest.mark.parametrize("state", ["build", "maintain"])
def test_two_opening_week_lifts_cannot_pay_for_next_strength_week(state):
    windows = _requirements({"goal": "strength", "state": state}, _calendar_brief())
    assert windows == [{"min_d_day": 20, "max_d_day": 26}, {"min_d_day": 14, "max_d_day": 19}]
    assert not all(any(w["min_d_day"] <= day <= w["max_d_day"] for day in (26, 20)) for w in windows)
    assert all(any(w["min_d_day"] <= day <= w["max_d_day"] for day in (26, 16)) for w in windows)


def test_partial_calendar_cannot_erase_the_rest_of_a_long_camp():
    brief = _calendar_brief()
    brief["athlete_snapshot"]["days_until_fight"] = 56
    windows = _requirements({"goal": "strength", "state": "maintain"}, brief)
    assert max(w["max_d_day"] for w in windows) == 55
    assert len(windows) > 2


def test_secondary_physical_weaknesses_are_verified_once_at_their_priority():
    athlete = {"key_goals": ["power", "strength"], "primary_goal": "power",
               "weaknesses": ["power", "trunk_strength", "strength", "gas_tank"], "primary_weak_area": "power"}
    assert selected_goals(athlete) == [("power", "primary"), ("strength", "secondary"),
                                      ("trunk_strength", "secondary"), ("conditioning", "secondary")]
    duplicate = deepcopy(athlete)
    duplicate["weaknesses"] *= 2
    assert selected_goals(duplicate) == selected_goals(athlete)


def test_trunk_gap_requires_a_live_receipt_for_every_available_host():
    window = {"min_d_day": 2, "max_d_day": 15}
    conditioning = {"category": "conditioning", "role_key": "fight_pace_repeatability_day",
        "scheduled_countdown_label": "D-14", "conditioning_composition_policy": {
            "hard_sparring_adjacent": True, "embedded_trunk_support_skip_reason": "hard_sparring_adjacent"}}
    tail = {"category": "strength", "role_key": "strength_touch_day",
            "scheduled_countdown_label": "D-13", "late_fight_tail_owned": True}
    weeks = [{"week_index": 1, "session_roles": [conditioning, tail]}]
    reasons = _trunk_capacity_reasons(weeks, window)
    assert {r["authority"] for r in reasons} == {
        "session_composition.embedded_trunk_support", "late_fight_tail_ownership"}
    assert {r["d_day"] for r in reasons} == {14, 13}
    weeks[0]["session_roles"].append({"category": "strength", "role_key": "primary_strength_day",
                                    "scheduled_countdown_label": "D-15"})
    assert _trunk_capacity_reasons(weeks, window) == []
    assert _trunk_capacity_reasons([{"session_roles": [tail]}], window) == []
    conditioning["conditioning_composition_policy"]["hard_sparring_adjacent"] = False
    assert _trunk_capacity_reasons([{"session_roles": [conditioning, tail]}], window) == []


def test_ballistic_programming_is_not_loaded_strength_but_contrast_keeps_both():
    bank = {e["name"]: e for e in get_exercise_bank()}
    for name in ("Barbell Thruster", "Push Press"):
        assert "power" in strength_adaptation_relevance(bank[name])
        assert "strength" not in strength_adaptation_relevance(bank[name], prescription_type=_classify_prescription_type(bank[name]))
    assert "strength" in strength_adaptation_relevance(bank["Cluster Set Trap Bar Deadlift"], prescription_type="barbell")
    assert {"strength", "power"} <= strength_adaptation_relevance(bank["Heavy RDL → Broad Jump"])


def test_compound_working_dose_survives_both_card_conversion_paths():
    dose = "3 rounds: heavy movement 2 reps @ 85% 1RM → explosive movement 2 reps at max intent; rest 4 min per round."
    source = _source_block(["- Heavy RDL → Broad Jump: " + dose, "  Cue: Stick the landing."], "Heavy RDL → Broad Jump")
    assert source is not None
    assert dose.rstrip(".") in source["execution_instructions"]
    assert dose in _preserve_unrepresented_dose(dose, "Stick the landing.")
    assert _preserve_unrepresented_dose("3 sets x 3 reps; RPE 7", "Brace.") == "Brace."
    assert "light sled" in _preserve_unrepresented_dose("6 x 5 sec with light sled; rest 90 sec", None)
    witness = {"sets": 3, "reps": 2, "minimum_load_percent": 85, "quality_class": "anchor_power"}
    assert _goal_witness_dose_matches(witness, dose)
    assert not _goal_witness_dose_matches(witness, dose.replace("3 rounds", "2 rounds"))
    assert not _goal_witness_dose_matches(witness, dose.replace("85%", "50%"))


@pytest.mark.parametrize(("dose", "rest"), [
    ("3 x 180s work / 60s rest; RPE 5", {"value": 60, "unit": "seconds"}),
    ("3 rounds: heavy 2 reps → jump 2 reps; rest 4 min per round.", {"value": 4, "unit": "minutes"}),
])
def test_embedded_rest_is_structured_without_losing_the_full_dose(dose, rest):
    block = _source_block(["- Example Drill: " + dose], "Example Drill")
    assert block["rest"] == rest
    if "→" in dose:
        # A compound dose is not one statistic: it stays whole.
        assert dose.split("; RPE")[0].rstrip(".") in block["execution_instructions"]
    else:
        # Every quantity is a stat, so How does not repeat it.
        assert (block["sets"], block["duration"]) == (3, {"value": 180, "unit": "seconds"})
        assert not block.get("execution_instructions")
    if "RPE 5" in dose:
        assert block["effort"] == {"method": "RPE", "value": 5, "scale": "1-10"}


def test_separate_locked_support_is_not_an_extra_strength_member():
    support = "- Cage Circle: 2 x 90 sec technical sets, 60 sec reset"
    brief = {"weekly_role_map": {"weeks": [{"week_index": 1, "phase": "SPP",
        "calendar_days": [{"d_day": 20, "weekday": "monday"}], "session_roles": [
            {"role_key": "primary_strength_day", "category": "strength", "scheduled_d_day": 20,
             "athlete_facing_label": "Strength",
             "scheduled_countdown_label": "D-20", "scheduled_day_hint": "Monday",
             "effective_strength_envelope": {"scheduled_d_day": 20, "complete_exercise_allow_list": True,
                                             "allowed_exercise_names": ["Deadlift"]}},
            {"role_key": "footwork_walkthrough", "category": "support_insert", "scheduled_d_day": 20,
             "athlete_facing_label": "Footwork",
             "scheduled_countdown_label": "D-20", "scheduled_day_hint": "Monday",
             "display_text": support, "selected_drill_locked": True},
        ]}]}}
    rendered = "D-20 (Monday) — Strength\n- Deadlift: 3 x 3 @ RPE 7\nD-20 (Monday) — Footwork\n" + support
    def membership_findings(text):
        raw = _late_camp_effective_prescription_warnings(brief, text)
        return postprocess_stage2_validator_report(
            planning_brief=brief, final_plan_text=text,
            validator_report={"errors": raw, "late_camp_effective_prescription_warnings": raw},
        )["errors"]

    assert membership_findings(rendered) == []
    changed = rendered.replace("Cage Circle: 2 x", "Cage Circle: 4 x")
    assert any("exercise_allow_list" in e["violation_dimensions"]
               for e in _late_camp_effective_prescription_warnings(brief, changed))
    moved = rendered.replace("D-20 (Monday) — Footwork\n", "")
    assert any("exercise_allow_list" in e["violation_dimensions"] for e in membership_findings(moved))


def test_execution_annotation_is_not_an_additional_selected_exercise():
    assert not _late_fight_line_is_exercise_like("How: One maximal-intent first step, then reset.")
    assert _late_fight_line_is_exercise_like("- Extra jump squat: 3 x 5 reps")


def test_dose_count_distinguishes_sets_from_a_range():
    assert _extract_leading_count("1 x 6 @ RPE 5") == 1
    assert _extract_leading_count("6-8 rounds") == 8
    assert _extract_leading_count("6 rounds") == 6


def test_preferred_exercise_check_recognizes_only_exact_declared_combat_copy():
    from fightcamp.combat_render_authority import CANONICAL_LIGHT_COMBAT_NOTE

    role = {"role_key": "light_combat_day", "category": "technical", "coach_owned": True,
            "scheduled_countdown_label": "D-5"}
    brief = {"late_fight_session_sequence": [role]}
    warning = {"code": "late_fight_window_preferred_missing", "days_out_bucket": "D-5",
               "section_title": "D-5 (Monday) - Light Combat / Technical"}
    rendered = "D-5 (Monday) - Light Combat / Technical\n" + CANONICAL_LIGHT_COMBAT_NOTE
    def reviewed(text):
        return postprocess_stage2_validator_report(planning_brief=brief, final_plan_text=text,
                                                   validator_report={"warnings": [warning]})["warnings"]
    assert reviewed(rendered) == []
    assert reviewed(rendered.replace(CANONICAL_LIGHT_COMBAT_NOTE, "Extra hard intervals today.")) == [warning]


def test_bank_cue_cannot_reintroduce_a_second_working_dose():
    coaching = exercise_coaching({"name": "Jump Squat", "slot_group": "strength_slots",
        "effective_prescription": "2 x 2 at max speed; rest 120s",
        "coaching_notes": "Use bodyweight for 3-5 sets of 3 reps. Stop if landings become unstable."},
        {"role_key": "strength_touch_day"}, phase="SPP", d_day=10)
    assert coaching["coaching_cues"]
    assert not any("3-5" in cue for cue in coaching["coaching_cues"])
    assert any("landings become unstable" in rule for rule in coaching["stop_rules"])
