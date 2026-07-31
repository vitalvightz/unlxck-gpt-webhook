"""Athlete-local training day resolver (Block 4 §3 day-boundary).

Single source of truth for "which training day does a timestamp belong to".
Recommendation validity, landing logic, and completion records all derive the
day boundary from here so the frontend never re-invents it.

Rules (``docs/block-4-ux-hierarchy-addendum.md`` §3):

* Use the athlete's timezone when available; fall back safely to a default and
  finally to UTC — never crash on a missing/unknown timezone.
* ``day_rollover_hour`` is 03:00 local time.
* The training day for a timestamp ``t`` is the local calendar date of
  ``t - 3h`` — so 00:00-02:59 local still belongs to the previous training day.
* The UTC instant alone does not define the athlete-facing training day; the
  athlete's local time does.

Everything here is a pure function so it can be unit-tested without a store.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo

try:  # zoneinfo is stdlib on Python 3.9+; degrade gracefully if unavailable.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - defensive fallback only
    ZoneInfo = None  # type: ignore[assignment]

DAY_ROLLOVER_HOUR = 3
DEFAULT_TIMEZONE = "UTC"


def _coerce_aware(timestamp: datetime) -> datetime:
    """Treat a naive timestamp as UTC; leave aware timestamps untouched."""
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def resolve_timezone(
    athlete_timezone: str | None,
    *,
    default_timezone: str | None = DEFAULT_TIMEZONE,
) -> tzinfo:
    """Return a ``tzinfo`` for the athlete, falling back safely.

    Tries the athlete timezone, then ``default_timezone``, then UTC. A blank or
    unknown timezone name (or a build without ``zoneinfo``) never raises — it
    just falls through to the next candidate.
    """
    for candidate in (athlete_timezone, default_timezone):
        name = (candidate or "").strip()
        if not name or ZoneInfo is None:
            continue
        try:
            return ZoneInfo(name)
        except Exception:
            # Unknown/invalid timezone — try the next fallback.
            continue
    return timezone.utc


def resolve_training_day(
    timestamp: datetime,
    *,
    athlete_timezone: str | None = None,
    default_timezone: str | None = DEFAULT_TIMEZONE,
    rollover_hour: int = DAY_ROLLOVER_HOUR,
) -> date:
    """Athlete-local training day (a ``date``) for ``timestamp``.

    ``timestamp`` may be naive (interpreted as UTC) or timezone-aware. The
    result is the local calendar date of ``timestamp - rollover_hour`` hours.
    """
    tz = resolve_timezone(athlete_timezone, default_timezone=default_timezone)
    local = _coerce_aware(timestamp).astimezone(tz)
    return (local - timedelta(hours=rollover_hour)).date()


def resolve_training_day_str(
    timestamp: datetime,
    *,
    athlete_timezone: str | None = None,
    default_timezone: str | None = DEFAULT_TIMEZONE,
    rollover_hour: int = DAY_ROLLOVER_HOUR,
) -> str:
    """``resolve_training_day`` as an ISO ``YYYY-MM-DD`` string."""
    return resolve_training_day(
        timestamp,
        athlete_timezone=athlete_timezone,
        default_timezone=default_timezone,
        rollover_hour=rollover_hour,
    ).isoformat()


def current_training_day(
    *,
    now: datetime | None = None,
    athlete_timezone: str | None = None,
    default_timezone: str | None = DEFAULT_TIMEZONE,
    rollover_hour: int = DAY_ROLLOVER_HOUR,
) -> date:
    """Current athlete-local training day. ``now`` is injectable for tests."""
    reference = now or datetime.now(timezone.utc)
    return resolve_training_day(
        reference,
        athlete_timezone=athlete_timezone,
        default_timezone=default_timezone,
        rollover_hour=rollover_hour,
    )
