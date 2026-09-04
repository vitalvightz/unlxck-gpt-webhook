"""Central policy distinguishes releasable quality flags from blocking contract failures."""

import pytest
from fastapi import HTTPException

from api.generation.persistence import _apply_plan_contract_validation
from api.services.admin_stage2_service import _manual_stage2_result


def test_manual_goal_failure_holds_and_retains_report(monkeypatch):
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
    assert result["status"] == "review_required"
    assert result["plan_text"] == ""
    assert result["final_plan_text"] == "# Usable camp"
    assert result["stage2_status"] == "stage2_failed"
    assert result["stage2_validator_report"]["errors"] == [finding]
    assert result["stage2_validator_report"]["is_athlete_releasable"] is False
    assert result["stage2_validator_report"]["release_decision"] == "hold"
    assert result["stage2_retry_text"] == ""


def test_blocker_severity_goal_failure_holds(monkeypatch):
    import fightcamp.stage2_pipeline as pipeline

    finding = {
        "code": "goal_preservation_failed",
        "goal": "speed",
        "satisfied": False,
        "missing_coverage": ["D14-D20"],
        "severity": "blocker",
        "confidence": "high",
    }
    monkeypatch.setattr(
        pipeline,
        "review_stage2_output",
        lambda **_: {"validator_report": {"errors": [finding], "warnings": []}},
    )
    result = _manual_stage2_result({}, "# Usable camp")
    assert result["status"] == "review_required"
    assert result["stage2_status"] == "stage2_failed"
    assert result["plan_text"] == ""
    assert result["final_plan_text"] == "# Usable camp"
    assert result["stage2_validator_report"]["errors"] == [finding]
    assert result["stage2_validator_report"]["release_decision"] == "hold"
    assert result["stage2_validator_report"]["is_athlete_releasable"] is False
    assert result["stage2_retry_text"] == ""


def test_goal_failure_retry_requires_planner_regeneration():
    from fightcamp.stage2_pipeline import build_stage2_retry

    finding = {
        "code": "goal_preservation_failed",
        "goal": "speed",
        "missing_coverage": ["D14-D20"],
        "severity": "blocker",
    }
    result = build_stage2_retry(
        stage1_result={"planning_brief": {}},
        final_plan_text="# Rendered plan",
        validator_report={"errors": [finding], "warnings": []},
    )
    assert result["needs_retry"] is False
    assert result["requires_planner_regeneration"] is True
    assert result["repair_prompt"] is None
    assert result["validator_report"]["release_decision"] == "hold"


def test_manual_empty_content_is_not_released():
    with pytest.raises(HTTPException):
        _manual_stage2_result({}, "   ")


def test_unknown_contract_finding_holds_raw_text_without_card(monkeypatch):
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
    assert result["status"] == "review_required"
    assert result["why_log"]["plan_contract_validation"] == report


@pytest.mark.parametrize("source", ["review_required", "held_for_review"])
def test_manual_flagged_release_transition_is_allowed(source):
    from api.state_machine import can_transition

    assert can_transition("plan", source, "publishable_with_flags")


@pytest.mark.parametrize(
    "code",
    [
        "restriction_violation",
        "late_fight_hard_sparring_violation",
        "late_fight_countdown_blocked_drill",
        "late_fight_window_forbidden_exercise",
        "dangerous_late_fight_strength_or_conditioning",
        "late_camp_effective_prescription_exceeded",
        "fight_day_protocol_violation",
        "stage2_output_truncated",
        "goal_preservation_render_mismatch",
        "unknown_error",
    ],
)
def test_automatic_and_manual_safety_holds_are_identical(monkeypatch, code):
    import asyncio
    from types import SimpleNamespace
    import api.stage2_automation as automation
    import fightcamp.stage2_pipeline as pipeline
    from support import FakeOpenAIClient

    finding = {"code": code, "message": "renderer diverged from canonical plan"}
    goal_failure = {
        "code": "goal_preservation_failed",
        "goal": "speed",
        "satisfied": False,
    }
    review = {
        "status": "FAIL",
        "needs_retry": True,
        "validator_report": {"errors": [goal_failure, finding], "warnings": []},
    }
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0")
    monkeypatch.setattr(automation, "review_stage2_output", lambda **_: review)
    monkeypatch.setattr(pipeline, "review_stage2_output", lambda **_: review)
    responses = [
        SimpleNamespace(id="test", output_text="# Rendered plan") for _ in range(2)
    ]
    client = FakeOpenAIClient(responses)
    auto = asyncio.run(
        automation.OpenAIStage2Automator(client=client, model="test").finalize(
            stage1_result={
                "planning_brief": {},
                "stage2_payload": {},
                "stage2_handoff_text": "handoff",
                "plan_text": "Internal draft",
            }
        )
    )
    manual = _manual_stage2_result({}, "# Rendered plan")
    for result in (auto, manual):
        assert result["status"] == "review_required"
        assert result["stage2_status"] == "stage2_failed"
        assert result["plan_text"] == ""
        assert result["final_plan_text"] == "# Rendered plan"
        assert result["stage2_validator_report"]["errors"] == [goal_failure, finding]
        assert result["stage2_validator_report"]["release_decision"] == "hold"
        assert result["stage2_validator_report"]["is_athlete_releasable"] is False


def test_goal_preservation_errors_always_hold():
    from fightcamp.stage2_policy import apply_stage2_release_policy

    findings = [
        {"code": "goal_preservation_failed", "goal": goal, "satisfied": False}
        for goal in ("speed", "strength")
    ]
    report = apply_stage2_release_policy({"errors": findings, "warnings": []})
    assert report["errors"] == findings
    assert report["quality_review_flags"] == []
    assert report["release_decision"] == "hold"
    assert report["is_athlete_releasable"] is False


def test_malformed_errors_fail_closed_even_with_goal_finding():
    from fightcamp.stage2_policy import apply_stage2_release_policy

    report = apply_stage2_release_policy(
        {
            "errors": "malformed",
            "warnings": [{"code": "goal_preservation_failed", "goal": "speed"}],
        }
    )
    assert report["release_decision"] == "hold"
