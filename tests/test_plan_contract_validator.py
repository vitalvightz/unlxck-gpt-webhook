"""Tests for the post-generation plan contract / invariant validator."""
from __future__ import annotations

from fightcamp.plan_contract_validator import (
    contract_report_requires_review,
    validate_plan_contract,
)

FIGHT_DATE = "2026-07-01"


def _brief(weeks: list[dict]) -> dict:
    return {"fight_date": FIGHT_DATE, "weekly_role_map": {"weeks": weeks}}


def _result(status: str = "ready", *, weeks: list[dict], **extra) -> dict:
    payload = {
        "status": status,
        "plan_text": "the plan",
        "planning_brief": _brief(weeks),
    }
    payload.update(extra)
    return payload


def _codes(report: dict) -> list[str]:
    return [v["code"] for v in report["violations"]]


def test_healthy_normal_camp_week_passes():
    # countdown_range reaching D-0 renders a full calendar with the fight day.
    report = validate_plan_contract(
        _result(weeks=[{"phase": "fight", "countdown_range": [6, 0]}]),
        fight_date=FIGHT_DATE,
    )
    assert report["ok"] is True
    assert report["has_errors"] is False
    assert report["checks"]["calendar_renderable"] is True
    assert report["checks"]["fight_day_present"] is True
    assert report["violations"] == []
    assert contract_report_requires_review(report) is False


def test_late_fight_countdown_span_renders_like_normal_camp():
    # The late-fight span contract must render a calendar just like a range.
    report = validate_plan_contract(
        _result(weeks=[{"phase": "fight", "countdown_span": {"start_day": 6, "end_day": 0}}]),
        fight_date=FIGHT_DATE,
    )
    assert report["ok"] is True
    assert report["checks"]["calendar_renderable"] is True


def test_blank_week_drift_is_an_error():
    # A structured week with no calendar_days and no resolvable countdown is the
    # classic range/span drift symptom: it renders a blank grid.
    report = validate_plan_contract(
        _result(weeks=[{"phase": "camp"}]),
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is True
    assert report["ok"] is False
    assert "weekly_schedule_blank" in _codes(report)
    assert contract_report_requires_review(report) is True


def test_explicitly_allowed_blank_week_is_not_an_error():
    report = validate_plan_contract(
        _result(
            weeks=[
                {"phase": "fight", "countdown_range": [6, 0]},
                {"phase": "rest", "allow_blank_calendar": True},
            ]
        ),
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is False
    assert "weekly_schedule_blank" not in _codes(report)


def test_missing_fight_day_when_fight_date_set_is_an_error():
    # Renderable week, but the countdown never reaches D-0.
    report = validate_plan_contract(
        _result(weeks=[{"phase": "camp", "countdown_range": [21, 14]}]),
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is True
    assert "fight_day_missing" in _codes(report)


def test_no_fight_date_does_not_require_fight_day():
    # An early-camp week (D-21..D-15) that renders from its own calendar_days but
    # never reaches D-0: with no fight date scheduled, that must not be flagged.
    calendar_days = [
        {"weekday": wd, "d_day": d, "calendar_date": f"2026-06-{day:02d}"}
        for wd, d, day in [
            ("Mon", 21, 8),
            ("Tue", 20, 9),
            ("Wed", 19, 10),
            ("Thu", 18, 11),
            ("Fri", 17, 12),
            ("Sat", 16, 13),
            ("Sun", 15, 14),
        ]
    ]
    report = validate_plan_contract(
        {
            "status": "ready",
            "plan_text": "plan",
            "planning_brief": {
                "weekly_role_map": {"weeks": [{"countdown_range": [21, 15], "calendar_days": calendar_days}]}
            },
        },
        fight_date=None,
    )
    assert "fight_day_missing" not in _codes(report)
    assert report["checks"]["calendar_renderable"] is True
    assert report["has_errors"] is False


def test_stale_brief_fight_date_does_not_assert_d0_when_caller_passes_none():
    # Open-camp safety: the D-0 assertion is driven by the caller's explicit
    # fight_date, never by a stale value lingering in the planning brief.
    report = validate_plan_contract(
        {
            "status": "ready",
            "plan_text": "plan",
            # brief still carries a fight_date, but the caller passes None
            "planning_brief": {
                "fight_date": FIGHT_DATE,
                "weekly_role_map": {"weeks": [{"phase": "camp", "countdown_range": [21, 14]}]},
            },
        },
        fight_date=None,
    )
    assert "fight_day_missing" not in _codes(report)
    assert report["has_errors"] is False


def test_late_fight_variant_missing_session_sequence_is_an_error():
    report = validate_plan_contract(
        _result(
            weeks=[{"phase": "fight", "countdown_range": [6, 0]}],
            stage2_payload={"payload_variant": "late_fight_stage2_payload"},
        ),
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is True
    assert "late_fight_session_sequence_empty" in _codes(report)


def test_late_fight_variant_with_session_sequence_passes():
    report = validate_plan_contract(
        _result(
            weeks=[{"phase": "fight", "countdown_range": [6, 0]}],
            stage2_payload={
                "payload_variant": "late_fight_stage2_payload",
                "late_fight_session_sequence": [{"d_day": 6}, {"d_day": 5}],
            },
        ),
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is False
    assert report["checks"]["late_fight_session_sequence_present"] is True


def test_empty_plan_text_is_an_error():
    report = validate_plan_contract(
        {
            "status": "ready",
            "plan_text": "",
            "final_plan_text": "",
            "planning_brief": _brief([{"phase": "fight", "countdown_range": [6, 0]}]),
        },
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is True
    assert "plan_text_empty" in _codes(report)


def test_missing_weekly_role_map_is_a_warning_not_an_error():
    # Legacy/edge shape: record it, but do not newly block a plan that has no
    # structured weekly schedule at all.
    report = validate_plan_contract(
        {"status": "ready", "plan_text": "plan", "planning_brief": {}},
        fight_date=FIGHT_DATE,
    )
    assert report["has_errors"] is False
    assert report["ok"] is True
    assert "weekly_schedule_missing" in _codes(report)
    assert contract_report_requires_review(report) is False


def test_validator_never_raises_on_garbage_input():
    for garbage in (None, [], "nope", 42, {"planning_brief": "not-a-dict"}):
        report = validate_plan_contract(garbage)  # type: ignore[arg-type]
        assert isinstance(report, dict)
        assert report["ok"] is True


def test_report_is_json_serialisable():
    import json

    report = validate_plan_contract(
        _result(weeks=[{"phase": "camp"}]),
        fight_date=FIGHT_DATE,
    )
    # Must round-trip cleanly: it is persisted into the plan's why_log.
    assert json.loads(json.dumps(report)) == report
