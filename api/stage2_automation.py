from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from fightcamp.stage2_pipeline import build_stage2_package, review_stage2_output

from .structured_plan_generation import (
    StructuredPlanOutcome,
    build_structured_plan_outcome,
    build_structured_plan_prompt,
    parse_structured_json,
)

_APP_STATUS_READY = "ready"
_APP_STATUS_PUBLISHABLE_WITH_FLAGS = "publishable_with_flags"
_APP_STATUS_HELD_FOR_REVIEW = "held_for_review"
_APP_STATUS_REVIEW_REQUIRED = "review_required"
_STAGE2_PASS = "stage2_pass"
_STAGE2_FAILED = "stage2_failed"

logger = logging.getLogger(__name__)
_DEFAULT_FIRST_PASS_CHAR_LIMIT = 180_000
_DEFAULT_OPENAI_MAX_RETRIES = 0
_DEFAULT_MAX_OUTPUT_TOKENS = 0


class Stage2AutomationError(RuntimeError):
    """Raised when Stage 2 automation cannot complete successfully.

    Carries an optional ``stage2_cost`` payload (token/cost telemetry captured up
    to the point of failure) so the orchestrator can still persist what is known
    about a failed attempt.
    """

    stage2_cost: dict[str, Any] | None = None


def _with_stage2_cost(
    error: Stage2AutomationError, cost: dict[str, Any]
) -> Stage2AutomationError:
    error.stage2_cost = cost
    return error


class Stage2AutomationUnavailableError(Stage2AutomationError):
    """Raised when Stage 2 automation is not configured for runtime use."""


class Stage2Automator(Protocol):
    async def finalize(
        self, *, stage1_result: dict[str, Any], log_context: dict[str, str] | None = None
    ) -> dict[str, Any]: ...


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


def _stage2_max_output_tokens() -> int:
    # Bounds output token count (and therefore cost/latency) on the Stage 2 call.
    # This budget is SHARED with the model's reasoning tokens (gpt-5-* burn a
    # large, hidden share of it before emitting any plan text), so a positive cap
    # set too low truncates the plan mid-output: ``_generate_text`` then sees an
    # ``incomplete`` response and raises Stage2AutomationError, which fails the
    # generation job (the athlete can retry). Default is 0 = no cap (provider
    # default) so plans are never truncated; the Stage 2 timeout still bounds
    # runtime. Set a positive value to bound output cost/latency.
    return _env_int(
        "UNLXCK_STAGE2_MAX_OUTPUT_TOKENS",
        _DEFAULT_MAX_OUTPUT_TOKENS,
        minimum=0,
    )


def _stage2_timeout_seconds() -> float:
    default_timeout = 210.0
    raw_value = os.getenv("UNLXCK_STAGE2_TIMEOUT_SECONDS", str(default_timeout)).strip()
    try:
        return max(1.0, float(raw_value))
    except ValueError:
        logger.warning("[stage2] invalid float env UNLXCK_STAGE2_TIMEOUT_SECONDS=%r; using %s", raw_value, default_timeout)
        return default_timeout


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _build_stage2_cost(
    model: str,
    *,
    prompt: str,
    response: Any = None,
    text: str | None = None,
    attempt_count: int = 1,
) -> dict[str, Any]:
    """Build the Stage 2 token/cost telemetry row persisted to generation_jobs.

    Captures *actual* usage from the OpenAI response when present, falling back
    to char-based estimates only when the provider omits a usage field. Safe to
    call on the failure path: anything genuinely unknown (e.g. output tokens
    when the request failed before a response) is recorded as ``None`` rather
    than fabricated, and the function never raises. The dict keys match the
    generation_jobs columns so the store can persist it directly. This carries
    no plan text or raw response body — only counts, the model id, the response
    id, and a timestamp.
    """
    usage = (
        _extract_response_usage(response)
        if response is not None
        else {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    )

    input_tokens = usage["input_tokens"]
    if input_tokens is None:
        input_tokens = _estimated_input_tokens(prompt)

    output_tokens = usage["output_tokens"]
    if output_tokens is None and text is not None:
        output_tokens = _estimated_input_tokens(text)

    total_tokens = usage["total_tokens"]
    if total_tokens is None and output_tokens is not None:
        total_tokens = (input_tokens or 0) + output_tokens

    response_id = getattr(response, "id", None) if response is not None else None
    if not response_id or response_id == "unknown":
        response_id = None

    return {
        "stage2_model": model,
        "stage2_input_tokens": input_tokens,
        "stage2_output_tokens": output_tokens,
        "stage2_total_tokens": total_tokens,
        "stage2_estimated_cost_usd": _estimated_cost_usd(input_tokens or 0, output_tokens or 0),
        "stage2_attempt_count": attempt_count,
        "stage2_response_id": response_id,
        "stage2_cost_recorded_at": _utc_now_iso(),
    }


def _merge_stage2_costs(*costs: dict[str, Any] | None) -> dict[str, Any]:
    """Aggregate token/cost telemetry across multiple Stage 2 model calls.

    Stage 2 normally makes a single model call, but when structured-plan
    generation is enabled it makes one or two more. Token counts and the
    estimated USD cost are summed so the persisted cost row reflects *total*
    Stage 2 spend; metadata (model, response_id, attempt_count, recorded_at) is
    taken from the last call. ``None``/empty entries are ignored.
    """

    token_keys = ("stage2_input_tokens", "stage2_output_tokens", "stage2_total_tokens")
    merged: dict[str, Any] = {}
    for cost in costs:
        if not cost:
            continue
        # Compute running totals from the prior accumulation *before* adopting the
        # current call's metadata, so the current call is counted exactly once.
        running_tokens = {
            key: (merged.get(key) or 0) + (cost.get(key) or 0) for key in token_keys
        }
        running_usd = (merged.get("stage2_estimated_cost_usd") or 0.0) + (
            cost.get("stage2_estimated_cost_usd") or 0.0
        )
        merged = dict(cost)
        merged.update(running_tokens)
        merged["stage2_estimated_cost_usd"] = running_usd
    return merged


def _is_quota_or_rate_limit_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "insufficient_quota" in message
        or "exceeded your current quota" in message
        or "rate_limit_exceeded" in message
        or "too many requests" in message
        or "429" in message
    )


def _structured_plan_enabled() -> bool:
    """Whether Stage 2 should also attempt structured-plan generation.

    Off by default: structured generation is a second model call, so it is
    opt-in (set ``UNLXCK_STAGE2_STRUCTURED_PLAN=1``) to preserve the single-call
    Stage 2 cost profile until the structured renderer is rolled out. When off,
    the structured outcome is recorded as ``not_attempted`` and the raw
    ``plan_text`` flow is unaffected.
    """

    return os.getenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _record_structured_outcome(
    result: dict[str, Any], outcome: StructuredPlanOutcome
) -> dict[str, Any]:
    """Attach a structured-plan outcome to a Stage 2 result dict.

    The validated plan (or ``None``) and its schema version go to dedicated
    ``structured_plan`` / ``schema_version`` keys that persistence maps to plan
    columns. The status/errors are nested in the existing validator report under
    a ``structured_plan`` key so admins can see them without new storage.
    """

    result["structured_plan"] = outcome.structured_plan
    result["schema_version"] = outcome.schema_version
    report = result.get("stage2_validator_report")
    if isinstance(report, dict):
        report["structured_plan"] = outcome.as_debug()
    return result


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




def _response_is_incomplete(response: Any) -> bool:
    payload = response.model_dump(mode="python") if hasattr(response, "model_dump") else response
    is_dict = isinstance(payload, dict)

    status = str((payload.get("status") if is_dict else getattr(response, "status", "")) or "").strip().lower()
    if status == "incomplete":
        return True

    details = payload.get("incomplete_details") if is_dict else getattr(response, "incomplete_details", None)
    if details is None:
        return False
    if hasattr(details, "model_dump"):
        details = details.model_dump(mode="python")

    if isinstance(details, dict):
        detail_text = " ".join(str(value) for value in details.values() if value is not None).lower()
    else:
        detail_text = str(details).lower()

    return any(marker in detail_text for marker in ("max_output_tokens", "output", "token", "length"))

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


def _base_result(
    stage1_result: dict[str, Any],
    *,
    draft_plan_text: str,
    stage2_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **stage1_result,
        "draft_plan_text": draft_plan_text,
        # Keep the legacy response field null; plans are displayed in-app, not exported.
        "pdf_url": None,
        "stage2_retry_text": "",
        "stage2_validator_report": {},
        "stage2_attempt_count": 0,
        "stage2_status": "",
        "final_plan_text": "",
        # Structured plan output (schema-first). Defaults to absent; populated by
        # the structured-generation attempt on a passing plan when enabled.
        # Persistence maps these to the plans.structured_plan / schema_version
        # columns and drops them gracefully on legacy schemas.
        "structured_plan": None,
        "schema_version": None,
        # Token/cost telemetry captured from the Stage 2 model call. Persistence
        # maps this to dedicated generation_jobs columns; it is not the plan body.
        "stage2_cost": stage2_cost or {},
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
    app_status: str = _APP_STATUS_READY,
    stage2_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **_base_result(stage1_result, draft_plan_text=draft_plan_text, stage2_cost=stage2_cost),
        "status": app_status,
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
    stage2_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **_base_result(stage1_result, draft_plan_text=draft_plan_text, stage2_cost=stage2_cost),
        "status": _APP_STATUS_HELD_FOR_REVIEW,
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

    async def finalize(
        self, *, stage1_result: dict[str, Any], log_context: dict[str, str] | None = None
    ) -> dict[str, Any]:
        raise Stage2AutomationUnavailableError(self.reason)


@dataclass
class OpenAIStage2Automator:
    client: Any
    model: str

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
        timeout_seconds = _stage2_timeout_seconds()
        client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=_stage2_openai_max_retries(),
        )
        return cls(
            client=client,
            model=model,
        )

    async def _generate_text(
        self,
        prompt: str,
        *,
        attempt_label: str,
        source: str,
        log_context: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        _enforce_stage2_prompt_budget(prompt, attempt_label=attempt_label, source=source)
        request: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }
        max_output_tokens = _stage2_max_output_tokens()
        if max_output_tokens > 0:
            request["max_output_tokens"] = max_output_tokens
        logger.info(
            "[stage2] sending %s prompt to model=%s chars=%s max_output_tokens=%s",
            attempt_label,
            self.model,
            len(prompt),
            max_output_tokens or "unset",
        )
        try:
            response = await self.client.responses.create(**request)
        except Exception as exc:  # pragma: no cover - provider failure surfaces via integration
            # No response means no actual usage; record the estimated input cost
            # so a failed attempt still leaves an auditable cost row.
            failure_cost = _build_stage2_cost(self.model, prompt=prompt, response=None)
            if _is_quota_or_rate_limit_error(exc):
                raise _with_stage2_cost(
                    Stage2AutomationError(
                        "Stage 2 stopped: OpenAI quota/rate limit hit. No further retry attempted."
                    ),
                    failure_cost,
                ) from exc
            # Keep the raw provider exception (which can carry request payloads or
            # provider internals) out of the stored/visible error; the full detail
            # is captured in the server log below.
            logger.exception("[stage2] model_request_failed error_type=%s", type(exc).__name__)
            raise _with_stage2_cost(
                Stage2AutomationError("Stage 2 model request failed. Check server logs."),
                failure_cost,
            ) from exc
        response_id = getattr(response, "id", None) or "unknown"
        if _response_is_incomplete(response):
            # We have a response (with usage), just not a full plan — capture the
            # actual tokens burned before truncation.
            raise _with_stage2_cost(
                Stage2AutomationError(
                    "Stage 2 model response was incomplete before producing a full plan."
                ),
                _build_stage2_cost(self.model, prompt=prompt, response=response),
            )
        try:
            text = _extract_response_text(response)
        except Stage2AutomationError as exc:
            raise _with_stage2_cost(
                exc, _build_stage2_cost(self.model, prompt=prompt, response=response)
            )
        cost = _build_stage2_cost(self.model, prompt=prompt, response=response, text=text)
        # Attribute cost to the job/athlete so it can be aggregated per user from
        # the logs. Falls back to "unknown" when the caller does not supply it.
        context = log_context or {}
        logger.info(
            "[stage2] received %s response id=%s job_id=%s athlete_id=%s chars=%s "
            "actual_input_tokens=%s actual_output_tokens=%s total_tokens=%s estimated_cost_usd=%s",
            attempt_label,
            response_id,
            context.get("job_id") or "unknown",
            context.get("athlete_id") or "unknown",
            len(text),
            cost["stage2_input_tokens"],
            cost["stage2_output_tokens"],
            cost["stage2_total_tokens"],
            cost["stage2_estimated_cost_usd"],
        )
        return text, cost

    async def finalize(
        self, *, stage1_result: dict[str, Any], log_context: dict[str, str] | None = None
    ) -> dict[str, Any]:
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

        first_pass_text, first_pass_cost = await self._generate_text(
            handoff_text, attempt_label="first_pass", source=source, log_context=log_context
        )
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
            app_status = (
                _APP_STATUS_PUBLISHABLE_WITH_FLAGS
                if int(first_review["validator_report"].get("review_flag_count") or 0) > 0
                else _APP_STATUS_READY
            )
            result = _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=first_pass_text,
                validator_report=first_review["validator_report"],
                attempt_count=1,
                stage2_status=_STAGE2_PASS,
                app_status=app_status,
                stage2_cost=first_pass_cost,
            )
            # Additive structured-plan attempt. Never blocks the raw plan: any
            # failure degrades to the plan_text fallback (status not_attempted /
            # invalid_fallback_used) and is recorded for admin debug.
            outcome, structured_costs = await self._attempt_structured_plan(
                final_plan_text=first_pass_text,
                package=package,
                source=source,
                log_context=log_context,
            )
            # Roll the structured calls' tokens into the persisted cost row so it
            # reflects total Stage 2 spend, not just the plan-text pass.
            result["stage2_cost"] = _merge_stage2_costs(first_pass_cost, *structured_costs)
            return _record_structured_outcome(result, outcome)

        logger.warning("[stage2] review required after first_pass: automatic retry disabled")
        return _review_required_result(
            stage1_result,
            draft_plan_text=draft_plan_text,
            latest_plan_text=first_pass_text,
            validator_report=first_review["validator_report"],
            retry_text="",
            attempt_count=1,
            stage2_cost=first_pass_cost,
        )

    async def _attempt_structured_plan(
        self,
        *,
        final_plan_text: str,
        package: dict[str, Any],
        source: str,
        log_context: dict[str, str] | None = None,
    ) -> tuple[StructuredPlanOutcome, list[dict[str, Any]]]:
        """Best-effort structured-plan generation. Never raises.

        Returns the outcome plus the cost telemetry of any structured model
        calls made, so the caller can fold them into the persisted cost row.
        """

        if not _structured_plan_enabled() or not final_plan_text.strip():
            return StructuredPlanOutcome(status="not_attempted"), []
        costs: list[dict[str, Any]] = []
        try:
            return await self._generate_structured_outcome(
                final_plan_text=final_plan_text,
                package=package,
                source=source,
                log_context=log_context,
                costs=costs,
            )
        except Exception:  # never block the raw plan on structured failure
            logger.exception("[stage2] structured_plan attempt failed; using raw fallback")
            # Preserve costs from any calls that did complete before the failure.
            return (
                StructuredPlanOutcome(
                    status="not_attempted",
                    errors=["structured generation error (see server logs)"],
                ),
                costs,
            )

    async def _generate_structured_outcome(
        self,
        *,
        final_plan_text: str,
        package: dict[str, Any],
        source: str,
        log_context: dict[str, str] | None = None,
        costs: list[dict[str, Any]],
    ) -> tuple[StructuredPlanOutcome, list[dict[str, Any]]]:
        planning_brief = package.get("planning_brief") if isinstance(package, dict) else None
        if not isinstance(planning_brief, dict):
            planning_brief = None
        event_date = ""
        if planning_brief:
            event_date = str(planning_brief.get("fight_date") or "")

        first_prompt = build_structured_plan_prompt(
            plan_markdown=final_plan_text,
            planning_brief=planning_brief,
            event_date=event_date,
        )
        first_text, first_cost = await self._generate_text(
            first_prompt,
            attempt_label="structured_first",
            source=source,
            log_context=log_context,
        )
        costs.append(first_cost)
        first_json = parse_structured_json(first_text)
        if first_json is None:
            return (
                StructuredPlanOutcome(
                    status="invalid_fallback_used",
                    errors=["structured model output was not valid JSON"],
                ),
                costs,
            )

        # build_structured_plan_outcome strips biometrics + conservatively
        # normalizes before validating, so a near-miss first pass can succeed
        # without spending a repair call.
        first_outcome = build_structured_plan_outcome(first_json, raw_markdown=final_plan_text)
        if first_outcome.status == "valid":
            return first_outcome, costs

        # Single repair retry: re-prompt with the validation errors and the
        # broken JSON, then let build_structured_plan_outcome score the result.
        repair_prompt = build_structured_plan_prompt(
            plan_markdown=final_plan_text,
            planning_brief=planning_brief,
            event_date=event_date,
            repair_errors=first_outcome.errors,
            broken_json=first_text,
        )
        repaired_text, repair_cost = await self._generate_text(
            repair_prompt,
            attempt_label="structured_repair",
            source=source,
            log_context=log_context,
        )
        costs.append(repair_cost)
        repaired_json = parse_structured_json(repaired_text)
        return (
            build_structured_plan_outcome(
                first_json,
                raw_markdown=final_plan_text,
                repair_fn=lambda _data, _errors: repaired_json,
            ),
            costs,
        )


def build_default_stage2_automator() -> Stage2Automator:
    return OpenAIStage2Automator.from_env()
