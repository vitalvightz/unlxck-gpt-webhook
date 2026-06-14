"""Tests for the contract-validation gate wired into plan persistence."""
from __future__ import annotations

from dataclasses import dataclass

from api.generation.persistence import (
    _apply_plan_contract_validation,
    _contract_fight_date,
    _contract_report_is_card_rescuable,
)


@dataclass
class _Req:
    fight_date: str = ""
    no_scheduled_fight: bool = False

FIGHT_DATE = "2026-07-01"


def _emit_collector():
    events: list[tuple] = []

    def emit(code, title, detail, **kwargs):
        events.append((code, kwargs))

    return emit, events


def _result(status, weeks, **extra):
    payload = {
        "status": status,
        "plan_text": "plan",
        "planning_brief": {"fight_date": FIGHT_DATE, "weekly_role_map": {"weeks": weeks}},
    }
    payload.update(extra)
    return payload


def test_visible_plan_with_blank_week_is_routed_to_review():
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "camp"}]),  # blank week => drift
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    assert result["status"] == "review_required"
    report = result["why_log"]["plan_contract_validation"]
    assert report["has_errors"] is True
    assert any(code == "plan_contract_review_required" for code, _ in events)


def test_healthy_visible_plan_keeps_its_status():
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "fight", "countdown_range": [6, 0]}]),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    assert result["status"] == "ready"
    assert result["why_log"]["plan_contract_validation"]["has_errors"] is False
    assert events == []


def _clean_card_fields():
    """final_result fields that make has_clean_structured_card() True."""
    return {
        "structured_plan": {"plan_metadata": {"ok": True}},
        "stage2_validator_report": {"structured_plan": {"status": "valid"}},
    }


def test_visible_plan_with_blank_week_is_rescued_by_clean_card():
    # A render/extraction contract finding (blank week) is overridden when the
    # plan carries a schema-valid structured card — trust the card.
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "camp"}], **_clean_card_fields()),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    assert result["status"] == "ready"
    report = result["why_log"]["plan_contract_validation"]
    assert report["has_errors"] is True  # finding still recorded
    assert any(code == "plan_contract_structured_card_rescue" for code, _ in events)
    assert not any(code == "plan_contract_review_required" for code, _ in events)


def test_empty_plan_text_is_not_rescued_even_with_card():
    # An empty body is unrecoverable output integrity; the card cannot vouch for
    # it, so the plan is still routed to review.
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result(
            "ready",
            [{"phase": "fight", "countdown_range": [6, 0]}],
            plan_text="",
            **_clean_card_fields(),
        ),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    assert result["status"] == "review_required"
    assert any(code == "plan_contract_review_required" for code, _ in events)


def test_already_non_visible_status_is_not_changed():
    # held_for_review plans are already gated; record the report, change nothing.
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("held_for_review", [{"phase": "camp"}]),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    assert result["status"] == "held_for_review"
    assert "plan_contract_validation" in result["why_log"]
    assert events == []


def test_contract_fight_date_uses_scheduled_fight_date():
    assert _contract_fight_date(_Req(fight_date=FIGHT_DATE)) == FIGHT_DATE


def test_open_camp_with_stale_fight_date_resolves_to_none():
    # no_scheduled_fight wins even if a stale fight_date lingers on the request.
    assert _contract_fight_date(_Req(fight_date=FIGHT_DATE, no_scheduled_fight=True)) is None


def test_open_camp_with_stale_fight_date_does_not_require_d0():
    # End-to-end through the gate: an open camp whose week never reaches D-0 must
    # not be flagged for a missing fight day once the date is resolved to None.
    emit, events = _emit_collector()
    fight_date = _contract_fight_date(_Req(fight_date=FIGHT_DATE, no_scheduled_fight=True))
    calendar_days = [
        {"weekday": wd, "d_day": d, "calendar_date": f"2026-06-{day:02d}"}
        for wd, d, day in [
            ("Mon", 21, 8), ("Tue", 20, 9), ("Wed", 19, 10), ("Thu", 18, 11),
            ("Fri", 17, 12), ("Sat", 16, 13), ("Sun", 15, 14),
        ]
    ]
    result = _apply_plan_contract_validation(
        _result("ready", [{"countdown_range": [21, 15], "calendar_days": calendar_days}]),
        fight_date=fight_date,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    report = result["why_log"]["plan_contract_validation"]
    assert "fight_day_missing" not in [v["code"] for v in report["violations"]]
    assert result["status"] == "ready"
    assert events == []


def test_gate_never_raises_when_emit_milestone_throws():
    # A throwing milestone callback must not crash the persistence flow; the
    # plan is still returned with the review downgrade applied beforehand.
    def boom(*_args, **_kwargs):
        raise RuntimeError("milestone sink exploded")

    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "camp"}]),  # blank week => routes to review
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=boom,
    )
    assert result["status"] == "review_required"


def test_gate_never_raises_on_garbage_final_result():
    emit, _ = _emit_collector()
    for garbage in (None, "nope", 42, []):
        result = _apply_plan_contract_validation(
            garbage,  # type: ignore[arg-type]
            fight_date=FIGHT_DATE,
            athlete_id="ath-1",
            job_id="job-1",
            emit_milestone=emit,
        )
        assert result is garbage


def test_existing_why_log_entries_are_preserved():
    emit, _ = _emit_collector()
    result = _apply_plan_contract_validation(
        _result(
            "ready",
            [{"phase": "fight", "countdown_range": [6, 0]}],
            why_log={"injury_triage": {"mode": "clear"}},
        ),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    assert result["why_log"]["injury_triage"] == {"mode": "clear"}
    assert "plan_contract_validation" in result["why_log"]


# ---------------------------------------------------------------------------
# _contract_report_is_card_rescuable: defensive allowlist predicate
# ---------------------------------------------------------------------------


def _err(code, severity="error"):
    return {"code": code, "severity": severity, "message": "x"}


def test_contract_rescuable_true_for_known_render_findings():
    assert _contract_report_is_card_rescuable({"violations": [_err("weekly_schedule_blank")]}) is True
    assert _contract_report_is_card_rescuable({"violations": [_err("fight_day_missing")]}) is True
    assert _contract_report_is_card_rescuable(
        {"violations": [_err("calendar_unrenderable"), _err("fight_day_missing")]}
    ) is True


def test_contract_rescuable_false_for_plan_text_empty():
    assert _contract_report_is_card_rescuable({"violations": [_err("plan_text_empty")]}) is False


def test_contract_rescuable_false_for_unknown_code():
    assert _contract_report_is_card_rescuable({"violations": [_err("brand_new_code")]}) is False


def test_contract_rescuable_false_for_mixed_known_and_unrescuable():
    report = {"violations": [_err("weekly_schedule_blank"), _err("plan_text_empty")]}
    assert _contract_report_is_card_rescuable(report) is False


def test_contract_rescuable_false_when_no_error_level_findings():
    # Warning-only reports have nothing to rescue.
    report = {"violations": [_err("weekly_schedule_missing", severity="warning")]}
    assert _contract_report_is_card_rescuable(report) is False
    assert _contract_report_is_card_rescuable({"violations": []}) is False


def test_contract_rescuable_false_for_malformed_reports():
    assert _contract_report_is_card_rescuable(None) is False
    assert _contract_report_is_card_rescuable([]) is False
    assert _contract_report_is_card_rescuable({"violations": "nope"}) is False
    assert _contract_report_is_card_rescuable({"violations": [None]}) is False
    assert _contract_report_is_card_rescuable({"violations": ["bad"]}) is False
    assert _contract_report_is_card_rescuable({"violations": [{"severity": "error"}]}) is False
    assert _contract_report_is_card_rescuable(
        {"violations": [{"severity": "error", "code": ""}]}
    ) is False


def test_contract_unknown_code_with_card_routes_to_review():
    # End-to-end: an unknown error-level finding is NOT rescued even with a card.
    emit, events = _emit_collector()

    def _fake_validate(_final_result, *, fight_date=None):
        return {
            "ran": True,
            "ok": False,
            "has_errors": True,
            "checks": {},
            "violations": [{"code": "brand_new_code", "severity": "error", "message": "x"}],
            "week_count": 1,
        }

    import api.generation.persistence as persistence_module

    original = persistence_module.validate_plan_contract
    persistence_module.validate_plan_contract = _fake_validate
    try:
        result = _apply_plan_contract_validation(
            _result("ready", [{"phase": "fight", "countdown_range": [6, 0]}], **_clean_card_fields()),
            fight_date=FIGHT_DATE,
            athlete_id="ath-1",
            job_id="job-1",
            emit_milestone=emit,
        )
    finally:
        persistence_module.validate_plan_contract = original

    assert result["status"] == "review_required"
    assert any(code == "plan_contract_review_required" for code, _ in events)
