"""Canonical read-only calendar-context adapter.

Single owner of the translation ``planner state -> canonical CalendarEvent[]``
that both the final :mod:`calendar_integrity` governor and the upstream support
fillers (:mod:`camp_week_fillers`, :mod:`gap_fill_inserts`) depend on. Extracting
it here means there is exactly one interpretation of:

- chronological position (monotonically increasing ``-d_day``);
- resolved contact events (owned by the sparring resolver / ``hard_sparring_plan``);
- role-load classification (delegated to ``combat_load_policy.role_load_profile``);
- collision scope;
- contact-role de-duplication (a visible ``hard_sparring_day`` role and the
  resolved plan entry describe one appointment, not two).

This module is representation only. ``combat_load_policy`` remains the rule
authority: nothing here decides ALLOW / DEPRIORITIZE / FORBID. It only builds the
inputs the policy evaluates, so that a filler asking "can this coexist here?"
before mutation and the governor verifying the finished calendar read the same
calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Sequence

from .combat_load_policy import (
    CalendarEvent,
    CalendarLoadProfile,
    LoadClass,
    PlacementDecision,
    PlacementDirective,
    contact_load_profile,
    evaluate_candidate_at_position,
    role_load_profile,
)


_CONTACT_LOADS = frozenset(
    {LoadClass.TECHNICAL_CONTACT, LoadClass.REDUCED_CONTACT, LoadClass.HARD_CONTACT}
)
_PHYSICAL_CATEGORIES = frozenset(
    {"strength", "conditioning", "recovery", "mobility", "rehab", "sparring"}
)
_CONTACT_MIRROR_ROLE_KEYS = frozenset({"hard_sparring_day", "no_hard_sparring_day"})

# Late-fight gap-fill runs on one continuous countdown window rather than a
# planner-week map, so its scoped between-hard-contact protection uses one scope.
LATE_FIGHT_SCOPE: tuple[str, int] = ("late_fight", 0)


class UnclassifiablePlannerRoleError(ValueError):
    """A physical planner role could not be classified by ``combat_load_policy``.

    Callers that must fail loudly (the final governor) pass their own
    ``error_cls`` so the raised type stays theirs; representation-only callers
    (the fillers) run lenient and receive ``None`` instead.
    """


def _normalise(value: Any) -> str:
    return str(value or "").strip().lower()


def _calendar_by_day(week: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        weekday = _normalise(day.get("weekday"))
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


def role_d_day(week: dict[str, Any], role: dict[str, Any]) -> int | None:
    calendar = _calendar_by_day(week)
    weekday = _normalise(role.get("scheduled_day_hint") or role.get("real_weekday"))
    if weekday in calendar:
        return calendar[weekday]
    for key in ("scheduled_countdown_label", "countdown_label"):
        if (d_day := _label_d_day(role.get(key))) is not None:
            return d_day
    return None


def contact_d_day(week: dict[str, Any], entry: dict[str, Any]) -> int | None:
    calendar = _calendar_by_day(week)
    weekday = _normalise(entry.get("day"))
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
    if _normalise(role.get("category")) in _PHYSICAL_CATEGORIES:
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


def classify_role(
    role: dict[str, Any],
    *,
    strict: bool = False,
    error_cls: type[Exception] | None = None,
) -> CalendarLoadProfile | None:
    """Return the shared load profile for a planner ``role``.

    Visible contact mirrors (``hard_sparring_day`` / ``no_hard_sparring_day``)
    return ``None``: resolved contact is owned by ``hard_sparring_plan``, not the
    visible role, so callers supply contact events from the resolved plan.

    When ``strict`` and a physical role is not classifiable, raise ``error_cls``
    (or :class:`UnclassifiablePlannerRoleError`) so an unhandled physical role
    fails loudly instead of silently dropping out of the calendar view.
    """
    profile = role_load_profile(role)
    if profile is not None:
        return profile
    if _normalise(role.get("role_key")) in _CONTACT_MIRROR_ROLE_KEYS:
        return None
    if strict and _looks_physical(role):
        cls = error_cls or UnclassifiablePlannerRoleError
        raise cls(
            "Physical planner role is not classifiable by combat_load_policy: "
            f"{role.get('role_key')!r}. Extend the shared classifier; do not guess."
        )
    return None


def week_scope(week: dict[str, Any], ordinal: int | None = None) -> tuple[str, int | None]:
    try:
        index = int(week.get("week_index"))
    except (TypeError, ValueError):
        index = ordinal
    return ("normal_week", index)


@dataclass(frozen=True)
class RoleRef:
    week: dict[str, Any]
    week_ordinal: int
    role: dict[str, Any]
    d_day: int
    profile: CalendarLoadProfile

    @property
    def scope(self) -> tuple[str, int | None]:
        return week_scope(self.week, self.week_ordinal)


@dataclass(frozen=True)
class ContactRef:
    week: dict[str, Any]
    week_ordinal: int
    entry: dict[str, Any]
    d_day: int
    profile: CalendarLoadProfile

    @property
    def scope(self) -> tuple[str, int | None]:
        return week_scope(self.week, self.week_ordinal)


def role_refs(
    weekly_role_map: dict[str, Any],
    *,
    strict: bool = False,
    error_cls: type[Exception] | None = None,
) -> list[RoleRef]:
    refs: list[RoleRef] = []
    for ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            d_day = role_d_day(week, role)
            profile = classify_role(role, strict=strict, error_cls=error_cls)
            if d_day is None or profile is None or profile.load_class is LoadClass.OFF:
                continue
            refs.append(RoleRef(week, ordinal, role, d_day, profile))
    return refs


def contact_refs(weekly_role_map: dict[str, Any]) -> list[ContactRef]:
    refs: list[ContactRef] = []
    for ordinal, week in enumerate(weekly_role_map.get("weeks", []) or [], start=1):
        if not isinstance(week, dict):
            continue
        for entry in week.get("hard_sparring_plan") or []:
            if not isinstance(entry, dict):
                continue
            profile = contact_load_profile(entry)
            d_day = contact_d_day(week, entry)
            if profile is None or profile.load_class is LoadClass.OFF or d_day is None:
                continue
            refs.append(ContactRef(week, ordinal, entry, d_day, profile))
    return refs


def authoritative_contact_positions(weekly_role_map: dict[str, Any]) -> set[int]:
    return {-ref.d_day for ref in contact_refs(weekly_role_map)}


def build_events(
    weekly_role_map: dict[str, Any],
    *,
    exclude_role: dict[str, Any] | None = None,
    exclude_contact: dict[str, Any] | None = None,
    strict: bool = False,
    error_cls: type[Exception] | None = None,
) -> list[CalendarEvent]:
    """Canonical ``weekly_role_map -> CalendarEvent[]`` construction.

    Contact events come from the resolved ``hard_sparring_plan``; a visible
    contact role at a resolved contact position is a mirror and is dropped so the
    resolved plan stays the single contact authority.
    """
    events: list[CalendarEvent] = []
    contact_positions = authoritative_contact_positions(weekly_role_map)
    for ref in contact_refs(weekly_role_map):
        if exclude_contact is ref.entry:
            continue
        events.append(CalendarEvent(-ref.d_day, ref.profile, ref.scope))
    for ref in role_refs(weekly_role_map, strict=strict, error_cls=error_cls):
        if exclude_role is ref.role:
            continue
        if ref.profile.load_class in _CONTACT_LOADS and -ref.d_day in contact_positions:
            continue
        events.append(CalendarEvent(-ref.d_day, ref.profile, ref.scope))
    return events


def sequence_role_offset(role: dict[str, Any]) -> int | None:
    """Chronological countdown offset (D-day) of a flat late-fight session role."""
    value = role.get("countdown_offset")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    for key in ("scheduled_countdown_label", "countdown_label"):
        if (offset := _label_d_day(role.get(key))) is not None:
            return offset
    return None


def contact_profile_for_load(load: Any) -> CalendarLoadProfile | None:
    """Translate a resolved-contact load token to a canonical contact profile.

    ``load`` may already be a :class:`CalendarLoadProfile`, or a resolved
    ``effective_load`` string (``hard`` / ``reduced`` / ``technical`` / ``none``).
    Resolution stays owned by the sparring resolver; this only re-uses the policy
    contact classifier so the profile matches every other contact event.
    """
    if isinstance(load, CalendarLoadProfile):
        return load
    text = _normalise(load)
    if not text:
        return None
    return contact_load_profile({"effective_load": text})


def sequence_events(
    roles: Iterable[dict[str, Any]],
    *,
    scope: Hashable | None = LATE_FIGHT_SCOPE,
    resolved_contacts: Sequence[tuple[int, Any]] | Iterable[tuple[int, Any]] = (),
) -> list[CalendarEvent]:
    """Canonical ``flat late-fight session sequence -> CalendarEvent[]``.

    ``resolved_contacts`` carries ``(countdown_offset, load)`` pairs from the
    late-fight sparring resolver and is the authoritative contact source; visible
    ``hard_sparring_day`` mirrors in ``roles`` classify to ``None`` and are not a
    second contact source. Other app-owned roles (contact-light sessions, exclusive
    stressors) classify through the same shared policy the governor uses.
    """
    events: list[CalendarEvent] = []
    contact_positions: set[int] = set()
    for offset, load in resolved_contacts:
        try:
            off = int(offset)
        except (TypeError, ValueError):
            continue
        if off <= 0:
            continue
        profile = contact_profile_for_load(load)
        if profile is None or profile.load_class is LoadClass.OFF:
            continue
        position = -off
        events.append(CalendarEvent(position, profile, scope))
        contact_positions.add(position)
    for role in roles:
        if not isinstance(role, dict):
            continue
        off = sequence_role_offset(role)
        if off is None or off <= 0:
            continue
        profile = classify_role(role)
        if profile is None or profile.load_class is LoadClass.OFF:
            continue
        position = -off
        if profile.load_class in _CONTACT_LOADS and position in contact_positions:
            continue
        events.append(CalendarEvent(position, profile, scope))
    return events


@dataclass(frozen=True)
class CalendarLegalityView:
    """A built calendar view (events + collision scope) paired with the policy.

    This is the single seam a support filler uses to ask *"may this candidate go
    on this day?"* before it mutates the calendar. The rule answer comes entirely
    from :func:`combat_load_policy.evaluate_candidate_at_position`; the view only
    carries the canonical events/scope so every caller queries the same calendar
    the final governor verifies. It never decides doctrine itself.
    """

    events: tuple[CalendarEvent, ...]
    scope: Hashable | None = None

    def decision_for_profile(
        self, profile: CalendarLoadProfile, offset: int
    ) -> PlacementDecision:
        return evaluate_candidate_at_position(
            profile,
            candidate_position=-int(offset),
            events=self.events,
            candidate_scope=self.scope,
        )

    def decision_for_role(
        self, role: dict[str, Any], offset: int
    ) -> PlacementDecision | None:
        profile = classify_role(role)
        if profile is None:
            return None
        return self.decision_for_profile(profile, offset)

    def role_is_forbidden(self, role: dict[str, Any], offset: int) -> bool:
        decision = self.decision_for_role(role, offset)
        return decision is not None and decision.directive is PlacementDirective.FORBID

    def contact_offsets(self) -> set[int]:
        """Countdown offsets (positive D-days) that carry a resolved contact.

        Lets a filler ask "is this day an effective hard/technical contact day?"
        from the canonical contact events rather than raw declared weekday names.
        """
        return {
            -event.position
            for event in self.events
            if event.profile.load_class in _CONTACT_LOADS
        }


def weekly_role_map_legality(
    weekly_role_map: dict[str, Any],
    week: dict[str, Any],
    ordinal: int | None = None,
) -> CalendarLegalityView:
    """Legality view for a normal-camp filler placing inside ``week``.

    Events are built from the *whole* ``weekly_role_map`` so immediate
    hard-contact adjacency is seen across planner-week boundaries; the scope is
    ``week``'s own collision scope so scoped between-hard-contact protection stays
    per-week. Runs lenient: an unclassifiable physical role upstream is the
    governor's problem to raise, not the filler's.
    """
    return CalendarLegalityView(
        events=tuple(build_events(weekly_role_map)),
        scope=week_scope(week, ordinal),
    )


def sequence_legality(
    roles: Iterable[dict[str, Any]],
    *,
    scope: Hashable | None = LATE_FIGHT_SCOPE,
    resolved_contacts: Sequence[tuple[int, Any]] | Iterable[tuple[int, Any]] = (),
) -> CalendarLegalityView:
    """Legality view for a late-fight gap-fill insert over a flat sequence."""
    return CalendarLegalityView(
        events=tuple(sequence_events(roles, scope=scope, resolved_contacts=resolved_contacts)),
        scope=scope,
    )


__all__ = [
    "LATE_FIGHT_SCOPE",
    "CalendarLegalityView",
    "ContactRef",
    "RoleRef",
    "UnclassifiablePlannerRoleError",
    "authoritative_contact_positions",
    "build_events",
    "classify_role",
    "contact_d_day",
    "contact_profile_for_load",
    "contact_refs",
    "role_d_day",
    "role_refs",
    "sequence_events",
    "sequence_legality",
    "sequence_role_offset",
    "week_scope",
    "weekly_role_map_legality",
]
