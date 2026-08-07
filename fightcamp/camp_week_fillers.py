"""Low-cost support inserts for normal fight-camp weeks."""

from __future__ import annotations

from typing import Any

from .gap_fill_inserts import (
    PHYSICAL_INSERTS,
    _new_usage_ledger,
    _record_insert_usage,
    select_gap_fill_insert,
)
from .normalization import WEEKDAY_ORDER, clean_list
from .tactical_watch_library import (
    build_watch_display_text,
    extract_tactical_style,
    select_tactical_watch,
    watch_metadata,
)

_FIGHT_PHASE_CAPS = {"GPP": 1, "SPP": 2, "TAPER": 1}
_LEGACY_PHASE_CAPS = {"SPP": 2, "TAPER": 1}
_MAX_SHARED_DAY_FILLERS = 1
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
    index = WEEKDAY_ORDER.get(str(value or "").strip().lower())
    return _CANONICAL_WEEKDAYS[index] if index is not None else ""


def _calendar_d_day(week: dict[str, Any], weekday: str) -> int | None:
    canonical = _canonical_day(weekday)
    for day in week.get("calendar_days") or []:
        if isinstance(day, dict) and _canonical_day(day.get("weekday")) == canonical:
            try:
                return int(day.get("d_day"))
            except (TypeError, ValueError):
                return None
    return None


def _week_is_compressed(week: dict[str, Any]) -> bool:
    compression = week.get("intentional_compression")
    return bool(compression.get("active")) if isinstance(compression, dict) else bool(compression)


def _has_future_fight(athlete_model: dict[str, Any]) -> bool:
    try:
        return int(athlete_model.get("days_until_fight")) > 0
    except (TypeError, ValueError):
        return False


def _week_hard_sparring_days(week: dict[str, Any], athlete_model: dict[str, Any]) -> set[str]:
    declared = clean_list(week.get("declared_hard_sparring_days")) or clean_list(
        athlete_model.get("hard_sparring_days", [])
    )
    return {_canonical_day(day) for day in declared if _canonical_day(day)}


def _role_day_counts(session_roles: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for role in session_roles:
        if not isinstance(role, dict) or role.get("camp_week_filler"):
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


def _decorate_filler(insert: dict[str, Any], day: str, d_day: int) -> None:
    day_title = str(day).strip().title()
    insert["session_index"] = 0
    insert["scheduled_day_hint"] = day_title
    insert["real_weekday"] = day_title
    insert["countdown_display_label"] = f"D-{d_day} ({day_title})"
    insert["camp_week_filler"] = True


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
    d_day = _calendar_d_day(week, day)
    if d_day is None:
        return None
    insert = select_gap_fill_insert(
        athlete_model,
        d_day,
        on_hard_sparring_day=_canonical_day(day) in hard_days,
        usage_ledger=usage_ledger,
    )
    if insert is None or (not allow_physical and insert.get("role_key") in PHYSICAL_INSERTS):
        return None
    _decorate_filler(insert, day, d_day)
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
    if not isinstance(session_roles, list) or cap <= 0:
        return

    hard_days = _week_hard_sparring_days(week, athlete_model)
    added = 0
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
        insert = _place_filler(
            week,
            session_roles,
            athlete_model,
            day,
            hard_days=hard_days,
            usage_ledger=usage_ledger,
            allow_physical=_week_physical_filler_count(session_roles) < 1,
        )
        if insert is None:
            kept_unused.append(day_entry)
            continue
        insert["converted_from_unused_day"] = True
        insert["original_unused_day_role"] = unused_role
        added += 1
    week["intentionally_unused_days"] = kept_unused

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
        insert = _place_filler(
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
        added += 1
        shared_added += 1
        day_counts[normalized] = day_counts.get(normalized, 0) + 1


def _existing_training_day(week: dict[str, Any], session_roles: list[dict[str, Any]]) -> tuple[str, int] | None:
    for role in session_roles:
        if not isinstance(role, dict) or role.get("camp_week_filler"):
            continue
        day = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
        d_day = _calendar_d_day(week, day)
        if day and d_day is not None and d_day > 0:
            return day, d_day
    return None


def _ensure_tactical_watch(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    phase: str,
    used_watch_keys: set[str],
    usage_ledger: dict[str, Any],
) -> bool:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return False

    existing = next(
        (
            role
            for role in session_roles
            if isinstance(role, dict) and str(role.get("role_key") or "") == "tactical_watch"
        ),
        None,
    )
    if existing is not None:
        day = str(existing.get("scheduled_day_hint") or existing.get("real_weekday") or "").strip()
        d_day = _calendar_d_day(week, day)
        if not day or d_day is None or d_day <= 0:
            existing = None

    slot = (day, d_day) if existing is not None else _existing_training_day(week, session_roles)
    if slot is None:
        return False
    day, d_day = slot

    watch = select_tactical_watch(extract_tactical_style(athlete_model), phase, used_watch_keys)
    metadata = watch_metadata(watch)
    watch_governance = dict(metadata.pop("governance"))
    role = existing if existing is not None else {
        "category": "support_insert",
        "role_key": "tactical_watch",
        "athlete_facing_label": "Fight Tactical Watch",
        "rpe_max": 1,
        "support_insert_category": "tactical",
        "support_insert_cost_category": "zero_cost",
        "mechanical_load_regions": [],
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "scheduled_countdown_label": f"D-{d_day}",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {"authority": "camp_week_support_insert"},
    }
    role.update(metadata)
    role["display_text"] = build_watch_display_text(watch)
    role["duration_min"] = [watch.duration_minutes, watch.duration_minutes]
    role["mandatory_tactical_watch"] = True
    role["weekly_requirement"] = "fight_tactical_watch"
    role["camp_phase"] = phase
    role["governance"] = {
        **dict(role.get("governance") or {}),
        **watch_governance,
        "mandatory": True,
        "meaningful_stress": False,
    }
    _decorate_filler(role, day, d_day)
    if existing is None:
        session_roles.append(role)
    used_watch_keys.add(watch.key)
    _record_insert_usage(usage_ledger, "tactical_watch", d_day)
    return True


def apply_camp_week_fillers(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    athlete_model = athlete_model or {}
    fight_dated = _has_future_fight(athlete_model)
    usage_ledger = _new_usage_ledger()
    used_watch_keys: set[str] = set()

    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()
        if fight_dated and phase in _FIGHT_PHASE_CAPS:
            _ensure_tactical_watch(week, athlete_model, phase, used_watch_keys, usage_ledger)
            if not _week_is_compressed(week):
                _fill_week(week, athlete_model, _FIGHT_PHASE_CAPS[phase] - 1, usage_ledger)
            continue

        cap = _LEGACY_PHASE_CAPS.get(phase)
        if cap and not _week_is_compressed(week):
            _fill_week(week, athlete_model, cap, usage_ledger)
    return weekly_role_map
