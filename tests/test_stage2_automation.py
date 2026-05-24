from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

import api.stage2_automation as stage2_module
from api.stage2_automation import OpenAIStage2Automator, Stage2AutomationError


class FakeResponses:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    async def create(self, **request: object) -> object:
        self.calls.append(request)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


class FakeClient:
    def __init__(self, outputs: list[object]) -> None:
        self.responses = FakeResponses(outputs)


def _response(text: str, *, input_tokens: int = 10, output_tokens: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_test",
        output_text=text,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )


def _review(status_value: str) -> dict:
    errors = [{"code": "restriction_violation"}] if status_value == "FAIL" else []
    warnings = [{"code": "missing_required_element", "blocking": True}] if status_value == "WARN" else []
    review_flags = [{"code": "generic_filler_phrase"}] if status_value == "PASS_WITH_FLAGS" else []
    return {
        "status": "PASS" if status_value == "PASS_WITH_FLAGS" else status_value,
        "needs_retry": status_value not in {"PASS", "PASS_WITH_FLAGS"},
        "validator_report": {
            "errors": errors,
            "warnings": warnings + review_flags,
            "review_flag_count": len(review_flags),
        },
    }


def _stage1_result() -> dict:
    return {
        "plan_text": "# Stage 1 Draft",
        "coach_notes": "### Coach Review",
        "pdf_url": "https://example.com/stage1.pdf",
        "why_log": {"strength": {}},
        "stage2_payload": {"ok": True},
        "planning_brief": {"schema_version": "planning_brief.v1", "main_limiter": "conditioning"},
        "stage2_handoff_text": "handoff",
    }


def test_first_pass_pass_returns_ready_with_one_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 1
    assert result["status"] == "ready"
    assert result["plan_text"] == "# final plan"
    assert result["final_plan_text"] == "# final plan"
    assert result["stage2_status"] == "stage2_pass"
    assert result["stage2_attempt_count"] == 1
    assert result["stage2_retry_text"] == ""

def test_first_pass_pass_with_review_flags_returns_publishable_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS_WITH_FLAGS"))
    client = FakeClient([_response("# final plan with minor flags")])
    automator = OpenAIStage2Automator(client=client, model="test-model")
    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))
    assert result["status"] == "publishable_with_flags"
    assert result["plan_text"] == "# final plan with minor flags"


@pytest.mark.parametrize("review_status", ["FAIL", "WARN"])
def test_first_pass_non_pass_returns_held_for_review_with_one_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    review_status: str,
) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review(review_status))
    client = FakeClient([_response("# first pass needs review")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 1
    assert result["status"] == "held_for_review"
    assert result["plan_text"] == ""
    assert result["final_plan_text"] == "# first pass needs review"
    assert result["stage2_status"] == "stage2_failed"
    assert result["stage2_attempt_count"] == 1
    assert result["stage2_retry_text"] == ""
    assert result["stage2_validator_report"] == _review(review_status)["validator_report"]


def test_build_stage2_retry_is_not_called_during_automatic_finalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("FAIL"))

    def _unexpected_retry(**_: object) -> dict:
        raise AssertionError("automatic Stage 2 finalization must not build a repair prompt")

    monkeypatch.setattr(
        stage2_module,
        "build_stage2_retry",
        _unexpected_retry,
        raising=False,
    )
    client = FakeClient([_response("# failed first pass")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 1
    assert result["status"] == "held_for_review"


def test_retry_pass_is_never_sent_during_automatic_finalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("FAIL"))
    client = FakeClient([_response("# failed first pass"), _response("# retry should stay unused")])
    automator = OpenAIStage2Automator(client=client, model="test-model")
    original_generate_text = automator._generate_text
    seen_attempts: list[str] = []

    async def _record_attempt(prompt: str, *, attempt_label: str, source: str) -> str:
        seen_attempts.append(attempt_label)
        if attempt_label == "retry_pass":
            raise AssertionError("automatic Stage 2 finalization must not send retry_pass")
        return await original_generate_text(prompt, attempt_label=attempt_label, source=source)

    monkeypatch.setattr(automator, "_generate_text", _record_attempt)

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["status"] == "held_for_review"
    assert seen_attempts == ["first_pass"]
    assert len(client.responses.calls) == 1


def test_first_pass_over_limit_blocks_before_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNLXCK_STAGE2_MAX_FIRST_PASS_CHARS", "10")
    stage1 = _stage1_result()
    stage1["stage2_handoff_text"] = "x" * 11
    client = FakeClient([_response("# should not be called")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError, match="first_pass prompt too large"):
        asyncio.run(automator.finalize(stage1_result=stage1))

    assert client.responses.calls == []


def test_first_pass_default_limit_is_180k_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNLXCK_STAGE2_MAX_FIRST_PASS_CHARS", raising=False)
    stage1 = _stage1_result()
    stage1["stage2_handoff_text"] = "x" * 180_001
    client = FakeClient([_response("# should not be called")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError, match="chars > 180000"):
        asyncio.run(automator.finalize(stage1_result=stage1))

    assert client.responses.calls == []


def test_quota_error_stops_after_single_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        [
            RuntimeError(
                'Error code: 429 - {"error":{"message":"Too Many Requests","code":"insufficient_quota"}}'
            )
        ]
    )
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError, match="quota/rate limit hit"):
        asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 1


def test_from_env_disables_openai_sdk_retries_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("UNLXCK_STAGE2_OPENAI_MAX_RETRIES", raising=False)

    automator = OpenAIStage2Automator.from_env()

    assert isinstance(automator, OpenAIStage2Automator)
    assert captured_kwargs["max_retries"] == 0
