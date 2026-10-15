"""Drill explanations are app-wide content, not a second short cue."""
from copy import deepcopy
from api.structured_plan_coaching import recover_selected_coaching
from api.structured_plan_models import SessionBlock
from fightcamp.exercise_coaching import exercise_coaching, coaching_lines
from fightcamp.exercise_instructions import exercise_instructions
from fightcamp.session_composition import assignment_from_slot


def card(name, **fields):
    return {"schema_version": "1.0", "weeks": [{"days": [{"sessions": [{"blocks": [
        {"display_name": name, "block_type": "skill", "sets": 1,
         "work": {"value": 5, "unit": "seconds"}, **fields}]}]}]}]}


def block(plan):
    return plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]


def test_saved_drills_without_a_planning_brief_recover_bank_sequence():
    for name in ("Range Feint-Entry-Exit", "Pendulum Jab-Cross Reset", "Explosive Straight Burst"):
        plan = card(name)
        before = deepcopy(plan)
        result = recover_selected_coaching(plan, {})
        assert plan == before
        assert block(result)["execution_instructions"] == exercise_instructions({"name": name})
        assert block(result)["work"] == block(before)["work"]
        assert recover_selected_coaching(result, {}) == result
    assert "no second entry" in exercise_instructions({"name": "Range Feint-Entry-Exit"})


def test_new_bank_description_survives_selection_and_raw_rendering():
    selected = assignment_from_slot("GPP", "strength_slots", {"selected": {
        "name": "Coach combination", "prescription": "2 x 5 reps",
        "description": "Feint, step in, throw once, then exit to range."}})
    fields = exercise_coaching(selected, {}, d_day=30)
    assert fields["execution_instructions"] == selected["execution_instructions"]
    assert f"  How: {selected['execution_instructions']}" in coaching_lines(fields)


def test_existing_and_athlete_instructions_are_not_overwritten():
    plan = card("Range Feint-Entry-Exit", execution_instructions="Coach's own sequence.")
    assert recover_selected_coaching(plan, {}) == plan
    custom = card("Range Feint-Entry-Exit", prescription_source="athlete")
    assert recover_selected_coaching(custom, {"custom_plan": True}) == custom
    unknown = card("Unknown drill")
    assert recover_selected_coaching(unknown, {}) == unknown


def test_explanation_survives_the_structured_block_schema():
    explanation = "Feint at range, enter once, throw, and exit."
    parsed = SessionBlock.model_validate({"block_type": "skill", "display_name": "Range Feint-Entry-Exit",
        "execution_instructions": explanation})
    assert parsed.model_dump()["execution_instructions"] == explanation


def test_raw_how_line_survives_fallback_without_becoming_a_second_cue():
    from api.structured_plan_deterministic_fallback import _source_block
    explanation = "Feint at range, enter once, throw, and exit."
    for detail in (f"How: {explanation}\n  Cue: Keep guard ready.",
                   f"How: {explanation} Cue: Keep guard ready."):
        source = [f"- Coach Drill: 2 x 5 reps. {detail}"]
        result = _source_block(source, "Coach Drill")
        assert result["execution_instructions"] == explanation
        assert "Cue: Keep guard ready." in result["coaching_cues"]
        assert not any("How:" in cue or explanation in cue for cue in result["coaching_cues"])
