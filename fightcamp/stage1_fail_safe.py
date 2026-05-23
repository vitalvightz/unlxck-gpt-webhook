import logging

logger = logging.getLogger(__name__)


def bounded_max_iterations(target: int, *, multiplier: int = 4, floor: int = 8) -> int:
    safe_target = max(0, int(target or 0))
    return max(safe_target * multiplier, floor)


def log_fail_safe_degrade(*, module: str, phase: str, reason: str, target: int, actual: int) -> None:
    logger.warning(
        "[stage1] fail_safe_degrade module=%s phase=%s reason=%s target=%s actual=%s",
        module,
        phase,
        reason,
        target,
        actual,
    )
