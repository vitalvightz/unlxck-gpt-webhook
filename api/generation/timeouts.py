"""Stage 1 / Stage 2 timeout environment parsing for the generation runtime."""
from __future__ import annotations

import logging
import os

from ..environment import is_production_environment

logger = logging.getLogger(__name__)


def _stage2_finalize_timeout_seconds() -> float | None:
    # Budget for the WHOLE Stage 2 finalize: plan-text pass (client default
    # 210s, UNLXCK_STAGE2_TIMEOUT_SECONDS) + structured card first pass and
    # repair retry (600s each, UNLXCK_STAGE2_STRUCTURED_TIMEOUT_SECONDS). The
    # default must exceed the worst-case sum of those per-request timeouts or
    # the per-request budgets can never actually be used.
    raw_value = os.getenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "1500").strip()
    if raw_value in {"", "0", "none", "None", "NONE"}:
        return None
    try:
        return max(1.0, float(raw_value))
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_stage2_timeout value=%r; falling back to 1500s",
            raw_value,
        )
        return 1500.0


def _stage1_planner_timeout_seconds() -> float | None:
    raw_value = os.getenv("STAGE1_PLANNER_TIMEOUT_SECONDS")
    if raw_value is None:
        raw_value = os.getenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "600")
    raw_value = raw_value.strip()
    if raw_value in {"", "0", "none", "None", "NONE"}:
        if is_production_environment():
            logger.warning(
                "[jobs] generation:stage1_timeout_disabled_in_production value=%r; falling back to 600s",
                raw_value,
            )
            return 600.0
        return None
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_stage1_timeout value=%r; falling back to 600s",
            raw_value,
        )
        return 600.0
    if parsed <= 0:
        logger.warning(
            "[jobs] generation:invalid_stage1_timeout value=%r; falling back to 600s",
            raw_value,
        )
        return 600.0
    return parsed
