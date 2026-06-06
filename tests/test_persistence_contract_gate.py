"""Tests for the contract-validation gate wired into plan persistence."""
from __future__ import annotations

from api.generation.persistence import _apply_plan_contract_validation

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
