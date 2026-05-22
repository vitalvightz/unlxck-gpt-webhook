from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

from fightcamp.stage2_pipeline import build_stage2_package, review_stage2_output

_APP_STATUS_READY = "ready"
_APP_STATUS_REVIEW_REQUIRED = "review_required"
_STAGE2_PASS = "stage2_pass"
_STAGE2_FAILED = "stage2_failed"

logger = logging.getLogger(__name__)
_DEFAULT_FIRST_PASS_CHAR_LIMIT = 120_000
_DEFAULT_OPENAI_MAX_RETRIES = 0


class Stage2AutomationError(RuntimeError):
    """Raised when Stage 2 automation cannot complete successfully."""


class Stage2AutomationUnavailableError(Stage2AutomationError):
    """Raised when Stage 2 automation is not configured for runtime use."""


class Stage2Automator(Protocol):
    async def finalize(self, *, stage1_result: dict[str, Any]) -> dict[str, Any]: ...


def _env_int(name: str, default: int, *, minimum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return max(minimum, int(raw_value))
    except ValueError:
        logger.warning("[stage2] invalid integer env %s=%r; using %s", name, raw_value, default)
        return default


def _stage2_char_limit(attempt_label: str) -> int:
    return _env_int(
        "UNLXCK_STAGE2_MAX_FIRST_PASS_CHARS",
        _DEFAULT_FIRST_PASS_CHAR_LIMIT,
        minimum=1,
    )


def _stage2_openai_max_retries() -> int:
    return _env_int(
        "UNLXCK_STAGE2_OPENAI_MAX_RETRIES",
        _DEFAULT_OPENAI_MAX_RETRIES,
        minimum=0,
    )


def _estimated_input_tokens(prompt: str) -> int:
    if not prompt:
        return 0
    return max(1, (len(prompt) + 3) // 4)


def _token_rate_per_1m(name: str) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return 0.0
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        logger.warning("[stage2] invalid token cost env %s=%r; using 0", name, raw_value)
        return 0.0


def _estimated_cost_usd(input_tokens: int, output_tokens: int = 0) -> float:
    input_rate = _token_rate_per_1m("UNLXCK_STAGE2_INPUT_COST_PER_1M")
    output_rate = _token_rate_per_1m("UNLXCK_STAGE2_OUTPUT_COST_PER_1M")
    return round((input_tokens / 1_000_000 * input_rate) + (output_tokens / 1_000_000 * output_rate), 6)


def _get_usage_value(usage: Any, key: str) -> int | None:
    if isinstance(usage, dict):
        value = usage.get(key)
    else:
        value = getattr(usage, key, None)
    if isinstance(value, int):
        return value
    return None


def _extract_response_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump(mode="python")
    return {
        "input_tokens": _get_usage_value(usage, "input_tokens") or _get_usage_value(usage, "prompt_tokens"),
        "output_tokens": _get_usage_value(usage, "output_tokens") or _get_usage_value(usage, "completion_tokens"),
        "total_tokens": _get_usage_value(usage, "total_tokens"),
    }


def _is_quota_or_rate_limit_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "insufficient_quota" in message
        or "exceeded your current quota" in message
        or "rate_limit_exceeded" in message
        or "too many requests" in message
        or "429" in message
    )


def _stage2_source(stage1_result: dict[str, Any]) -> str:
    explicit = str(stage1_result.get("_generation_source") or "").strip()
    if explicit:
        return explicit
    why_log = stage1_result.get("why_log") if isinstance(stage1_result.get("why_log"), dict) else {}
    if isinstance(why_log.get("injury_triage_resume_override"), dict):
        return "admin_triage_resume"
    return "unknown"


def _log_stage2_prompt_budget(prompt: str, *, attempt_label: str, source: str, will_send: bool) -> None:
    estimated_tokens = _estimated_input_tokens(prompt)
    logger.info(
        "[stage2] prompt_budget stage2_attempt=%s source=%s prompt_chars=%s "
        "estimated_input_tokens=%s max_allowed_chars=%s will_send=%s estimated_cost_usd=%s",
        attempt_label,
        source,
        len(prompt),
        estimated_tokens,
        _stage2_char_limit(attempt_label),
        will_send,
        _estimated_cost_usd(estimated_tokens),
    )


def _enforce_stage2_prompt_budget(prompt: str, *, attempt_label: str, source: str) -> None:
    limit = _stage2_char_limit(attempt_label)
    will_send = len(prompt) <= limit
    _log_stage2_prompt_budget(prompt, attempt_label=attempt_label, source=source, will_send=will_send)
    if not will_send:
        raise Stage2AutomationError(
            f"Stage 2 {attempt_label} prompt too large: {len(prompt)} chars > {limit}"
        )


def _strip_wrapping_code_fence(text: str) -> str:
    normalized = text.strip()
    if not normalized.startswith("```") or not normalized.endswith("```"):
        return normalized
    first_newline = normalized.find("\n")
    if first_newline == -1:
        return normalized.strip("`").strip()
    return normalized[first_newline + 1 : -3].strip()


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return _strip_wrapping_code_fence(output_text)

    payload = response.model_dump(mode="python") if hasattr(response, "model_dump") else response
    if not isinstance(payload, dict):
        raise Stage2AutomationError("Stage 2 model returned an unreadable response payload.")

    parts: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = str(content.get("text") or "").strip()
                if text:
                    parts.append(text)

    combined = "\n".join(parts).strip()
    if not combined:
        raise Stage2AutomationError("Stage 2 model returned no plan text.")
    return _strip_wrapping_code_fence(combined)


def _base_result(stage1_result: dict[str, Any], *, draft_plan_text: str) -> dict[str, Any]:
    return {
        **stage1_result,
        "draft_plan_text": draft_plan_text,
        # The Stage 1 PDF reflects the raw draft, so do not publish it as the final athlete artifact.
        "pdf_url": None,
        "stage2_retry_text": "",
        "stage2_validator_report": {},
        "stage2_attempt_count": 0,
        "stage2_status": "",
        "final_plan_text": "",
    }


def _approved_result(
    stage1_result: dict[str, Any],
    *,
    draft_plan_text: str,
    final_plan_text: str,
    validator_report: dict[str, Any],
    attempt_count: int,
    stage2_status: str,
    retry_text: str = "",
) -> dict[str, Any]:
    return {
        **_base_result(stage1_result, draft_plan_text=draft_plan_text),
        "status": _APP_STATUS_READY,
        "plan_text": final_plan_text,
        "final_plan_text": final_plan_text,
        "stage2_status": stage2_status,
        "stage2_validator_report": validator_report,
        "stage2_retry_text": retry_text,
        "stage2_attempt_count": attempt_count,
    }


def _review_required_result(
    stage1_result: dict[str, Any],
    *,
    draft_plan_text: str,
    latest_plan_text: str,
    validator_report: dict[str, Any],
    retry_text: str,
    attempt_count: int,
) -> dict[str, Any]:
    return {
        **_base_result(stage1_result, draft_plan_text=draft_plan_text),
        "status": _APP_STATUS_REVIEW_REQUIRED,
        "plan_text": "",
        "final_plan_text": latest_plan_text,
        "stage2_status": _STAGE2_FAILED,
        "stage2_validator_report": validator_report,
        "stage2_retry_text": retry_text,
        "stage2_attempt_count": attempt_count,
    }


@dataclass
class DisabledStage2Automator:
    reason: str

    async def finalize(self, *, stage1_result: dict[str, Any]) -> dict[str, Any]:
        raise Stage2AutomationUnavailableError(self.reason)


@dataclass
class OpenAIStage2Automator:
    client: Any
    model: str
    max_output_tokens: int | None = None

    @classmethod
    def from_env(cls) -> Stage2Automator:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return DisabledStage2Automator(
                "OPENAI_API_KEY is required for automated Stage 2 finalization."
            )

        try:
            from openai import AsyncOpenAI
        except ImportError:
            return DisabledStage2Automator(
                "The openai package is required for automated Stage 2 finalization."
            )

        model = os.getenv("UNLXCK_STAGE2_MODEL", "gpt-5-mini").strip() or "gpt-5-mini"
        timeout_seconds = float(os.getenv("UNLXCK_STAGE2_TIMEOUT_SECONDS", "90"))
        max_output_tokens = os.getenv("UNLXCK_STAGE2_MAX_OUTPUT_TOKENS", "").strip()
        client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=_stage2_openai_max_retries(),
        )
        return cls(
            client=client,
            model=model,
            max_output_tokens=int(max_output_tokens) if max_output_tokens else None,
        )

    async def _generate_text(self, prompt: str, *, attempt_label: str, source: str) -> str:
        _enforce_stage2_prompt_budget(prompt, attempt_label=attempt_label, source=source)
        request: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }
        if self.max_output_tokens is not None:
            request["max_output_tokens"] = self.max_output_tokens
        logger.info(
            "[stage2] sending %s prompt to model=%s chars=%s",
            attempt_label,
            self.model,
            len(prompt),
        )
        try:
            response = await self.client.responses.create(**request)
        except Exception as exc:  # pragma: no cover - provider failure surfaces via integration
            if _is_quota_or_rate_limit_error(exc):
                raise Stage2AutomationError(
                    "Stage 2 stopped: OpenAI quota/rate limit hit. No further retry attempted."
                ) from exc
            raise Stage2AutomationError(f"Stage 2 model request failed: {exc}") from exc
        response_id = getattr(response, "id", None) or "unknown"
        text = _extract_response_text(response)
        usage = _extract_response_usage(response)
        actual_input_tokens = usage["input_tokens"] or _estimated_input_tokens(prompt)
        actual_output_tokens = usage["output_tokens"] or _estimated_input_tokens(text)
        total_tokens = usage["total_tokens"] or actual_input_tokens + actual_output_tokens
        logger.info(
            "[stage2] received %s response id=%s chars=%s actual_input_tokens=%s "
            "actual_output_tokens=%s total_tokens=%s estimated_cost_usd=%s",
            attempt_label,
            response_id,
            len(text),
            actual_input_tokens,
            actual_output_tokens,
            total_tokens,
            _estimated_cost_usd(actual_input_tokens, actual_output_tokens),
        )
        return text

    async def finalize(self, *, stage1_result: dict[str, Any]) -> dict[str, Any]:
        package = build_stage2_package(stage1_result=stage1_result)
        draft_plan_text = str(package.get("draft_plan_text") or "")
        handoff_text = str(package["handoff_text"])
        source = _stage2_source(stage1_result)
        logger.info(
            "[stage2] package ready model=%s source=%s handoff_chars=%s draft_chars=%s max_model_calls=1",
            self.model,
            source,
            len(handoff_text),
            len(draft_plan_text),
        )

        first_pass_text = await self._generate_text(handoff_text, attempt_label="first_pass", source=source)
        first_review = review_stage2_output(
            planning_brief=package["planning_brief"],
            final_plan_text=first_pass_text,
        )
        logger.info(
            "[stage2] first_pass review status=%s needs_retry=%s",
            first_review["status"],
            first_review["needs_retry"],
        )

        if first_review["status"] == "PASS":
            return _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=first_pass_text,
                validator_report=first_review["validator_report"],
                attempt_count=1,
                stage2_status=_STAGE2_PASS,
            )

        logger.warning("[stage2] review required after first_pass: automatic retry disabled")
        return _review_required_result(
            stage1_result,
            draft_plan_text=draft_plan_text,
            latest_plan_text=first_pass_text,
            validator_report=first_review["validator_report"],
            retry_text="",
            attempt_count=1,
        )


def build_default_stage2_automator() -> Stage2Automator:
    return OpenAIStage2Automator.from_env()
