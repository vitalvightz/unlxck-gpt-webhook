"""Cross-owner regressions: actual stimulus, recurring cadence and card dose."""
from copy import deepcopy

import pytest

from api.structured_plan_deterministic_fallback import _source_block, _preserve_unrepresented_dose
from fightcamp.goal_preservation import _requirements, selected_goals
from fightcamp.strength_session_quality import strength_adaptation_relevance
from fightcamp.strength import get_exercise_bank, _classify_prescription_type
from fightcamp.stage2_validator import _goal_witness_dose_matches, _late_camp_effective_prescription_warnings


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
                                      ("trunk_strength", "secondary_weakness"), ("conditioning", "secondary_weakness")]
    duplicate = deepcopy(athlete)
    duplicate["weaknesses"] *= 2
    assert selected_goals(duplicate) == selected_goals(athlete)


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
    assert dose in _preserve_unrepresented_dose(dose, {"load": {"value": 85}}, "Stick the landing.")
    assert _preserve_unrepresented_dose("3 x 3 @ RPE 7", {"sets": 3, "reps": 3}, "Brace.") == "Brace."
    witness = {"sets": 3, "reps": 2, "minimum_load_percent": 85, "quality_class": "anchor_power"}
    assert _goal_witness_dose_matches(witness, dose)
    assert not _goal_witness_dose_matches(witness, dose.replace("3 rounds", "2 rounds"))
    assert not _goal_witness_dose_matches(witness, dose.replace("85%", "50%"))


def test_separate_locked_support_is_not_an_extra_strength_member():
    support = "- Cage Circle: 2 x 90 sec technical sets, 60 sec reset"
    brief = {"weekly_role_map": {"weeks": [{"week_index": 1, "phase": "SPP",
        "calendar_days": [{"d_day": 20, "weekday": "monday"}], "session_roles": [
            {"role_key": "primary_strength_day", "category": "strength", "scheduled_d_day": 20,
             "scheduled_countdown_label": "D-20", "scheduled_day_hint": "Monday",
             "effective_strength_envelope": {"scheduled_d_day": 20, "complete_exercise_allow_list": True,
                                             "allowed_exercise_names": ["Deadlift"]}},
            {"role_key": "footwork_walkthrough", "category": "support_insert", "scheduled_d_day": 20,
             "scheduled_countdown_label": "D-20", "scheduled_day_hint": "Monday",
             "display_text": support, "selected_drill_locked": True},
        ]}]}}
    rendered = "D-20 (Monday) — Strength\n- Deadlift: 3 x 3 @ RPE 7\nD-20 (Monday) — Footwork\n" + support
    assert _late_camp_effective_prescription_warnings(brief, rendered) == []
    changed = rendered.replace("Cage Circle: 2 x", "Cage Circle: 4 x")
    assert any("exercise_allow_list" in e["violation_dimensions"]
               for e in _late_camp_effective_prescription_warnings(brief, changed))
