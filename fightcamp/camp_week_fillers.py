"""Low-cost filler sessions for normal-camp SPP/TAPER weeks.

The late-fight payload already gap-fills its session sequence with low/zero-cost
support inserts (tactical cue cards, breathing resets, mobility touches, ...) via
:mod:`fightcamp.gap_fill_inserts`. The normal camp path never did: SPP and TAPER
weeks ship only their main session roles, so declared training days the planner
left unused render as plain off/recovery days and the athlete gets no low-cost
support work at all.

This module is a thin overlay that reuses the *same* insert selection policy for
normal-camp weeks. It only places fillers:

* in SPP and TAPER weeks (capped at 2 and 1 fillers per week respectively);
* on intentionally-unused training days first (the "space"), falling back to at
  most one filler alongside an existing session when a week has no free day;
* never on a week compressed on purpose (fatigue / safety compression), never on
  an unused day a safety gate already annotated, and never more than one
  physical insert per week.

All athlete-state safety rules (active weight cut, high fatigue, injury state,
hard-sparring days, D-1/D-0 restrictions) come from
:func:`fightcamp.gap_fill_inserts.select_gap_fill_insert` unchanged, so camp
fillers can never be more aggressive than the late-fight ones.
"""

from __future__ import annotations

from typing import Any

from .gap_fill_inserts import (
    PHYSICAL_INSERTS,
    _new_usage_ledger,
    _record_insert_usage,
    select_gap_fill_insert,
)
from .normalization import WEEKDAY_ORDER, clean_list

# Per-week filler caps. GPP is intentionally absent: early camp has enough real
# training volume that low-cost filler adds noise, not value.
_PHASE_FILLER_CAPS = {"SPP": 2, "TAPER": 1}

# At most one filler may share a day with an existing session per week; free
# (intentionally unused) days are always preferred.
_MAX_SHARED_DAY_FILLERS = 1

_CANONICAL_WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)


def _canonical_day(value: Any) -> str:
    """Normalise a weekday token to its full lowercase name (``Wed`` -> ``wednesday``).

    The role map mixes short tokens (``Mon``) on roles/declared days with full
    names on ``calendar_days``, so day comparisons must go through this.
    """
    index = WEEKDAY_ORDER.get(str(value or "").strip().lower())
    return _CANONICAL_WEEKDAYS[index] if index is not None else ""


def _calendar_d_day(week: dict[str, Any], weekday: str) -> int | None:
    """Resolve the countdown day for a weekday from the week's calendar spine."""
    canonical = _canonical_day(weekday)
    if not canonical:
        return None
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        if _canonical_day(day.get("weekday")) == canonical:
            try:
                return int(day.get("d_day"))
            except (TypeError, ValueError):
                return None
    return None


def _week_is_compressed(week: dict[str, Any]) -> bool:
    compression = week.get("intentional_compression")
    if isinstance(compression, dict):
        return bool(compression.get("active"))
    return bool(compression)


def _week_hard_sparring_days(week: dict[str, Any], athlete_model: dict[str, Any]) -> set[str]:
    declared = clean_list(week.get("declared_hard_sparring_days")) or clean_list(
        athlete_model.get("hard_sparring_days", [])
    )
    return {canonical for day in declared if (canonical := _canonical_day(day))}


def _role_day_counts(session_roles: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for role in session_roles:
        if not isinstance(role, dict):
            continue
        day = _canonical_day(role.get("scheduled_day_hint"))
        if day:
            counts[day] = counts.get(day, 0) + 1
    return counts


def _week_physical_filler_count(session_roles: list[Any]) -> int:
    return sum(
        1
        for role in session_roles
        if isinstance(role, dict)
        and role.get("camp_week_filler")
        and str(role.get("role_key") or "") in PHYSICAL_INSERTS
    )


def _place_filler(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    day: str,
    *,
    hard_days: set[str],
    usage_ledger: dict[str, Any],
    allow_physical: bool,
) -> dict[str, Any] | None:
    """Select and append one filler for ``day``. Returns the role or None."""
    d_day = _calendar_d_day(week, day)
    if d_day is None:
        return None

    insert = select_gap_fill_insert(
        athlete_model,
        d_day,
        on_hard_sparring_day=_canonical_day(day) in hard_days,
        usage_ledger=usage_ledger,
    )
    if insert is None:
        return None
    if not allow_physical and insert.get("role_key") in PHYSICAL_INSERTS:
        return None

    day_title = str(day).strip().title()
    insert["session_index"] = 0
    insert["scheduled_day_hint"] = day_title
    insert["real_weekday"] = day_title
    insert["countdown_display_label"] = f"D-{d_day} ({day_title})"
    insert["camp_week_filler"] = True
    session_roles.append(insert)
    _record_insert_usage(usage_ledger, str(insert.get("role_key") or ""), d_day)
    return insert


def _fill_week(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    cap: int,
    usage_ledger: dict[str, Any],
) -> None:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return

    hard_days = _week_hard_sparring_days(week, athlete_model)
    added = 0

    # Pass 1 — free days: intentionally unused off/recovery training days that no
    # safety gate has annotated. A filled day stops being intentionally unused
    # (same contract as the low-load support upgrade in stage2_role_map).
    kept_unused: list[Any] = []
    for day_entry in week.get("intentionally_unused_days") or []:
        if added >= cap or not isinstance(day_entry, dict):
            kept_unused.append(day_entry)
            continue
        day = str(day_entry.get("day") or "").strip()
        unused_role = str(day_entry.get("role") or "").strip()
        if (
            not day
            or unused_role not in {"off_day", "recovery_only_day"}
            or day_entry.get("low_aerobic_cap_skipped")
        ):
            kept_unused.append(day_entry)
            continue
        allow_physical = _week_physical_filler_count(session_roles) < 1
        insert = _place_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=allow_physical,
        )
        if insert is None:
            kept_unused.append(day_entry)
            continue
        insert["converted_from_unused_day"] = True
        insert["original_unused_day_role"] = unused_role
        added += 1
    week["intentionally_unused_days"] = kept_unused

    # Pass 2 — shared days: when the week still has filler budget, allow at most
    # one filler alongside an existing single session. Hard-sparring days stay
    # eligible because the selector then restricts to zero-cost/recovery work
    # (a cue card next to sparring is fine; extra S&C is not).
    if added >= cap:
        return
    day_counts = _role_day_counts(session_roles)
    shared_added = 0
    for day in clean_list(week.get("declared_training_days")):
        if added >= cap or shared_added >= _MAX_SHARED_DAY_FILLERS:
            break
        normalized = _canonical_day(day)
        if day_counts.get(normalized, 0) != 1:
            continue
        allow_physical = _week_physical_filler_count(session_roles) < 1
        insert = _place_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=allow_physical,
        )
        if insert is None:
            continue
        added += 1
        shared_added += 1
        day_counts[normalized] = day_counts.get(normalized, 0) + 1


def apply_camp_week_fillers(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add low-cost filler sessions to SPP/TAPER camp weeks. Mutates and returns.

    Weeks outside SPP/TAPER, compressed weeks, and weeks without a usable
    calendar spine are left untouched, so the overlay is a no-op wherever it
    cannot place a filler safely.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    athlete_model = athlete_model or {}
    usage_ledger = _new_usage_ledger()
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        cap = _PHASE_FILLER_CAPS.get(str(week.get("phase") or "").strip().upper())
        if not cap:
            continue
        # A deliberately compressed week left days empty to protect the athlete
        # (fatigue, cut, injury, sparring load) — never refill it.
        if _week_is_compressed(week):
            continue
        _fill_week(week, athlete_model, cap, usage_ledger)
    return weekly_role_map
