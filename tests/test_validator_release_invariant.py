"""Release invariant: usable planner output ships; validators only report."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.generation.persistence import _apply_plan_contract_validation
from api.services.admin_stage2_service import _manual_stage2_result


def _review_with_error(finding: dict):
    return {
        "status": "FAIL",
        "needs_retry": True,
        "validator_report": {
            "errors": [finding],
            "warnings": [],
            "blocking_warnings": [],
        },
    }


def test_manual_goal_failure_releases_and_retains_report(monkeypatch):
    import fightcamp.stage2_pipeline as pipeline

    finding = {
        "code": "goal_preservation_failed",
        "goal": "speed",
        "satisfied": False,
        "missing_coverage": ["D14-D20"],
        "severity": "blocker",
    }
    monkeypatch.setattr(
        pipeline,
        "review_stage2_output",
        lambda **_: _review_with_error(finding),
    )

    result = _manual_stage2_result({}, "# Usable camp")

    assert result["status"] == "publishable_with_flags"
    assert result["plan_text"] == "# Usable camp"
    assert result["final_plan_text"] == "# Usable camp"
    assert result["stage2_status"] == "stage2_pass"
    assert result["stage2_validator_report"]["errors"] == [finding]
    assert result["stage2_validator_report"]["is_athlete_releasable"] is True
    assert result["stage2_validator_report"]["release_decision"] == "publish_with_flags"
    assert result["stage2_retry_text"] == ""


def test_goal_failure_does_not_require_retry_or_planner_regeneration():
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
    assert result.get("requires_planner_regeneration") is not True
    assert result["repair_prompt"] is None
    assert result["validator_report"]["release_decision"] == "publish_with_flags"


def test_manual_empty_content_is_not_released():
    with pytest.raises(HTTPException):
        _manual_stage2_result({}, "   ")


def test_unknown_contract_finding_is_recorded_without_holding_plan(monkeypatch):
    import api.generation.persistence as persistence

    report = {
        "has_errors": True,
        "violations": [
            {"code": "future_validator_disagreement", "severity": "error"}
        ],
    }
    monkeypatch.setattr(
        persistence,
        "validate_plan_contract",
        lambda *args, **kwargs: report,
    )

    result = _apply_plan_contract_validation(
        {"status": "ready", "plan_text": "# Usable camp"},
        fight_date=None,
        athlete_id="test",
        job_id="test",
        emit_milestone=lambda *args, **kwargs: None,
    )

    assert result["status"] == "ready"
    assert result["plan_text"] == "# Usable camp"
    assert result["why_log"]["plan_contract_validation"] == report


@pytest.mark.parametrize("source", ["review_required", "held_for_review"])
def test_manual_flagged_release_transition_is_allowed(source):
    from api.state_machine import can_transition

    assert can_transition("plan", source, "publishable_with_flags")


@pytest.mark.parametrize(
    "code",
    [
        "goal_preservation_failed",
        "goal_preservation_render_mismatch",
        "restriction_violation",
        "late_fight_hard_sparring_violation",
        "late_fight_countdown_blocked_drill",
        "late_fight_window_forbidden_exercise",
        "dangerous_late_fight_strength_or_conditioning",
        "late_camp_effective_prescription_exceeded",
        "fight_day_protocol_violation",
        "stage2_output_truncated",
        "missing_required_element",
        "weekly_session_overage",
        "unknown_error",
    ],
)
def test_automatic_and_manual_validator_findings_release_identically(
    monkeypatch, code
):
    import api.stage2_automation as automation
    import fightcamp.stage2_pipeline as pipeline
    from support import FakeOpenAIClient

    finding = {
        "code": code,
        "message": "validator disagreed with produced plan",
        "severity": "blocker",
    }
    review = _review_with_error(finding)

    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0")
    monkeypatch.setattr(automation, "review_stage2_output", lambda **_: review)
    monkeypatch.setattr(automation, "validate_goal_preservation", lambda *_: [])
    monkeypatch.setattr(pipeline, "review_stage2_output", lambda **_: review)

    client = FakeOpenAIClient(
        [SimpleNamespace(id="test", output_text="# Rendered plan")]
    )
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

    # No validator-triggered repair call: one usable Stage 2 response is enough.
    assert len(client.responses.calls) == 1

    for result in (auto, manual):
        assert result["status"] == "publishable_with_flags"
        assert result["stage2_status"] == "stage2_pass"
        assert result["plan_text"] == "# Rendered plan"
        assert result["final_plan_text"] == "# Rendered plan"
        assert result["stage2_validator_report"]["errors"] == [finding]
        assert (
            result["stage2_validator_report"]["release_decision"]
            == "publish_with_flags"
        )
        assert result["stage2_validator_report"]["is_athlete_releasable"] is True


def test_all_validator_errors_are_observational():
    from fightcamp.stage2_policy import apply_stage2_release_policy

    findings = [
        {
            "code": "goal_preservation_failed",
            "goal": "speed",
            "satisfied": False,
            "severity": "blocker",
        },
        {
            "code": "restriction_violation",
            "severity": "blocker",
        },
        {
            "code": "future_unknown_validator_code",
            "severity": "error",
        },
    ]

    report = apply_stage2_release_policy({"errors": findings, "warnings": []})

    assert report["errors"] == findings
    assert report["quality_review_flags"] == findings
    assert report["release_decision"] == "publish_with_flags"
    assert report["is_athlete_releasable"] is True
    assert report["is_publishable"] is True
    assert report["validator_findings_observational"] is True


def test_malformed_validator_report_is_flagged_but_not_held():
    from fightcamp.stage2_policy import apply_stage2_release_policy

    report = apply_stage2_release_policy(
        {
            "errors": "malformed",
            "warnings": [
                {"code": "goal_preservation_failed", "goal": "speed"}
            ],
        }
    )

    assert report["errors"] == []
    assert report["release_decision"] == "publish_with_flags"
    assert report["is_athlete_releasable"] is True
    assert report["release_policy_malformed_fields"] == ["errors"]
    assert any(
        item.get("code") == "validator_report_malformed"
        for item in report["quality_review_flags"]
    )
