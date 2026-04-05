from __future__ import annotations

from typing import Any


_LATE_FIGHT_WINDOWS = {"d7_to_d5", "d4_to_d2", "d1", "d0"}


def resolve_late_fight_window(*, payload: dict | None = None, athlete: dict | None = None) -> str:
    payload = payload or {}
    athlete = athlete or {}
    window = str(payload.get("late_fight_window", "")).strip().lower()
    if window in _LATE_FIGHT_WINDOWS:
        return window
    try:
        days = int(athlete.get("days_until_fight"))
    except (TypeError, ValueError):
        return "camp"
    if 5 <= days <= 7:
        return "d7_to_d5"
    if 2 <= days <= 4:
        return "d4_to_d2"
    if days == 1:
        return "d1"
    if days == 0:
        return "d0"
    return "camp"


def late_fight_block_cap(days_until_fight: Any) -> int | None:
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return None
    if 2 <= days <= 7:
        return 5
    if days == 1:
        return 4
    if days == 0:
        return 3
    return None
