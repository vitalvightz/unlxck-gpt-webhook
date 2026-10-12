"""Time to first usable plan: how long a new athlete waits between signing up
and holding a plan they can train from.

Read from ``admin_athlete_rollups``: ``created_at`` is the signup and
``first_usable_plan_at`` is the earliest plan with an activation-ready status.
Both are stored rows, so the number covers every athlete in the window, not
only those who signed up after the metric shipped.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from ..datetimes import parse_utc_datetime


def time_to_first_usable_plan_seconds(row: Mapping[str, Any]) -> int | None:
    """Seconds from signup to first usable plan, or None if there is none yet."""
    signed_up = parse_utc_datetime(row.get("created_at"))
    first_plan = parse_utc_datetime(row.get("first_usable_plan_at"))
    if signed_up is None or first_plan is None:
        return None
    # A plan cannot predate the account; clamp clock skew rather than report it.
    return max(0, int((first_plan - signed_up).total_seconds()))


def _percentile(sorted_values: list[int], fraction: float) -> int | None:
    """Nearest-rank percentile; None for an empty list."""
    if not sorted_values:
        return None
    rank = max(1, math.ceil(len(sorted_values) * fraction))
    return sorted_values[rank - 1]


def summarize_time_to_first_usable_plan(
    rows: Iterable[Mapping[str, Any]],
    *,
    window_days: int,
    since: datetime,
) -> dict[str, Any]:
    """Funnel summary for athletes who signed up in the window."""
    signups = 0
    durations: list[int] = []
    for row in rows:
        if str(row.get("role") or "athlete") != "athlete":
            continue
        signed_up = parse_utc_datetime(row.get("created_at"))
        if signed_up is None or signed_up < since:
            continue
        signups += 1
        seconds = time_to_first_usable_plan_seconds(row)
        if seconds is not None:
            durations.append(seconds)
    durations.sort()
    return {
        "window_days": window_days,
        "signups": signups,
        "with_usable_plan": len(durations),
        "median_seconds": _percentile(durations, 0.5),
        "p75_seconds": _percentile(durations, 0.75),
    }
