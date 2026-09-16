"""Normal camp-week fillers plus the long-camp -> finished late-fight handoff.

The established filler implementation lives in ``camp_week_fillers_impl``. This
module keeps its public/back-compat surface while owning the D-14/D-13 boundary:
normal camp logic remains authoritative through D-14, then the already-finished
existing D-13 late-fight path is spliced into the continuous calendar.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .normalization import clean_list
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
_canonical_day = _impl._canonical_day
_complete_week_physical_occupancy = _impl._complete_week_physical_occupancy
_ensure_coordination_support = _impl._ensure_coordination_support
_fill_week = _impl._fill_week
_has_future_fight = _impl._has_future_fight
_new_usage_ledger = _impl._new_usage_ledger
_record_insert_usage = _impl._record_insert_usage
_role_d_day = _impl._role_d_day
_seed_programme_coverage_roles = _impl._seed_programme_coverage_roles
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


# ── D-14 / D-13 ownership handoff: unplaced normal roles ─────────────────────
#
# ``fill_missing_session_days`` deliberately leaves a role dayless when no legal
# free declared day remains ("leave a role dayless when no legal free declared
# day remains"). Normal placement is finished by the time the handoff runs, so
# such a role is not "waiting for a day" — it failed placement, and D-13 inward
# has just transferred to the finished late-fight allocator. Keeping it active
# leaves a stale normal-planner session beside the authoritative tail: it is
# still composed downstream (composition runs after this splice), so it reaches
# the validator as a zero-workload physical session and raises
# ``conditioning_role_workload_underfilled`` for a session that has no day at
# all.
#
# This is an ownership resolution, not readiness compression and not weight-cut
# suppression: nothing about the athlete's readiness changed, the planner simply
# no longer owns the only window the role could have used.
HANDOFF_UNPLACED_REASON_CODE = "late_fight_tail_handoff_unplaced_normal_role"
HANDOFF_UNPLACED_REASON = (
    "Normal placement completed without a legal scheduled day for this role, and "
    "D-13 inward has transferred to the finished late-fight allocator. A stale "
    "normal-planner session cannot remain active beside the finished tail."
)

# Authorities that mark a role as belonging to the handed-over tail rather than
# to the normal planner.
_TAIL_ROLE_AUTHORITIES = frozenset(
    {"finished_late_fight_tail", "late_fight_tail_allocator"}
)


def _is_unplaced_normal_physical_session(role: dict[str, Any]) -> bool:
    """Whether a dayless role is normal-planner physical work, not metadata.

    The criterion is deliberately borrowed from the downstream composition
    authority rather than invented here: these are exactly the predicates
    :mod:`fightcamp.session_composition` uses to decide which roles it fills as
    physical training (``compose_normal_strength_assignments``,
    ``compose_normal_conditioning_assignments``,
    ``compose_normal_rehab_assignments``). If composition would treat the role as
    a physical session, a dayless copy of it is a ghost session; if composition
    would skip it, this leaves it alone.

    Support inserts, camp-week fillers, coach-owned combat locks and anything the
    tail already owns are never touched — an undated support/metadata object is
    not a stale training session.
    """
    if role.get("late_fight_tail_owned") or role.get("camp_week_filler"):
        return False
    if role.get("coach_owned"):
        return False
    governance = role.get("governance")
    if isinstance(governance, dict) and str(
        governance.get("authority") or ""
    ) in _TAIL_ROLE_AUTHORITIES:
        return False

    category = str(role.get("category") or "").strip().lower()
    preferred_pool = str(role.get("preferred_pool") or "").strip().lower()
    if category == "support_insert":
        return False
    if category == "conditioning":
        return True
    if category == "strength" or preferred_pool == "strength_slots":
        return True
    # Normal-camp recovery roles are rehab-composed physical sessions; a bare
    # recovery marker with no pool is not.
    if category == "recovery" and preferred_pool == "rehab_slots_or_recovery_only":
        return True
    return False


def _handoff_unplaced_suppression(role: dict[str, Any]) -> dict[str, Any]:
    """Audit record for a normal role the handoff could not leave active."""
    suppression = {
        "role_key": role.get("role_key"),
        "category": role.get("category"),
        "preferred_system": role.get("preferred_system", ""),
        "preferred_pool": role.get("preferred_pool", ""),
        "governance": deepcopy(role.get("governance") or {}),
        "reason_code": HANDOFF_UNPLACED_REASON_CODE,
        "reason": HANDOFF_UNPLACED_REASON,
        "reasons": [HANDOFF_UNPLACED_REASON],
        "authority": "late_fight_tail_handoff",
        "late_fight_tail_handoff": True,
        "normal_planner_through_d": 14,
        "late_fight_planner_from_d": 13,
        "unplaced_by_normal_planner": True,
        "original_role": deepcopy(role),
    }
    return suppression


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
        handoff_suppressions: list[dict[str, Any]] = []
        claimed_normal_days = {
            resolved
            for existing in week.get("session_roles") or []
            if isinstance(existing, dict)
            and (resolved := _role_d_day(week, existing)) is not None
            and resolved >= _NORMAL_PLANNER_OWNED_MIN_D_DAY
        }
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                kept_roles.append(role)
                continue
            d_day = _role_d_day(week, role)
            if d_day is not None and 1 <= d_day <= 13:
                reanchored = _normal_planner_reanchor_d_day(week, role, claimed_normal_days)
                if reanchored is None:
                    continue
                role["countdown_offset"] = reanchored
                role["scheduled_countdown_label"] = f"D-{reanchored}"
                role["countdown_label"] = f"D-{reanchored}"
                role["normal_planner_reanchored_from_d_day"] = d_day
                claimed_normal_days.add(reanchored)
                kept_roles.append(role)
                continue
            if (
                d_day is None
                and owned_tail_days
                and not str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip()
                and _is_unplaced_normal_physical_session(role)
            ):
                # Unresolved normal work in a week whose tail days have just
                # changed owner. It is not moved into D-13..D-1 and no new
                # placement pass is run for it: it is recorded and removed.
                handoff_suppressions.append(_handoff_unplaced_suppression(role))
                continue
            kept_roles.append(role)
        week["session_roles"] = kept_roles
        if handoff_suppressions:
            week["suppressed_roles"] = [
                *(week.get("suppressed_roles") or []),
                *handoff_suppressions,
            ]

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



_NORMAL_PLANNER_OWNED_MIN_D_DAY = 14


def _normal_planner_reanchor_d_day(
    week: dict[str, Any], role: dict[str, Any], taken: set[int]
) -> int | None:
    """The D-14+ occurrence of this role's weekday, when the week still has one.

    A week whose span exceeds seven days repeats a weekday — a D-14..D-7 week
    holds two Thursdays. Weekday -> D-day resolution picks one of them, and when
    it picks the occurrence inside D-13 the handoff deletes a role that the
    normal planner still owns, leaving the *declared* D-14 training day empty.
    That is the reported D-14 hole.

    Ownership breaks the tie rather than the calendar: D-14 and outward belong to
    the normal planner, so its role is re-anchored onto that occurrence instead of
    being dropped. The day must be one the athlete declared and nothing else has
    claimed; otherwise the role is dropped exactly as before. Ownership itself is
    unchanged — nothing moves into D-13..D-1, and the tail keeps its authority.
    """
    weekday = _canonical_day(role.get("scheduled_day_hint") or role.get("real_weekday"))
    if not weekday:
        return None
    declared = {
        _canonical_day(day) for day in clean_list(week.get("declared_training_days"))
    }
    if declared and weekday not in declared:
        return None
    for entry in week.get("calendar_days") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("d_day"), int):
            continue
        d_day = int(entry["d_day"])
        if d_day < _NORMAL_PLANNER_OWNED_MIN_D_DAY:
            continue
        if _canonical_day(entry.get("weekday")) != weekday or d_day in taken:
            continue
        return d_day
    return None


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
    _seed_programme_coverage_roles(weekly_role_map, usage_ledger)
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
            # Tactical Watch is a zero-load informational insert (it sits in
            # ZERO_COST_INSERTS and coexists with physical sessions), so it does
            # not spend the week's physical filler budget. The legacy path below
            # already only charges the coordination insert; charging the watch
            # here left GPP with no discretionary budget at all.
            discretionary_cap = max(0, _FIGHT_PHASE_CAPS[phase])
            coordination_added = False
            if discretionary_cap > 0:
                coordination_added = _ensure_coordination_support(
                    week,
                    athlete_model,
                    phase,
                    used_coordination_keys,
                    weekly_role_map=weekly_role_map,
                    week_ordinal=week_ordinal,
                    usage_ledger=usage_ledger,
                )
            if not _week_is_compressed(week):
                _fill_week(
                    week,
                    athlete_model,
                    max(0, discretionary_cap - int(coordination_added)),
                    usage_ledger,
                    weekly_role_map=weekly_role_map,
                    week_ordinal=week_ordinal,
                )
            continue

        coordination_added = False
        if phase in {"GPP", "SPP", "TAPER"}:
            coordination_added = _ensure_coordination_support(
                week,
                athlete_model,
                phase,
                used_coordination_keys,
                weekly_role_map=weekly_role_map,
                week_ordinal=week_ordinal,
                usage_ledger=usage_ledger,
            )

        cap = _LEGACY_PHASE_CAPS.get(phase)
        if cap and not _week_is_compressed(week):
            _fill_week(
                week,
                athlete_model,
                max(0, cap - int(coordination_added)),
                usage_ledger,
                weekly_role_map=weekly_role_map,
                week_ordinal=week_ordinal,
            )

    # Occupancy completion runs last, over every week, so it sees the final
    # placed calendar: normal-planner roles, the spliced finished D-13 tail, and
    # every filler above. It only ever adds low-cost *physical* work to a day the
    # athlete declared and the planner left empty, and records a deterministic
    # reason when it cannot.
    if fight_dated:
        for week in weekly_role_map.get("weeks", []) or []:
            if isinstance(week, dict):
                _complete_week_physical_occupancy(week, athlete_model, usage_ledger)
    return weekly_role_map
