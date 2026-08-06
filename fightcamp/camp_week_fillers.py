"""Low-cost support sessions for normal fight-camp weeks.

Fight-dated plans reserve one zero-cost ``tactical_watch`` support slot in every
GPP, SPP, and TAPER week. The slot is mandatory in plan generation, including
weeks compressed for fatigue, injury, weight-cut, or sparring-load reasons,
because it adds no physical stress. It never lands on D-0 and never consumes an
extra slot beyond the phase's existing support-session budget:

* GPP: Tactical Watch only (cap 1)
* SPP: Tactical Watch plus at most one adaptive filler (cap 2)
* TAPER: Tactical Watch only (cap 1)

Non-fight-dated callers retain the previous behaviour: adaptive fillers are
limited to uncompressed SPP/TAPER weeks. Free off/recovery training days are
preferred, then one existing single-session day may be shared. Physical filler
selection continues to use :func:`fightcamp.gap_fill_inserts.select_gap_fill_insert`
so all existing injury, fatigue, weight-cut, hard-sparring, and D-1/D-0 safety
rules remain authoritative.
"""

from __future__ import annotations

from typing import Any

from .gap_fill_inserts import (
    PHYSICAL_INSERTS,
    _build_insert_role,
    _new_usage_ledger,
    _record_insert_usage,
    build_tactical_watch_template,
    select_gap_fill_insert,
)
from .normalization import WEEKDAY_ORDER, clean_list

_PHASE_FILLER_CAPS = {"GPP": 1, "SPP": 2, "TAPER": 1}
_LEGACY_PHASE_FILLER_CAPS = {"SPP": 2, "TAPER": 1}
_MAX_SHARED_DAY_FILLERS = 1
_TACTICAL_WATCH_ROLE_KEY = "tactical_watch"

_CANONICAL_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _canonical_day(value: Any) -> str:
    """Normalise a weekday token to its full lowercase name (``Wed`` -> ``wednesday``)."""
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
        if _canonical_day(day.get("weekday")) != canonical:
            continue
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


def _has_future_fight(athlete_model: dict[str, Any]) -> bool:
    """Return True only when Stage 2 resolved a future fight countdown."""
    try:
        return int(athlete_model.get("days_until_fight")) > 0
    except (TypeError, ValueError):
        return False


def _week_hard_sparring_days(
    week: dict[str, Any], athlete_model: dict[str, Any]
) -> set[str]:
    declared = clean_list(week.get("declared_hard_sparring_days")) or clean_list(
        athlete_model.get("hard_sparring_days", [])
    )
    return {
        canonical
        for day in declared
        if (canonical := _canonical_day(day))
    }


def _role_day_counts(session_roles: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for role in session_roles:
        if not isinstance(role, dict):
            continue
        day = _canonical_day(role.get("scheduled_day_hint"))
        if day:
            counts[day] = counts.get(day, 0) + 1
    return counts


def _roles_by_day(session_roles: list[Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for role in session_roles:
        if not isinstance(role, dict):
            continue
        day = _canonical_day(role.get("scheduled_day_hint"))
        if day:
            grouped.setdefault(day, []).append(role)
    return grouped


def _week_physical_filler_count(session_roles: list[Any]) -> int:
    return sum(
        1
        for role in session_roles
        if isinstance(role, dict)
        and role.get("camp_week_filler")
        and str(role.get("role_key") or "") in PHYSICAL_INSERTS
    )


def _week_filler_count(session_roles: list[Any]) -> int:
    return sum(
        1
        for role in session_roles
        if isinstance(role, dict)
        and (
            role.get("camp_week_filler")
            or str(role.get("category") or "") == "support_insert"
        )
    )


def _week_has_tactical_watch(session_roles: list[Any]) -> bool:
    return any(
        isinstance(role, dict)
        and str(role.get("role_key") or "") == _TACTICAL_WATCH_ROLE_KEY
        for role in session_roles
    )


def _phase_watch_guidance(phase: str) -> str:
    if phase == "GPP":
        return (
            "Camp focus: review your latest clean round or a fighter with a similar "
            "style. Find repeatable habits before opponent-specific planning."
        )
    if phase == "TAPER":
        return (
            "Camp focus: review familiar opponent footage and confirmed cues only. "
            "Do not add a new tactical theory this week."
        )
    return (
        "Camp focus: study the confirmed opponent. If footage is limited, use the "
        "closest style match and connect each cue to this week's technical work."
    )


def _decorate_insert(
    insert: dict[str, Any],
    *,
    day: str,
    d_day: int,
    mandatory_tactical_watch: bool = False,
) -> dict[str, Any]:
    day_title = str(day).strip().title()
    insert["session_index"] = 0
    insert["scheduled_day_hint"] = day_title
    insert["real_weekday"] = day_title
    insert["countdown_display_label"] = f"D-{d_day} ({day_title})"
    insert["camp_week_filler"] = True
    if mandatory_tactical_watch:
        insert["mandatory_tactical_watch"] = True
        insert["weekly_requirement"] = "fight_tactical_watch"
        insert["governance"] = {
            **dict(insert.get("governance") or {}),
            "authority": "mandatory_weekly_tactical_watch",
            "meaningful_stress": False,
        }
    return insert


def _place_adaptive_filler(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    day: str,
    *,
    hard_days: set[str],
    usage_ledger: dict[str, Any],
    allow_physical: bool,
) -> dict[str, Any] | None:
    d_day = _calendar_d_day(week, day)
    if d_day is None or d_day <= 0:
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

    _decorate_insert(insert, day=day, d_day=d_day)
    session_roles.append(insert)
    _record_insert_usage(usage_ledger, str(insert.get("role_key") or ""), d_day)
    return insert


def _place_tactical_watch(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
    athlete_model: dict[str, Any],
    day: str,
    *,
    phase: str,
    usage_ledger: dict[str, Any],
) -> dict[str, Any] | None:
    d_day = _calendar_d_day(week, day)
    if d_day is None or d_day <= 0:
        return None

    insert = _build_insert_role(
        _TACTICAL_WATCH_ROLE_KEY,
        athlete_model,
        d_day,
        weekday=str(day).strip().title(),
    )
    insert["display_text"] = (
        f"{build_tactical_watch_template(athlete_model)}\n\n"
        f"{_phase_watch_guidance(phase)}"
    )
    insert["camp_phase"] = phase
    _decorate_insert(
        insert,
        day=day,
        d_day=d_day,
        mandatory_tactical_watch=True,
    )
    session_roles.append(insert)
    _record_insert_usage(usage_ledger, _TACTICAL_WATCH_ROLE_KEY, d_day)
    return insert


def _eligible_unused_entries(week: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    eligible: list[tuple[int, dict[str, Any]]] = []
    for entry in week.get("intentionally_unused_days") or []:
        if not isinstance(entry, dict):
            continue
        day = str(entry.get("day") or "").strip()
        role = str(entry.get("role") or "").strip()
        d_day = _calendar_d_day(week, day)
        if (
            not day
            or role not in {"off_day", "recovery_only_day"}
            or entry.get("low_aerobic_cap_skipped")
            or d_day is None
            or d_day <= 0
        ):
            continue
        eligible.append((d_day, entry))
    # Prefer earlier camp days and keep D-1 as the final fallback.
    return sorted(eligible, key=lambda item: (item[0] == 1, -item[0]))


def _remove_unused_entry(week: dict[str, Any], selected: dict[str, Any]) -> None:
    week["intentionally_unused_days"] = [
        entry
        for entry in week.get("intentionally_unused_days") or []
        if entry is not selected
    ]


def _shared_day_candidates(
    week: dict[str, Any], session_roles: list[dict[str, Any]]
) -> list[str]:
    grouped = _roles_by_day(session_roles)
    candidates: list[tuple[int, int, str]] = []

    for day in clean_list(week.get("declared_training_days")):
        canonical = _canonical_day(day)
        roles = grouped.get(canonical, [])
        d_day = _calendar_d_day(week, day)
        if len(roles) != 1 or d_day is None or d_day <= 0:
            continue
        role = roles[0]
        role_key = str(role.get("role_key") or "")
        category = str(role.get("category") or "").lower()
        if category in {"technical", "recovery", "support_insert"}:
            priority = 0
        elif role_key == "hard_sparring_day" or category == "sparring":
            priority = 1
        else:
            priority = 2
        candidates.append((priority, 1 if d_day == 1 else 0, str(day)))

    return [day for _, _, day in sorted(candidates)]


def _ensure_weekly_tactical_watch(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    usage_ledger: dict[str, Any],
) -> bool:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return False
    if _week_has_tactical_watch(session_roles):
        return True

    phase = str(week.get("phase") or "").strip().upper()

    for _, entry in _eligible_unused_entries(week):
        day = str(entry.get("day") or "").strip()
        insert = _place_tactical_watch(
            week,
            session_roles,
            athlete_model,
            day,
            phase=phase,
            usage_ledger=usage_ledger,
        )
        if insert is None:
            continue
        insert["converted_from_unused_day"] = True
        insert["original_unused_day_role"] = str(entry.get("role") or "")
        _remove_unused_entry(week, entry)
        return True

    for day in _shared_day_candidates(week, session_roles):
        if _place_tactical_watch(
            week,
            session_roles,
            athlete_model,
            day,
            phase=phase,
            usage_ledger=usage_ledger,
        ) is not None:
            return True

    return False


def _fill_adaptive_slots(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    cap: int,
    usage_ledger: dict[str, Any],
) -> None:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return

    hard_days = _week_hard_sparring_days(week, athlete_model)

    for _, entry in list(_eligible_unused_entries(week)):
        if _week_filler_count(session_roles) >= cap:
            break
        day = str(entry.get("day") or "").strip()
        insert = _place_adaptive_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=_week_physical_filler_count(session_roles) < 1,
        )
        if insert is None:
            continue
        insert["converted_from_unused_day"] = True
        insert["original_unused_day_role"] = str(entry.get("role") or "")
        _remove_unused_entry(week, entry)

    if _week_filler_count(session_roles) >= cap:
        return

    shared_added = 0
    day_counts = _role_day_counts(session_roles)
    for day in _shared_day_candidates(week, session_roles):
        if (
            _week_filler_count(session_roles) >= cap
            or shared_added >= _MAX_SHARED_DAY_FILLERS
        ):
            break
        canonical = _canonical_day(day)
        if day_counts.get(canonical, 0) != 1:
            continue
        insert = _place_adaptive_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=_week_physical_filler_count(session_roles) < 1,
        )
        if insert is None:
            continue
        shared_added += 1
        day_counts[canonical] = day_counts.get(canonical, 0) + 1


def apply_camp_week_fillers(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply weekly Tactical Watch and adaptive support slots in place."""
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    athlete_model = athlete_model or {}
    has_future_fight = _has_future_fight(athlete_model)
    usage_ledger = _new_usage_ledger()

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue

        phase = str(week.get("phase") or "").strip().upper()
        if has_future_fight:
            cap = _PHASE_FILLER_CAPS.get(phase)
            if not cap:
                continue
            _ensure_weekly_tactical_watch(week, athlete_model, usage_ledger)
            # Compression protects the body, so the zero-cost Tactical Watch
            # remains while every optional adaptive filler stays suppressed.
            if _week_is_compressed(week):
                continue
            _fill_adaptive_slots(week, athlete_model, cap, usage_ledger)
            continue

        # Backwards-compatible behaviour for callers without a resolved fight.
        cap = _LEGACY_PHASE_FILLER_CAPS.get(phase)
        if not cap or _week_is_compressed(week):
            continue
        _fill_adaptive_slots(week, athlete_model, cap, usage_ledger)

    return weekly_role_map
