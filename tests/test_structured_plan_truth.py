"""Focused coverage for deterministic structured-truth shadow validation."""

from __future__ import annotations

import logging

import pytest

from api.structured_plan_truth import (
    compare_structured_plan_to_truth,
    extract_structured_plan_truth,
)

BASIC = """D-12 (Monday) - Neural speed touch
Why: maintain explosive hip-drive.
- Kettlebell swing — 2-3 sets x 6 reps; RPE 6-7. Rest 2-3 min.
"""

WATCH = """D-11 (Tuesday): Fight Tactical Watch
Why: Know what happens after the first punches.
- Pocket Exchange Map: 10 minutes, tactical review only. No physical load.
  Step 1: Identify the opponent's most common pocket sequence.
  Step 2: Choose your answer to that sequence.
  Step 3: Choose the finishing shot that best fits the opening.
  Step 4: Decide whether that exchange should end with an exit or a smother.
  Intent: Win the second decision inside the pocket.
  Focus: Watch the opponent's response after the first two punches.
  Reset: If the exchange loses shape, smother or leave instead of trading blindly.
  Anchor: Know the next beat.
  Purpose: SPP pocket planning for a brawler.
  Progress: Rehearse the chosen exchange ending, not just the opening combination.
"""


def _card(
    day: str = "D-11",
    *,
    progress: bool = True,
    steps: int = 4,
    session_title: str = "Fight Tactical Watch",
) -> dict:
    instructions = [
        "Identify the opponent's most common pocket sequence.",
        "Choose your answer to that sequence.",
        "Choose the finishing shot that best fits the opening.",
        "Decide whether that exchange should end with an exit or a smother.",
    ]
    return {"weeks": [{"days": [{"countdown_label": day, "sessions": [{
        "title": session_title,
        "mindset_anchor": {
            "intent": "Win the second decision inside the pocket.",
            "focus_cue": "Watch the opponent's response after the first two punches.",
            "reset_cue": "If the exchange loses shape, smother or leave instead of trading blindly.",
            "confidence_anchor": "Know the next beat.",
        },
        "blocks": [{
            "display_name": "Pocket Exchange Map",
            "duration": {"value": 10, "unit": "minutes"},
            "purpose": "SPP pocket planning for a brawler.",
            "coaching_cues": instructions[:steps],
            "progression_rule": "Rehearse the chosen exchange ending, not just the opening combination." if progress else None,
        }],
    }]}]}]}


def test_extracts_basic_dday_and_explicit_prescription():
    truth = extract_structured_plan_truth(BASIC)
    day = truth.days[0]
    block = day.sessions[0].blocks[0]
    assert (day.countdown_label, day.weekday, day.sessions[0].title) == (
        "D-12", "Monday", "Neural speed touch"
    )
    assert (block.display_name, block.sets, block.reps, block.effort, block.rest) == (
        "Kettlebell swing", "2-3", "6", "RPE 6-7", "2-3 min"
    )


def test_multiple_sessions_on_one_dday_are_not_collapsed():
    truth = extract_structured_plan_truth(
        "D-11 - Technical-only combat\n- Pads — 3 rounds\n"
        "D-11 - Fight Tactical Watch\n- Review — 10 min\n"
    )
    assert len(truth.days) == 1
    assert [session.title for session in truth.days[0].sessions] == [
        "Technical-only combat",
        "Fight Tactical Watch",
    ]


def test_tactical_watch_text_extracts_exact_fields():
    block = extract_structured_plan_truth(WATCH).days[0].sessions[0].blocks[0]
    assert block.display_name == "Pocket Exchange Map"
    assert block.duration == "10 minutes"
    assert len(block.steps) == 4
    assert block.steps[2] == "Choose the finishing shot that best fits the opening."
    assert block.intent == "Win the second decision inside the pocket."
    assert block.focus == "Watch the opponent's response after the first two punches."
    assert block.reset.startswith("If the exchange loses shape")
    assert block.anchor == "Know the next beat."
    assert block.purpose == "SPP pocket planning for a brawler."
    assert block.progress.startswith("Rehearse the chosen exchange ending")


def test_locked_planning_brief_metadata_is_authoritative():
    brief = {"weeks": [{"session_roles": [{
        "countdown_label": "D-11",
        "preferred_exercise_names": ["Pocket Exchange Map"],
        "governance": {"selected_drill_locked": True, "selected_drill_name": "Pocket Exchange Map"},
        "tactical_watch": {
            "name": "Pocket Exchange Map", "why": "Exact session why.", "duration_min": 12,
            "instructions": ["Exact step one.", "Exact step two."],
            "mindset": {
                "intent": "Exact intent.", "focus": "Exact focus.",
                "reset": "Exact reset.", "anchor": "Exact anchor.",
                "context": "Exact bank purpose.",
            },
            "progress": "Exact progress.",
        },
    }]}]}
    block = extract_structured_plan_truth(WATCH, brief).days[0].sessions[0].blocks[0]
    assert block.locked is True
    assert block.duration == "12 min"
    assert block.steps == ("Exact step one.", "Exact step two.")
    assert (block.purpose, block.progress, block.intent) == (
        "Exact bank purpose.", "Exact progress.", "Exact intent."
    )


def test_matching_card_has_no_differences_and_ignores_cosmetic_metadata():
    truth = extract_structured_plan_truth(WATCH)
    card = _card()
    card["plan_metadata"] = {"title": "A different generated headline", "plan_id": "cosmetic-id"}
    assert compare_structured_plan_to_truth(truth, card) == []


def test_misplaced_block_reports_day_mismatch():
    truth = extract_structured_plan_truth(WATCH.replace("D-11", "D-10", 1))
    assert {item.code for item in compare_structured_plan_to_truth(truth, _card(day="D-8"))} >= {"DAY_MISMATCH"}


def test_block_in_wrong_same_day_session_does_not_satisfy_truth():
    truth = extract_structured_plan_truth(WATCH)
    codes = {
        item.code
        for item in compare_structured_plan_to_truth(
            truth, _card(session_title="Technical-only combat")
        )
    }
    assert "SESSION_MISSING" in codes


def test_empty_truth_session_still_requires_matching_session():
    truth = extract_structured_plan_truth("D-9 - Recovery check-in\n")
    assert [
        item.code
        for item in compare_structured_plan_to_truth(truth, {"weeks": [{"days": []}]})
    ] == ["SESSION_MISSING"]


def test_load_and_effort_mismatches_are_compared():
    truth = extract_structured_plan_truth(
        "D-10 - Strength touch\n- Trap-bar deadlift — 2 sets x 3 reps; 85% 1RM; RPE 6-7.\n"
    )
    card = {
        "weeks": [{"days": [{"countdown_label": "D-10", "sessions": [{
            "title": "Strength touch",
            "blocks": [{
                "display_name": "Trap-bar deadlift", "sets": 2, "reps": 3,
                "load": {"method": "percentage", "value": 70, "unit": "percent", "ref": "1RM"},
                "effort": {"method": "RPE", "value": "9"},
            }],
        }]}]}],
    }
    mismatched_fields = {
        item.field for item in compare_structured_plan_to_truth(truth, card)
    }
    assert {"load", "effort"} <= mismatched_fields
    block = card["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block["load"].update(value=85)
    block["effort"]["value"] = "6-7"
    assert compare_structured_plan_to_truth(truth, card) == []


def test_stop_rule_in_progression_rule_or_red_flag_is_accepted():
    source = "D-10 - Shoulder support\n- Cable row — 2 sets x 8 reps\n  Stop: sharp shoulder pain.\n"
    truth = extract_structured_plan_truth(source)
    base = {
        "weeks": [{"days": [{"countdown_label": "D-10", "sessions": [{
            "title": "Shoulder support",
            "blocks": [{"display_name": "Cable row", "sets": 2, "reps": 8}],
        }]}]}],
    }
    block = base["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block["progression_rule"] = "Stop: sharp shoulder pain."
    assert compare_structured_plan_to_truth(truth, base) == []
    block.pop("progression_rule")
    block["red_flags"] = [{"display_text": "Sharp shoulder pain.", "action": "Stop."}]
    assert compare_structured_plan_to_truth(truth, base) == []


def test_fast_burst_interval_is_work_not_total_duration():
    block = extract_structured_plan_truth(
        "D-10 - Speed\n- Sprint — 3 x 5-6 sec fast relaxed bursts; full recovery 90-120 sec.\n"
    ).days[0].sessions[0].blocks[0]
    assert block.work == "5-6 sec"
    assert block.rest == "90-120 sec"
    assert block.duration is None


def test_missing_locked_step_and_progress_are_machine_readable():
    role = {"governance": {"selected_drill_locked": True, "selected_drill_name": "Pocket Exchange Map"}, "preferred_exercise_names": ["Pocket Exchange Map"]}
    truth = extract_structured_plan_truth(WATCH, {"session_roles": [role]})
    codes = [item.code for item in compare_structured_plan_to_truth(truth, _card(steps=3, progress=False))]
    assert "LOCKED_TEXT_MISMATCH" in codes
    assert "PROGRESS_MISSING" in codes


def test_shadow_exception_is_logged_and_cannot_change_valid_outcome(monkeypatch, caplog):
    pytest.importorskip("pydantic")
    import api.structured_plan_generation as generation

    from test_structured_plan_models import _valid_plan

    candidate = _valid_plan()
    monkeypatch.setattr(generation, "extract_structured_plan_truth", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    with caplog.at_level(logging.ERROR):
        outcome = generation.build_structured_plan_outcome(candidate, raw_markdown="")
    assert outcome.status == "valid"
    assert outcome.structured_plan is not None
    assert "comparison_failed" in caplog.text
