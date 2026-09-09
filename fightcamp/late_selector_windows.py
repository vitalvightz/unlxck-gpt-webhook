from __future__ import annotations

from typing import Any


CONTROL_D28 = "control_d28"
D21_TO_D14 = "d21_to_d14"
D13_TO_D8 = "d13_to_d8"
D7 = "d7"
D6_TO_D5 = "d6_to_d5"
D4_TO_D2 = "d4_to_d2"
D1 = "d1"

LATE_SELECTOR_AUDIT_WINDOWS = (
    CONTROL_D28,
    D21_TO_D14,
    D13_TO_D8,
    D7,
    D6_TO_D5,
    D4_TO_D2,
    D1,
)


def coerce_days_until_fight(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def classify_late_selector_window(
    days_until_fight: Any,
    *,
    include_control: bool = False,
) -> str | None:
    days = coerce_days_until_fight(days_until_fight)
    if days is None or days < 0:
        return None
    if include_control and days == 28:
        return CONTROL_D28
    if 14 <= days <= 21:
        return D21_TO_D14
    if 8 <= days <= 13:
        return D13_TO_D8
    if days == 7:
        return D7
    if 5 <= days <= 6:
        return D6_TO_D5
    if 2 <= days <= 4:
        return D4_TO_D2
    if days == 1:
        return D1
    return None


def is_active_late_selector_window(window: str | None) -> bool:
    return window in {D21_TO_D14, D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1}


def _normalise_late_window_tokens(value: object) -> set[str]:
    values = list(value) if isinstance(value, (list, tuple, set)) else [value]
    return {
        str(token).strip().lower().replace("-", "_")
        for item in values
        for token in str(item or "").replace(",", " ").split()
        if str(token).strip()
    }


def late_window_allowed(entries: list[dict[str, Any]], *, offset: int) -> bool:
    """Apply the canonical opt-in ``late_windows`` contract for a D-day.

    Active late-fight selection is opt-in. At least one matching bank row must
    explicitly contain the scheduled window (or ``all``); missing or empty
    metadata is not late-fight approval.
    """
    window = classify_late_selector_window(offset)
    if not window:
        return True

    for item in entries:
        late_windows = _normalise_late_window_tokens(item.get("late_windows"))
        if "all" in late_windows or window in late_windows:
            return True
    return False


def required_late_windows(roles: list[dict[str, Any]]) -> set[str]:
    """Late windows that a camp's own scheduled roles will actually ask for.

    Stage 1 selects by phase, while the dated late-fight selector admits a
    candidate only when the bank opts that exercise into the role's countdown
    window. Nothing reconciled the two, so a camp could hand over a pool with no
    legal candidate for a window it was certain to need and ship an empty
    physical session. This derives the requirement from the roles that exist, so
    only windows the camp actually reaches are ever demanded.
    """
    windows: set[str] = set()
    for role in roles or []:
        if not isinstance(role, dict):
            continue
        label = str(
            role.get("scheduled_countdown_label") or role.get("countdown_label") or ""
        ).strip()
        offset: int | None = None
        if label.upper().startswith("D-"):
            try:
                offset = int(label.upper().removeprefix("D-"))
            except ValueError:
                offset = None
        if offset is None:
            try:
                offset = int(role.get("countdown_offset"))
            except (TypeError, ValueError):
                offset = None
        if offset is None:
            continue
        window = classify_late_selector_window(offset)
        if window:
            windows.add(window)
    return windows


def late_windows_spanned(days_until_fight: Any) -> set[str]:
    """Late windows a camp of this length actually reaches.

    Derived from the countdown the camp spans, so a five-day camp never demands
    coverage for a window it will never schedule, and a long camp demands every
    window its tail will own. Used instead of the late-fight session sequence
    because a long camp splices its tail separately and that sequence is empty
    until the splice runs - long after the candidate handoff is built.
    """
    try:
        days = int(days_until_fight)
    except (TypeError, ValueError):
        return set()
    if days < 0:
        return set()
    windows: set[str] = set()
    for offset in range(0, days + 1):
        window = classify_late_selector_window(offset)
        if window:
            windows.add(window)
    return windows
