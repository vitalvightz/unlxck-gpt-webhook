"""Low-cost support sessions for normal fight-camp weeks.

For fight-dated plans, one zero-load ``tactical_watch`` is mandatory in every
GPP, SPP and TAPER week. The watch is selected from the Tactical Watch drill bank
using only the athlete's declared tactical style, the current camp phase and the
set of watch keys already used in the camp.

The existing adaptive filler behaviour is otherwise unchanged:

* GPP: Tactical Watch only (total support cap 1)
* SPP: Tactical Watch plus at most one adaptive filler (total support cap 2)
* TAPER: Tactical Watch only (total support cap 1)
* non-fight-dated plans keep the previous SPP/TAPER filler behaviour

The mandatory watch adds no physical stress, so it remains present in compressed
weeks. It shares an already scheduled camp day rather than converting an off or
recovery-only day. Adaptive fillers keep their existing placement and safety
rules from :mod:`fightcamp.gap_fill_inserts`.
"""

from __future__ import annotations

from typing import Any

from .gap_fill_inserts import (
    PHYSICAL_INSERTS,
    _build_insert_role,
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

# Total per-week support budget. On a fight-dated plan the mandatory Tactical
# Watch always owns one slot of it, so only SPP has room left for an adaptive
# filler. Without a fight date the original SPP/TAPER caps apply unchanged (GPP
# is intentionally absent there: early camp has enough real training volume that
# low-cost filler adds noise, not value).
_FIGHT_PHASE_FILLER_CAPS = {"GPP": 1, "SPP": 2, "TAPER": 1}
_LEGACY_PHASE_FILLER_CAPS = {"SPP": 2, "TAPER": 1}

# At most one adaptive filler may share a day with an existing session per week;
# free (intentionally unused) days are always preferred.
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
    """Normalise a weekday token to its full lowercase name (``Wed`` -> ``wednesday``).

    The role map mixes short tokens (``Mon``) on roles/declared days with full
    names on ``calendar_days``, so day comparisons must go through this.
    """
    index = WEEKDAY_ORDER.get(str(value or "").strip().lower())
    return _CANONICAL_WEEKDAYS[index] if index is not None else ""


def _calendar_d_day(week: dict[str, Any], weekday: str) -> int | None:
    """Resolve the countdown day for a weekday from the week's calendar spine.

    Returns ``None`` when the week has no calendar spine, which is the signal
    that nothing — mandatory watch or adaptive filler — can be placed safely.
    """
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


def _has_future_fight(athlete_model: dict[str, Any]) -> bool:
    try:
        return int(athlete_model.get("days_until_fight")) > 0
    except (TypeError, ValueError):
        return False


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
        if role.get("camp_week_filler"):
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


def _decorate_insert(
    insert: dict[str, Any],
    *,
    day: str,
    d_day: int,
    mandatory_tactical_watch: bool = False,
) -> None:
    day_title = str(day).strip().title()
    insert["session_index"] = 0
    insert["scheduled_day_hint"] = day_title
    insert["real_weekday"] = day_title
    insert["countdown_display_label"] = f"D-{d_day} ({day_title})"
    insert["camp_week_filler"] = True
    if mandatory_tactical_watch:
        insert["mandatory_tactical_watch"] = True
        insert["weekly_requirement"] = "fight_tactical_watch"
        insert["stress_class"] = "support"
        insert["cost_class"] = "low"
        insert["governance"] = {
            **dict(insert.get("governance") or {}),
            "mandatory": True,
            "meaningful_stress": False,
        }


def _stamp_tactical_watch(
    role: dict[str, Any],
    athlete_model: dict[str, Any],
    *,
    phase: str,
    used_watch_keys: set[str],
) -> None:
    watch = select_tactical_watch(
        extract_tactical_style(athlete_model),
        phase,
        used_watch_keys,
    )
    metadata = watch_metadata(watch)
    watch_governance = dict(metadata.pop("governance", {}) or {})
    role.update(metadata)
    role["governance"] = {
        **dict(role.get("governance") or {}),
        **watch_governance,
    }
    role["display_text"] = build_watch_display_text(watch)
    used_watch_keys.add(watch.key)


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
    """Select and append one adaptive filler for ``day``. Returns the role or None."""
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

    _decorate_insert(insert, day=day, d_day=d_day)
    session_roles.append(insert)
    _record_insert_usage(usage_ledger, str(insert.get("role_key") or ""), d_day)
    return insert


def _valid_existing_watch(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for role in session_roles:
        if str(role.get("role_key") or "") != _TACTICAL_WATCH_ROLE_KEY:
            continue
        day = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
        d_day = _calendar_d_day(week, day)
        if day and d_day is not None and d_day > 0:
            return role
    return None


def _mandatory_watch_day(
    week: dict[str, Any],
    session_roles: list[dict[str, Any]],
) -> str | None:
    """Attach the watch to an already scheduled camp day; do not create a new day."""
    counts = _role_day_counts(session_roles)
    scheduled_days: list[str] = []
    for role in session_roles:
        if not isinstance(role, dict) or role.get("camp_week_filler"):
            continue
        day = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
        if (
            day
            and day not in scheduled_days
            and (d_day := _calendar_d_day(week, day)) is not None
            and d_day > 0
        ):
            scheduled_days.append(day)
    if scheduled_days:
        return min(
            scheduled_days,
            key=lambda day: (counts.get(_canonical_day(day), 0), scheduled_days.index(day)),
        )

    # Fallback only: no session role in the week carries a usable day. Declared
    # training days the planner deliberately left unused (off / recovery-only)
    # stay off-limits — the mandatory watch shares a training day, it never
    # converts a rest day just to satisfy itself.
    unused_days = {
        canonical
        for entry in week.get("intentionally_unused_days") or []
        if isinstance(entry, dict) and (canonical := _canonical_day(entry.get("day")))
    }
    declared = [
        str(day).strip()
        for day in clean_list(week.get("declared_training_days"))
        if str(day).strip()
        and _canonical_day(day) not in unused_days
        and (d_day := _calendar_d_day(week, str(day))) is not None
        and d_day > 0
    ]
    return declared[0] if declared else None


def _ensure_mandatory_tactical_watch(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    *,
    phase: str,
    usage_ledger: dict[str, Any],
    used_watch_keys: set[str],
) -> bool:
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return False

    existing = _valid_existing_watch(week, session_roles)
    if existing is not None:
        day = str(existing.get("scheduled_day_hint") or existing.get("real_weekday") or "").strip()
        d_day = _calendar_d_day(week, day)
        if d_day is None or d_day <= 0:
            return False
        _stamp_tactical_watch(
            existing,
            athlete_model,
            phase=phase,
            used_watch_keys=used_watch_keys,
        )
        existing["camp_phase"] = phase
        _decorate_insert(
            existing,
            day=day,
            d_day=d_day,
            mandatory_tactical_watch=True,
        )
        _record_insert_usage(usage_ledger, _TACTICAL_WATCH_ROLE_KEY, d_day)
        return True

    day = _mandatory_watch_day(week, session_roles)
    if day is None:
        return False
    d_day = _calendar_d_day(week, day)
    if d_day is None or d_day <= 0:
        return False

    watch_role = _build_insert_role(
        _TACTICAL_WATCH_ROLE_KEY,
        athlete_model,
        d_day,
        weekday=str(day).strip().title(),
    )
    _stamp_tactical_watch(
        watch_role,
        athlete_model,
        phase=phase,
        used_watch_keys=used_watch_keys,
    )
    watch_role["camp_phase"] = phase
    _decorate_insert(
        watch_role,
        day=day,
        d_day=d_day,
        mandatory_tactical_watch=True,
    )
    session_roles.append(watch_role)
    _record_insert_usage(usage_ledger, _TACTICAL_WATCH_ROLE_KEY, d_day)
    return True


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
    """Add mandatory fight Tactical Watch plus the existing adaptive fillers."""
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

        if fight_dated:
            total_cap = _FIGHT_PHASE_FILLER_CAPS.get(phase)
            if not total_cap:
                continue
            _ensure_mandatory_tactical_watch(
                week,
                athlete_model,
                phase=phase,
                usage_ledger=usage_ledger,
                used_watch_keys=used_watch_keys,
            )
            # A deliberately compressed week left days empty to protect the
            # athlete — the zero-load watch is still allowed, extra fillers are
            # not. The watch always owns one slot of the phase cap, whether or
            # not the week had a usable day for it, so adaptive fillers can
            # never push a week past its support budget.
            if _week_is_compressed(week):
                continue
            _fill_week(week, athlete_model, max(0, total_cap - 1), usage_ledger)
            continue

        cap = _LEGACY_PHASE_FILLER_CAPS.get(phase)
        if not cap or _week_is_compressed(week):
            continue
        _fill_week(week, athlete_model, cap, usage_ledger)

    return weekly_role_map
