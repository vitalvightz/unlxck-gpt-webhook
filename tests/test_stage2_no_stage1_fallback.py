from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import api.stage2_automation as stage2_module
from api.stage2_automation import (
    OpenAIStage2Automator,
    Stage2AutomationError,
)


class _Stream:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_final_response(self):
        return self.response


class _Responses:
    def __init__(self, response):
        self.response = response
        self.requests: list[dict] = []

    def stream(self, **request):
        self.requests.append(request)
        return _Stream(self.response)


class _Client:
    def __init__(self, response):
        self.responses = _Responses(response)


def _incomplete_response(text: str):
    return SimpleNamespace(
        id="resp_incomplete",
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        output_text=text,
        usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )


# Regression contract: usable Stage 2 output stays athlete-facing; Stage 1 is never promoted.
def test_incomplete_stage2_response_keeps_usable_stage2_text():
    response = _incomplete_response("# Partial Stage 2 plan\n\nDo the Stage 2 work.")
    automator = OpenAIStage2Automator(client=_Client(response), model="test-model")

    text, cost = asyncio.run(
        automator._generate_text(
            "handoff",
            attempt_label="first_pass",
            source="self_serve",
        )
    )

    assert text.startswith("# Partial Stage 2 plan")
    assert cost["stage2_incomplete_response"] is True
    assert cost["stage2_output_tokens"] == 50


def test_incomplete_stage2_response_without_text_still_fails():
    response = _incomplete_response("")
    automator = OpenAIStage2Automator(client=_Client(response), model="test-model")

    with pytest.raises(Stage2AutomationError, match="incomplete and contained no usable plan text"):
        asyncio.run(
            automator._generate_text(
                "handoff",
                attempt_label="first_pass",
                source="self_serve",
            )
        )


def test_incomplete_stage2_plan_is_released_flagged_not_replaced_by_stage1(monkeypatch):
    response = _incomplete_response("# Partial Stage 2 plan\n\nKeep this athlete-facing.")
    automator = OpenAIStage2Automator(client=_Client(response), model="test-model")

    monkeypatch.setattr(
        stage2_module,
        "build_stage2_package",
        lambda **_: {
            "draft_plan_text": "# ugly Stage 1 draft",
            "handoff_text": "handoff",
            "planning_brief": {},
        },
    )
    monkeypatch.setattr(
        stage2_module,
        "review_stage2_output",
        lambda **_: {
            "status": "PASS",
            "needs_retry": False,
            "validator_report": {
                "errors": [],
                "warnings": [],
                "blocking_warnings": [],
                "review_flags": [],
            },
        },
    )
    monkeypatch.setattr(
        stage2_module,
        "apply_stage2_release_policy",
        lambda report: {
            **report,
            "release_decision": "publish",
            "is_athlete_releasable": True,
            "is_publishable": True,
        },
    )
    monkeypatch.setattr(stage2_module, "athlete_release_with_flags_findings", lambda _report: [])
    monkeypatch.setattr(stage2_module, "admin_review_blocking_findings", lambda _report: [])
    monkeypatch.setattr(stage2_module, "_structured_plan_enabled", lambda: False)

    result = asyncio.run(
        automator.finalize(
            stage1_result={"status": "ready", "plan_text": "# ugly Stage 1 draft"}
        )
    )

    assert result["status"] == "publishable_with_flags"
    assert result["plan_text"].startswith("# Partial Stage 2 plan")
    assert result["plan_text"] != "# ugly Stage 1 draft"
    assert any(
        warning.get("code") == "stage2_incomplete_response"
        for warning in result["stage2_validator_report"]["warnings"]
    )
