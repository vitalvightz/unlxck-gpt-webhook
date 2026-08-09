"""Focused regression coverage for authoritative locked Tactical Watch merging."""
from __future__ import annotations

from copy import deepcopy

import pytest

from api.structured_plan_faithfulness import check_structured_faithfulness
from api.structured_plan_generation import build_structured_plan_outcome
from api.structured_plan_locked_merge import merge_locked_structured_content
from api.structured_plan_models import safe_parse_structured_plan

WHY = "Know what happens after the first punches so pocket exchanges stay planned rather than chaotic."
STEPS = [
    "Identify the opponent's most common pocket sequence.",
    "Choose your answer to that sequence.",
    "Choose the finishing shot that best fits the opening.",
    "Decide whether that exchange should end with an exit or a smother.",
]
MINDSET = {
    "intent": "Win the second decision inside the pocket.",
    "focus": "Watch the opponent's response after the first two punches.",
    "reset": "If the exchange loses shape, smother or leave instead of trading blindly.",
    "anchor": "Know the next beat.",
    "context": "SPP pocket planning for a brawler.",
}
PROGRESS = "Rehearse the chosen exchange ending, not just the opening combination."
SOURCE = """D-11 (Tuesday): Fight Tactical Watch
Why: {why}
- Pocket Exchange Map: 10 minutes, tactical review only. No physical load.
  Step 1: {step0}
  Step 2: {step1}
  Step 3: {step2}
  Step 4: {step3}
  Intent: {intent}
  Focus: {focus}
  Reset: {reset}
  Anchor: {anchor}
  Purpose: {context}
  Progress: {progress}
""".format(why=WHY, step0=STEPS[0], step1=STEPS[1], step2=STEPS[2], step3=STEPS[3], progress=PROGRESS, **MINDSET)


def _brief(*, locked=True, day="D-11"):
    return {"weeks": [{"session_roles": [{
        "scheduled_countdown_label": day,
        "countdown_label": "D-99",  # scheduled label has authority
        "display_text": "\n".join(SOURCE.splitlines()[1:]),
        "governance": {
            "selected_drill_locked": locked,
            "selected_drill_name": "Pocket Exchange Map",
            "render_selected_drill_exactly": True,
            "do_not_reselect_or_generalize": True,
        },
        "tactical_watch": {
            "name": "Pocket Exchange Map", "why": WHY, "duration_min": 10,
            "instructions": STEPS, "mindset": MINDSET, "progress": PROGRESS,
        },
    }]}]}


def _plan(*, day="D-11", include=True):
    blocks = [] if not include else [{
        "block_id": "watch-1", "block_type": "mindset",
        "display_name": "Pocket Exchange Map", "duration": {"value": 8, "unit": "minutes"},
        "coaching_cues": ["AI step."], "purpose": "AI purpose.",
        "progression_rule": "AI progress.", "category": "tactical",
        "energy_system": "none", "impact_level": "low",
    }]
    return {"weeks": [{"days": [{"countdown_label": day, "sessions": [{
        "session_type": "mindset", "title": "Fight Tactical Watch", "objective": "AI why.",
        "primary_stressor": "decision-making", "cns_demand": "low",
        "mindset_anchor": {"intent": "Clarify pocket decisions.", "focus_cue": "Read patterns.",
                           "reset_cue": "Reset calmly.", "confidence_anchor": "Control it."},
        "blocks": blocks,
    }]}]}]}


def _merged(plan=None, brief=None):
    return merge_locked_structured_content(plan or _plan(), brief or _brief())


def test_exact_output_is_semantically_unchanged_and_merge_is_idempotent():
    once = _merged().plan
    twice = merge_locked_structured_content(once, _brief()).plan
    assert twice == once
    assert merge_locked_structured_content(deepcopy(once), _brief()).plan == once


@pytest.mark.parametrize("initial", [[], STEPS[:2]])
def test_missing_or_partial_steps_are_replaced_not_appended(initial):
    plan = _plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["coaching_cues"] = initial
    assert _merged(plan).plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["coaching_cues"] == STEPS


def test_all_locked_fields_are_restored_and_why_stays_distinct_from_purpose():
    result = _merged()
    session = result.plan["weeks"][0]["days"][0]["sessions"][0]
    block = session["blocks"][0]
    assert session["objective"] == WHY
    assert session["mindset_anchor"] == {
        "intent": MINDSET["intent"], "focus_cue": MINDSET["focus"],
        "reset_cue": MINDSET["reset"], "confidence_anchor": MINDSET["anchor"],
    }
    assert block["purpose"] == MINDSET["context"] != WHY
    assert block["progression_rule"] == PROGRESS
    assert block["duration"] == {"value": 10, "unit": "minutes"}
    assert block["coaching_cues"] == STEPS
    assert len(result.applied) == 1 and result.unresolved == []


def test_ai_enhancement_metadata_survives():
    session = _merged().plan["weeks"][0]["days"][0]["sessions"][0]
    block = session["blocks"][0]
    assert (block["category"], block["energy_system"], block["impact_level"]) == ("tactical", "none", "low")
    assert (session["primary_stressor"], session["cns_demand"]) == ("decision-making", "low")


def test_unlocked_content_is_untouched():
    plan = _plan()
    result = _merged(plan, _brief(locked=False))
    assert result.plan == plan
    assert result.applied == result.unresolved == []


def test_wrong_day_is_unresolved_and_not_moved_then_faithfulness_rejects():
    plan = _plan(day="D-8")
    result = _merged(plan)
    assert result.plan == plan and result.applied == [] and len(result.unresolved) == 1
    assert any("LOCKED_CONTENT" in issue for issue in check_structured_faithfulness(result.plan, SOURCE, _brief()))


def test_missing_block_is_restored_from_authoritative_role():
    plan = _plan(include=False)
    result = _merged(plan)
    block = result.plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["display_name"] == "Pocket Exchange Map"
    assert block["coaching_cues"] == STEPS
    assert result.unresolved == []
    assert check_structured_faithfulness(result.plan, SOURCE, _brief()) == []


def test_locked_block_in_wrong_same_day_session_moves_without_overwriting_combat():
    plan = _plan()
    plan["weeks"][0]["days"][0]["sessions"][0]["title"] = "Technical-only combat"

    result = _merged(plan)

    sessions = result.plan["weeks"][0]["days"][0]["sessions"]
    assert [session["title"] for session in sessions] == [
        "Technical-only combat",
        "Fight Tactical Watch",
    ]
    assert sessions[0]["blocks"] == []
    assert sessions[1]["blocks"][0]["display_name"] == "Pocket Exchange Map"
    assert result.unresolved == []
    assert check_structured_faithfulness(result.plan, SOURCE, _brief()) == []


def test_omitted_tactical_watch_session_is_created_without_another_model_call():
    plan = {"weeks": [{"days": [{"countdown_label": "D-11", "sessions": []}]}]}

    result = _merged(plan)

    session = result.plan["weeks"][0]["days"][0]["sessions"][0]
    assert session["session_type"] == "skill"
    assert session["title"] == "Fight Tactical Watch"
    assert session["blocks"][0]["display_name"] == "Pocket Exchange Map"
    assert result.unresolved == []
    assert check_structured_faithfulness(result.plan, SOURCE, _brief()) == []


def test_renamed_mindset_block_is_reused_instead_of_duplicated():
    plan = _plan()
    session = plan["weeks"][0]["days"][0]["sessions"][0]
    session["blocks"][0]["display_name"] = "Pocket review"

    result = _merged(plan)

    blocks = result.plan["weeks"][0]["days"][0]["sessions"][0]["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["display_name"] == "Pocket Exchange Map"
    assert blocks[0]["coaching_cues"] == STEPS
    assert check_structured_faithfulness(result.plan, SOURCE, _brief()) == []


def test_schema_valid_card_with_omitted_watch_is_repaired_and_persistable():
    from test_structured_plan_models import _valid_plan

    plan = _valid_plan()
    week = plan["weeks"][0]
    week["countdown_start"] = week["countdown_end"] = "D-11"
    day = week["days"][0]
    day["countdown_label"] = "D-11"
    day["sessions"] = []

    outcome = build_structured_plan_outcome(
        plan,
        raw_markdown=SOURCE,
        planning_brief=_brief(),
    )

    assert outcome.status == "valid"
    assert outcome.structured_plan is not None
    sessions = outcome.structured_plan["weeks"][0]["days"][0]["sessions"]
    assert sessions[0]["title"] == "Fight Tactical Watch"
    assert sessions[0]["blocks"][0]["coaching_cues"] == STEPS
    assert safe_parse_structured_plan(
        outcome.structured_plan, raw_markdown=SOURCE
    ).ok


def test_previous_pocket_exchange_failure_is_repaired_before_faithfulness():
    result = _merged()
    assert check_structured_faithfulness(result.plan, SOURCE, _brief()) == []
