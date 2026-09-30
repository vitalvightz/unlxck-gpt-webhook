"""Parse the timestamps and calendar dates the API reads from rows and payloads.

Stored timestamps arrive as ISO strings (Supabase writes ``...Z`` or
``+00:00``) or as datetimes; calendar days arrive as ``YYYY-MM-DD`` strings,
sometimes with a time suffix. These two parsers are the shared reading of both;
modules that need a different reading (keeping a naive time, keeping the
original offset, or accepting only a bare date) keep their own.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def parse_utc_datetime(value: Any) -> datetime | None:
    """An aware UTC datetime, or None for anything that is not a timestamp.

    Naive values are taken to be UTC. Strings are stripped and may use ``Z``.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_calendar_date(value: Any) -> date | None:
    """The calendar day an ISO value starts with (``2026-08-01T09:00Z`` -> 1 Aug), or None."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except (ValueError, AttributeError):
        return None
