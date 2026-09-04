"""Post-plan audit findings cannot veto either release entry point."""

import pytest
from fastapi import HTTPException

from api.generation.persistence import _apply_plan_contract_validation
from api.services.admin_stage2_service import _manual_stage2_result


def test_manual_goal_failure_releases_and_retains_report(monkeypatch):
    import fightcamp.stage2_pipeline as pipeline

    finding = {
        "code": "goal_preservation_failed",
        "goal": "speed",
        "satisfied": False,
        "missing_coverage": ["D14-D20"],
    }
    monkeypatch.setattr(
        pipeline,
        "review_stage2_output",
        lambda **_: {"validator_report": {"errors": [finding], "warnings": []}},
    )
    result = _manual_stage2_result({}, "# Usable camp")
    assert result["status"] == "publishable_with_flags"
    assert result["plan_text"] == "# Usable camp"
    assert result["stage2_validator_report"]["errors"] == [finding]
    assert result["stage2_validator_report"]["is_athlete_releasable"] is True
    assert result["stage2_retry_text"] == ""


def test_manual_empty_content_is_not_released():
    with pytest.raises(HTTPException):
        _manual_stage2_result({}, "   ")


def test_unknown_contract_finding_releases_raw_text_without_card(monkeypatch):
    import api.generation.persistence as persistence

    report = {
        "has_errors": True,
        "violations": [{"code": "future_validator_disagreement", "severity": "error"}],
    }
    monkeypatch.setattr(
        persistence, "validate_plan_contract", lambda *args, **kwargs: report
    )
    result = _apply_plan_contract_validation(
        {"status": "ready", "plan_text": "# Usable camp"},
        fight_date=None,
        athlete_id="test",
        job_id="test",
        emit_milestone=lambda *args, **kwargs: None,
    )
    assert result["status"] == "publishable_with_flags"
    assert result["why_log"]["plan_contract_validation"] == report


@pytest.mark.parametrize("source", ["review_required", "held_for_review"])
def test_manual_flagged_release_transition_is_allowed(source):
    from api.state_machine import can_transition

    assert can_transition("plan", source, "publishable_with_flags")
