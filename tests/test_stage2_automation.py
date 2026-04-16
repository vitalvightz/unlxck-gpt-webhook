from __future__ import annotations

import asyncio

from api import stage2_automation


def _stage1_result() -> dict:
    return {"plan_text": "# Stage 1 Draft"}


def test_finalize_disables_retry_by_default(monkeypatch):
    monkeypatch.delenv("UNLXCK_STAGE2_RETRY_ACTIVE", raising=False)
    monkeypatch.setattr(
        stage2_automation,
        "build_stage2_package",
        lambda *, stage1_result: {
            "draft_plan_text": "# Stage 1 Draft",
            "handoff_text": "handoff",
            "planning_brief": {"brief": True},
        },
    )
    monkeypatch.setattr(
        stage2_automation,
        "review_stage2_output",
        lambda *, planning_brief, final_plan_text: {
            "status": "FAIL",
            "needs_retry": True,
            "validator_report": {"errors": [{"code": "restriction_violation"}], "warnings": []},
        },
    )
    monkeypatch.setattr(
        stage2_automation,
        "build_stage2_retry",
        lambda *, stage1_result, final_plan_text, validator_report: {"repair_prompt": "repair prompt"},
    )

    calls: list[str] = []

    class _FakeAutomator(stage2_automation.OpenAIStage2Automator):
        async def _generate_text(self, prompt: str, *, attempt_label: str) -> str:
            calls.append(attempt_label)
            return "first output"

    automator = _FakeAutomator(client=object(), model="fake")
    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert calls == ["first_pass"]
    assert result["status"] == "review_required"
    assert result["stage2_status"] == "stage2_failed"
    assert result["stage2_retry_text"] == "repair prompt"
    assert result["stage2_attempt_count"] == 1


def test_finalize_allows_retry_when_env_enabled(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE2_RETRY_ACTIVE", "1")
    monkeypatch.setattr(
        stage2_automation,
        "build_stage2_package",
        lambda *, stage1_result: {
            "draft_plan_text": "# Stage 1 Draft",
            "handoff_text": "handoff",
            "planning_brief": {"brief": True},
        },
    )

    def _review(*, planning_brief, final_plan_text):
        if final_plan_text == "first output":
            return {
                "status": "FAIL",
                "needs_retry": True,
                "validator_report": {"errors": [{"code": "restriction_violation"}], "warnings": []},
            }
        return {"status": "PASS", "needs_retry": False, "validator_report": {"errors": [], "warnings": []}}

    monkeypatch.setattr(stage2_automation, "review_stage2_output", _review)
    monkeypatch.setattr(
        stage2_automation,
        "build_stage2_retry",
        lambda *, stage1_result, final_plan_text, validator_report: {"repair_prompt": "repair prompt"},
    )

    calls: list[str] = []

    class _FakeAutomator(stage2_automation.OpenAIStage2Automator):
        async def _generate_text(self, prompt: str, *, attempt_label: str) -> str:
            calls.append(attempt_label)
            return "first output" if attempt_label == "first_pass" else "second output"

    automator = _FakeAutomator(client=object(), model="fake")
    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert calls == ["first_pass", "retry_pass"]
    assert result["status"] == "ready"
    assert result["stage2_status"] == "stage2_retry_pass"
    assert result["stage2_retry_text"] == "repair prompt"
    assert result["stage2_attempt_count"] == 2
