"""Shared fight-date and weekday helpers.

Lives outside the late-fight payload module so both the normal-camp and the
late-fight pipelines can depend on it without crossing each other.

The fight day's weekday is resolved with this priority:

1. ``fight_date`` parsed to a ``date`` (the strongest signal).
2. ``plan_creation_weekday + days_until_fight`` (legacy fallback for inputs
   that have not threaded the actual date through).

Calendar arithmetic uses ``datetime.date.weekday()`` so the result cannot
drift with the runtime clock or the renderer's wall time.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


WEEKDAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


_WEEKDAY_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}


def parse_fight_date(value: Any) -> date | None:
    """Return a ``date`` for the fight, accepting date / datetime / ISO strings.

    The accepted string forms include the ones used elsewhere in the codebase:
    ``YYYY-MM-DD`` and any ISO 8601 date prefix. Returns ``None`` for empty,
    malformed, or unsupported inputs — callers fall back to weekday arithmetic.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Strip any trailing time / timezone the source may carry.
        candidate = text[:10]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            try:
                return datetime.fromisoformat(text).date()
            except ValueError:
                return None
    return None


def _coerce_days(value: Any) -> int | None:
    if value is None:
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return days if days >= 0 else None


def fight_weekday_from_fight_date(value: Any) -> str | None:
    """Compute the fight weekday directly from the fight date."""
    parsed = parse_fight_date(value)
    if parsed is None:
        return None
    return WEEKDAY_NAMES[parsed.weekday()]


def fight_weekday_from_offset(
    plan_creation_weekday: str | None,
    days_until_fight: Any,
) -> str | None:
    """Legacy fallback: derive fight weekday from creation weekday + offset."""
    if not plan_creation_weekday:
        return None
    days = _coerce_days(days_until_fight)
    if days is None:
        return None
    creation_index = _WEEKDAY_INDEX.get(str(plan_creation_weekday).strip().lower())
    if creation_index is None:
        return None
    return WEEKDAY_NAMES[(creation_index + days) % 7]


def d_day_for_weekday(
    weekday: Any,
    *,
    fight_weekday: Any,
    projected_days_until_fight_end: int,
    span_days: int,
) -> int | None:
    """Return the D-day of ``weekday`` within a week ending at ``end_d``.

    ``projected_days_until_fight_end`` is the D-day of the week's day closest
    to the fight (e.g. 1 means the week's last day is D-1). The week's
    countdown range runs from ``end_d + span_days - 1`` (start of week) down to
    ``end_d`` (end of week). Returns ``None`` when the inputs do not resolve a
    weekday inside the week's span.
    """
    fw_idx = _WEEKDAY_INDEX.get(str(fight_weekday or "").strip().lower())
    wd_idx = _WEEKDAY_INDEX.get(str(weekday or "").strip().lower())
    if fw_idx is None or wd_idx is None:
        return None
    try:
        end_d = int(projected_days_until_fight_end)
        span = int(span_days)
    except (TypeError, ValueError):
        return None
    if end_d < 0 or span <= 0:
        return None
    weekday_of_end = (fw_idx - end_d) % 7
    offset_back = (weekday_of_end - wd_idx) % 7
    if offset_back >= span:
        return None
    return end_d + offset_back


def build_calendar_days(
    *,
    fight_weekday: Any,
    projected_days_until_fight_end: int,
    span_days: int,
) -> list[dict[str, Any]]:
    """Return per-day calendar entries for a normal-camp week.

    Each entry has ``weekday``, ``d_day``, ``is_fight_day``, and
    ``is_after_fight_day``. Returns an empty list when fight weekday or span
    cannot be resolved.
    """
    fw_idx = _WEEKDAY_INDEX.get(str(fight_weekday or "").strip().lower())
    if fw_idx is None:
        return []
    try:
        end_d = int(projected_days_until_fight_end)
        span = int(span_days)
    except (TypeError, ValueError):
        return []
    if end_d < 0 or span <= 0:
        return []
    days: list[dict[str, Any]] = []
    # Earliest day in the week first (largest d_day).
    for offset in range(span):
        d_day = end_d + (span - 1 - offset)
        wd_idx = (fw_idx - d_day) % 7
        days.append(
            {
                "weekday": WEEKDAY_NAMES[wd_idx],
                "d_day": d_day,
                "is_fight_day": d_day == 0,
                "is_after_fight_day": d_day < 0,
            }
        )
    return days


def resolve_fight_weekday(
    *,
    fight_date: Any = None,
    plan_creation_weekday: str | None = None,
    days_until_fight: Any = None,
) -> str | None:
    """Prefer the actual fight date; fall back to weekday arithmetic.

    Keeping the priority explicit at the API level makes it impossible for
    callers to silently drop fight_date and accidentally rely on the offset
    fallback when both inputs are present.
    """
    weekday = fight_weekday_from_fight_date(fight_date)
    if weekday is not None:
        return weekday
    return fight_weekday_from_offset(plan_creation_weekday, days_until_fight)
