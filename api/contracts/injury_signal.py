"""Derived daily injury-risk signal from logged history (Block 4 §6 follow-up).

The Today/Overview risk watch is driven by the SAME-DAY check-in. That makes the
injury badge go blank the moment the athlete hasn't opened the check-in form
today — green stops meaning anything because it never reflects what actually
happened in training. But two signals already live in persistence and outlive a
single check-in:

* **post-session pain** logged on each ``session_completions`` row
  (``pain_after``), and
* recent post-session pain readings across completions.

This module turns that logged history into at most one risk-watch item so the
badge reflects training reality even with no check-in today:

* an escalating post-session pain reading,
* a rising post-session pain trend (the "post-session pain delta").

Pure and deterministic: no I/O, no plan mutation, and no invented medical
advice. The text states what was logged and frames load; the recommendation
engine (``checkin_decision``) still owns the train/modify/pull-back decision.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from .command_view import RiskWatchItem, make_risk

# Post-session pain (0-10) thresholds. HIGH is "ease in and reassess"; ELEVATED
# is the floor for treating consecutive readings as a rising trend.
HIGH_PAIN_AFTER = 7
ELEVATED_PAIN_AFTER = 4
# A jump of this much between consecutive logged sessions reads as "climbing".
PAIN_RISE_DELTA = 3
# Ignore history older than this — a month-old tweak is not today's risk.
LOOKBACK_DAYS = 14


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _coerce_pain(value: Any) -> int | None:
    """Read a 0-10 ``pain_after`` integer, ignoring junk/out-of-range values."""
    if isinstance(value, bool):  # bool is an int subclass — never a pain score
        return None
    try:
        score = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return score if 0 <= score <= 10 else None


def _within_lookback(day: date | None, current: date) -> bool:
    if day is None:
        return False
    delta = (current - day).days
    return 0 <= delta <= LOOKBACK_DAYS


def _pain_series(
    completions: Sequence[Mapping[str, Any]], current: date
) -> list[tuple[date, int]]:
    """Logged ``(day, pain_after)`` points within the lookback, oldest first.

    One point per day (the worst reading that day) so multiple sessions on a day
    can't manufacture a fake trend.
    """
    worst_by_day: dict[date, int] = {}
    for row in completions:
        day = _parse_day(row.get("training_day"))
        if not _within_lookback(day, current):
            continue
        pain = _coerce_pain(row.get("pain_after"))
        if pain is None:
            continue
        assert day is not None  # narrowed by _within_lookback
        worst_by_day[day] = max(worst_by_day.get(day, pain), pain)
    return sorted(worst_by_day.items())


def derive_injury_signal(
    *,
    completions: Sequence[Mapping[str, Any]],
    current_training_day: str,
    current_phase: str | None = None,
) -> list[RiskWatchItem]:
    """Derive at most one risk-watch item from logged post-session pain history.

    Returns ``[]`` when nothing in the recent history reads as a risk. At most
    one item is returned, for either an escalating last reading or a rising
    trend. Callers fold this into the same-day check-in risks.
    """
    current = _parse_day(current_training_day)
    if current is None:
        return []
    phase = str(current_phase or "").strip().upper()

    series = _pain_series(completions, current)

    # A. Escalation — the most recent logged session pain is high on its own.
    if series:
        last_day, last_pain = series[-1]
        if last_pain >= HIGH_PAIN_AFTER:
            action = "Reassess before your next session."
            if phase == "TAPER":
                action = (
                    "Keep today minimal, protect freshness, and reassess before "
                    "your next session."
                )
            return [
                make_risk(
                    "high_pain",
                    text=f"Pain was logged at {last_pain}/10. {action}",
                    timeframe="last_session",
                )
            ]

    # B. Rising trend — the "post-session pain delta" between the two most recent
    # logged sessions, when the latest is itself at least elevated.
    if len(series) >= 2:
        (_, prev_pain), (_, last_pain) = series[-2], series[-1]
        if last_pain >= ELEVATED_PAIN_AFTER and (last_pain - prev_pain) >= PAIN_RISE_DELTA:
            return [
                make_risk(
                    "high_pain",
                    text=(
                        f"Pain rose from {prev_pain}/10 to {last_pain}/10 across your last "
                        "two logged sessions. Reassess before your next session."
                    ),
                    timeframe="recent_sessions",
                )
            ]

    return []
