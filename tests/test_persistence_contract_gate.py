"""Tests for observational post-generation plan-contract validation."""
from __future__ import annotations

from dataclasses import dataclass

from api.generation.persistence import (
    _apply_plan_contract_validation,
    _contract_fight_date,
    _contract_report_is_card_rescuable,
    _contract_report_is_flaggable,
)


@dataclass
class _Req:
    fight_date: str = ""
    no_scheduled_fight: bool = False


FIGHT_DATE = "2026-07-01"


def _emit_collector():
    events: list[tuple] = []

    def emit(code, title, detail, **kwargs):
        events.append((code, title, detail, kwargs))

    return emit, events


def _result(status, weeks, **extra):
    payload = {
        "status": status,
        "plan_text": "plan",
        "planning_brief": {
            "fight_date": FIGHT_DATE,
            "weekly_role_map": {"weeks": weeks},
        },
    }
    payload.update(extra)
    return payload


def _err(code, severity="error"):
    return {"code": code, "severity": severity, "message": "x"}


def _clean_card_fields():
    return {
        "structured_plan": {"plan_metadata": {"ok": True}},
        "stage2_validator_report": {
            "structured_plan": {"status": "valid"}
        },
    }


def test_visible_plan_with_blank_week_is_recorded_without_status_change():
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "camp"}]),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )

    assert result["status"] == "ready"
    report = result["why_log"]["plan_contract_validation"]
    assert report["has_errors"] is True
    assert any(v.get("code") == "weekly_schedule_blank" for v in report["violations"])
    assert not any(event[0] == "plan_contract_review_required" for event in events)


def test_unknown_contract_finding_is_observational(monkeypatch):
    import api.generation.persistence as persistence

    report = {
        "ran": True,
        "ok": False,
        "has_errors": True,
        "checks": {},
        "violations": [
            {
                "code": "brand_new_contract_code",
                "severity": "error",
                "message": "future validator disagreement",
            }
        ],
        "week_count": 1,
    }
    monkeypatch.setattr(
        persistence,
        "validate_plan_contract",
        lambda *_args, **_kwargs: report,
    )
    emit, events = _emit_collector()

    result = _apply_plan_contract_validation(
        _result("publishable_with_flags", [{"phase": "fight", "countdown_range": [6, 0]}]),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )

    assert result["status"] == "publishable_with_flags"
    assert result["plan_text"] == "plan"
    assert result["why_log"]["plan_contract_validation"] == report
    assert not any(event[0] == "plan_contract_review_required" for event in events)


def test_contract_finding_does_not_need_structured_card_rescue():
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "camp"}], **_clean_card_fields()),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )

    assert result["status"] == "ready"
    assert result["why_log"]["plan_contract_validation"]["has_errors"] is True
    # A structured card is no longer a release authority or rescue mechanism.
    assert not any(event[0] == "plan_contract_review_required" for event in events)


def test_blocked_structured_card_cannot_turn_contract_finding_into_hold():
    from api.structured_plan_generation import has_clean_structured_card

    blocked_fields = {
        "structured_plan": {"plan_metadata": {"ok": True}},
        "stage2_validator_report": {
            "structured_plan": {"status": "blocked_by_safety_audit"}
        },
    }
    assert has_clean_structured_card(blocked_fields) is False

    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "camp"}], **blocked_fields),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )

    assert result["status"] == "ready"
    assert result["plan_text"] == "plan"
    assert result["why_log"]["plan_contract_validation"]["has_errors"] is True
    assert not any(event[0] == "plan_contract_review_required" for event in events)


def test_empty_text_contract_finding_does_not_create_validator_hold():
    """No-text failure is owned upstream; this validator still only reports it."""
    emit, events = _emit_collector()
    result = _apply_plan_contract_validation(
        {
            "status": "ready",
            "plan_text": "",
            "final_plan_text": "",
            "draft_plan_text": "",
            "planning_brief": {
                "fight_date": FIGHT_DATE,
                "weekly_role_map": {
                    "weeks": [{"phase": "fight", "countdown_range": [6, 0]}]
                },
            },
        },
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )

    assert result["status"] == "ready"
    report = result["why_log"]["plan_contract_validation"]
    assert any(v.get("code") == "plan_text_empty" for v in report["violations"])
    assert not any(event[0] == "plan_contract_review_required" for event in events)


def test_already_non_visible_status_is_not_changed():
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
    assert not any(event[0] == "plan_contract_review_required" for event in events)


def test_healthy_visible_plan_keeps_status_and_records_clean_report():
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


def test_contract_fight_date_uses_scheduled_fight_date():
    assert _contract_fight_date(_Req(fight_date=FIGHT_DATE)) == FIGHT_DATE


def test_open_camp_with_stale_fight_date_resolves_to_none():
    assert _contract_fight_date(
        _Req(fight_date=FIGHT_DATE, no_scheduled_fight=True)
    ) is None


def test_open_camp_with_stale_fight_date_does_not_require_d0():
    emit, _ = _emit_collector()
    fight_date = _contract_fight_date(
        _Req(fight_date=FIGHT_DATE, no_scheduled_fight=True)
    )
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
    result = _apply_plan_contract_validation(
        _result(
            "ready",
            [{"countdown_range": [21, 15], "calendar_days": calendar_days}],
        ),
        fight_date=fight_date,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=emit,
    )
    report = result["why_log"]["plan_contract_validation"]
    assert "fight_day_missing" not in [v["code"] for v in report["violations"]]
    assert result["status"] == "ready"


def test_validator_or_milestone_failure_never_blocks_persistence(monkeypatch):
    import api.generation.persistence as persistence

    def boom_validate(*_args, **_kwargs):
        raise RuntimeError("validator exploded")

    monkeypatch.setattr(persistence, "validate_plan_contract", boom_validate)

    result = _apply_plan_contract_validation(
        _result("ready", [{"phase": "fight", "countdown_range": [6, 0]}]),
        fight_date=FIGHT_DATE,
        athlete_id="ath-1",
        job_id="job-1",
        emit_milestone=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("sink exploded")
        ),
    )
    assert result["status"] == "ready"
    assert result["plan_text"] == "plan"


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


# Legacy helper predicates remain available for diagnostics/card tooling. They no
# longer determine athlete release.
def test_contract_rescuable_predicate_still_classifies_known_render_findings():
    assert _contract_report_is_card_rescuable(
        {"violations": [_err("weekly_schedule_blank")]}
    ) is True
    assert _contract_report_is_card_rescuable(
        {"violations": [_err("fight_day_missing")]}
    ) is True
    assert _contract_report_is_card_rescuable(
        {"violations": [_err("plan_text_empty")]}
    ) is False
    assert _contract_report_is_card_rescuable(
        {"violations": [_err("brand_new_code")]}
    ) is False


def test_contract_flaggable_predicate_remains_diagnostic_only():
    assert _contract_report_is_flaggable(
        {"violations": [_err("weekly_schedule_blank")]}
    ) is True
    assert _contract_report_is_flaggable(
        {"violations": [_err("plan_text_empty")]}
    ) is False
    assert _contract_report_is_flaggable(
        {"violations": [_err("brand_new_code")]}
    ) is False


def test_contract_predicates_fail_closed_on_malformed_input_without_affecting_release():
    for report in (
        None,
        [],
        {"violations": "nope"},
        {"violations": [None]},
        {"violations": [{"severity": "error"}]},
    ):
        assert _contract_report_is_card_rescuable(report) is False
        assert _contract_report_is_flaggable(report) is False
