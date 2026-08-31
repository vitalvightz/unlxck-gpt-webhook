"""Normal camp-week fillers plus the long-camp -> finished late-fight handoff.

The established filler implementation lives in ``camp_week_fillers_impl``. This
module keeps its public/back-compat surface while owning the D-14/D-13 boundary:
normal camp logic remains authoritative through D-14, then the already-finished
existing D-13 late-fight path is spliced into the continuous calendar.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import camp_week_fillers_impl as _impl
from .late_fight_tail import build_finished_late_fight_tail

# Preserve the old module surface, including private helpers imported by tests and
# older call sites. Functions copied from the implementation keep their original
# globals; the boundary-specific functions below are deliberately redefined here.
for _export_name in dir(_impl):
    if not _export_name.startswith("__"):
        globals()[_export_name] = getattr(_impl, _export_name)

# Explicit aliases keep static analysis aware of the implementation symbols this
# adapter calls while the dynamic export loop preserves the full back-compat API.
_FIGHT_PHASE_CAPS = _impl._FIGHT_PHASE_CAPS
_LEGACY_PHASE_CAPS = _impl._LEGACY_PHASE_CAPS
_calendar_d_day = _impl._calendar_d_day
_ensure_coordination_support = _impl._ensure_coordination_support
_fill_week = _impl._fill_week
_has_future_fight = _impl._has_future_fight
_new_usage_ledger = _impl._new_usage_ledger
_record_insert_usage = _impl._record_insert_usage
_role_d_day = _impl._role_d_day
_week_for_d_day = _impl._week_for_d_day
_week_is_compressed = _impl._week_is_compressed


def _sync_impl_dependencies() -> None:
    """Keep common monkeypatch/test seams working after the implementation split."""
    for name in (
        "select_gap_fill_insert",
        "select_tactical_watch",
        "select_coordination_support",
        "has_coordination_target",
        "_new_usage_ledger",
        "_record_insert_usage",
    ):
        if name in globals():
            setattr(_impl, name, globals()[name])


def _ensure_tactical_watch(
    week: dict[str, Any],
    athlete_model: dict[str, Any],
    phase: str,
    used_watch_keys: set[str],
    usage_ledger: dict[str, Any],
) -> bool:
    """Keep a finished-tail Tactical Watch untouched by normal-week fillers.

    The direct D-13 path may legitimately place more than one watch inside a
    calendar week when countdown windows and normal week boundaries do not line
    up. Normal camp filler logic must not delete/reselect those finished-tail
    watches after ownership has handed over.
    """
    session_roles = week.get("session_roles")
    if not isinstance(session_roles, list):
        return False

    tail_days = set(week.get("late_fight_tail_days") or [])
    tail_watches: list[tuple[dict[str, Any], int]] = []
    for candidate in session_roles:
        if not isinstance(candidate, dict) or str(candidate.get("role_key") or "") != "tactical_watch":
            continue
        day = str(candidate.get("scheduled_day_hint") or candidate.get("real_weekday") or "").strip()
        d_day = _role_d_day(week, candidate)
        if d_day is None:
            d_day = _calendar_d_day(week, day)
        if d_day in tail_days and candidate.get("late_fight_tail_owned"):
            tail_watches.append((candidate, int(d_day)))

    if tail_watches:
        # A completed late-fight watch satisfies the support requirement for this
        # mixed/pure week. Remove only normal-camp tactical duplicates; never
        # mutate or collapse the finished tail sequence.
        session_roles[:] = [
            candidate
            for candidate in session_roles
            if not (
                isinstance(candidate, dict)
                and str(candidate.get("role_key") or "") == "tactical_watch"
                and not candidate.get("late_fight_tail_owned")
            )
        ]
        for watch_role, d_day in tail_watches:
            watch_key = str(watch_role.get("tactical_watch_key") or "").strip()
            if watch_key:
                used_watch_keys.add(watch_key)
            _record_insert_usage(usage_ledger, "tactical_watch", d_day)
        return True

    # No tail-owned watch: retain the established normal-camp behaviour.
    return _impl._ensure_tactical_watch(
        week,
        athlete_model,
        phase,
        used_watch_keys,
        usage_ledger,
    )


def _segment_summary_for_week(
    segment: dict[str, Any],
    calendar_d_days: set[int],
) -> dict[str, Any] | None:
    span = segment.get("countdown_span")
    if not isinstance(span, dict):
        return None
    try:
        start_day = int(span.get("start_day"))
        end_day = int(span.get("end_day"))
    except (TypeError, ValueError):
        return None
    if start_day < end_day:
        start_day, end_day = end_day, start_day
    intersecting = sorted(calendar_d_days & set(range(end_day, start_day + 1)), reverse=True)
    if not intersecting:
        return None
    return {
        "stage_key": segment.get("stage_key"),
        "payload_mode": segment.get("payload_mode"),
        "countdown_span": deepcopy(span),
        "intersecting_d_days": intersecting,
        "intentional_compression": deepcopy(segment.get("intentional_compression") or {}),
        "role_budget": deepcopy(segment.get("role_budget") or {}),
        "suppressed_roles": deepcopy(segment.get("suppressed_roles") or []),
        "hard_sparring_plan": deepcopy(segment.get("hard_sparring_plan") or []),
        "effective_hard_sparring_days": deepcopy(
            segment.get("effective_hard_sparring_days") or []
        ),
    }


def _splice_late_fight_tail(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any],
) -> bool:
    """Splice the *finished* existing D-13 -> D-1 path into a D-14+ camp.

    D-14 and further out remain physically owned by the normal planner. From
    scheduled D-13 inward, roles come from the same completed late-fight path as
    a plan generated directly at D-13: allocator + coach combat spine + late
    strength caps + existing gap/support work. D-0 remains the pre-existing
    deterministic fight-day protocol in the normal calendar.
    """
    try:
        days_until_fight = int(athlete_model.get("days_until_fight"))
    except (TypeError, ValueError):
        return False
    if days_until_fight < 14:
        return False

    weeks = [
        week
        for week in weekly_role_map.get("weeks", []) or []
        if isinstance(week, dict)
    ]
    if not weeks or _week_for_d_day(weeks, 13) is None:
        return False

    finished_tail = build_finished_late_fight_tail(
        days_until_fight,
        athlete_model,
        start_day=13,
    )
    tail_roles = [
        deepcopy(role)
        for role in finished_tail.get("session_sequence", []) or []
        if isinstance(role, dict)
        and (d_day := _role_d_day({}, role)) is not None
        and 1 <= d_day <= 13
    ]
    if not tail_roles:
        return False

    day_metadata = finished_tail.get("day_metadata") or {}
    segments = [
        segment
        for segment in finished_tail.get("segments", []) or []
        if isinstance(segment, dict)
    ]
    tail_range = set(range(0, 14))

    for week in weeks:
        calendar_d_days = {
            int(day.get("d_day"))
            for day in week.get("calendar_days") or []
            if isinstance(day, dict) and isinstance(day.get("d_day"), int)
        }
        owned_tail_days = sorted(calendar_d_days & tail_range)
        if owned_tail_days:
            week["late_fight_tail_days"] = owned_tail_days
            week["late_fight_tail_complete_week"] = bool(
                calendar_d_days and max(calendar_d_days) <= 13
            )
            summaries = [
                summary
                for segment in segments
                if (summary := _segment_summary_for_week(segment, calendar_d_days))
                is not None
            ]
            if summaries:
                week["late_fight_tail_segments"] = summaries
        else:
            week.pop("late_fight_tail_days", None)
            week.pop("late_fight_tail_complete_week", None)
            week.pop("late_fight_tail_segments", None)

        kept_roles: list[Any] = []
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                kept_roles.append(role)
                continue
            d_day = _role_d_day(week, role)
            if d_day is not None and 1 <= d_day <= 13:
                continue
            kept_roles.append(role)
        week["session_roles"] = kept_roles

        # Normal-planner off/recovery placeholders must not survive inside the
        # handed-over tail or later filler passes can try to repopulate it.
        week["intentionally_unused_days"] = [
            entry
            for entry in week.get("intentionally_unused_days") or []
            if not isinstance(entry, dict)
            or (
                (entry_d := _calendar_d_day(week, str(entry.get("day") or ""))) is None
                or entry_d >= 14
            )
        ]

    for role in tail_roles:
        d_day = int(_role_d_day({}, role) or -1)
        week = _week_for_d_day(weeks, d_day)
        if week is None:
            continue
        metadata = deepcopy(day_metadata.get(d_day) or {})
        role["late_fight_tail_owned"] = True
        role["late_fight_stage_key"] = metadata.get("stage_key")
        role["late_fight_payload_mode"] = metadata.get("payload_mode")
        role["late_fight_tail_metadata"] = metadata
        governance = dict(role.get("governance") or {})
        governance.update(
            {
                "authority": "finished_late_fight_tail",
                "payload_mode": metadata.get("payload_mode"),
                "stage_key": metadata.get("stage_key"),
            }
        )
        role["governance"] = governance
        week.setdefault("session_roles", []).append(role)

    for week in weeks:
        if not week.get("late_fight_tail_days"):
            continue
        week["session_roles"] = sorted(
            week.get("session_roles") or [],
            key=lambda role: (
                -int(
                    _role_d_day(week, role)
                    if isinstance(role, dict) and _role_d_day(week, role) is not None
                    else -999
                ),
                int(role.get("session_index") or 0) if isinstance(role, dict) else 0,
            ),
        )

    weekly_role_map["late_fight_tail_handoff"] = {
        "active": True,
        "normal_planner_through_d": 14,
        "late_fight_planner_from_d": 13,
        "source": "finished_existing_late_fight_path",
    }
    return True


def apply_camp_week_fillers(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply normal fillers while treating the finished D-13 tail as immutable."""
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    _sync_impl_dependencies()
    athlete_model = athlete_model or {}
    fight_dated = _has_future_fight(athlete_model)
    _splice_late_fight_tail(weekly_role_map, athlete_model)
    usage_ledger = _new_usage_ledger()
    used_watch_keys: set[str] = set()
    used_coordination_keys: set[str] = set()

    # Seed normal filler de-duplication from the already-finished tail. Otherwise
    # earlier normal weeks can reuse the same Tactical Watch/support insert keys.
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or not role.get("late_fight_tail_owned"):
                continue
            d_day = _role_d_day(week, role)
            if d_day is not None:
                _record_insert_usage(
                    usage_ledger,
                    str(role.get("role_key") or ""),
                    d_day,
                )
            watch_key = str(role.get("tactical_watch_key") or "").strip()
            if watch_key:
                used_watch_keys.add(watch_key)

    for week_ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
        if not isinstance(week, dict):
            continue
        phase = str(week.get("phase") or "").strip().upper()

        if fight_dated and phase in _FIGHT_PHASE_CAPS:
            _ensure_tactical_watch(
                week,
                athlete_model,
                phase,
                used_watch_keys,
                usage_ledger,
            )
            _ensure_coordination_support(
                week,
                athlete_model,
                phase,
                used_coordination_keys,
                weekly_role_map=weekly_role_map,
                week_ordinal=week_ordinal,
            )
            if not _week_is_compressed(week):
                _fill_week(
                    week,
                    athlete_model,
                    _FIGHT_PHASE_CAPS[phase] - 1,
                    usage_ledger,
                    weekly_role_map=weekly_role_map,
                    week_ordinal=week_ordinal,
                )
            continue

        if phase in {"GPP", "SPP", "TAPER"}:
            _ensure_coordination_support(
                week,
                athlete_model,
                phase,
                used_coordination_keys,
                weekly_role_map=weekly_role_map,
                week_ordinal=week_ordinal,
            )

        cap = _LEGACY_PHASE_CAPS.get(phase)
        if cap and not _week_is_compressed(week):
            _fill_week(
                week,
                athlete_model,
                cap,
                usage_ledger,
                weekly_role_map=weekly_role_map,
                week_ordinal=week_ordinal,
            )
    return weekly_role_map
