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


async def retry_structured_card_before_release(
    *,
    stage2: Stage2Automator,
    final_result: dict[str, Any],
    emit_milestone: Callable[..., None],
    log_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Give a failed inline enhanced card its one retry before the job completes.

    The athlete stays on the generation screen until the job completes, so the
    retry must happen here, not after release. Doing it after release showed the
    plain-text fallback while the retry was still running. Runs the same
    conversion the post-release retry used (``attempt_structured_plan_for_result``
    through the canonical trigger), so only plans the inline pass could have
    converted are retried. Never raises: on any failure or timeout the inline
    outcome stands and the plan releases on the text fallback.
    """
    from ..stage2_automation import (
        _merge_stage2_costs,
        _structured_plan_enabled,
        attempt_structured_plan_for_result,
        has_clean_structured_card,
        should_attempt_structured_plan,
    )

    if has_clean_structured_card(final_result):
        return final_result
    # Without a converter a retry can only record "unavailable" again.
    if getattr(stage2, "_attempt_structured_plan", None) is None:
        return final_result
    if not should_attempt_structured_plan(final_result, _structured_plan_enabled()):
        return final_result

    emit_milestone(
        "structured_card_retry_started",
        "Retrying your enhanced card",
        "The first enhanced card attempt did not validate; building it again before release.",
    )
    candidate = dict(final_result)
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
            "Enhanced card retry finished",
            "The retry could not complete; releasing the plan.",
        )
        return final_result

    if costs:
        retried["stage2_cost"] = _merge_stage2_costs(final_result.get("stage2_cost"), *costs)
    emit_milestone(
        "structured_card_retry_finished",
        "Enhanced card retry finished",
        "Enhanced card ready."
        if has_clean_structured_card(retried)
        else "The retry did not validate either; releasing the plan.",
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
