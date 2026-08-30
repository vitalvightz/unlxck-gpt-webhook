"""Final deterministic calendar integrity governor.

This module is the Stage-3 consumer of :mod:`fightcamp.combat_load_policy`.
It does not define combat-load doctrine. It converts the finished weekly role
map into the shared load vocabulary, repairs only placements the shared policy
marks ``FORBID``, and verifies that no forbidden deterministic placement reaches
the AI finalizer.

Ownership boundaries:
- resolved contact state comes from ``sparring_dose_planner`` data already
  stamped into ``hard_sparring_plan``;
- normal allocator / late-fight allocator still decide which roles exist;
- countdown dose remains owned by ``late_camp_role_morph``;
- D-13 inward finished-tail placement and D-0 are immutable here;
- ``DEPRIORITIZE`` is legal and is never treated as ``FORBID``;
- this governor never creates replacement training.
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
    {
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.REDUCED_CONTACT,
        LoadClass.HARD_CONTACT,
    }
)
_PHYSICAL_CATEGORIES = frozenset(
    {"strength", "conditioning", "recovery", "mobility", "rehab", "sparring"}
)


class CalendarIntegrityError(ValueError):
    """Raised when peer/immutable authorities leave a forbidden calendar state."""


@dataclass(frozen=True)
class _RoleRef:
    week: dict[str, Any]
    week_ordinal: int
    role: dict[str, Any]
    d_day: int
    profile: CalendarLoadProfile

    @property
    def scope(self) -> tuple[str, int]:
        raw = self.week.get("week_index")
        try:
            week_index = int(raw)
        except (TypeError, ValueError):
            week_index = self.week_ordinal
        return ("normal_week", week_index)


@dataclass(frozen=True)
class _ContactRef:
    week: dict[str, Any]
    week_ordinal: int
    entry: dict[str, Any]
    d_day: int
    profile: CalendarLoadProfile

    @property
    def scope(self) -> tuple[str, int]:
        raw = self.week.get("week_index")
        try:
            week_index = int(raw)
        except (TypeError, ValueError):
            week_index = self.week_ordinal
        return ("normal_week", week_index)


def _normalise_day(value: Any) -> str:
    return str(value or "").strip().lower()


def _calendar_by_day(week: dict[str, Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        weekday = _normalise_day(day.get("weekday"))
        d_day = day.get("d_day")
        if weekday and isinstance(d_day, int):
            mapping[weekday] = d_day
    return mapping


def _role_d_day(week: dict[str, Any], role: dict[str, Any]) -> int | None:
    calendar = _calendar_by_day(week)
    weekday = _normalise_day(
        role.get("scheduled_day_hint") or role.get("real_weekday")
    )
    if weekday in calendar:
        return calendar[weekday]
    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if not label.startswith("D-"):
            continue
        digits: list[str] = []
        for char in label[2:]:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if digits:
            return int("".join(digits))
    return None


def _contact_d_day(week: dict[str, Any], entry: dict[str, Any]) -> int | None:
    calendar = _calendar_by_day(week)
    weekday = _normalise_day(entry.get("day"))
    if weekday in calendar:
        return calendar[weekday]
    for key in ("d_day", "countdown_offset"):
        try:
            value = int(entry.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _looks_physical(role: dict[str, Any]) -> bool:
    category = _normalise_day(role.get("category"))
    if category in _PHYSICAL_CATEGORIES:
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
    if profile is None and _looks_physical(role):
        raise CalendarIntegrityError(
            "Physical planner role is not classifiable by combat_load_policy: "
            f"{role.get('role_key')!r}. Extend the shared classifier; do not guess in the governor."
        )
    return profile


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


def _authoritative_contact_positions(
    weekly_role_map: dict[str, Any],
) -> set[int]:
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
        events.append(
            CalendarEvent(
                position=-ref.d_day,
                profile=ref.profile,
                collision_scope=ref.scope,
            )
        )

    for ref in _role_refs(weekly_role_map):
        if exclude_role is ref.role:
            continue
        # A visible contact role and the resolved hard_sparring_plan entry describe
        # one appointment, not two. Resolved contact remains the authority.
        if ref.profile.load_class in _CONTACT_LOADS and -ref.d_day in contact_positions:
            continue
        events.append(
            CalendarEvent(
                position=-ref.d_day,
                profile=ref.profile,
                collision_scope=ref.scope,
            )
        )
    return events


def _is_immutable_role(ref: _RoleRef) -> bool:
    if ref.d_day <= 13:
        return True
    if ref.role.get("late_fight_tail_owned"):
        return True
    governance = ref.role.get("governance")
    return bool(
        isinstance(governance, dict)
        and str(governance.get("authority") or "") == "finished_late_fight_tail"
    )


def _protection_rank(ref: _RoleRef) -> tuple[int, int]:
    """Least protected roles repair first so subordinate support loses first."""
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


def _evaluate_role(
    weekly_role_map: dict[str, Any],
    ref: _RoleRef,
    *,
    d_day: int | None = None,
) -> PlacementDecision:
    candidate_d_day = ref.d_day if d_day is None else int(d_day)
    return evaluate_candidate_at_position(
        ref.profile,
        candidate_position=-candidate_d_day,
        events=_build_events(weekly_role_map, exclude_role=ref.role),
        candidate_scope=ref.scope,
    )


def _available_destination_days(ref: _RoleRef) -> list[tuple[str, int]]:
    calendar = _calendar_by_day(ref.week)
    declared = [
        _normalise_day(day)
        for day in clean_list(ref.week.get("declared_training_days"))
        if _normalise_day(day)
    ]
    if not declared:
        declared = list(calendar)

    tail_days = {
        int(value)
        for value in ref.week.get("late_fight_tail_days") or []
        if isinstance(value, int)
    }
    result: list[tuple[str, int]] = []
    for weekday in declared:
        d_day = calendar.get(weekday)
        if d_day is None or d_day <= 13 or d_day == ref.d_day or d_day in tail_days:
            continue
        result.append((weekday, d_day))
    return result


def _destination_occupancy_rank(events: list[CalendarEvent], d_day: int) -> int:
    profiles = [event.profile for event in events if event.position == -d_day]
    if not profiles:
        return 0
    if all(profile.occupancy is DayOccupancy.COEXISTABLE for profile in profiles):
        return 1
    return 2


def _best_destination(
    weekly_role_map: dict[str, Any],
    ref: _RoleRef,
) -> tuple[str, int, PlacementDecision] | None:
    events = _build_events(weekly_role_map, exclude_role=ref.role)
    candidates: list[tuple[tuple[int, int, int, int], str, int, PlacementDecision]] = []
    for weekday, d_day in _available_destination_days(ref):
        decision = evaluate_candidate_at_position(
            ref.profile,
            candidate_position=-d_day,
            events=events,
            candidate_scope=ref.scope,
        )
        if decision.directive is PlacementDirective.FORBID:
            continue
        directive_rank = 0 if decision.directive is PlacementDirective.ALLOW else 1
        score = (
            directive_rank,
            _destination_occupancy_rank(events, d_day),
            abs(d_day - ref.d_day),
            -d_day,  # final tie-break: farther from fight, never closer by preference
        )
        candidates.append((score, weekday, d_day, decision))
    if not candidates:
        return None
    _score, weekday, d_day, decision = min(candidates, key=lambda item: item[0])
    return weekday, d_day, decision


def _stamp_relocation(
    role: dict[str, Any],
    *,
    weekday: str,
    d_day: int,
    reason_code: str,
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
    integrity_reason = f"calendar_integrity:{reason_code}"
    if integrity_reason not in reasons:
        reasons.append(integrity_reason)
    summary["reduction_reasons"] = reasons


def _suppress_role(
    ref: _RoleRef,
    *,
    decision: PlacementDecision,
    attempted_days: list[str],
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
        # A previous repair may have removed this role.
        if ref.role not in (ref.week.get("session_roles") or []):
            continue
        current = _evaluate_role(weekly_role_map, ref)
        if current.directive is PlacementDirective.ALLOW:
            continue
        if current.directive is PlacementDirective.DEPRIORITIZE:
            deprioritized_kept += 1
            continue

        destinations = _available_destination_days(ref)
        best = _best_destination(weekly_role_map, ref)
        if best is not None:
            weekday, d_day, destination_decision = best
            from_day = str(ref.role.get("scheduled_day_hint") or ref.role.get("real_weekday") or "")
            from_d_day = ref.d_day
            _stamp_relocation(
                ref.role,
                weekday=weekday,
                d_day=d_day,
                reason_code=current.reason_code,
            )
            actions.append(
                {
                    "role_key": ref.role.get("role_key"),
                    "action": "relocated",
                    "from_day": from_day,
                    "from_d_day": from_d_day,
                    "to_day": weekday.title(),
                    "to_d_day": d_day,
                    "reason_code": current.reason_code,
                    "destination_directive": destination_decision.directive.value,
                }
            )
            continue

        suppression = _suppress_role(
            ref,
            decision=current,
            attempted_days=[weekday.title() for weekday, _d in destinations],
        )
        actions.append({"action": "suppressed", **suppression})

    return actions, deprioritized_kept


def _verify_roles(weekly_role_map: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    contact_positions = _authoritative_contact_positions(weekly_role_map)
    for ref in _role_refs(weekly_role_map):
        # Visible contact roles mirror the resolved contact appointment.
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
                    "immutable": _is_immutable_role(ref),
                    "reason_code": decision.reason_code,
                }
            )
    return violations


def _verify_contacts(weekly_role_map: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for ref in _contact_refs(weekly_role_map):
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
                    "immutable": True,
                    "reason_code": decision.reason_code,
                }
            )
    return violations


def apply_final_calendar_integrity(
    weekly_role_map: dict[str, Any],
    *,
    remorph_callback: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Legalize the finished normal-camp calendar and verify the final state.

    Only ``FORBID`` triggers repair. ``DEPRIORITIZE`` remains legal. Normal
    app-owned roles may relocate inside the same planner week or be suppressed;
    contact, D-13 inward finished-tail state, and D-0 are immutable.

    If any role moves and ``remorph_callback`` is supplied, countdown dose is
    re-resolved by its canonical owner before the final verification pass.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map

    checked_before = len(_role_refs(weekly_role_map)) + len(_contact_refs(weekly_role_map))
    actions, deprioritized_kept = _repair_forbidden_roles(weekly_role_map)
    relocated = sum(action.get("action") == "relocated" for action in actions)
    suppressed = sum(action.get("action") == "suppressed" for action in actions)

    if relocated and remorph_callback is not None:
        remorph_callback(weekly_role_map)

    violations = [
        *_verify_roles(weekly_role_map),
        *_verify_contacts(weekly_role_map),
    ]
    summary = {
        "schema_version": "calendar_integrity.v1",
        "checked_roles": checked_before,
        "relocated_roles": relocated,
        "suppressed_roles": suppressed,
        "deprioritized_kept": deprioritized_kept,
        "unresolved_forbidden": len(violations),
        "actions": actions,
        "violations": violations,
    }
    weekly_role_map["calendar_integrity"] = summary

    if violations:
        codes = ", ".join(
            sorted({str(item.get("reason_code") or "unknown") for item in violations})
        )
        raise CalendarIntegrityError(
            "Final deterministic calendar still contains forbidden placement(s): "
            f"{codes}. Fix the canonical allocator/policy owner; do not ask the AI finalizer to repair it."
        )

    return weekly_role_map


__all__ = ["CalendarIntegrityError", "apply_final_calendar_integrity"]
