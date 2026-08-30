"""Final deterministic calendar integrity governor.

Stage 3 consumes ``combat_load_policy`` after the current allocator, fillers and
scheduled-day dose morph have finished. It does not define combat-load doctrine.
Only placements the shared policy marks ``FORBID`` are repaired.

Ownership boundaries:
- ``hard_sparring_plan`` is the resolved contact source of truth;
- visible hard-sparring roles are mirrors, not a second contact source;
- ``DEPRIORITIZE`` remains legal;
- normal D-14+ app roles may relocate inside their existing planner week or be
  suppressed when no legal home exists;
- D-13 inward finished-tail state and D-0 are never re-planned here;
- the governor never creates replacement training;
- if relocation changes scheduled D-day, the canonical morph owner is called
  again before final normal-camp verification.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .combat_load_policy import (
    CalendarEvent,
    CalendarLoadProfile,
    DayOccupancy,
    LoadClass,
    PlacementDecision,
    PlacementDirective,
    contact_load_profile,
    evaluate_candidate_at_position,
    role_load_profile,
)
from .normalization import clean_list


_CONTACT_LOADS = frozenset(
    {LoadClass.TECHNICAL_CONTACT, LoadClass.REDUCED_CONTACT, LoadClass.HARD_CONTACT}
)
_PHYSICAL_CATEGORIES = frozenset(
    {"strength", "conditioning", "recovery", "mobility", "rehab", "sparring"}
)
_CONTACT_MIRROR_ROLE_KEYS = frozenset({"hard_sparring_day", "no_hard_sparring_day"})


class CalendarIntegrityError(ValueError):
    """Raised when canonical authorities leave a forbidden normal-camp state."""


@dataclass(frozen=True)
class _RoleRef:
    week: dict[str, Any]
    week_ordinal: int
    role: dict[str, Any]
    d_day: int
    profile: CalendarLoadProfile

    @property
    def scope(self) -> tuple[str, int]:
        try:
            index = int(self.week.get("week_index"))
        except (TypeError, ValueError):
            index = self.week_ordinal
        return ("normal_week", index)


@dataclass(frozen=True)
class _ContactRef:
    week: dict[str, Any]
    week_ordinal: int
    entry: dict[str, Any]
    d_day: int
    profile: CalendarLoadProfile

    @property
    def scope(self) -> tuple[str, int]:
        try:
            index = int(self.week.get("week_index"))
        except (TypeError, ValueError):
            index = self.week_ordinal
        return ("normal_week", index)


def _normalise_day(value: Any) -> str:
    return str(value or "").strip().lower()


def _calendar_by_day(week: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        weekday = _normalise_day(day.get("weekday"))
        d_day = day.get("d_day")
        if weekday and isinstance(d_day, int):
            out[weekday] = d_day
    return out


def _label_d_day(value: Any) -> int | None:
    label = str(value or "").strip().upper()
    if not label.startswith("D-"):
        return None
    digits: list[str] = []
    for char in label[2:]:
        if char.isdigit():
            digits.append(char)
        else:
            break
    return int("".join(digits)) if digits else None


def _role_d_day(week: dict[str, Any], role: dict[str, Any]) -> int | None:
    calendar = _calendar_by_day(week)
    weekday = _normalise_day(role.get("scheduled_day_hint") or role.get("real_weekday"))
    if weekday in calendar:
        return calendar[weekday]
    for key in ("scheduled_countdown_label", "countdown_label"):
        if (d_day := _label_d_day(role.get(key))) is not None:
            return d_day
    return None


def _contact_d_day(week: dict[str, Any], entry: dict[str, Any]) -> int | None:
    calendar = _calendar_by_day(week)
    weekday = _normalise_day(entry.get("day"))
    if weekday in calendar:
        return calendar[weekday]
    for key in ("d_day", "countdown_offset"):
        try:
            d_day = int(entry.get(key))
        except (TypeError, ValueError):
            continue
        if d_day >= 0:
            return d_day
    return None


def _looks_physical(role: dict[str, Any]) -> bool:
    if _normalise_day(role.get("category")) in _PHYSICAL_CATEGORIES:
        return True
    return any(
        key in role
        for key in (
            "preferred_system",
            "strength_dose_cap",
            "meaningful_stress",
            "stress_class",
            "cost_class",
            "rpe_cap",
        )
    )


def _classify_role(role: dict[str, Any]) -> CalendarLoadProfile | None:
    profile = role_load_profile(role)
    if profile is not None:
        return profile
    # Current visible contact mirrors carry hard_sparring_status rather than the
    # canonical status/effective_load fields. The resolved hard_sparring_plan
    # entry is the contact authority and supplies the CalendarEvent instead.
    if _normalise_day(role.get("role_key")) in _CONTACT_MIRROR_ROLE_KEYS:
        return None
    if _looks_physical(role):
        raise CalendarIntegrityError(
            "Physical planner role is not classifiable by combat_load_policy: "
            f"{role.get('role_key')!r}. Extend the shared classifier; do not guess in the governor."
        )
    return None


def _role_refs(weekly_role_map: dict[str, Any]) -> list[_RoleRef]:
    refs: list[_RoleRef] = []
    for ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            d_day = _role_d_day(week, role)
            profile = _classify_role(role)
            if d_day is None or profile is None or profile.load_class is LoadClass.OFF:
                continue
            refs.append(_RoleRef(week, ordinal, role, d_day, profile))
    return refs


def _contact_refs(weekly_role_map: dict[str, Any]) -> list[_ContactRef]:
    refs: list[_ContactRef] = []
    for ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
        if not isinstance(week, dict):
            continue
        for entry in week.get("hard_sparring_plan") or []:
            if not isinstance(entry, dict):
                continue
            profile = contact_load_profile(entry)
            d_day = _contact_d_day(week, entry)
            if profile is None or profile.load_class is LoadClass.OFF or d_day is None:
                continue
            refs.append(_ContactRef(week, ordinal, entry, d_day, profile))
    return refs


def _authoritative_contact_positions(weekly_role_map: dict[str, Any]) -> set[int]:
    return {-ref.d_day for ref in _contact_refs(weekly_role_map)}


def _build_events(
    weekly_role_map: dict[str, Any],
    *,
    exclude_role: dict[str, Any] | None = None,
    exclude_contact: dict[str, Any] | None = None,
) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    contact_positions = _authoritative_contact_positions(weekly_role_map)
    for ref in _contact_refs(weekly_role_map):
        if exclude_contact is ref.entry:
            continue
        events.append(CalendarEvent(-ref.d_day, ref.profile, ref.scope))
    for ref in _role_refs(weekly_role_map):
        if exclude_role is ref.role:
            continue
        # A visible contact role and the resolved plan entry describe one
        # appointment, not two. Resolved contact remains authoritative.
        if ref.profile.load_class in _CONTACT_LOADS and -ref.d_day in contact_positions:
            continue
        events.append(CalendarEvent(-ref.d_day, ref.profile, ref.scope))
    return events


def _is_immutable_role(ref: _RoleRef) -> bool:
    if ref.d_day <= 13 or ref.role.get("late_fight_tail_owned"):
        return True
    governance = ref.role.get("governance")
    return bool(
        isinstance(governance, dict)
        and str(governance.get("authority") or "") == "finished_late_fight_tail"
    )


def _protection_rank(ref: _RoleRef) -> tuple[int, int]:
    load = ref.profile.load_class
    if load in {
        LoadClass.ZERO_LOAD,
        LoadClass.RECOVERY_ONLY,
        LoadClass.LOW_LOAD_PHYSICAL,
        LoadClass.LOW_LOAD_AEROBIC,
    }:
        rank = 0
    elif load is LoadClass.NEURAL_MICRODOSE:
        rank = 1
    else:
        rank = 2
    try:
        session_index = int(ref.role.get("session_index") or 0)
    except (TypeError, ValueError):
        session_index = 0
    return (rank, -session_index)


def _evaluate_role(weekly_role_map: dict[str, Any], ref: _RoleRef) -> PlacementDecision:
    return evaluate_candidate_at_position(
        ref.profile,
        candidate_position=-ref.d_day,
        events=_build_events(weekly_role_map, exclude_role=ref.role),
        candidate_scope=ref.scope,
    )


def _available_destination_days(ref: _RoleRef) -> list[tuple[str, int]]:
    calendar = _calendar_by_day(ref.week)
    declared = [
        _normalise_day(day)
        for day in clean_list(ref.week.get("declared_training_days"))
        if _normalise_day(day)
    ] or list(calendar)
    tail_days = {
        int(value)
        for value in ref.week.get("late_fight_tail_days") or []
        if isinstance(value, int)
    }
    return [
        (weekday, d_day)
        for weekday in declared
        if (d_day := calendar.get(weekday)) is not None
        and d_day > 13
        and d_day != ref.d_day
        and d_day not in tail_days
    ]


def _destination_occupancy_rank(events: list[CalendarEvent], d_day: int) -> int:
    profiles = [event.profile for event in events if event.position == -d_day]
    if not profiles:
        return 0
    if all(profile.occupancy is DayOccupancy.COEXISTABLE for profile in profiles):
        return 1
    return 2


def _best_destination(
    weekly_role_map: dict[str, Any], ref: _RoleRef
) -> tuple[str, int, PlacementDecision] | None:
    events = _build_events(weekly_role_map, exclude_role=ref.role)
    ranked: list[tuple[tuple[int, int, int, int], str, int, PlacementDecision]] = []
    for weekday, d_day in _available_destination_days(ref):
        decision = evaluate_candidate_at_position(
            ref.profile,
            candidate_position=-d_day,
            events=events,
            candidate_scope=ref.scope,
        )
        if decision.directive is PlacementDirective.FORBID:
            continue
        ranked.append(
            (
                (
                    0 if decision.directive is PlacementDirective.ALLOW else 1,
                    _destination_occupancy_rank(events, d_day),
                    abs(d_day - ref.d_day),
                    -d_day,
                ),
                weekday,
                d_day,
                decision,
            )
        )
    if not ranked:
        return None
    _score, weekday, d_day, decision = min(ranked, key=lambda item: item[0])
    return weekday, d_day, decision


def _stamp_relocation(
    role: dict[str, Any], *, weekday: str, d_day: int, reason_code: str
) -> None:
    previous_day = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "")
    role["scheduled_day_hint"] = weekday.title()
    if "real_weekday" in role:
        role["real_weekday"] = weekday.title()
    if "scheduled_countdown_label" in role:
        role["scheduled_countdown_label"] = f"D-{d_day}"
    if "countdown_offset" in role:
        role["countdown_offset"] = d_day
    role["calendar_integrity_relocation"] = {
        "from_day": previous_day,
        "to_day": weekday.title(),
        "to_d_day": d_day,
        "reason_code": reason_code,
        "authority": "final_calendar_integrity",
    }
    role["day_assignment_reason"] = (
        f"Final calendar integrity relocated this role to {weekday.title()} (D-{d_day}) "
        f"because the original placement was forbidden: {reason_code}."
    )


def _stamp_week_reduction(week: dict[str, Any], reason_code: str) -> None:
    summary = week.get("session_count_summary")
    if not isinstance(summary, dict):
        return
    summary["reduced_from_planned"] = True
    reasons = [str(value) for value in summary.get("reduction_reasons") or []]
    reason = f"calendar_integrity:{reason_code}"
    if reason not in reasons:
        reasons.append(reason)
    summary["reduction_reasons"] = reasons


def _suppress_role(
    ref: _RoleRef, *, decision: PlacementDecision, attempted_days: list[str]
) -> dict[str, Any]:
    suppression = {
        "role_key": ref.role.get("role_key"),
        "calendar_integrity": True,
        "reason_code": decision.reason_code,
        "reason": decision.reason,
        "original_day": ref.role.get("scheduled_day_hint") or ref.role.get("real_weekday"),
        "original_d_day": ref.d_day,
        "attempted_legal_days": attempted_days,
        "authority": "final_calendar_integrity",
    }
    ref.week.setdefault("suppressed_roles", []).append(suppression)
    roles = ref.week.get("session_roles")
    if isinstance(roles, list):
        roles[:] = [role for role in roles if role is not ref.role]
    _stamp_week_reduction(ref.week, decision.reason_code)
    return suppression


def _repair_forbidden_roles(
    weekly_role_map: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    actions: list[dict[str, Any]] = []
    deprioritized_kept = 0
    refs = sorted(
        (ref for ref in _role_refs(weekly_role_map) if not _is_immutable_role(ref)),
        key=_protection_rank,
    )
    for ref in refs:
        if ref.role not in (ref.week.get("session_roles") or []):
            continue
        decision = _evaluate_role(weekly_role_map, ref)
        if decision.directive is PlacementDirective.ALLOW:
            continue
        if decision.directive is PlacementDirective.DEPRIORITIZE:
            deprioritized_kept += 1
            continue

        destinations = _available_destination_days(ref)
        best = _best_destination(weekly_role_map, ref)
        if best is None:
            suppression = _suppress_role(
                ref,
                decision=decision,
                attempted_days=[weekday.title() for weekday, _d_day in destinations],
            )
            actions.append({"action": "suppressed", **suppression})
            continue

        weekday, d_day, destination_decision = best
        from_day = str(ref.role.get("scheduled_day_hint") or ref.role.get("real_weekday") or "")
        _stamp_relocation(
            ref.role,
            weekday=weekday,
            d_day=d_day,
            reason_code=decision.reason_code,
        )
        actions.append(
            {
                "role_key": ref.role.get("role_key"),
                "action": "relocated",
                "from_day": from_day,
                "from_d_day": ref.d_day,
                "to_day": weekday.title(),
                "to_d_day": d_day,
                "reason_code": decision.reason_code,
                "destination_directive": destination_decision.directive.value,
            }
        )
    return actions, deprioritized_kept


def _verify_normal_roles(weekly_role_map: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    contact_positions = _authoritative_contact_positions(weekly_role_map)
    for ref in _role_refs(weekly_role_map):
        # Stage 3 does not re-judge the finished D-13 tail internally. Tail events
        # remain in context so they can still constrain D-14+ roles.
        if _is_immutable_role(ref):
            continue
        if ref.profile.load_class in _CONTACT_LOADS and -ref.d_day in contact_positions:
            continue
        decision = _evaluate_role(weekly_role_map, ref)
        if decision.directive is PlacementDirective.FORBID:
            violations.append(
                {
                    "kind": "role",
                    "role_key": ref.role.get("role_key"),
                    "d_day": ref.d_day,
                    "day": ref.role.get("scheduled_day_hint") or ref.role.get("real_weekday"),
                    "reason_code": decision.reason_code,
                }
            )
    return violations


def _verify_normal_contacts(weekly_role_map: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for ref in _contact_refs(weekly_role_map):
        if ref.d_day <= 13:
            continue
        decision = evaluate_candidate_at_position(
            ref.profile,
            candidate_position=-ref.d_day,
            events=_build_events(weekly_role_map, exclude_contact=ref.entry),
            candidate_scope=ref.scope,
        )
        if decision.directive is PlacementDirective.FORBID:
            violations.append(
                {
                    "kind": "resolved_contact",
                    "day": ref.entry.get("day"),
                    "d_day": ref.d_day,
                    "load_class": ref.profile.load_class.value,
                    "reason_code": decision.reason_code,
                }
            )
    return violations


def apply_final_calendar_integrity(
    weekly_role_map: dict[str, Any],
    *,
    remorph_callback: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Repair forbidden D-14+ placements and verify the final normal calendar."""
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    checked = len(_role_refs(weekly_role_map)) + len(_contact_refs(weekly_role_map))
    actions, deprioritized_kept = _repair_forbidden_roles(weekly_role_map)
    relocated = sum(action.get("action") == "relocated" for action in actions)
    suppressed = sum(action.get("action") == "suppressed" for action in actions)

    if relocated and remorph_callback is not None:
        remorph_callback(weekly_role_map)

    violations = [
        *_verify_normal_roles(weekly_role_map),
        *_verify_normal_contacts(weekly_role_map),
    ]
    weekly_role_map["calendar_integrity"] = {
        "schema_version": "calendar_integrity.v1",
        "checked_roles": checked,
        "relocated_roles": relocated,
        "suppressed_roles": suppressed,
        "deprioritized_kept": deprioritized_kept,
        "unresolved_forbidden": len(violations),
        "late_fight_tail_replanned": False,
        "actions": actions,
        "violations": violations,
    }

    if violations:
        codes = ", ".join(
            sorted({str(item.get("reason_code") or "unknown") for item in violations})
        )
        raise CalendarIntegrityError(
            "Final deterministic D-14+ calendar still contains forbidden placement(s): "
            f"{codes}. Fix the canonical allocator/policy owner; do not ask the AI finalizer to repair it."
        )
    return weekly_role_map


__all__ = ["CalendarIntegrityError", "apply_final_calendar_integrity"]
