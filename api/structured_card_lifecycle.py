"""Durable lifecycle helpers for structured-card conversion attempts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY = "structured_card_attempt_started_at"
STRUCTURED_CARD_BUILD_STALE_AFTER = timedelta(minutes=25)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mark_structured_card_attempt_started(
    result: dict[str, Any], *, started_at: str | None = None
) -> dict[str, Any]:
    """Stamp a conversion attempt onto a plan-like result's validator report."""

    report = result.get("stage2_validator_report")
    report = dict(report) if isinstance(report, dict) else {}
    report[STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY] = started_at or utc_now_iso()
    result["stage2_validator_report"] = report
    return result


def clear_structured_card_attempt_started(result: dict[str, Any]) -> dict[str, Any]:
    """Remove the in-flight marker after a terminal conversion outcome."""

    report = result.get("stage2_validator_report")
    report = dict(report) if isinstance(report, dict) else {}
    report.pop(STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY, None)
    result["stage2_validator_report"] = report
    return result


def parse_structured_card_attempt_started_at(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def has_fresh_structured_card_attempt(
    report: Any,
    *,
    now: datetime | None = None,
    stale_after: timedelta = STRUCTURED_CARD_BUILD_STALE_AFTER,
) -> bool:
    """Whether a validator report carries a non-stale conversion marker."""

    if not isinstance(report, dict):
        return False
    started_at = parse_structured_card_attempt_started_at(
        report.get(STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY)
    )
    if started_at is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age = current.astimezone(timezone.utc) - started_at
    return age < stale_after
