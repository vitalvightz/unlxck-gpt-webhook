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
# These tests exist specifically to prevent the old technical-failure fallback from returning.
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
\n\n\nclass _SequentialResponses:\n    def __init__(self, responses):\n        self._responses = list(responses)\n        self.requests: list[dict] = []\n\n    def stream(self, **request):\n        self.requests.append(request)\n        if not self._responses:\n            raise AssertionError("unexpected extra Stage 2 model call")\n        return _Stream(self._responses.pop(0))\n\n\nclass _SequentialClient:\n    def __init__(self, responses):\n        self.responses = _SequentialResponses(responses)\n\n\ndef _complete_response(text: str):\n    return SimpleNamespace(\n        id="resp_complete",\n        status="completed",\n        incomplete_details=None,\n        output_text=text,\n        usage={"input_tokens": 120, "output_tokens": 60, "total_tokens": 180},\n    )\n\n\ndef test_incomplete_first_pass_audit_survives_effective_dose_repair(monkeypatch):\n    automator = OpenAIStage2Automator(\n        client=_SequentialClient(\n            [\n                _incomplete_response("# Partial Stage 2 plan\\n\\nNeeds dose repair."),\n                _complete_response("# Repaired Stage 2 plan\\n\\nAthlete-facing repaired output."),\n            ]\n        ),\n        model="test-model",\n    )\n\n    monkeypatch.setattr(\n        stage2_module,\n        "build_stage2_package",\n        lambda **_: {\n            "draft_plan_text": "# Stage 1 draft must stay internal",\n            "handoff_text": "handoff",\n            "planning_brief": {},\n        },\n    )\n    review_calls = {"count": 0}\n\n    def fake_review(**_):\n        review_calls["count"] += 1\n        findings = (\n            [{"code": "late_camp_effective_prescription_exceeded", "message": "repair"}]\n            if review_calls["count"] == 1\n            else []\n        )\n        return {\n            "status": "FAIL" if findings else "PASS",\n            "needs_retry": bool(findings),\n            "validator_report": {\n                "errors": findings,\n                "warnings": [],\n                "blocking_warnings": [],\n                "review_flags": [],\n            },\n        }\n\n    monkeypatch.setattr(stage2_module, "review_stage2_output", fake_review)\n    monkeypatch.setattr(\n        stage2_module,\n        "build_stage2_retry",\n        lambda **_: {"needs_retry": True, "repair_prompt": "repair"},\n    )\n    monkeypatch.setattr(\n        stage2_module,\n        "apply_stage2_release_policy",\n        lambda report: {\n            **report,\n            "release_decision": "publish",\n            "is_athlete_releasable": True,\n            "is_publishable": True,\n        },\n    )\n    monkeypatch.setattr(stage2_module, "athlete_release_with_flags_findings", lambda _report: [])\n    monkeypatch.setattr(stage2_module, "admin_review_blocking_findings", lambda _report: [])\n    monkeypatch.setattr(stage2_module, "_structured_plan_enabled", lambda: False)\n\n    result = asyncio.run(\n        automator.finalize(\n            stage1_result={\n                "status": "ready",\n                "plan_text": "# Stage 1 draft must stay internal",\n            }\n        )\n    )\n\n    assert result["status"] == "publishable_with_flags"\n    assert result["plan_text"].startswith("# Repaired Stage 2 plan")\n    assert result["plan_text"] != "# Stage 1 draft must stay internal"\n    assert result["stage2_attempt_count"] == 2\n    assert result["stage2_cost"]["stage2_incomplete_response"] is True\n    assert any(\n        warning.get("code") == "stage2_incomplete_response"\n        for warning in result["stage2_validator_report"]["warnings"]\n    )\n