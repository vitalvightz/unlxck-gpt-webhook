"""Stage 2 finalization timeout wrapper and OpenAI quota-error detection."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .timeouts import _stage2_finalize_timeout_seconds

if TYPE_CHECKING:
    from ..stage2_automation import Stage2Automator

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


def is_openai_quota_error(error: Exception) -> bool:
    message = str(error or "").lower()
    if (
        "insufficient_quota" in message
        or "exceeded your current quota" in message
        or "openai quota/rate limit" in message
    ):
        return True
    return "429" in message and "quota" in message
