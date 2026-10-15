"""Persist an exact, verified planner-backed card after model countdown mistakes."""

from api.stage2_automation import _recover_coverage_failed_card
from api.structured_plan_generation import StructuredPlanOutcome
from test_structured_salvage_planner_coverage import _brief, _source_text, _sessions_by_dday, _SC_COUNT, _sc_counts


def _lost_card(*errors):
    return StructuredPlanOutcome(
        status="invalid_fallback_used",
        errors=list(errors),
        warnings=["salvaged: MISPLACED: converted strength changed D-day"],
    )


def test_converter_day_mistake_recovers_valid_planner_card_with_exact_membership():
    original = _lost_card(
        "planner_coverage: D-23 'primary_strength_day' selected exercises ['Push-Up (Weighted)'] "
        "are missing from the structured card",
    )
    repaired = _recover_coverage_failed_card(
        original, planning_brief=_brief(), plan_text=_source_text(),
    )
    assert repaired.status == "valid", repaired.errors
    assert repaired.structured_plan is not None
    assert _sc_counts(repaired.structured_plan) == _SC_COUNT
    days = _sessions_by_dday(repaired.structured_plan)
    assert any(
        block["display_name"] == "Push-Up (Weighted)"
        for session in days[23] for block in session["blocks"]
    )
    assert any("deterministic_source_recovery" in w for w in repaired.warnings)
    assert original.structured_plan is None  # Never modifies source outcome.


def test_never_recover_an_unrelated_or_mixed_conversion_failure():
    for errors in (
        ("faithfulness: INTRODUCED: injected work",),
        ("planner_coverage: D-23 lost selected exercise", "faithfulness: INTRODUCED: unrelated"),
        (),
    ):
        original = _lost_card(*errors)
        assert _recover_coverage_failed_card(
            original, planning_brief=_brief(), plan_text=_source_text(),
        ) is original


def test_refuses_recovery_without_authoritative_text_or_role_map():
    original = _lost_card("planner_coverage: D-23 selected exercise lost")
    assert _recover_coverage_failed_card(original, planning_brief={}, plan_text=_source_text()) is original
    assert _recover_coverage_failed_card(original, planning_brief=_brief(), plan_text="") is original
