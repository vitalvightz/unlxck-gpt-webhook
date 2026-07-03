from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

import api.stage2_automation as stage2_module
from api.stage2_automation import OpenAIStage2Automator, Stage2AutomationError
from support import FakeOpenAIClient as FakeClient


@pytest.fixture(autouse=True)
def _structured_plan_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin structured-plan generation OFF for this module.

    These tests exercise the single-call plan-text finalize/retry flow and
    assert exact provider call counts. Structured generation is on by default
    now (a second conversion call), so disable it here; the structured path has
    dedicated coverage in test_stage2_structured_persistence.py.
    """
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0")


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


def _incomplete_response() -> SimpleNamespace:
    # Mirrors an OpenAI Responses result truncated by the output-token budget
    # (reasoning tokens + plan text exceeded max_output_tokens).
    return SimpleNamespace(
        id="resp_incomplete",
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output_text="# Fight Camp Plan\n\nWeek 1 of a cut-off pl",
        usage=SimpleNamespace(input_tokens=10, output_tokens=24000, total_tokens=24010),
    )


def _review(status_value: str) -> dict:
    errors = [{"code": "restriction_violation"}] if status_value == "FAIL" else []
    warnings = [{"code": "generic_filler_phrase", "blocking": True}] if status_value == "WARN" else []
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

def test_first_pass_omits_max_output_tokens_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNLXCK_STAGE2_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    # Default is 0 (no cap) so the model is never truncated mid-plan.
    assert "max_output_tokens" not in client.responses.calls[0]


def test_first_pass_honors_max_output_tokens_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNLXCK_STAGE2_MAX_OUTPUT_TOKENS", "12000")
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert client.responses.calls[0]["max_output_tokens"] == 12000


def test_first_pass_omits_max_output_tokens_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNLXCK_STAGE2_MAX_OUTPUT_TOKENS", "0")
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert "max_output_tokens" not in client.responses.calls[0]


def test_structured_calls_request_json_object_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # The structured-card conversion calls must ask the provider for JSON output
    # mode so the response is always syntactically valid JSON.
    import json

    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_JSON_MODE", raising=False)
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_REPAIR", "0")  # single call keeps it simple
    client = FakeClient([_response(json.dumps([1, 2, 3]))])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    asyncio.run(
        automator._generate_structured_outcome(
            final_plan_text="# plan", planning_brief={}, source="test", costs=[]
        )
    )

    assert client.responses.calls[0]["text"] == {"format": {"type": "json_object"}}


def test_structured_calls_omit_json_mode_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_JSON_MODE", "0")
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_REPAIR", "0")
    client = FakeClient([_response(json.dumps([1, 2, 3]))])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    asyncio.run(
        automator._generate_structured_outcome(
            final_plan_text="# plan", planning_brief={}, source="test", costs=[]
        )
    )

    assert "text" not in client.responses.calls[0]


def test_plan_text_first_pass_omits_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # The markdown plan-text pass must stay free-form (never JSON output mode),
    # regardless of the structured JSON-mode flag.
    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_JSON_MODE", "1")
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_response("# final plan")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert "text" not in client.responses.calls[0]


def test_first_pass_incomplete_response_fails_the_job(monkeypatch: pytest.MonkeyPatch) -> None:
    # A response truncated by the output-token cap must hard-fail (athlete retries)
    # rather than ship a half-written plan. This is the production failure that the
    # generous default + 0-means-no-cap knob are meant to avoid.
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_incomplete_response()])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError, match="incomplete before producing a full plan"):
        asyncio.run(automator.finalize(stage1_result=_stage1_result()))


def test_first_pass_pass_with_review_flags_returns_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS_WITH_FLAGS"))
    client = FakeClient([_response("# final plan with minor flags")])
    automator = OpenAIStage2Automator(client=client, model="test-model")
    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))
    assert result["status"] == "ready"
    assert result["plan_text"] == "# final plan with minor flags"


def test_first_pass_publish_blocking_review_flags_hold_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    def _quality_blocked_review(**_: object) -> dict:
        finding = {"code": "missing_required_element", "phase": "SPP"}
        return {
            "status": "PASS",
            "needs_retry": False,
            "validator_report": {
                "errors": [],
                "warnings": [finding],
                "review_flags": [finding],
                "review_flag_count": 1,
            },
        }

    monkeypatch.setattr(stage2_module, "review_stage2_output", _quality_blocked_review)
    client = FakeClient([_response("# final plan missing required work")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 1
    assert result["status"] == "held_for_review"
    assert result["plan_text"] == ""
    assert result["final_plan_text"] == "# final plan missing required work"
    assert result["stage2_validator_report"]["publish_blocking_review_flags"] == [
        {"code": "missing_required_element", "phase": "SPP"}
    ]


def test_first_pass_hard_failure_returns_held_for_review_with_one_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("FAIL"))
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
    # A held/review-required plan is not athlete-displayable, so structured
    # conversion is skipped (not_attempted) and never makes a model call. The
    # debug marker is always recorded; the rest of the report is unchanged.
    report = dict(result["stage2_validator_report"])
    assert report.pop("structured_plan") == {
        "status": "not_attempted",
        "errors": [],
        "warnings": [],
        "schema_version": None,
    }
    assert report == _review("FAIL")["validator_report"]


def test_first_pass_non_pass_without_release_blockers_returns_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("WARN"))
    client = FakeClient([_response("# first pass clean enough to release")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert len(client.responses.calls) == 1
    assert result["status"] == "ready"
    assert result["plan_text"] == "# first pass clean enough to release"
    assert result["final_plan_text"] == "# first pass clean enough to release"
    assert result["stage2_status"] == "stage2_pass"
    assert result["stage2_attempt_count"] == 1
    assert result["stage2_retry_text"] == ""


def test_stage2_report_blocks_release_when_warnings_is_not_a_list() -> None:
    report = {
        "errors": [],
        "blocking_warnings": [],
        "warnings": {"code": "generic_filler_phrase"},
    }

    assert stage2_module._stage2_report_blocks_release(report) is True


def test_stage2_report_allows_non_blocking_warning_array() -> None:
    report = {
        "errors": [],
        "blocking_warnings": [],
        "warnings": [{"code": "generic_filler_phrase"}],
    }

    assert stage2_module._stage2_report_blocks_release(report) is False


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

    async def _record_attempt(
        prompt: str,
        *,
        attempt_label: str,
        source: str,
        log_context: dict | None = None,
        timeout: float | None = None,
        response_format: dict | None = None,
    ) -> tuple[str, dict]:
        seen_attempts.append(attempt_label)
        if attempt_label == "retry_pass":
            raise AssertionError("automatic Stage 2 finalization must not send retry_pass")
        return await original_generate_text(
            prompt,
            attempt_label=attempt_label,
            source=source,
            log_context=log_context,
            timeout=timeout,
            response_format=response_format,
        )

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


def test_generic_provider_failure_raises_sanitized_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A non-quota provider failure must not surface raw exception text (which can
    # carry request payloads/provider internals) in the raised/stored error.
    raw = "boom connecting to https://api.openai.com with key sk-secret-payload-12345"
    client = FakeClient([RuntimeError(raw)])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError) as exc_info:
        asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    message = str(exc_info.value)
    assert message == "Stage 2 model request failed. Check server logs."
    assert "sk-secret-payload-12345" not in message
    assert "api.openai.com" not in message
    assert len(client.responses.calls) == 1


def test_first_pass_pass_records_token_cost_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_response("# final plan", input_tokens=123, output_tokens=456)])
    automator = OpenAIStage2Automator(client=client, model="gpt-5-mini")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    cost = result["stage2_cost"]
    assert cost["stage2_model"] == "gpt-5-mini"
    assert cost["stage2_input_tokens"] == 123
    assert cost["stage2_output_tokens"] == 456
    assert cost["stage2_total_tokens"] == 579
    assert cost["stage2_attempt_count"] == 1
    assert cost["stage2_response_id"] == "resp_test"
    assert cost["stage2_cost_recorded_at"]
    assert isinstance(cost["stage2_estimated_cost_usd"], float)


def test_review_required_result_also_carries_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("FAIL"))
    client = FakeClient([_response("# first pass needs review", input_tokens=7, output_tokens=9)])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    assert result["status"] == "held_for_review"
    assert result["stage2_cost"]["stage2_input_tokens"] == 7
    assert result["stage2_cost"]["stage2_output_tokens"] == 9


def test_missing_usage_does_not_crash_and_falls_back_to_estimates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An OpenAI response with no ``usage`` field must not crash generation; cost
    # falls back to char-based estimates so the row is still populated.
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    response = SimpleNamespace(id="resp_no_usage", output_text="# final plan")
    client = FakeClient([response])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    result = asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    cost = result["stage2_cost"]
    assert result["status"] == "ready"
    assert cost["stage2_input_tokens"] >= 1
    assert cost["stage2_output_tokens"] >= 1
    assert cost["stage2_response_id"] == "resp_no_usage"


def test_incomplete_response_failure_carries_actual_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stage2_module, "review_stage2_output", lambda **_: _review("PASS"))
    client = FakeClient([_incomplete_response()])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError) as exc_info:
        asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    cost = exc_info.value.stage2_cost
    assert cost is not None
    assert cost["stage2_model"] == "test-model"
    assert cost["stage2_input_tokens"] == 10
    assert cost["stage2_output_tokens"] == 24000
    assert cost["stage2_response_id"] == "resp_incomplete"


def test_request_failure_carries_estimated_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    # No response means no actual usage; the failed attempt still records an
    # estimated input cost and leaves genuinely-unknown fields as None.
    client = FakeClient([RuntimeError("boom")])
    automator = OpenAIStage2Automator(client=client, model="test-model")

    with pytest.raises(Stage2AutomationError) as exc_info:
        asyncio.run(automator.finalize(stage1_result=_stage1_result()))

    cost = exc_info.value.stage2_cost
    assert cost is not None
    assert cost["stage2_model"] == "test-model"
    assert cost["stage2_input_tokens"] >= 1
    assert cost["stage2_output_tokens"] is None
    assert cost["stage2_total_tokens"] is None
    assert cost["stage2_response_id"] is None


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


def test_from_env_invalid_timeout_falls_back_to_210(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeAsyncOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("UNLXCK_STAGE2_TIMEOUT_SECONDS", "not-a-number")

    automator = OpenAIStage2Automator.from_env()

    assert isinstance(automator, OpenAIStage2Automator)
    assert captured_kwargs["timeout"] == 210.0


# ---------------------------------------------------------------------------
# _stage2_hold_is_card_rescuable: defensive predicate
# ---------------------------------------------------------------------------

_is_rescuable = stage2_module._stage2_hold_is_card_rescuable


def test_rescuable_true_for_soft_non_safety_error() -> None:
    assert _is_rescuable({"errors": [{"code": "true_internal_system_leak"}]}) is True


def test_rescuable_false_for_safety_error() -> None:
    assert _is_rescuable({"errors": [{"code": "restriction_violation"}]}) is False


def test_rescuable_false_when_any_error_is_unrescuable() -> None:
    # A mix of one soft and one safety error must hold (the safety one wins).
    report = {"errors": [{"code": "true_internal_system_leak"}, {"code": "restriction_violation"}]}
    assert _is_rescuable(report) is False


def test_rescuable_true_when_only_card_rescuable_blocking_warnings_present() -> None:
    report = {
        "errors": [],
        "blocking_warnings": [{"code": "generic_filler_phrase"}],
    }
    assert _is_rescuable(report) is True


def test_rescuable_false_when_publish_blocking_warning_present() -> None:
    report = {
        "errors": [],
        "blocking_warnings": [{"code": "missing_required_element"}],
    }
    assert _is_rescuable(report) is False


def test_rescuable_false_when_unknown_blocking_warning_present() -> None:
    report = {
        "errors": [],
        "blocking_warnings": [{"code": "brand_new_warning_code"}],
    }
    assert _is_rescuable(report) is False


def test_rescuable_false_when_hard_blocking_warning_present() -> None:
    report = {
        "errors": [],
        "blocking_warnings": [{"code": "calendar_spine_fight_day_protocol_violation"}],
    }
    assert _is_rescuable(report) is False


def test_rescuable_false_for_non_dict_report() -> None:
    assert _is_rescuable(None) is False
    assert _is_rescuable([]) is False
    assert _is_rescuable("nope") is False


def test_rescuable_false_for_non_list_or_empty_errors() -> None:
    assert _is_rescuable({}) is False  # missing errors
    assert _is_rescuable({"errors": []}) is False  # empty
    assert _is_rescuable({"errors": "boom"}) is False  # not a list


def test_rescuable_false_for_malformed_error_entries() -> None:
    assert _is_rescuable({"errors": [None]}) is False
    assert _is_rescuable({"errors": ["malformed_error"]}) is False
    assert _is_rescuable({"errors": [{}]}) is False  # no code
    assert _is_rescuable({"errors": [{"code": ""}]}) is False  # blank code
    assert _is_rescuable({"errors": [{"code": "   "}]}) is False  # whitespace-only code


def test_rescuable_false_for_mixed_valid_soft_and_malformed_error() -> None:
    report = {"errors": [{"code": "true_internal_system_leak"}, None]}
    assert _is_rescuable(report) is False
    report = {"errors": [{"code": "true_internal_system_leak"}, {}]}
    assert _is_rescuable(report) is False


def test_structured_repair_disabled_skips_second_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the repair lever off, an invalid first pass is not retried.

    The repair retry is the second sequential structured model call. When
    ``UNLXCK_STAGE2_STRUCTURED_REPAIR`` is disabled, a first pass that parses but
    fails validation returns the first-pass outcome as-is — no second call — so
    worst-case latency is halved.
    """
    import json

    monkeypatch.setenv("UNLXCK_STAGE2_STRUCTURED_REPAIR", "0")
    automator = OpenAIStage2Automator(client=FakeClient([]), model="test-model")

    labels: list[str] = []

    async def _fake_generate_text(prompt, *, attempt_label, source, log_context=None, timeout=None, response_format=None):
        labels.append(attempt_label)
        # Valid JSON that is not a schema-valid plan: parses, then fails
        # validation so the repair gate is reached (but skipped while disabled).
        return json.dumps([1, 2, 3]), {}

    monkeypatch.setattr(automator, "_generate_text", _fake_generate_text)

    outcome, costs = asyncio.run(
        automator._generate_structured_outcome(
            final_plan_text="# plan",
            planning_brief={},
            source="test",
            costs=[],
        )
    )

    assert labels == ["structured_first"]  # repair call was skipped
    assert len(costs) == 1
    assert outcome.structured_plan is None


def test_structured_repair_enabled_makes_second_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default behaviour: an invalid first pass triggers exactly one repair retry."""
    import json

    monkeypatch.delenv("UNLXCK_STAGE2_STRUCTURED_REPAIR", raising=False)
    automator = OpenAIStage2Automator(client=FakeClient([]), model="test-model")

    labels: list[str] = []

    async def _fake_generate_text(prompt, *, attempt_label, source, log_context=None, timeout=None, response_format=None):
        labels.append(attempt_label)
        return json.dumps([1, 2, 3]), {}

    monkeypatch.setattr(automator, "_generate_text", _fake_generate_text)

    asyncio.run(
        automator._generate_structured_outcome(
            final_plan_text="# plan",
            planning_brief={},
            source="test",
            costs=[],
        )
    )

    assert labels == ["structured_first", "structured_repair"]
