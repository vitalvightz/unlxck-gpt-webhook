"""Enforce field ownership and sampling at the real Stage 2 boundary."""
import asyncio

import pytest

from api.stage2_automation import OpenAIStage2Automator
from api.structured_plan_deterministic_fallback import _lift_dose_fields
from api.structured_plan_generation import build_structured_plan_outcome, build_structured_plan_prompt
from fightcamp.exercise_output_contract import exercise_field_ownership_errors
from support import FakeOpenAIClient
from test_stage2_automation import _response
from test_structured_plan_models import _valid_plan
from test_structured_plan_generation import _faithful_source


def test_strict_conversion_prompt_is_compact_and_has_one_semantic_contract():
    source = "Monday — Strength\n- Squat: 3 sets x 5 reps; load 75% 1RM; rest 120 sec; RPE 7."
    legacy = build_structured_plan_prompt(plan_markdown=source)
    strict = build_structured_plan_prompt(plan_markdown=source, schema_constrained=True)
    assert len(strict) < len(legacy) / 4
    assert source in strict
    assert "Do not infer missing rest" in strict
    assert "never a dose recap" in strict
    assert "never today's full dose" in strict
    assert "EXACT ROOT SKELETON" not in strict


def test_prompt_compaction_keeps_source_athlete_context_and_computed_support_identical():
    source = "D-20 (Monday) — Strength\n- Squat: 3 sets x 5 reps; load 75% 1RM; rest 120 sec; RPE 7.\n  Stop: sharp pain or joint instability."
    brief = {"athlete_snapshot": {"sport": "boxing", "fatigue_level": "high"},
             "computed_support": {"mindset": {"athlete_note": "Keep my focus under pressure."}}}
    legacy = build_structured_plan_prompt(plan_markdown=source, planning_brief=brief)
    strict = build_structured_plan_prompt(plan_markdown=source, planning_brief=brief, schema_constrained=True)
    # Only the duplicated instruction/skeleton prefix changes. All supplied
    # context, deterministic support and the exact source remain byte-identical.
    marker = "PLANNING BRIEF (context for athlete/event/phases"
    assert strict[strict.index(marker):] == legacy[legacy.index(marker):]
    assert "75% 1RM" in strict
    assert "sharp pain or joint instability" in strict


@pytest.mark.parametrize("model, temperature", [("gpt-4.1-mini", 0), ("gpt-4o", 0),
                                               ("gpt-5-mini", None), ("o3", None)])
def test_low_sampling_only_for_models_that_support_temperature(model, temperature):
    client = FakeOpenAIClient([_response("done")])
    automator = OpenAIStage2Automator(client=client, model=model)
    asyncio.run(automator._generate_text("Render source faithfully.", attempt_label="first", source="test"))
    assert client.responses.calls[0].get("temperature") == temperature
    if temperature is None:
        assert "temperature" not in client.responses.calls[0]


@pytest.mark.parametrize("field,text", [
    ("coaching_cues", "6 rounds x 180 sec work; rest 60 sec."),
    ("execution_instructions", "Complete 8 rounds of 20 seconds work with 10 seconds rest."),
])
def test_schema_valid_dose_in_execution_prose_is_not_publishable_in_strict_mode(field, text):
    card = _valid_plan()
    block = card["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block[field] = [text] if field == "coaching_cues" else text
    outcome = build_structured_plan_outcome(card, raw_markdown=_faithful_source(card), strict_content=True)
    assert outcome.structured_plan is None
    assert any("field_ownership:" in error for error in outcome.errors)


def test_numbered_movement_instructions_and_locked_mental_steps_are_preserved():
    plan = {"weeks": [{"days": [{"sessions": [{"blocks": [
        {"block_type": "strength", "coaching_cues": ["Keep elbows at 45 degrees."],
         "execution_instructions": "Turn 90 degrees, then reset your guard."},
        {"block_type": "mindset", "coaching_cues": ["3 rounds of observations."]},
    ]}]}]}]}
    assert exercise_field_ownership_errors(plan) == []


@pytest.mark.parametrize("dose", [
    "8 rounds of 20s all-out work / 10s rest; 1 blocks, 2 min between blocks.",
    "8 rounds x 20 sec work; rest 10 sec; 1 blocks; between-block rest 120 sec",
])
def test_tabata_keeps_round_work_rest_and_between_block_rest_separate(dose):
    fields, _ = _lift_dose_fields(dose)
    assert fields["rounds"] == 8
    assert fields["work"] == {"value": 20, "unit": "seconds"}
    assert fields["rest"] == {"value": 10, "unit": "seconds"}
    assert fields["interval_blocks"] == 1
    between = fields["between_block_rest"]
    assert between["value"] * (60 if between["unit"] == "minutes" else 1) == 120


@pytest.mark.parametrize("rest", ["full rest between holds", "rest until ready"])
def test_strict_conversion_preserves_qualitative_rest_without_inventing_seconds(rest):
    card = _valid_plan()
    block = card["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block.pop("rest")
    block["reps"] = 6
    block["rest_note"] = rest
    source = _faithful_source(card).replace(
        f"- {block['display_name']}",
        f"- {block['display_name']}: 4 sets x 6 reps; {rest}; RPE 7.",
    )
    outcome = build_structured_plan_outcome(card, raw_markdown=source, strict_content=True)
    assert outcome.status == "valid", outcome.errors
    actual = outcome.structured_plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert actual["rest"] is None
    assert actual["rest_note"].casefold() == rest.casefold()


@pytest.mark.parametrize("rest", ["Rest 90-120 sec", "90-120 seconds recovery", "rest: 90 sec"])
def test_strict_conversion_still_rejects_missing_numeric_rest(rest):
    card = _valid_plan()
    block = card["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block.pop("rest")
    block["reps"] = 6
    source = _faithful_source(card).replace(
        f"- {block['display_name']}",
        f"- {block['display_name']}: 4 sets x 6 reps; {rest}; RPE 7.",
    )
    outcome = build_structured_plan_outcome(card, raw_markdown=source, strict_content=True)
    assert outcome.structured_plan is None
    assert any("dropped explicit source rest" in error for error in outcome.errors)
