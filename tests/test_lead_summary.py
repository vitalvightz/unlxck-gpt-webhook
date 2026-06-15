"""Tests for the deterministic injury / weight-cut lead summary."""

from __future__ import annotations

from fightcamp.lead_summary import render_lead_summary
from fightcamp.stage2_validator import validate_stage2_output


def test_no_summary_when_no_injury_or_cut():
    assert render_lead_summary({"athlete_model": {"sport": "boxing"}}) == ""
    assert render_lead_summary({}) == ""
    assert render_lead_summary({"athlete_model": {}}) == ""


def test_injury_summary_includes_injury_keyword_and_text():
    summary = render_lead_summary(
        {"athlete_model": {"has_active_injury": True, "injuries": ["left knee irritation"]}}
    )
    assert "## Readiness & Constraints" in summary
    assert "Injury watch" in summary
    assert "left knee irritation" in summary
    # A keyword the validator's injury lead pattern recognises.
    assert "restrictions" in summary or "rehab" in summary


def test_weight_cut_summary_includes_cut_keyword():
    summary = render_lead_summary({"athlete_model": {"weight_cut_risk": True}})
    assert "Weight cut" in summary
    assert "cut stress" in summary and "target weight" in summary


def test_weight_cut_high_pressure_wording():
    high = render_lead_summary(
        {"athlete_model": {"weight_cut_risk": True, "readiness_flags": ["aggressive_weight_cut"]}}
    )
    assert "under pressure" in high
    low = render_lead_summary(
        {"athlete_model": {"weight_cut_risk": True, "fatigue": "low", "days_until_fight": 60}}
    )
    assert "under pressure" not in low


def test_readiness_flags_drive_detection():
    # injury_management flag counts as an active injury even without an injuries list.
    summary = render_lead_summary({"athlete_model": {"readiness_flags": ["injury_management"]}})
    assert "Injury watch" in summary
    # active_weight_cut flag counts as an active cut.
    summary = render_lead_summary({"athlete_model": {"readiness_flags": ["active_weight_cut"]}})
    assert "Weight cut" in summary


def _brief_with_injury_and_cut() -> dict:
    return {
        "athlete_model": {
            "sport": "boxing",
            "has_active_injury": True,
            "injuries": ["left knee irritation"],
            "weight_cut_risk": True,
            "readiness_flags": [],
            "days_until_fight": 40,
        }
    }


def test_lead_summary_satisfies_validator_contract():
    brief = _brief_with_injury_and_cut()
    summary = render_lead_summary(brief)
    plan_text = f"# FIGHT CAMP PLAN\n\n{summary}\n\n## PHASE 1: GPP\n- Back Squat - 4x5\n"

    report = validate_stage2_output(planning_brief=brief, final_plan_text=plan_text)
    codes = {warning.get("code") for warning in report["warnings"]}
    assert "missing_injury_lead_summary" not in codes
    assert "missing_weight_cut_lead_summary" not in codes


def test_validator_flags_missing_summaries_without_lead():
    # Control: the same brief without a lead summary trips both codes, proving
    # the summary is what satisfies the contract.
    brief = _brief_with_injury_and_cut()
    plan_text = "# FIGHT CAMP PLAN\n\n## PHASE 1: GPP\n- Back Squat - 4x5\n"

    report = validate_stage2_output(planning_brief=brief, final_plan_text=plan_text)
    codes = {warning.get("code") for warning in report["warnings"]}
    assert "missing_injury_lead_summary" in codes
    assert "missing_weight_cut_lead_summary" in codes
