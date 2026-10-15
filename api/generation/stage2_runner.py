"""Stage 2 finalization timeout wrapper, the pre-release enhanced-card retry,
and OpenAI quota-error detection."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from .timeouts import _stage2_finalize_timeout_seconds

if TYPE_CHECKING:
    from ..stage2_automation import Stage2Automator

logger = logging.getLogger(__name__)

_OPENAI_QUOTA_ADMIN_ERROR = "OpenAI quota exceeded. Check API billing, credits, project budget, or organization limits."
_OPENAI_QUOTA_ATHLETE_ERROR = "Generation is temporarily unavailable. Please try again later."
# A model conversion of the final text already ran and validation rejected it.
_MODEL_CARD_REJECTED_STATUSES = frozenset({"invalid_fallback_used", "blocked_by_safety_audit"})


async def finalize_stage2_with_timeout(
    *,
    stage2: Stage2Automator,
    stage1_result: dict[str, Any],
    log_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    finalize = stage2.finalize(stage1_result=stage1_result, log_context=log_context)
    timeout_seconds = _stage2_finalize_timeout_seconds()
    if timeout_seconds is None:
        return await finalize
    return await asyncio.wait_for(finalize, timeout=timeout_seconds)


def _planning_brief(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _release_status(final_result: dict[str, Any]) -> str:
    """The status this result will actually be released with.

    Persistence never holds a plan that has content: a held status is rewritten
    to ``publishable_with_flags`` on save (``_release_held_plan_with_flags``).
    Stage 2's inline card gate runs before that, sees the held status and skips
    the card, so the card decision has to use the release status instead.
    """
    from .persistence import _RELEASE_OVERRIDE_HELD_STATUSES, _RELEASE_OVERRIDE_STATUS

    status = str(final_result.get("status") or "").strip().lower()
    has_text = bool(
        str(final_result.get("final_plan_text") or final_result.get("plan_text") or "").strip()
    )
    if status in _RELEASE_OVERRIDE_HELD_STATUSES and has_text:
        return _RELEASE_OVERRIDE_STATUS
    return status


async def retry_structured_card_before_release(
    *,
    stage2: Stage2Automator,
    final_result: dict[str, Any],
    emit_milestone: Callable[..., None],
    log_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make sure the enhanced card has been attempted before the job completes.

    The athlete stays on the generation screen until the job completes, so the
    card must be built here, never after release. This covers a card Stage 2
    never attempted because the plan was held at that point and only released
    with flags on save, and an inline attempt that could not run. A card the
    validators already rejected is not re-converted. Runs the canonical
    conversion (``attempt_structured_plan_for_result``) against the status the
    plan will be released with. Never raises: on any failure or timeout the
    plan releases on the text fallback.
    """
    from ..stage2_automation import (
        _merge_stage2_costs,
        _structured_plan_enabled,
        attempt_structured_plan_for_result,
        has_clean_structured_card,
        record_stage2_model_calls,
        should_attempt_structured_plan,
    )

    if has_clean_structured_card(final_result):
        return final_result
    prior_report = final_result.get("stage2_validator_report")
    prior_card = prior_report.get("structured_plan") if isinstance(prior_report, dict) else None
    prior_status = str((prior_card or {}).get("status") or "not_attempted")
    if prior_status in _MODEL_CARD_REJECTED_STATUSES:
        # The AI converter omitted planner-selected exercises on actual
        # published fights (Louis D-5, Yami D-17/D-24). Never ask it to guess
        # again and never persist its incomplete payload. Use the deterministic
        # planner-owned card, then pass it through the SAME schema, faithfulness
        # and safety audit used for model cards before allowing persistence.
        from ..structured_plan_deterministic_fallback import build_deterministic_structured_plan
        from ..structured_plan_generation import build_structured_plan_outcome
        brief = _planning_brief(final_result.get("planning_brief"))
        source_text = str(final_result.get("final_plan_text") or final_result.get("plan_text") or "")
        if brief and source_text:
            fallback = build_deterministic_structured_plan(brief, plan_text=source_text)
            if fallback:
                outcome = build_structured_plan_outcome(
                    fallback, raw_markdown=source_text, planning_brief=brief,
                    repair_fn=None,
                )
                if outcome.structured_plan and outcome.status == "valid":
                    outcome.warnings.append(
                        "deterministic_recovery: rejected model card omitted planner-selected content"
                    )
                    recovered = dict(final_result)
                    recovered["structured_plan"] = outcome.structured_plan
                    recovered["schema_version"] = outcome.schema_version
                    report = dict(recovered.get("stage2_validator_report") or {})
                    report["structured_plan"] = outcome.as_debug()
                    recovered["stage2_validator_report"] = report
                    logger.info(
                        "[jobs] generation:structured_card_deterministic_recovery_success context=%s",
                        log_context or {},
                    )
                    emit_milestone(
                        "structured_card_retry_finished",
                        "Enhanced card restored",
                        "Planner-selected exercises restored into the enhanced card.",
                    )
                    return recovered
        logger.warning(
            "[jobs] generation:structured_card_recovery_unavailable prior_status=%s context=%s",
            prior_status, log_context or {},
        )
        return final_result
    # Without a converter an attempt can only record "unavailable" again.
    if getattr(stage2, "_attempt_structured_plan", None) is None:
        return final_result
    candidate = {**final_result, "status": _release_status(final_result)}
    if not should_attempt_structured_plan(candidate, _structured_plan_enabled()):
        return final_result

    emit_milestone(
        "structured_card_retry_started",
        "Building your enhanced card",
        "No valid enhanced card yet; building it before release.",
    )
    report = candidate.get("stage2_validator_report")
    candidate["stage2_validator_report"] = dict(report) if isinstance(report, dict) else {}
    try:
        attempt = attempt_structured_plan_for_result(
            candidate,
            planning_brief=_planning_brief(final_result.get("planning_brief")),
            automator=stage2,
            source="generation_card_retry",
            log_context=log_context,
        )
        timeout_seconds = _stage2_finalize_timeout_seconds()
        if timeout_seconds is None:
            retried, costs = await attempt
        else:
            retried, costs = await asyncio.wait_for(attempt, timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - the text fallback must always release
        logger.warning(
            "[jobs] generation:structured_card_retry_failed exc_type=%s context=%s",
            type(exc).__name__,
            log_context or {},
        )
        emit_milestone(
            "structured_card_retry_finished",
            "Enhanced card attempt finished",
            "The card could not be built; releasing the plan.",
        )
        return final_result

    # Only the card is decided here. The release status stays persistence's call.
    retried["status"] = final_result.get("status")
    if costs:
        for cost in costs:
            for call in cost.get("stage2_calls") or []:
                if isinstance(call, dict):
                    # Why this conversion ran: Stage 2 held the plan (no inline
                    # attempt) or the inline attempt could not run.
                    call.setdefault("retry_reason", prior_status)
        retried["stage2_cost"] = _merge_stage2_costs(final_result.get("stage2_cost"), *costs)
        record_stage2_model_calls(retried)
    emit_milestone(
        "structured_card_retry_finished",
        "Enhanced card attempt finished",
        "Enhanced card ready."
        if has_clean_structured_card(retried)
        else "The card did not validate; releasing the plan.",
    )
    return retried


def is_openai_quota_error(error: Exception) -> bool:
    message = str(error or "").lower()
    if (
        "insufficient_quota" in message
        or "exceeded your current quota" in message
        or "openai quota/rate limit" in message
    ):
        return True
    return "429" in message and "quota" in message
