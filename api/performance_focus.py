from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PerformanceFocusCap:
    days_until_fight: int
    weeks_out: int
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
    max_days_until_fight: int
    max_selections: int
    window_label: str
    reason: str


_PERFORMANCE_FOCUS_CAP_WINDOWS: tuple[_PerformanceFocusCapWindow, ...] = (
    _PerformanceFocusCapWindow(
        max_days_until_fight=7,
        max_selections=3,
        window_label="Fight week",
        reason="Fight-week plans stay extremely selective so sharpness and readiness do not get buried under too many priorities.",
    ),
    _PerformanceFocusCapWindow(
        max_days_until_fight=21,
        max_selections=4,
        window_label="Ultra-short camp",
        reason="Ultra-short camps need a tight focus so the plan does not spread work across too many targets at once.",
    ),
    _PerformanceFocusCapWindow(
        max_days_until_fight=42,
        max_selections=5,
        window_label="Short camp",
        reason="Short camps can cover a few parallel priorities, but they still need selectivity to keep sessions coherent.",
    ),
    _PerformanceFocusCapWindow(
        max_days_until_fight=70,
        max_selections=6,
        window_label="Mid-length camp",
        reason="Mid-length camps have room for a broader focus without losing the main thread of the plan.",
    ),
    _PerformanceFocusCapWindow(
        max_days_until_fight=10**9,
        max_selections=7,
        window_label="Long camp",
        reason="Longer camps have enough runway to support more development themes without diluting the plan.",
    ),
)


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
    selection_label = "selection" if excess_selections == 1 else "selections"
    return (
        f"This camp allows {max_selections} total focus picks. "
        f"Remove {excess_selections} goal or weak-area {selection_label} before generating."
    )


def get_performance_focus_cap(
    fight_date: str | None,
    *,
    now: datetime | None = None,
    time_zone: str | None = None,
) -> PerformanceFocusCap | None:
    parsed_fight_date = _parse_date_only(fight_date)
    if parsed_fight_date is None:
        return None

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
