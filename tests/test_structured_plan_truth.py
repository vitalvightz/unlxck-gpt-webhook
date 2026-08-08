"""Focused coverage for deterministic structured-truth shadow validation."""
from __future__ import annotations

import logging

import api.structured_plan_generation as generation
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


def _card(day: str = "D-11", *, progress: bool = True, steps: int = 4) -> dict:
    instructions = [
        "Identify the opponent's most common pocket sequence.",
        "Choose your answer to that sequence.",
        "Choose the finishing shot that best fits the opening.",
        "Decide whether that exchange should end with an exit or a smother.",
    ]
    return {"weeks": [{"days": [{"countdown_label": day, "sessions": [{
        "title": "Fight Tactical Watch",
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
        "Technical-only combat", "Fight Tactical Watch"
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
            "name": "Pocket Exchange Map", "why": "Exact bank purpose.", "duration_min": 12,
            "instructions": ["Exact step one.", "Exact step two."],
            "mindset": {"intent": "Exact intent.", "focus": "Exact focus.", "reset": "Exact reset.", "anchor": "Exact anchor."},
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


def test_missing_locked_step_and_progress_are_machine_readable():
    role = {"governance": {"selected_drill_locked": True, "selected_drill_name": "Pocket Exchange Map"}, "preferred_exercise_names": ["Pocket Exchange Map"]}
    truth = extract_structured_plan_truth(WATCH, {"session_roles": [role]})
    codes = [item.code for item in compare_structured_plan_to_truth(truth, _card(steps=3, progress=False))]
    assert "LOCKED_TEXT_MISMATCH" in codes
    assert "PROGRESS_MISSING" in codes


def test_shadow_exception_is_logged_and_cannot_change_valid_outcome(monkeypatch, caplog):
    from test_structured_plan_models import _valid_plan

    candidate = _valid_plan()
    monkeypatch.setattr(generation, "extract_structured_plan_truth", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    with caplog.at_level(logging.ERROR):
        outcome = generation.build_structured_plan_outcome(candidate, raw_markdown="")
    assert outcome.status == "valid"
    assert outcome.structured_plan is not None
    assert "comparison_failed" in caplog.text
