"""Canonical calendar-load vocabulary and collision-legality queries.

This module is the shared policy seam described by PLANNER_ARCHITECTURE_CONTRACT.md.
It is intentionally not wired into existing production allocators yet.

The seam has four responsibilities:
1. translate resolved combat-contact state into canonical contact load;
2. translate deterministic planner roles into canonical calendar load;
3. derive calendar context from monotonic chronological positions;
4. return one operational placement directive: ALLOW, DEPRIORITIZE, or FORBID.

Important boundaries:
- ``sparring_dose_planner`` remains the source of truth for resolving declared
  contact into hard / reduced / technical / suppressed contact;
- this module consumes resolved contact state and never infers hard contact from
  a raw declared weekday or athlete-facing label;
- calendar positions are generic integers that increase with time (for example,
  ``date.toordinal()`` or a planner-owned chronological slot index). Raw D-day
  values must be converted before use because D-day counts run in reverse;
- renderers and labels are never inputs to legality decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class LoadClass(str, Enum):
    """Small semantic vocabulary shared by all calendar writers."""

    OFF = "off"
    ZERO_LOAD = "zero_load"
    RECOVERY_ONLY = "recovery_only"
    LOW_LOAD_PHYSICAL = "low_load_physical"
    LOW_LOAD_AEROBIC = "low_load_aerobic"

    TECHNICAL_CONTACT = "technical_contact"
    REDUCED_CONTACT = "reduced_contact"
    HARD_CONTACT = "hard_contact"

    NEURAL_MICRODOSE = "neural_microdose"
    MEANINGFUL_STRENGTH = "meaningful_strength"
    MEANINGFUL_CONDITIONING = "meaningful_conditioning"


class PlacementDirective(str, Enum):
    """Operational result consumed consistently by future calendar writers."""

    ALLOW = "allow"
    DEPRIORITIZE = "deprioritize"
    FORBID = "forbid"


@dataclass(frozen=True)
class PlacementDecision:
    directive: PlacementDirective
    reason_code: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.directive is not PlacementDirective.FORBID

    @property
    def should_deprioritize(self) -> bool:
        return self.directive is PlacementDirective.DEPRIORITIZE


@dataclass(frozen=True)
class CalendarEvent:
    """One already-resolved load at a monotonic chronological position."""

    position: int
    load_class: LoadClass


@dataclass(frozen=True)
class CalendarCollisionContext:
    """Day-level context derived from the entire resolved calendar."""

    candidate_position: int
    same_day_loads: tuple[LoadClass, ...]
    previous_hard_distance: int | None
    next_hard_distance: int | None
    between_effective_hard_contacts: bool

    @property
    def same_day_contacts(self) -> tuple[LoadClass, ...]:
        return tuple(load for load in self.same_day_loads if load in _CONTACT_LOADS)


_CONTACT_EFFECTIVE_LOAD_TO_CLASS = {
    "hard": LoadClass.HARD_CONTACT,
    "reduced": LoadClass.REDUCED_CONTACT,
    "technical": LoadClass.TECHNICAL_CONTACT,
    "none": LoadClass.OFF,
    "suppressed": LoadClass.OFF,
}

_CONTACT_STATUS_TO_CLASS = {
    "hard_as_planned": LoadClass.HARD_CONTACT,
    "deload_suggested": LoadClass.REDUCED_CONTACT,
    "convert_to_technical_suggested": LoadClass.TECHNICAL_CONTACT,
    "suppressed": LoadClass.OFF,
}

_CONTACT_LOADS = frozenset(
    {
        LoadClass.TECHNICAL_CONTACT,
        LoadClass.REDUCED_CONTACT,
        LoadClass.HARD_CONTACT,
    }
)

_MEANINGFUL_LOADS = frozenset(
    {
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
    }
)

_SANDWICH_SAFE_LOADS = frozenset(
    {
        LoadClass.OFF,
        LoadClass.ZERO_LOAD,
        LoadClass.RECOVERY_ONLY,
        LoadClass.LOW_LOAD_AEROBIC,
    }
)

_SAME_CONTACT_DAY_COEXISTABLE = frozenset(
    {
        LoadClass.OFF,
        LoadClass.ZERO_LOAD,
        LoadClass.RECOVERY_ONLY,
    }
)

_ZERO_LOAD_ROLE_KEYS = frozenset(
    {
        "tactical_watch",
        "tactical_cue_card",
        "self_review",
        "neural_visualization",
        "breathing_reset",
        "sleep_downshift",
    }
)

_RECOVERY_ONLY_ROLE_KEYS = frozenset(
    {
        "recovery_reset",
        "fight_week_freshness_day",
        "mobility_rehab",
        "joint_prep",
        "tissue_recovery_day",
        "recovery_reset_day",
    }
)

_LOW_LOAD_PHYSICAL_ROLE_KEYS = frozenset(
    {
        "technical_shadow_rhythm",
        "footwork_walkthrough",
        "movement_quality",
        "small_strength_touch_day",
    }
)

_LOW_LOAD_AEROBIC_ROLE_KEYS = frozenset(
    {
        "aerobic_flush_day",
        "aerobic_support_day",
        "repeatability_support_day",
        "light_fight_pace_touch_day",
        "recovery_aerobic_gas_tank_day",
        "converted_low_aerobic_gas_tank_day",
        "aerobic_shadow_flow",
        "aerobic_footwork_rhythm",
        "aerobic_skip_flush",
        "aerobic_jog_flush",
        "walk_flush",
        "aerobic_walk_flush",
    }
)

_NEURAL_MICRODOSE_ROLE_KEYS = frozenset(
    {
        "neural_primer_day",
        "strength_touch_day",
        "alactic_sharpness_day",
    }
)

_TECHNICAL_CONTACT_ROLE_KEYS = frozenset({"technical_touch_day"})


def _enum_value(enum_type: type[Enum], value: Any):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    try:
        return enum_type(normalized)
    except ValueError:
        return None


def contact_load_class(entry: Mapping[str, Any] | None) -> LoadClass | None:
    """Translate *resolved* sparring-plan state into the shared load vocabulary.

    ``None`` means the record does not contain enough canonical contact state to
    classify safely. Athlete-facing labels and raw declared weekdays are ignored.
    """

    if not isinstance(entry, Mapping):
        return None

    explicit = _enum_value(LoadClass, entry.get("calendar_load_class"))
    if explicit in _CONTACT_LOADS or explicit is LoadClass.OFF:
        return explicit

    effective_load = str(entry.get("effective_load") or "").strip().lower()
    if effective_load in _CONTACT_EFFECTIVE_LOAD_TO_CLASS:
        return _CONTACT_EFFECTIVE_LOAD_TO_CLASS[effective_load]

    status = str(entry.get("status") or "").strip().lower()
    if status in _CONTACT_STATUS_TO_CLASS:
        return _CONTACT_STATUS_TO_CLASS[status]

    return None


def is_effective_hard_contact(entry: Mapping[str, Any] | None) -> bool:
    """True only for resolved effective hard contact."""

    return contact_load_class(entry) is LoadClass.HARD_CONTACT


def _strength_role_load_class(role: Mapping[str, Any]) -> LoadClass:
    cap = role.get("strength_dose_cap")
    if isinstance(cap, Mapping):
        try:
            if int(cap.get("max_sets", 0)) <= 1:
                return LoadClass.NEURAL_MICRODOSE
        except (TypeError, ValueError):
            pass

    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key in _NEURAL_MICRODOSE_ROLE_KEYS:
        return LoadClass.NEURAL_MICRODOSE

    if role.get("late_camp_strength_morph") and str(role.get("set_cap") or "").startswith("1"):
        return LoadClass.NEURAL_MICRODOSE

    return LoadClass.MEANINGFUL_STRENGTH


def _conditioning_role_load_class(role: Mapping[str, Any]) -> LoadClass:
    role_key = str(role.get("role_key") or "").strip().lower()
    system = str(role.get("preferred_system") or "").strip().lower()

    if role_key in _LOW_LOAD_AEROBIC_ROLE_KEYS:
        return LoadClass.LOW_LOAD_AEROBIC
    if role.get("counts_toward_conditioning_cap") is False:
        return LoadClass.LOW_LOAD_AEROBIC
    if role.get("recovery_compatible") and system == "aerobic":
        return LoadClass.LOW_LOAD_AEROBIC
    if role.get("late_camp_role_morph") is True:
        return LoadClass.LOW_LOAD_AEROBIC
    if system == "aerobic":
        return LoadClass.LOW_LOAD_AEROBIC

    return LoadClass.MEANINGFUL_CONDITIONING


def role_load_class(role: Mapping[str, Any] | None) -> LoadClass | None:
    """Classify an existing deterministic planner role into calendar semantics.

    The function prefers an explicit ``calendar_load_class`` stamp. Otherwise it
    maps current deterministic role metadata. Unknown/ambiguous roles return
    ``None`` instead of guessing from labels.

    Declared hard-spar roles are deliberately *not* inferred as hard. A
    ``hard_sparring_day`` requires resolved sparring state on the record (or a
    separate ``contact_load_class`` call) because declared contact is not
    synonymous with effective hard load.
    """

    if not isinstance(role, Mapping):
        return None

    explicit = _enum_value(LoadClass, role.get("calendar_load_class"))
    if isinstance(explicit, LoadClass):
        return explicit

    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()

    if role_key == "hard_sparring_day":
        return contact_load_class(role)
    if role_key in _TECHNICAL_CONTACT_ROLE_KEYS:
        return LoadClass.TECHNICAL_CONTACT
    if role_key in _ZERO_LOAD_ROLE_KEYS:
        return LoadClass.ZERO_LOAD
    if role_key in _RECOVERY_ONLY_ROLE_KEYS:
        return LoadClass.RECOVERY_ONLY
    if role_key in _LOW_LOAD_PHYSICAL_ROLE_KEYS:
        return LoadClass.LOW_LOAD_PHYSICAL
    if role_key in _LOW_LOAD_AEROBIC_ROLE_KEYS:
        return LoadClass.LOW_LOAD_AEROBIC
    if role_key in _NEURAL_MICRODOSE_ROLE_KEYS:
        return LoadClass.NEURAL_MICRODOSE

    if category in {"recovery", "mobility", "rehab"}:
        return LoadClass.RECOVERY_ONLY
    if category == "strength":
        return _strength_role_load_class(role)
    if category == "conditioning":
        return _conditioning_role_load_class(role)

    stress_class = str(role.get("stress_class") or "").strip().lower()
    cost_class = str(role.get("cost_class") or "").strip().lower()
    meaningful = role.get("meaningful_stress")
    if meaningful is None and isinstance(role.get("governance"), Mapping):
        meaningful = role["governance"].get("meaningful_stress")

    if meaningful is False and cost_class == "low":
        return LoadClass.LOW_LOAD_PHYSICAL
    if stress_class == "support" and cost_class == "low":
        return LoadClass.LOW_LOAD_PHYSICAL

    return None


def build_calendar_context(
    candidate_position: int,
    events: Sequence[CalendarEvent] | Iterable[CalendarEvent],
) -> CalendarCollisionContext:
    """Build weekday-agnostic collision context from the full resolved calendar.

    ``position`` must increase chronologically. The function works for any day
    geometry and never contains weekday-specific rules.
    """

    position = int(candidate_position)
    snapshot = tuple(events)

    same_day_loads = tuple(event.load_class for event in snapshot if int(event.position) == position)
    hard_positions = sorted(
        {
            int(event.position)
            for event in snapshot
            if event.load_class is LoadClass.HARD_CONTACT
        }
    )

    previous_positions = [day for day in hard_positions if day < position]
    next_positions = [day for day in hard_positions if day > position]

    previous_hard_distance = (
        position - previous_positions[-1] if previous_positions else None
    )
    next_hard_distance = (
        next_positions[0] - position if next_positions else None
    )

    return CalendarCollisionContext(
        candidate_position=position,
        same_day_loads=same_day_loads,
        previous_hard_distance=previous_hard_distance,
        next_hard_distance=next_hard_distance,
        between_effective_hard_contacts=bool(previous_positions and next_positions),
    )


def _decision(
    directive: PlacementDirective,
    reason_code: str,
    reason: str,
) -> PlacementDecision:
    return PlacementDecision(directive=directive, reason_code=reason_code, reason=reason)


def evaluate_calendar_candidate(
    candidate: LoadClass,
    context: CalendarCollisionContext,
) -> PlacementDecision:
    """Evaluate one candidate load against contact ownership and hard-load spacing.

    This function only answers legality/priority. It never relocates, suppresses,
    inserts, or mutates sessions.
    """

    same_day_contacts = set(context.same_day_contacts)
    same_day_hard = LoadClass.HARD_CONTACT in same_day_contacts

    # Contact-day ownership is distinct from hard-contact recovery pressure.
    if same_day_contacts:
        if same_day_hard:
            if candidate is LoadClass.HARD_CONTACT:
                return _decision(
                    PlacementDirective.ALLOW,
                    "hard_contact_day_owner",
                    "The resolved hard-contact session owns this contact day.",
                )
            if candidate in _SAME_CONTACT_DAY_COEXISTABLE:
                return _decision(
                    PlacementDirective.ALLOW,
                    "hard_contact_day_zero_or_recovery_support",
                    "Hard contact owns the physical day; only zero-load or recovery-only support may coexist.",
                )
            return _decision(
                PlacementDirective.FORBID,
                "hard_contact_same_day_physical_conflict",
                "Do not schedule another physical session on an effective hard-contact day.",
            )

        # Technical/reduced contact owns the physical session slot but does not
        # create hard-contact adjacency pressure on neighbouring days.
        if candidate in same_day_contacts:
            return _decision(
                PlacementDirective.ALLOW,
                "contact_day_owner",
                "The resolved technical/reduced contact session owns this contact slot.",
            )
        if candidate in _SAME_CONTACT_DAY_COEXISTABLE:
            return _decision(
                PlacementDirective.ALLOW,
                "contact_day_zero_or_recovery_support",
                "Technical/reduced contact owns the physical slot; zero-load or recovery-only support may coexist.",
            )
        return _decision(
            PlacementDirective.FORBID,
            "contact_day_extra_physical_conflict",
            "Do not add a separate physical session to a technical/reduced contact-owned day.",
        )

    # A candidate hard-contact session cannot create back-to-back hard contacts.
    if candidate is LoadClass.HARD_CONTACT and (
        context.previous_hard_distance == 1 or context.next_hard_distance == 1
    ):
        return _decision(
            PlacementDirective.FORBID,
            "consecutive_effective_hard_contact",
            "Back-to-back effective hard-contact days are not legal calendar neighbours.",
        )

    # Any position genuinely between two effective hard contacts uses the
    # sandwiched-day policy, regardless of weekday names or how many days apart
    # the two contacts are.
    if context.between_effective_hard_contacts:
        if candidate in _SANDWICH_SAFE_LOADS:
            return _decision(
                PlacementDirective.ALLOW,
                "between_hard_contacts_low_cost",
                "A day between effective hard contacts is reserved for off, zero-load, recovery, or low-aerobic support.",
            )
        if candidate is LoadClass.TECHNICAL_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_technical_contact",
                "Technical-only contact may fit between hard contacts but should lose to a lower-cost option when available.",
            )
        if candidate is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_reduced_contact",
                "Reduced contact still carries residual collision cost and should lose to a lower-cost option between hard contacts.",
            )
        return _decision(
            PlacementDirective.FORBID,
            "between_hard_contacts_meaningful_or_physical_stress",
            "Do not place meaningful S&C, neural stress, low-load physical work, or additional hard contact between effective hard contacts.",
        )

    # Immediate day after effective hard contact: no meaningful S&C.
    if context.previous_hard_distance == 1:
        if candidate in _MEANINGFUL_LOADS:
            return _decision(
                PlacementDirective.FORBID,
                "post_hard_contact_meaningful_stress",
                "The day immediately after effective hard contact cannot carry meaningful S&C.",
            )
        if candidate is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "post_hard_contact_microdose",
                "A neural microdose may survive only when no cleaner slot exists and the dose is genuinely tiny.",
            )
        if candidate is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "post_hard_contact_reduced_contact",
                "Reduced contact retains collision cost immediately after hard contact.",
            )
        return _decision(
            PlacementDirective.ALLOW,
            "post_hard_contact_low_cost",
            "Technical, recovery, tactical, or low-cost work may follow effective hard contact.",
        )

    # Immediate day before effective hard contact is intentionally asymmetric:
    # useful work may survive, but it must lose to a cleaner slot.
    if context.next_hard_distance == 1:
        if candidate in _MEANINGFUL_LOADS or candidate is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "pre_hard_contact_managed_stress",
                "Meaningful or neural work before hard contact is a managed collision and should lose to a cleaner slot.",
            )
        if candidate is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "pre_hard_contact_reduced_contact",
                "Reduced contact carries residual collision cost before hard contact.",
            )
        return _decision(
            PlacementDirective.ALLOW,
            "pre_hard_contact_low_cost",
            "Low-cost or technical work may precede effective hard contact.",
        )

    return _decision(
        PlacementDirective.ALLOW,
        "no_calendar_collision",
        "No contact-day ownership or effective hard-contact spacing rule blocks this candidate.",
    )


def evaluate_candidate_at_position(
    candidate: LoadClass,
    *,
    candidate_position: int,
    events: Sequence[CalendarEvent] | Iterable[CalendarEvent],
) -> PlacementDecision:
    """Convenience wrapper for future allocators, fillers, and integrity checks."""

    context = build_calendar_context(candidate_position, events)
    return evaluate_calendar_candidate(candidate, context)


__all__ = [
    "CalendarCollisionContext",
    "CalendarEvent",
    "LoadClass",
    "PlacementDecision",
    "PlacementDirective",
    "build_calendar_context",
    "contact_load_class",
    "evaluate_calendar_candidate",
    "evaluate_candidate_at_position",
    "is_effective_hard_contact",
    "role_load_class",
]
