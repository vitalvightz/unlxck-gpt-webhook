"""Regression tests for the PR1 rendering boundary, not Stage 1 selection."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fightcamp.closed_conditioning_render import (
    MISSING_CODE, restore_missing_conditioning,
)
from fightcamp.stage2_pipeline import build_stage2_retry
from fightcamp.stage2_retry_contract import apply_mandatory_render_guard


DOSE = "4 x 30 sec work; 90 sec rest; RPE 8"
NAMES = ["Plyo Step-Up Intervals", "KB Swing Intervals", "Burpee Broad Jumps"]


def _brief(names=None, day=16):
    names = NAMES if names is None else names
    role = {
        "role_key": "controlled_repeatability_day",
        "category": "conditioning",
        "athlete_facing_label": "Fight-pace conditioning",
        "scheduled_day_hint": "thursday",
        "scheduled_countdown_label": f"D-{day}",
        "selected_exercise_assignments": [
            {"slot_id": f"slot-{i}", "name": name, "source_phase": "SPP",
             "slot_group": "conditioning_slots", "effective_prescription": DOSE}
            for i, name in enumerate(names)
        ],
    }
    return {"athlete_snapshot": {}, "candidate_pools": {"SPP": {"conditioning_slots": []}},
            "weekly_role_map": {"weeks": [{"week_index": 1, "phase": "SPP",
                "calendar_days": [{"weekday": "thursday", "d_day": day}],
                "session_roles": [role]}]}}


def _text(names=None, day=16):
    names = NAMES[:1] if names is None else names
    return (f"SPP — Week 1 (D-{day} to D-{day}) — Repeatability\n"
            f"### D-{day} (Thursday) — Fight-pace conditioning\n"
            "Why: preserve repeatability without adding unnecessary fatigue.\n"
            + "\n".join(f"- {name}: {DOSE}" for name in names)
            + "\nEasier: reduce rounds if technique deteriorates.\n"
            + "Stop: stop if pain rises.\n")


def _report(names=None, day=16, extra=None):
    names = NAMES[1:] if names is None else names
    return {"errors": [{"code": MISSING_CODE, "scheduled_d_day": day,
                         "role_key": "controlled_repeatability_day", "exercise": name,
                         "effective_prescription": DOSE, "severity": "blocker"}
                        for name in names] + (extra or []), "warnings": []}


def test_three_selected_exercises_are_restored_without_extra_work():
    result = restore_missing_conditioning(planning_brief=_brief(), final_plan_text=_text(),
                                          validator_report=_report())
    assert result["unresolved"] == []
    assert [item["exercise"] for item in result["applied"]] == NAMES[1:]
    for name in NAMES:
        assert result["text"].count(f"- {name}: {DOSE}") == 1
    assert result["text"].count("4 x 30 sec work") == 3
    assert result["text"].count("D-16 (Thursday)") == 1
    assert "Easier:" in result["text"] and "Stop:" in result["text"]


def test_two_selected_aerobic_exercises_are_restored_on_their_day():
    names = ["Nasal Shadowboxing Flow (Gas Tank)", "Jump Rope Conditioning"]
    brief = _brief(names, day=15)
    brief["weekly_role_map"]["weeks"][0]["session_roles"][0]["selected_exercise_assignments"] = [
        {"slot_id": f"a-{i}", "name": name, "source_phase": "SPP",
         "slot_group": "conditioning_slots", "effective_prescription": "12-20min continuous"}
        for i, name in enumerate(names)
    ]
    source = _text(names[:1], day=15).replace(DOSE, "12-20min continuous")
    report = _report(names[1:], day=15)
    result = restore_missing_conditioning(planning_brief=brief, final_plan_text=source,
                                          validator_report=report)
    assert result["unresolved"] == []
    assert result["text"].count("Nasal Shadowboxing Flow (Gas Tank): 12-20min continuous") == 1
    assert result["text"].count("Jump Rope Conditioning: 12-20min continuous") == 1
    assert "D-16" not in result["text"]


def test_stale_missing_finding_does_not_duplicate_existing_work():
    source = _text(NAMES)
    result = restore_missing_conditioning(planning_brief=_brief(), final_plan_text=source,
                                          validator_report=_report())
    assert result["text"] == source
    assert result["unresolved"] == []


def test_missing_render_and_independent_goal_failure_have_separate_decisions():
    goal = {"code": "goal_preservation_failed", "goal": "speed",
            "message": "No qualifying effective coverage.", "severity": "blocker"}
    retry = build_stage2_retry(stage1_result={"planning_brief": _brief()},
                               final_plan_text=_text(), validator_report=_report(extra=[goal]))
    assert retry["needs_retry"] is True
    assert retry["requires_planner_regeneration"] is True
    assert "KB Swing Intervals" in retry["repair_prompt"]
    assert "Burpee Broad Jumps" in retry["repair_prompt"]
    assert retry["validator_report"]["release_decision"] == "hold"


def test_genuine_goal_failure_alone_does_not_request_a_render_retry():
    report = {"errors": [{"code": "goal_preservation_failed", "goal": "speed"}], "warnings": []}
    retry = build_stage2_retry(stage1_result={"planning_brief": _brief()},
                               final_plan_text=_text(NAMES), validator_report=report)
    assert retry["needs_retry"] is False
    assert retry["requires_planner_regeneration"] is True
    assert retry["repair_prompt"] is None


def test_missing_source_authority_cannot_be_invented_by_the_model():
    report = _report(["Unknown Exercise"])
    retry = build_stage2_retry(stage1_result={"planning_brief": _brief()},
                               final_plan_text=_text(), validator_report=report)
    assert retry["needs_retry"] is False
    assert retry["requires_planner_regeneration"] is True


def test_missing_canonical_week_and_ambiguous_day_are_not_reconstructed():
    brief = _brief()
    for source in ("### D-16 (Thursday) — Fight-pace conditioning\n- Plyo Step-Up Intervals: " + DOSE,
                   _text().replace("### D-16", "### D-17")):
        result = restore_missing_conditioning(planning_brief=brief, final_plan_text=source,
                                              validator_report=_report())
        assert result["text"] == source
        assert result["applied"] == []
        assert result["unresolved"]


def test_explicit_safety_conflict_prevents_deterministic_restoration():
    report = _report(extra=[{"code": "restriction_violation", "scheduled_d_day": 16,
                             "line": "- KB Swing Intervals", "severity": "blocker"}])
    source = _text()
    result = restore_missing_conditioning(planning_brief=_brief(), final_plan_text=source,
                                          validator_report=report)
    assert result["text"] == source
    assert result["unresolved"][0]["reason"] == "safety_finding_requires_review"


def test_mandatory_guard_is_narrow_and_preserves_explicit_holds():
    assert apply_mandatory_render_guard(_report())["release_decision"] == "hold"
    assert apply_mandatory_render_guard({"errors": [{"code": "goal_preservation_failed"}]})["is_publishable"] is False
    assert apply_mandatory_render_guard({"warnings": [{"code": "generic_filler_phrase"}]})["release_decision"] == "publish_with_flags"
    assert apply_mandatory_render_guard({"release_decision": "hold", "errors": []})["release_decision"] == "hold"


def test_complete_clean_plan_does_not_request_a_retry():
    retry = build_stage2_retry(stage1_result={"planning_brief": _brief()},
                               final_plan_text=_text(NAMES), validator_report={"errors": [], "warnings": []})
    assert retry["needs_retry"] is False
    assert retry["repair_prompt"] is None


def test_model_repair_failure_retains_source_and_budget(monkeypatch):
    from api.stage2_automation import Stage2AutomationError
    from api.stage2_conditioning_repair import run_stage2_render_repair
    import fightcamp.stage2_pipeline as pipeline

    brief = _brief(day=13)
    original = _text(day=13)
    report = apply_mandatory_render_guard(_report(day=13))
    review = {"validator_report": report, "status": "FAIL", "needs_retry": True}
    error = Stage2AutomationError("test repair failure")
    error.stage2_cost = {"stage2_input_tokens": 5, "stage2_output_tokens": 0,
                         "stage2_total_tokens": 5, "stage2_estimated_cost_usd": 0.0}
    automator = SimpleNamespace(_generate_text=AsyncMock(side_effect=error))
    monkeypatch.setattr(pipeline, "review_stage2_output", lambda **kw: review)
    result = asyncio.run(run_stage2_render_repair(
        automator=automator, stage1_result={"planning_brief": brief}, planning_brief=brief,
        first_review=review, first_pass_text=original,
        first_pass_cost={"stage2_input_tokens": 10, "stage2_output_tokens": 5,
                         "stage2_total_tokens": 15, "stage2_estimated_cost_usd": 0.0},
        reviewed_report=lambda r: r, source="test",
    ))
    assert automator._generate_text.await_count == 1
    assert result["attempt_count"] == 2
    assert result["cost"]["stage2_total_tokens"] == 20
    assert result["text"] == original
    assert result["review"]["validator_report"]["release_decision"] == "hold"
    assert result["audit"]["status"] == "model_request_failed"
