from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

from fightcamp.stage2_pipeline import build_stage2_package, review_stage2_output
from fightcamp.stage2_policy import (
    admin_review_blocking_findings,
    apply_stage2_release_policy,
    athlete_release_with_flags_findings,
)

from .generation.time_utils import utc_now_iso as _utc_now_iso
from .structured_card_lifecycle import (
    clear_structured_card_attempt_started,
    mark_structured_card_attempt_started,
)
from .structured_plan_generation import (
    StructuredPlanOutcome,
    build_structured_plan_outcome,
    build_structured_plan_prompt,
    has_clean_structured_card,
    parse_structured_json,
    should_attempt_structured_plan,
)
from .structured_plan_models import build_strict_structured_plan_schema
from .structured_plan_sparring_reconcile import reconcile_coach_led_sparring_days

# Plan statuses this module writes. Both are athlete-displayable: Stage 2
# validator findings never hold a plan. `publishable_with_flags` is also in
# ADMIN_REVIEW_PLAN_STATUSES, so a flagged plan reaches the athlete AND stays in
# the admin review surface. `held_for_review` / `review_required` are written by
# admin actions and Stage 1 triage elsewhere, never here.
# See docs/state_machine.md > "Stage 2 outcomes".
_APP_STATUS_READY = "ready"
_APP_STATUS_PUBLISHABLE_WITH_FLAGS = "publishable_with_flags"
_STAGE2_PASS = "stage2_pass"
_STAGE2_FAILED = "stage2_failed"
# `stage2_status` audit value for a technical Stage 2 failure — the finalizer
# never produced a usable plan (timeout, provider error, unavailable, incomplete
# output) — so the deterministic Stage 1 plan was completed instead. Distinct
# from `stage2_failed`, which means Stage 2 DID produce a plan that the validator
# flagged. Never a plan or job status.
STAGE2_STAGE1_FALLBACK = "stage2_failed_stage1_fallback"
# Key under `stage2_validator_report` recording why Stage 2 was unusable.
STAGE2_FALLBACK_REPORT_KEY = "stage2_fallback"

logger = logging.getLogger(__name__)
_DEFAULT_FIRST_PASS_CHAR_LIMIT = 180_000
_DEFAULT_OPENAI_MAX_RETRIES = 0
_DEFAULT_MAX_OUTPUT_TOKENS = 0


def _released_with_flags_report(validator_report: dict[str, Any]) -> dict[str, Any]:
    """Record that a plan with validator blockers was released anyway.

    Every finding is kept verbatim so the admin review surface still shows what
    the validator caught. Only the release decision changes, so the persisted
    report agrees with the saved `publishable_with_flags` status instead of
    claiming a hold that no longer happens.
    """

    return {
        **validator_report,
        "release_decision": "publish_with_flags",
        "is_athlete_releasable": True,
        "is_publishable": True,
    }


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
    # ``incomplete`` response and raises Stage2AutomationError. That no longer
    # fails the job — the orchestrator completes it on the Stage 1 plan — but the
    # athlete silently loses the coach-voice pass, so a cap is still worth
    # avoiding. Default is 0 = no cap (provider default) so plans are never
    # truncated; the Stage 2 timeout still bounds runtime. Set a positive value
    # to bound output cost/latency.
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


def _stage2_structured_timeout_seconds() -> float:
    # Per-request timeout for the structured-card calls only (structured_first /
    # structured_repair). Card conversion regularly runs longer than the plan-text
    # pass, so it gets a wider budget than the client default above. Raising this
    # is only effective while APP_STAGE2_FINALIZE_TIMEOUT_SECONDS (the whole-finalize
    # budget in api/generation/timeouts.py) leaves room for it.
    default_timeout = 600.0
    raw_value = os.getenv("UNLXCK_STAGE2_STRUCTURED_TIMEOUT_SECONDS", str(default_timeout)).strip()
    try:
        return max(1.0, float(raw_value))
    except ValueError:
        logger.warning(
            "[stage2] invalid float env UNLXCK_STAGE2_STRUCTURED_TIMEOUT_SECONDS=%r; using %s",
            raw_value,
            default_timeout,
        )
        return default_timeout


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

    On by default: the structured card is the athlete-facing plan view, so the
    second conversion call is part of the standard Stage 2 flow. Set
    ``UNLXCK_STAGE2_STRUCTURED_PLAN`` to a falsey value (``0``/``false``/``no``/
    ``off``/empty) to disable it; the structured outcome is then recorded as
    ``not_attempted`` and the raw ``plan_text`` flow is the fallback.
    """

    raw = os.getenv("UNLXCK_STAGE2_STRUCTURED_PLAN")
    if raw is None:
        return True  # unset → default on
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _structured_repair_enabled() -> bool:
    """Whether a failed first structured pass gets one repair retry.

    On by default. The repair retry is the second sequential model call and so is
    the main lever on worst-case structured-card latency. The
    ``[stage2] structured_repair`` telemetry logged in
    :meth:`_generate_structured_outcome` records how often it actually rescues a
    card; if the data shows it rarely helps, set
    ``UNLXCK_STAGE2_STRUCTURED_REPAIR`` to a falsey value to drop it (halving the
    worst case) without a code change. The first-pass outcome then stands as-is.
    """

    raw = os.getenv("UNLXCK_STAGE2_STRUCTURED_REPAIR")
    if raw is None:
        return True  # unset → default on
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Responses-API output-format object requesting a single JSON object. Applied
# only to the structured-card calls (never the markdown plan-text pass).
_STRUCTURED_JSON_FORMAT = {"type": "json_object"}


def _stage2_structured_json_mode() -> bool:
    """Whether the structured-card model calls request JSON output mode.

    On by default. The structured conversion must return one JSON object; asking
    the provider for JSON output mode (Responses API ``text.format`` =
    ``json_object``) guarantees syntactically valid JSON and removes the
    "structured model output was not valid JSON" failure class - the schema,
    normalizer, faithfulness gate, and repair retry still enforce shape/content.
    Set ``UNLXCK_STAGE2_STRUCTURED_JSON_MODE`` to a falsey value to disable it if
    the configured model/endpoint does not accept the parameter (the plan-text
    first pass never uses it, so free-form markdown is unaffected).
    """

    raw = os.getenv("UNLXCK_STAGE2_STRUCTURED_JSON_MODE")
    if raw is None:
        return True  # unset → default on
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _stage2_structured_schema_mode() -> bool:
    """Whether the structured-card calls use strict json_schema (vs json_object).

    OFF by default. When enabled, the calls send the strict json_schema built
    from ``StructuredTrainingPlan`` (via
    :func:`build_strict_structured_plan_schema`) instead of plain JSON object
    mode, so the provider guarantees the response *conforms to the schema* - which
    in turn makes the repair retry unnecessary (disable it with
    ``UNLXCK_STAGE2_STRUCTURED_REPAIR=0`` once schema mode is validated).

    It is off by default deliberately: the strict schema is verified only for
    structural compliance in-repo, and whether the live endpoint accepts it and
    the model output round-trips through validation must be confirmed in staging
    with a real API key first. Set ``UNLXCK_STAGE2_STRUCTURED_SCHEMA_MODE`` to a
    truthy value to opt in. JSON object mode remains the validated default.
    """

    raw = os.getenv("UNLXCK_STAGE2_STRUCTURED_SCHEMA_MODE")
    if raw is None:
        return False  # unset → default off (opt-in)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _structured_response_format() -> dict[str, Any] | None:
    """Pick the Responses-API output-format for the structured-card calls.

    Strict json_schema when schema mode is opted into; otherwise JSON object mode
    when enabled; otherwise ``None`` (free-form). Never applied to the plan-text
    pass. A schema-build failure degrades to JSON object mode rather than raising.
    """

    if _stage2_structured_schema_mode():
        try:
            return {
                "type": "json_schema",
                "name": "structured_training_plan",
                "schema": build_strict_structured_plan_schema(),
                "strict": True,
            }
        except Exception:  # never let schema generation break the call
            # Degrade deterministically to JSON object mode (still valid JSON),
            # not to free-form: schema mode opted into structured output, so a
            # build failure must not silently reintroduce non-JSON responses even
            # when json-object mode is toggled off.
            logger.exception("[stage2] strict schema build failed; falling back to json_object")
            return _STRUCTURED_JSON_FORMAT
    if _stage2_structured_json_mode():
        return _STRUCTURED_JSON_FORMAT
    return None


def _structured_attempt_status(result: dict[str, Any]) -> str:
    """The recorded structured-plan attempt status on a Stage 2 result, or ''."""
    report = result.get("stage2_validator_report")
    debug = report.get("structured_plan") if isinstance(report, dict) else None
    status = debug.get("status") if isinstance(debug, dict) else None
    return str(status or "")


def _record_structured_outcome(
    result: dict[str, Any], outcome: StructuredPlanOutcome
) -> dict[str, Any]:
    """Attach a structured-plan outcome to a Stage 2 result dict.

    The validated plan (or ``None``) and its schema version go to dedicated
    ``structured_plan`` / ``schema_version`` keys that persistence maps to plan
    columns. The status/errors are nested in the existing validator report under
    a ``structured_plan`` key so admins can see them without new storage.
    """

    # Every outcome passed here is terminal, including ``not_attempted``. Clear
    # any durable/in-memory building marker before recording the final debug so a
    # completed conversion can never remain stuck in the building state.
    clear_structured_card_attempt_started(result)
    result["structured_plan"] = outcome.structured_plan
    result["schema_version"] = outcome.schema_version
    report = result.get("stage2_validator_report")
    if not isinstance(report, dict):
        report = {}
        result["stage2_validator_report"] = report
    report["structured_plan"] = outcome.as_debug()
    return result


async def attempt_structured_plan_for_result(
    result: dict[str, Any],
    *,
    planning_brief: Any,
    automator: Any,
    source: str,
    log_context: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Centralized structured-plan trigger for any plan result.

    Single entry point used by both the automated Stage 2 path and the admin
    approval/manual paths, so the decision lives in one place. Gates on the
    canonical :func:`should_attempt_structured_plan` predicate (env flag +
    athlete-displayable status + final plan_text + not already converted), then
    runs the conversion via ``automator`` and records the outcome (and debug)
    onto ``result``. Always returns ``(result, structured_costs)`` and never
    raises — a failure leaves the plan_text fallback intact.
    """

    if not should_attempt_structured_plan(result, _structured_plan_enabled()):
        _record_structured_outcome(result, StructuredPlanOutcome(status="not_attempted"))
        return result, []
    # The automator must expose the conversion method (OpenAIStage2Automator).
    # A disabled/auxiliary automator skips, keeping plan_text the source — but
    # this plan WAS eligible, so record why the conversion could not run: a bare
    # "not_attempted" here previously left admins staring at an unexplained
    # missing card while every plan silently stayed on the markdown fallback.
    converter = getattr(automator, "_attempt_structured_plan", None)
    if converter is None:
        reason = str(getattr(automator, "reason", "") or "").strip() or (
            f"Stage 2 automator {type(automator).__name__} cannot convert structured plans."
        )
        logger.warning(
            "[stage2] structured_plan skipped: converter unavailable source=%s automator=%s reason=%s",
            source,
            type(automator).__name__,
            reason,
        )
        _record_structured_outcome(
            result,
            StructuredPlanOutcome(
                status="not_attempted",
                errors=[f"structured conversion unavailable: {reason}"],
            ),
        )
        return result, []
    # The worker result is not persisted until finalization completes, but it
    # still carries the same lifecycle marker as existing-row conversions. This
    # keeps the canonical result contract consistent and guarantees that any
    # terminal outcome recorded below clears the marker.
    mark_structured_card_attempt_started(result)
    outcome, costs = await converter(
        final_plan_text=str(result.get("final_plan_text") or result.get("plan_text") or ""),
        planning_brief=planning_brief,
        source=source,
        log_context=log_context,
    )
    _record_structured_outcome(result, outcome)
    return result, costs


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


class Stage1FallbackUnavailableError(RuntimeError):
    """Raised when Stage 2 failed and Stage 1 left no plan body to fall back to."""


def build_stage1_fallback_result(
    stage1_result: dict[str, Any],
    *,
    reason: str,
    detail: str = "",
    attempt_count: int = 1,
    stage2_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Complete the job on the Stage 1 plan after a technical Stage 2 failure.

    Used when the finalizer never produced a usable plan — it timed out, threw,
    was unavailable, or returned incomplete/empty output. Stage 1 has already
    built a complete deterministic plan, so the job completes on that instead of
    failing generation and stranding the athlete.

    This is not the validator path: a Stage 2 plan that exists but trips the
    validator is published as `publishable_with_flags` (see `finalize`). Here
    there is no Stage 2 plan at all, so the Stage 1 body is published as `ready`
    with a clean report — the validator never ran against it and has nothing to
    say about it. The failure is recorded under `stage2_fallback` and logged.

    ``attempt_count`` should be 1 when a provider request was actually started
    and 0 only when Stage 2 was unavailable before any call was made.

    Raises :class:`Stage1FallbackUnavailableError` when Stage 1 produced no plan
    text, so the caller keeps its existing failure handling rather than
    publishing an empty plan. That is a Stage 1 failure, which still blocks.
    """

    plan_text = str(stage1_result.get("plan_text") or "").strip()
    if not plan_text:
        raise Stage1FallbackUnavailableError(
            "Stage 1 produced no plan text; nothing to fall back to."
        )
    return {
        **_base_result(stage1_result, draft_plan_text=plan_text, stage2_cost=stage2_cost),
        "status": _APP_STATUS_READY,
        "plan_text": plan_text,
        "final_plan_text": plan_text,
        "stage2_status": STAGE2_STAGE1_FALLBACK,
        "stage2_validator_report": {
            "errors": [],
            "warnings": [],
            "blocking_warnings": [],
            "review_flags": [],
            "release_decision": "publish",
            "is_athlete_releasable": True,
            "is_publishable": True,
            # Terminal structured-card outcome. Without this the card state
            # derives as "none", which reads as "might still be building" and
            # leaves the client polling for a conversion that will never run.
            "structured_plan": StructuredPlanOutcome(
                status="not_attempted",
                warnings=["stage 1 fallback released; structured conversion skipped"],
            ).as_debug(),
            STAGE2_FALLBACK_REPORT_KEY: {
                "reason": reason,
                "detail": detail,
                "at": _utc_now_iso(),
            },
        },
        "stage2_retry_text": "",
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
        timeout: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        _enforce_stage2_prompt_budget(prompt, attempt_label=attempt_label, source=source)
        request: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            # Background mode: the provider keeps working on the response
            # server-side, so a dropped connection cannot kill a long generation.
            "background": True,
        }
        if response_format is not None:
            # Constrain the provider's output format (e.g. JSON object mode for the
            # structured-card calls) via the Responses API text.format field. The
            # plan-text first pass leaves this unset so it stays free-form markdown.
            request["text"] = {"format": response_format}
        max_output_tokens = _stage2_max_output_tokens()
        if max_output_tokens > 0:
            request["max_output_tokens"] = max_output_tokens
        if timeout is not None:
            # Per-request override. Do NOT pass None through: the SDK treats an
            # explicit None as "no timeout at all" rather than the client default.
            request["timeout"] = timeout
        logger.info(
            "[stage2] sending %s prompt to model=%s chars=%s max_output_tokens=%s timeout=%s format=%s",
            attempt_label,
            self.model,
            len(prompt),
            max_output_tokens or "unset",
            timeout if timeout is not None else "client_default",
            (response_format or {}).get("type", "text"),
        )
        try:
            # Stream instead of a single blocking create: the HTTP read timeout
            # then applies to the gap between events, not the whole generation,
            # so long responses stop tripping idle-connection timeouts.
            # get_final_response() drains the stream and returns the same
            # Response object create() would have.
            async with self.client.responses.stream(**request) as stream:
                response = await stream.get_final_response()
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
        first_review = {
            **first_review,
            "validator_report": apply_stage2_release_policy(first_review["validator_report"]),
        }
        quality_findings = athlete_release_with_flags_findings(first_review["validator_report"])
        admin_blocking_findings = admin_review_blocking_findings(first_review["validator_report"])
        release_decision = first_review["validator_report"].get("release_decision")
        logger.info(
            "[stage2] first_pass review status=%s needs_retry=%s release_decision=%s quality_flags=%s admin_blockers=%s",
            first_review["status"],
            first_review["needs_retry"],
            release_decision,
            len(quality_findings),
            len(admin_blocking_findings),
        )

        # Stage 2 validator findings never hold a plan. Every outcome below is
        # athlete-displayable; the findings decide which release status is
        # written, not whether the plan is released.
        if release_decision == "publish":
            result = _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=first_pass_text,
                validator_report=first_review["validator_report"],
                attempt_count=1,
                stage2_status=_STAGE2_PASS,
                app_status=_APP_STATUS_READY,
                stage2_cost=first_pass_cost,
            )
        elif release_decision == "publish_with_flags":
            logger.info(
                "[stage2] first_pass releasing with quality flags count=%s",
                len(quality_findings),
            )
            result = _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=first_pass_text,
                validator_report=first_review["validator_report"],
                attempt_count=1,
                stage2_status=_STAGE2_PASS,
                app_status=_APP_STATUS_PUBLISHABLE_WITH_FLAGS,
                stage2_cost=first_pass_cost,
            )
        else:
            # What used to be an admin hold. The plan is released with flags and
            # stays in the admin review surface (`publishable_with_flags` is in
            # ADMIN_REVIEW_PLAN_STATUSES), so every finding is still visible to
            # admins — it just no longer gates delivery to the athlete. The
            # `stage2_failed` audit value records that the validator did fail.
            logger.warning(
                "[stage2] first_pass has release blockers; releasing with flags for admin audit "
                "(errors=%s blocking=%s admin_blockers=%s)",
                len(first_review["validator_report"].get("errors") or []),
                len(first_review["validator_report"].get("blocking_warnings") or []),
                len(admin_blocking_findings),
            )
            result = _approved_result(
                stage1_result,
                draft_plan_text=draft_plan_text,
                final_plan_text=first_pass_text,
                validator_report=_released_with_flags_report(first_review["validator_report"]),
                attempt_count=1,
                stage2_status=_STAGE2_FAILED,
                app_status=_APP_STATUS_PUBLISHABLE_WITH_FLAGS,
                stage2_cost=first_pass_cost,
            )

        # Structured-plan conversion is triggered by the canonical state-machine
        # predicate (athlete-displayable plans only), not a hardcoded Stage 2
        # status. Any failure degrades to the plan_text fallback and is recorded
        # for admin debug — a missing or rejected card never holds the plan.
        result, structured_costs = await attempt_structured_plan_for_result(
            result,
            planning_brief=package["planning_brief"],
            automator=self,
            source=source,
            log_context=log_context,
        )
        if _structured_plan_enabled() and not has_clean_structured_card(result):
            # Logged, not held: the raw Stage 2 plan_text is the athlete-facing
            # fallback and the card status stays on the report for admins.
            logger.warning(
                "[stage2] no clean structured card; releasing on the plan_text fallback (card_status=%s)",
                _structured_attempt_status(result) or "unknown",
            )

        # Roll the structured calls' tokens into the persisted cost row so it
        # reflects total Stage 2 spend, not just the plan-text pass.
        result["stage2_cost"] = _merge_stage2_costs(first_pass_cost, *structured_costs)
        return result

    async def _attempt_structured_plan(
        self,
        *,
        final_plan_text: str,
        planning_brief: Any,
        source: str,
        log_context: dict[str, str] | None = None,
    ) -> tuple[StructuredPlanOutcome, list[dict[str, Any]]]:
        """Best-effort structured-plan generation. Never raises.

        The enable flag and displayable-status gating live in
        :func:`should_attempt_structured_plan`; this method just runs the
        conversion (first pass + one repair retry) and returns the outcome plus
        the cost telemetry of any structured model calls made.
        """

        if not final_plan_text.strip():
            return StructuredPlanOutcome(status="not_attempted"), []
        costs: list[dict[str, Any]] = []
        try:
            return await self._generate_structured_outcome(
                final_plan_text=final_plan_text,
                planning_brief=planning_brief,
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

    @staticmethod
    def _reconcile_coach_led(outcome: StructuredPlanOutcome, planning_brief: Any) -> StructuredPlanOutcome:
        """Guarantee declared sparring/coach-led days render as cards.

        The converted card derives a day's coach-led status from the LLM headline
        alone, so a dropped or mislabelled day silently becomes "Rest day.". The
        deterministic role map already knows every sparring day, so stamp/insert
        those cards from it. No-op unless the outcome actually carries a plan.
        """
        if outcome.structured_plan is None:
            return outcome
        notes = reconcile_coach_led_sparring_days(outcome.structured_plan, planning_brief)
        if notes:
            outcome.warnings = list(outcome.warnings) + [
                f"coach_led_reconcile: {note}" for note in notes
            ]
        return outcome

    async def _generate_structured_outcome(
        self,
        *,
        final_plan_text: str,
        planning_brief: Any,
        source: str,
        log_context: dict[str, str] | None = None,
        costs: list[dict[str, Any]],
    ) -> tuple[StructuredPlanOutcome, list[dict[str, Any]]]:
        if not isinstance(planning_brief, dict):
            planning_brief = None
        event_date = ""
        if planning_brief:
            event_date = str(planning_brief.get("fight_date") or "")

        json_format = _structured_response_format()

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
            timeout=_stage2_structured_timeout_seconds(),
            response_format=json_format,
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
        computed_support = (
            planning_brief.get("computed_support") if isinstance(planning_brief, dict) else None
        )
        first_outcome = build_structured_plan_outcome(
            first_json,
            raw_markdown=final_plan_text,
            computed_support=computed_support,
            planning_brief=planning_brief,
        )
        # A safety-blocked card is terminal: it was schema-valid, so the repair
        # path would re-validate the same JSON and hit the same blocking
        # findings — never spend the repair call on it.
        if first_outcome.status in ("valid", "blocked_by_safety_audit"):
            return self._reconcile_coach_led(first_outcome, planning_brief), costs

        # The repair retry is the second sequential model call (the dominant cost
        # on worst-case latency). It is gated so it can be dropped via env once
        # telemetry shows how rarely it rescues a card.
        if not _structured_repair_enabled():
            logger.info(
                "[stage2] structured_repair skipped (disabled) first_status=%s",
                first_outcome.status,
            )
            return self._reconcile_coach_led(first_outcome, planning_brief), costs

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
            timeout=_stage2_structured_timeout_seconds(),
            response_format=json_format,
        )
        costs.append(repair_cost)
        repaired_json = parse_structured_json(repaired_text)
        repaired_outcome = build_structured_plan_outcome(
            first_json,
            raw_markdown=final_plan_text,
            repair_fn=lambda _data, _errors: repaired_json,
            computed_support=computed_support,
            planning_brief=planning_brief,
        )
        # Telemetry for the repair lever: did the second call actually rescue a
        # card the first pass could not produce? Aggregated over time this tells
        # us whether the retry is worth its latency (see _structured_repair_enabled).
        logger.info(
            "[stage2] structured_repair first_status=%s repaired_status=%s rescued=%s",
            first_outcome.status,
            repaired_outcome.status,
            repaired_outcome.status in {"valid", "repair_attempted_valid"},
        )
        return self._reconcile_coach_led(repaired_outcome, planning_brief), costs


def build_default_stage2_automator() -> Stage2Automator:
    return OpenAIStage2Automator.from_env()
