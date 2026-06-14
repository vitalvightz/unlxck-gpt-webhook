"""Tests for the deterministic-first authority + safety audits (PR-5).

The audits are debug-only: they surface coach_gated leakage, computed_support vs
structured_plan conflicts, and duplicate rendered strings as warnings. They must
never mutate the plan, never resolve conflicts, and never change the plan
status / lifecycle / fallback behaviour.
"""
from __future__ import annotations

import copy

from api.structured_plan_generation import (
    build_structured_plan_outcome,
    build_structured_plan_prompt,
)
from api.structured_plan_safety import (
    audit_structured_plan,
    detect_coach_gated_leakage,
    detect_computed_support_conflicts,
    detect_duplicate_rendered_strings,
)
from fightcamp.stage2_payload import build_computed_support

from test_structured_plan_models import _valid_plan


def _support(**flags) -> dict:
    base = {"weight": 70, "mental_block": ["confidence"]}
    base.update(flags)
    return build_computed_support(flags=base, phases=["GPP", "SPP", "TAPER"])


def _plan(nutrition=None, weeks=None) -> dict:
    return {
        "nutrition": nutrition or {"summary": "Eat well.", "daily_focus": "", "weight_cut_warning": None},
        "weeks": weeks or [],
    }


# --- coach_gated leakage ----------------------------------------------------


def test_coach_gated_leakage_detected_when_copied_into_athlete_facing():
    support = _support(weight_cut_risk=True, weight_cut_pct=7.0, fatigue="high")
    gated = support["nutrition"]["by_phase"]["TAPER"]["coach_gated"]["acute_cut_protocol"]
    leaked_text = gated["bicarbonate_g_per_kg"]

    plan = _plan(nutrition={"summary": f"Pre-fight: {leaked_text}", "daily_focus": ""})
    warnings = detect_coach_gated_leakage(plan, support)

    assert any(w.startswith("LEAKAGE") for w in warnings), warnings


def test_no_leakage_when_athlete_facing_is_clean():
    support = _support(weight_cut_risk=True, weight_cut_pct=7.0, fatigue="high")
    plan = _plan(nutrition={"summary": "Hydrate and fuel around sessions.", "daily_focus": ""})
    assert detect_coach_gated_leakage(plan, support) == []


# --- computed_support conflicts --------------------------------------------


def test_macro_conflict_is_flagged():
    support = _support()  # protein envelope ~112-175 g/day for 70kg
    plan = _plan(nutrition={"summary": "Protein: 300 g/day.", "daily_focus": ""})
    warnings = detect_computed_support_conflicts(plan, support)
    assert any("protein_g_per_day" in w and w.startswith("CONFLICT") for w in warnings), warnings


def test_hydration_conflict_is_flagged():
    support = _support()  # hydration ~2100-2800 ml/day for 70kg
    plan = _plan(nutrition={"summary": "Hydration: 500 ml/day.", "daily_focus": ""})
    warnings = detect_computed_support_conflicts(plan, support)
    assert any("hydration_ml_per_day" in w for w in warnings), warnings


def test_weight_cut_risk_conflict_is_flagged():
    support = _support(weight_cut_risk=True, weight_cut_pct=7.0)  # severe band
    plan = _plan(nutrition={
        "summary": "Standard fuelling.",
        "daily_focus": "",
        "weight_cut_warning": {"risk_level": "green", "display_text": "minor", "requires_professional_support": False},
    })
    warnings = detect_computed_support_conflicts(plan, support)
    assert any("weight-cut risk understated" in w for w in warnings), warnings


def test_matching_computed_support_produces_no_conflict_warning():
    support = _support(weight_cut_risk=True, weight_cut_pct=7.0)
    plan = _plan(nutrition={
        "summary": "Protein 120-150 g/day; hydration 2200-2700 ml/day.",
        "daily_focus": "",
        "weight_cut_warning": {"risk_level": "red", "display_text": "supervised", "requires_professional_support": True},
    })
    assert detect_computed_support_conflicts(plan, support) == []


def test_no_conflict_when_no_computed_support():
    plan = _plan(nutrition={"summary": "Protein: 300 g/day.", "daily_focus": ""})
    assert detect_computed_support_conflicts(plan, None) == []


def test_per_kg_coefficients_do_not_create_macro_conflict():
    # "3-6 g/kg" is a per-kg coefficient, NOT a daily total — it must never be
    # parsed as 3-6 g/day and flagged against the daily-gram computed envelope.
    support = _support()
    plan = _plan(nutrition={
        "summary": "Carbs: 3-6 g/kg around sessions; protein 1.6-2.2 g/kg.",
        "daily_focus": "Fats 0.8-1.0 g/kg daily intake guidance.",
    })
    assert detect_computed_support_conflicts(plan, support) == []


def test_explicit_daily_total_still_conflicts():
    # A genuine per-day total that contradicts the envelope is still flagged.
    support = _support()
    plan = _plan(nutrition={"summary": "Carbs: 1500 g/day.", "daily_focus": ""})
    warnings = detect_computed_support_conflicts(plan, support)
    assert any("carbs_g_per_day" in w for w in warnings), warnings


# --- duplicates -------------------------------------------------------------


def _day_with_anchors(day_anchor: dict, session_anchor: dict) -> dict:
    return {
        "date": "2026-07-01",
        "today_card": {"headline": "Go", "mindset_anchor": day_anchor},
        "sessions": [{"mindset_anchor": session_anchor}],
    }


def test_duplicate_day_session_mindset_is_detected():
    anchor = {"intent": "Drive forward", "focus_cue": "Sharp hands", "reset_cue": "Breathe"}
    plan = {"weeks": [{"days": [_day_with_anchors(anchor, dict(anchor))]}]}
    warnings = detect_duplicate_rendered_strings(plan)
    assert any("mindset_anchor identical" in w for w in warnings), warnings


def test_distinct_day_session_mindset_is_not_flagged():
    day_anchor = {"intent": "Drive forward", "focus_cue": "Sharp hands", "reset_cue": "Breathe"}
    session_anchor = {"intent": "Stay loose", "focus_cue": "Move feet", "reset_cue": "Exhale"}
    plan = {"weeks": [{"days": [_day_with_anchors(day_anchor, session_anchor)]}]}
    assert detect_duplicate_rendered_strings(plan) == []


# --- audit wiring + invariants ---------------------------------------------


def test_audit_does_not_mutate_inputs():
    support = _support(weight_cut_risk=True, weight_cut_pct=7.0)
    plan = _plan(nutrition={"summary": "Protein: 300 g/day.", "daily_focus": ""})
    plan_before = copy.deepcopy(plan)
    support_before = copy.deepcopy(support)
    audit_structured_plan(plan, support)
    assert plan == plan_before
    assert support == support_before


def test_outcome_surfaces_warnings_without_changing_status():
    # A schema-valid plan still validates; the audit only adds debug warnings.
    support = _support()
    outcome = build_structured_plan_outcome(
        _valid_plan(), raw_markdown="# raw", computed_support=support
    )
    assert outcome.status == "valid"
    debug = outcome.as_debug()
    assert "warnings" in debug
    assert isinstance(debug["warnings"], list)


def test_prompt_keeps_valid_session_anchor_instead_of_omitting():
    # A session anchor must stay valid (schema requires it); the converter varies
    # phrasing rather than omitting an identical anchor.
    prompt = build_structured_plan_prompt(plan_markdown="PLAN")
    assert "vary phrasing while" in prompt
    assert "keeping a valid session-level mindset_anchor" in prompt
    assert "vary it or omit it" not in prompt


def test_plan_text_fallback_still_works():
    # No computed_support, unsalvageable payload -> fallback status unchanged.
    outcome = build_structured_plan_outcome(["not", "a", "plan"], raw_markdown="# raw")
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert outcome.warnings == []
    # And a skipped attempt is still skipped.
    assert build_structured_plan_outcome(None).status == "not_attempted"
