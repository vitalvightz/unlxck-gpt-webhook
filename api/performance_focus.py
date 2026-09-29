from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from shared.contracts import load_shared_contract, require_positive_int, require_string


@dataclass(frozen=True)
class PerformanceFocusCap:
    # ``math.inf`` for open plans, which have no fight-date countdown.
    days_until_fight: int | float
    weeks_out: int | float
    max_selections: int
    window_label: str
    reason: str


@dataclass(frozen=True)
class PerformanceFocusValidation:
    cap: PerformanceFocusCap | None
    total_selections: int
    excess_selections: int
    is_over_cap: bool
    error_message: str | None


@dataclass(frozen=True)
class _PerformanceFocusCapWindow:
    max_days_until_fight: int | float
    max_selections: int
    window_label: str
    reason: str


def _load_focus_policy() -> tuple[PerformanceFocusCap, tuple[_PerformanceFocusCapWindow, ...], str]:
    source = "Performance focus policy"
    policy = load_shared_contract("performance-focus-policy.json")
    open_plan = policy.get("open_plan")
    windows = policy.get("windows")
    if not isinstance(open_plan, dict):
        raise RuntimeError(f"{source} open_plan must be an object")
    if not isinstance(windows, list) or not windows or not all(isinstance(entry, dict) for entry in windows):
        raise RuntimeError(f"{source} windows must be a non-empty list of objects")
    parsed: list[_PerformanceFocusCapWindow] = []
    previous_max = -1
    for position, entry in enumerate(windows):
        last = position == len(windows) - 1
        max_days = entry.get("max_days_until_fight")
        if last:
            # The last window is open-ended: every later fight date falls in it.
            if max_days is not None:
                raise RuntimeError(f"{source} last window must have max_days_until_fight null")
            max_days = math.inf
        elif isinstance(max_days, bool) or not isinstance(max_days, int) or max_days <= previous_max:
            raise RuntimeError(f"{source} window bounds must be ascending integers")
        previous_max = max_days
        parsed.append(
            _PerformanceFocusCapWindow(
                max_days_until_fight=max_days,
                max_selections=require_positive_int(entry, "max_selections", source=source),
                window_label=require_string(entry, "window_label", source=source),
                reason=require_string(entry, "reason", source=source),
            )
        )
    cap = PerformanceFocusCap(
        days_until_fight=math.inf,
        weeks_out=math.inf,
        max_selections=require_positive_int(open_plan, "max_selections", source=source),
        window_label=require_string(open_plan, "window_label", source=source),
        reason=require_string(open_plan, "reason", source=source),
    )
    return cap, tuple(parsed), require_string(policy, "over_cap_message", source=source)


# The open-plan cap, the fight-date windows and the over-cap message live in
# shared/performance-focus-policy.json, which web/lib/performance-focus-cap.ts
# reads too: the client blocks submit at the same cap the server enforces.
_OPEN_PLAN_FOCUS_CAP, _PERFORMANCE_FOCUS_CAP_WINDOWS, _OVER_CAP_MESSAGE = _load_focus_policy()


def _parse_date_only(value: str | None) -> date | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None


def _get_today(*, now: datetime | None = None, time_zone: str | None = None) -> date:
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    try:
        if time_zone:
            return reference.astimezone(ZoneInfo(time_zone)).date()
    except Exception:
        pass
    return reference.astimezone(timezone.utc).date()


def _build_focus_cap_error_message(*, max_selections: int, excess_selections: int) -> str:
    return _OVER_CAP_MESSAGE.format(
        max_selections=max_selections,
        excess_selections=excess_selections,
        selection_label="selection" if excess_selections == 1 else "selections",
    )


def get_performance_focus_cap(
    fight_date: str | None,
    *,
    now: datetime | None = None,
    time_zone: str | None = None,
) -> PerformanceFocusCap | None:
    parsed_fight_date = _parse_date_only(fight_date)
    if parsed_fight_date is None:
        # No usable fight date: an open plan (or an unparseable one). These still
        # get a cap — the web client has always enforced one here, and leaving the
        # server uncapped meant a direct API call could ship unlimited focus picks.
        return _OPEN_PLAN_FOCUS_CAP

    today = _get_today(now=now, time_zone=time_zone)
    days_until_fight = (parsed_fight_date - today).days
    if days_until_fight < 0:
        return None

    window = next(
        entry for entry in _PERFORMANCE_FOCUS_CAP_WINDOWS if days_until_fight <= entry.max_days_until_fight
    )
    return PerformanceFocusCap(
        days_until_fight=days_until_fight,
        weeks_out=max(1, days_until_fight // 7),
        max_selections=window.max_selections,
        window_label=window.window_label,
        reason=window.reason,
    )


def validate_performance_focus_selections(
    fight_date: str | None,
    *,
    key_goals: list[str] | None,
    weak_areas: list[str] | None,
    time_zone: str | None = None,
    now: datetime | None = None,
) -> PerformanceFocusValidation:
    cap = get_performance_focus_cap(fight_date, now=now, time_zone=time_zone)
    total_selections = len(key_goals or []) + len(weak_areas or [])
    excess_selections = max(total_selections - cap.max_selections, 0) if cap else 0
    return PerformanceFocusValidation(
        cap=cap,
        total_selections=total_selections,
        excess_selections=excess_selections,
        is_over_cap=excess_selections > 0,
        error_message=(
            _build_focus_cap_error_message(
                max_selections=cap.max_selections,
                excess_selections=excess_selections,
            )
            if cap and excess_selections > 0
            else None
        ),
    )
