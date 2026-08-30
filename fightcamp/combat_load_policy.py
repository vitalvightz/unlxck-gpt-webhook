"""Canonical calendar-load vocabulary and collision-legality queries.

This module is the shared policy seam described by
``PLANNER_ARCHITECTURE_CONTRACT.md``. It is intentionally not wired into
production allocators yet.

Responsibilities:
1. consume resolved combat-contact state without re-deciding sparring dose;
2. classify deterministic planner roles into shared load + day-occupancy state;
3. derive collision context from generic chronological positions and an explicit
   planner-owned collision scope;
4. return one operational directive: ALLOW, DEPRIORITIZE, or FORBID.

Important boundaries:
- ``sparring_dose_planner`` remains the source of truth for hard / reduced /
  technical / suppressed contact;
- athlete-facing labels and raw declared weekdays never determine load;
- positions must increase chronologically. Raw D-day values run in reverse and
  must be converted by the caller before use;
- protected "between hard contacts" spans are scope-aware. Immediate +/-1-day
  hard-contact rules remain global so recovery protection survives a week/segment
  boundary;
- load and day occupancy are separate. A low-load session can still own a full
  physical slot, while a true zero/recovery insert may be coexistable;
- renderers are consumers only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Hashable, Iterable, Mapping, Sequence


class LoadClass(str, Enum):
    """Semantic training/contact load used by shared calendar policy."""

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


class DayOccupancy(str, Enum):
    """Whether a role may share a day with another physical/contact session."""

    COEXISTABLE = "coexistable"
    PHYSICAL = "physical"
    EXCLUSIVE_PHYSICAL = "exclusive_physical"


class PlacementDirective(str, Enum):
    """Operational result for allocators, fillers, and integrity checks."""

    ALLOW = "allow"
    DEPRIORITIZE = "deprioritize"
    FORBID = "forbid"


@dataclass(frozen=True)
class CalendarLoadProfile:
    load_class: LoadClass
    occupancy: DayOccupancy


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
    """One already-placed resolved load at a monotonic chronological position."""

    position: int
    profile: CalendarLoadProfile
    collision_scope: Hashable | None = None


@dataclass(frozen=True)
class CalendarCollisionContext:
    candidate_position: int
    candidate_scope: Hashable | None
    same_day_profiles: tuple[CalendarLoadProfile, ...]
    previous_hard_distance: int | None
    next_hard_distance: int | None
    between_effective_hard_contacts: bool

    @property
    def same_day_contacts(self) -> tuple[CalendarLoadProfile, ...]:
        return tuple(
            profile
            for profile in self.same_day_profiles
            if profile.load_class in _CONTACT_LOADS
        )


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

_SANDWICH_ALLOW_LOADS = frozenset(
    {
        LoadClass.OFF,
        LoadClass.ZERO_LOAD,
        LoadClass.RECOVERY_ONLY,
        LoadClass.LOW_LOAD_AEROBIC,
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

# These are inserts, not full physical sessions.
_COEXISTABLE_RECOVERY_ROLE_KEYS = frozenset({"recovery_reset"})

_PHYSICAL_RECOVERY_ROLE_KEYS = frozenset(
    {
        "fight_week_freshness_day",
        "mobility_rehab",
        "joint_prep",
        "tissue_recovery_day",
        "recovery_reset_day",
    }
)

_DAY_EXCLUSIVE_RECOVERY_ROLE_KEYS = frozenset({"fight_week_freshness_day"})

_LOW_LOAD_PHYSICAL_ROLE_KEYS = frozenset(
    {
        "technical_shadow_rhythm",
        "footwork_walkthrough",
        "movement_quality",
    }
)

_LOW_LOAD_AEROBIC_ROLE_KEYS = frozenset(
    {
        "aerobic_flush_day",
        "aerobic_support_day",
        "aerobic_base_day",
        "aerobic_coordination_day",
        "repeatability_support_day",
        "recovery_aerobic_gas_tank_day",
        "converted_low_aerobic_gas_tank_day",
        "converted_mobility_support_day",
        "converted_recovery_flush_day",
        "converted_rehab_friendly_support_day",
        "aerobic_shadow_flow",
        "aerobic_footwork_rhythm",
        "aerobic_skip_flush",
        "aerobic_jog_flush",
        "walk_flush",
        "aerobic_walk_flush",
    }
)

# Normal-camp alactic support is low-noise in the current planner. Speed and
# sharpness variants are neural work unless an explicit late-fight stress/cost
# classification upgrades them to meaningful stress.
_LOW_LOAD_ALACTIC_ROLE_KEYS = frozenset(
    {"alactic_support_day", "alactic_coordination_day"}
)
_NEURAL_ALACTIC_ROLE_KEYS = frozenset(
    {"alactic_speed_day", "alactic_sharpness_day"}
)

_TECHNICAL_CONTACT_ROLE_KEYS = frozenset(
    {"technical_touch_day", "light_combat_day"}
)

# Existing D-13-inward allocator treats these as day-exclusive stressor roles.
# The shared seam must preserve that occupancy when Step 9 eventually migrates
# the late-fight allocator to these semantics.
_DAY_EXCLUSIVE_STRESSOR_ROLE_KEYS = frozenset(
    {
        "strength_touch_day",
        "neural_primer_day",
        "alactic_sharpness_day",
        "light_fight_pace_touch_day",
    }
)


def _enum_value(enum_type: type[Enum], value: Any):
    if isinstance(value, enum_type):
        return value
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    try:
        return enum_type(normalized)
    except ValueError:
        return None


def _default_occupancy(load_class: LoadClass) -> DayOccupancy:
    if load_class in {LoadClass.OFF, LoadClass.ZERO_LOAD}:
        return DayOccupancy.COEXISTABLE
    if load_class in _CONTACT_LOADS:
        return DayOccupancy.EXCLUSIVE_PHYSICAL
    return DayOccupancy.PHYSICAL


def _validate_profile_compatibility(
    load_class: LoadClass,
    occupancy: DayOccupancy,
) -> None:
    if load_class in {LoadClass.OFF, LoadClass.ZERO_LOAD}:
        if occupancy is not DayOccupancy.COEXISTABLE:
            raise ValueError("Off/zero-load work must use coexistable occupancy.")
        return
    if load_class in _CONTACT_LOADS:
        if occupancy is not DayOccupancy.EXCLUSIVE_PHYSICAL:
            raise ValueError("Contact load must own an exclusive physical slot.")
        return
    if load_class is not LoadClass.RECOVERY_ONLY and occupancy is DayOccupancy.COEXISTABLE:
        raise ValueError("Physical training load cannot be stamped as coexistable support.")


def _profile(
    load_class: LoadClass,
    occupancy: DayOccupancy | None = None,
) -> CalendarLoadProfile:
    resolved_occupancy = occupancy or _default_occupancy(load_class)
    _validate_profile_compatibility(load_class, resolved_occupancy)
    return CalendarLoadProfile(load_class=load_class, occupancy=resolved_occupancy)


def _resolved_contact_class(entry: Mapping[str, Any]) -> LoadClass | None:
    effective_raw = str(entry.get("effective_load") or "").strip().lower()
    status_raw = str(entry.get("status") or "").strip().lower()
    effective = _CONTACT_EFFECTIVE_LOAD_TO_CLASS.get(effective_raw)
    status = _CONTACT_STATUS_TO_CLASS.get(status_raw)
    if effective is not None and status is not None and effective is not status:
        raise ValueError(
            "Resolved contact fields disagree: effective_load and status map to different contact classes."
        )
    return effective or status


def contact_load_profile(entry: Mapping[str, Any] | None) -> CalendarLoadProfile | None:
    """Translate resolved sparring state into canonical load + occupancy."""

    if not isinstance(entry, Mapping):
        return None

    resolved = _resolved_contact_class(entry)
    explicit_load = _enum_value(LoadClass, entry.get("calendar_load_class"))
    explicit_occupancy = _enum_value(
        DayOccupancy, entry.get("calendar_day_occupancy")
    )

    if explicit_load is not None and explicit_load not in _CONTACT_LOADS and explicit_load is not LoadClass.OFF:
        raise ValueError("Contact calendar_load_class must be a contact class or off.")
    if resolved is not None and explicit_load is not None and resolved is not explicit_load:
        raise ValueError("calendar_load_class conflicts with resolved sparring contact state.")

    load_class = resolved or explicit_load
    if load_class is None:
        return None

    canonical = _profile(load_class)
    if explicit_occupancy is not None and explicit_occupancy is not canonical.occupancy:
        raise ValueError("calendar_day_occupancy conflicts with contact ownership semantics.")
    return canonical


def contact_load_class(entry: Mapping[str, Any] | None) -> LoadClass | None:
    profile = contact_load_profile(entry)
    return profile.load_class if profile is not None else None


def is_effective_hard_contact(entry: Mapping[str, Any] | None) -> bool:
    return contact_load_class(entry) is LoadClass.HARD_CONTACT


def _exclusive_if_needed(
    role_key: str,
    profile: CalendarLoadProfile,
) -> CalendarLoadProfile:
    if role_key in _DAY_EXCLUSIVE_STRESSOR_ROLE_KEYS:
        return _profile(profile.load_class, DayOccupancy.EXCLUSIVE_PHYSICAL)
    return profile


def _strength_role_profile(role: Mapping[str, Any]) -> CalendarLoadProfile:
    cap = role.get("strength_dose_cap")
    if isinstance(cap, Mapping):
        try:
            max_sets = int(cap.get("max_sets", 0))
        except (TypeError, ValueError):
            max_sets = 0
        if max_sets <= 0:
            # Countdown morph may reduce a strength role to readiness/mobility
            # only. Do not keep calling a zero-set role meaningful strength.
            return _profile(LoadClass.RECOVERY_ONLY)
        if max_sets == 1:
            return _profile(LoadClass.NEURAL_MICRODOSE)
        return _profile(LoadClass.MEANINGFUL_STRENGTH)

    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key == "small_strength_touch_day":
        return _profile(LoadClass.NEURAL_MICRODOSE)
    return _profile(LoadClass.MEANINGFUL_STRENGTH)


def _conditioning_role_profile(role: Mapping[str, Any]) -> CalendarLoadProfile:
    role_key = str(role.get("role_key") or "").strip().lower()
    system = str(role.get("preferred_system") or "").strip().lower()
    stress_class = str(role.get("stress_class") or "").strip().lower()
    cost_class = str(role.get("cost_class") or "").strip().lower()
    meaningful = role.get("meaningful_stress")
    governance = role.get("governance") if isinstance(role.get("governance"), Mapping) else {}
    if meaningful is None:
        meaningful = governance.get("meaningful_stress")

    # Post-morph/recovery semantics outrank the old role name.
    if role.get("counts_toward_conditioning_cap") is False:
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if role.get("late_camp_role_morph") is True:
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if role.get("recovery_compatible") and system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if meaningful is False and system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if stress_class == "support" and cost_class == "low" and system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)

    # Explicit late-fight stress/cost metadata is authoritative for the role's
    # current meaning. This keeps e.g. a D-13 alactic sharpness role meaningful
    # while normal-camp alactic support remains low-noise.
    if meaningful is True or stress_class == "meaningful_stress" or cost_class in {"medium", "high"}:
        return _profile(LoadClass.MEANINGFUL_CONDITIONING)

    if role_key in _LOW_LOAD_AEROBIC_ROLE_KEYS or system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if role_key in _LOW_LOAD_ALACTIC_ROLE_KEYS:
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    if role_key in _NEURAL_ALACTIC_ROLE_KEYS:
        return _profile(LoadClass.NEURAL_MICRODOSE)
    if system in {"alactic", "atp-pcr", "atp_pcr"}:
        return _profile(LoadClass.NEURAL_MICRODOSE)
    if system == "glycolytic":
        return _profile(LoadClass.MEANINGFUL_CONDITIONING)

    # Unknown non-aerobic conditioning remains conservative rather than being
    # silently called recovery work.
    return _profile(LoadClass.MEANINGFUL_CONDITIONING)


def _derived_role_profile(role: Mapping[str, Any]) -> CalendarLoadProfile | None:
    """Derive profile from canonical current role semantics, never display text."""

    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()

    if role_key in _ZERO_LOAD_ROLE_KEYS:
        return _profile(LoadClass.ZERO_LOAD, DayOccupancy.COEXISTABLE)
    if role_key in _COEXISTABLE_RECOVERY_ROLE_KEYS:
        return _profile(LoadClass.RECOVERY_ONLY, DayOccupancy.COEXISTABLE)
    if role_key in _PHYSICAL_RECOVERY_ROLE_KEYS:
        occupancy = (
            DayOccupancy.EXCLUSIVE_PHYSICAL
            if role_key in _DAY_EXCLUSIVE_RECOVERY_ROLE_KEYS
            else DayOccupancy.PHYSICAL
        )
        return _profile(LoadClass.RECOVERY_ONLY, occupancy)
    if role_key in _LOW_LOAD_PHYSICAL_ROLE_KEYS:
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    if role_key in _LOW_LOAD_AEROBIC_ROLE_KEYS:
        return _profile(LoadClass.LOW_LOAD_AEROBIC)

    if category in {"recovery", "mobility", "rehab"}:
        return _profile(LoadClass.RECOVERY_ONLY)
    if category == "strength":
        return _exclusive_if_needed(role_key, _strength_role_profile(role))
    if category == "conditioning":
        return _exclusive_if_needed(role_key, _conditioning_role_profile(role))

    stress_class = str(role.get("stress_class") or "").strip().lower()
    cost_class = str(role.get("cost_class") or "").strip().lower()
    meaningful = role.get("meaningful_stress")
    governance = role.get("governance") if isinstance(role.get("governance"), Mapping) else {}
    if meaningful is None:
        meaningful = governance.get("meaningful_stress")

    if meaningful is False and cost_class == "low":
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    if stress_class == "support" and cost_class == "low":
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    return None


def _reconcile_explicit_role_stamp(
    role: Mapping[str, Any],
    derived: CalendarLoadProfile | None,
) -> CalendarLoadProfile | None:
    explicit_load = _enum_value(LoadClass, role.get("calendar_load_class"))
    explicit_occupancy = _enum_value(
        DayOccupancy, role.get("calendar_day_occupancy")
    )

    if derived is not None:
        if explicit_load is not None and explicit_load is not derived.load_class:
            raise ValueError("calendar_load_class conflicts with canonical role semantics.")
        if explicit_occupancy is not None and explicit_occupancy is not derived.occupancy:
            raise ValueError("calendar_day_occupancy conflicts with canonical role semantics.")
        return derived

    if explicit_load is None:
        if explicit_occupancy is not None:
            raise ValueError("calendar_day_occupancy requires calendar_load_class.")
        return None
    if explicit_load in _CONTACT_LOADS:
        raise ValueError("Only contact-owned roles may carry a contact calendar_load_class.")
    return _profile(explicit_load, explicit_occupancy)


def role_load_profile(role: Mapping[str, Any] | None) -> CalendarLoadProfile | None:
    """Classify deterministic role state into canonical load + occupancy.

    Known role/category semantics are authoritative. An explicit stamp can confirm
    them but cannot contradict them. Unknown future non-contact roles may opt in
    with a valid explicit stamp; contact truth must still come from the contact
    resolver.
    """

    if not isinstance(role, Mapping):
        return None

    role_key = str(role.get("role_key") or "").strip().lower()

    if role_key == "hard_sparring_day":
        return contact_load_profile(role)

    if role_key in _TECHNICAL_CONTACT_ROLE_KEYS:
        canonical = _profile(LoadClass.TECHNICAL_CONTACT)
        explicit_load = _enum_value(LoadClass, role.get("calendar_load_class"))
        explicit_occupancy = _enum_value(
            DayOccupancy, role.get("calendar_day_occupancy")
        )
        if explicit_load is not None and explicit_load is not canonical.load_class:
            raise ValueError("Technical contact role has a conflicting calendar_load_class stamp.")
        if explicit_occupancy is not None and explicit_occupancy is not canonical.occupancy:
            raise ValueError("Technical contact role has conflicting day occupancy.")
        return canonical

    derived = _derived_role_profile(role)
    return _reconcile_explicit_role_stamp(role, derived)


def role_load_class(role: Mapping[str, Any] | None) -> LoadClass | None:
    profile = role_load_profile(role)
    return profile.load_class if profile is not None else None


def build_calendar_context(
    candidate_position: int,
    events: Sequence[CalendarEvent] | Iterable[CalendarEvent],
    *,
    candidate_scope: Hashable | None = None,
) -> CalendarCollisionContext:
    """Build weekday-agnostic context from the resolved calendar."""

    position = int(candidate_position)
    snapshot = tuple(events)
    for event in snapshot:
        if not isinstance(event, CalendarEvent):
            raise TypeError("events must contain CalendarEvent instances")
        if not isinstance(event.profile, CalendarLoadProfile):
            raise TypeError("CalendarEvent.profile must be CalendarLoadProfile")
        _validate_profile_compatibility(
            event.profile.load_class, event.profile.occupancy
        )

    same_day_profiles = tuple(
        event.profile for event in snapshot if int(event.position) == position
    )

    hard_positions = sorted(
        {
            int(event.position)
            for event in snapshot
            if event.profile.load_class is LoadClass.HARD_CONTACT
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

    # "Between" is meaningful only inside an explicit allocator-owned collision
    # scope. Without one, the full camp's first and last hard contacts must not
    # accidentally turn every intervening day into a protected sandwich.
    between_in_scope = False
    if candidate_scope is not None:
        scope_hard_positions = sorted(
            {
                int(event.position)
                for event in snapshot
                if event.collision_scope == candidate_scope
                and event.profile.load_class is LoadClass.HARD_CONTACT
            }
        )
        between_in_scope = any(day < position for day in scope_hard_positions) and any(
            day > position for day in scope_hard_positions
        )

    return CalendarCollisionContext(
        candidate_position=position,
        candidate_scope=candidate_scope,
        same_day_profiles=same_day_profiles,
        previous_hard_distance=previous_hard_distance,
        next_hard_distance=next_hard_distance,
        between_effective_hard_contacts=between_in_scope,
    )


def _decision(
    directive: PlacementDirective,
    reason_code: str,
    reason: str,
) -> PlacementDecision:
    return PlacementDecision(
        directive=directive,
        reason_code=reason_code,
        reason=reason,
    )


def _same_day_ownership_decision(
    candidate: CalendarLoadProfile,
    same_day_profiles: tuple[CalendarLoadProfile, ...],
) -> PlacementDecision | None:
    if not same_day_profiles:
        return None

    existing_contact = any(
        profile.load_class in _CONTACT_LOADS for profile in same_day_profiles
    )
    existing_exclusive = any(
        profile.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL
        for profile in same_day_profiles
    )
    existing_physical = any(
        profile.occupancy
        in {DayOccupancy.PHYSICAL, DayOccupancy.EXCLUSIVE_PHYSICAL}
        for profile in same_day_profiles
    )

    if candidate.load_class in _CONTACT_LOADS and existing_physical:
        return _decision(
            PlacementDirective.FORBID,
            "contact_candidate_physical_conflict",
            "Do not add contact to a day that already contains a separate physical/contact session.",
        )

    if candidate.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL and existing_physical:
        return _decision(
            PlacementDirective.FORBID,
            "exclusive_physical_slot_conflict",
            "This candidate owns an exclusive physical slot and cannot be added to an already-occupied physical day.",
        )

    if existing_exclusive and candidate.occupancy is not DayOccupancy.COEXISTABLE:
        reason_code = (
            "contact_day_extra_physical_conflict"
            if existing_contact
            else "exclusive_day_extra_physical_conflict"
        )
        return _decision(
            PlacementDirective.FORBID,
            reason_code,
            "An existing exclusive physical/contact session owns this day; only coexistable support may be added.",
        )

    return None


def evaluate_calendar_candidate(
    candidate: CalendarLoadProfile,
    context: CalendarCollisionContext,
) -> PlacementDecision:
    """Evaluate one candidate against day ownership and hard-contact spacing."""

    if not isinstance(candidate, CalendarLoadProfile):
        raise TypeError("candidate must be CalendarLoadProfile")
    _validate_profile_compatibility(candidate.load_class, candidate.occupancy)

    same_day = _same_day_ownership_decision(candidate, context.same_day_profiles)
    if same_day is not None:
        return same_day

    load_class = candidate.load_class

    if load_class is LoadClass.HARD_CONTACT and (
        context.previous_hard_distance == 1 or context.next_hard_distance == 1
    ):
        return _decision(
            PlacementDirective.FORBID,
            "consecutive_effective_hard_contact",
            "Back-to-back effective hard-contact days are not legal calendar neighbours.",
        )

    if context.between_effective_hard_contacts:
        if load_class in _SANDWICH_ALLOW_LOADS:
            return _decision(
                PlacementDirective.ALLOW,
                "between_hard_contacts_low_cost",
                "This scoped position between effective hard contacts is reserved for off, zero-load, recovery, or low-aerobic support.",
            )
        if load_class is LoadClass.LOW_LOAD_PHYSICAL:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_low_load_physical",
                "Low-load movement may survive between hard contacts only when a cleaner recovery/aerobic option is unavailable.",
            )
        if load_class is LoadClass.TECHNICAL_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_technical_contact",
                "Technical-only contact may fit between hard contacts but should lose to a lower-cost option when available.",
            )
        if load_class is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_reduced_contact",
                "Reduced contact retains residual collision cost and should lose to a lower-cost option between hard contacts.",
            )
        return _decision(
            PlacementDirective.FORBID,
            "between_hard_contacts_meaningful_or_neural_stress",
            "Do not place meaningful S&C, neural stress, or additional hard contact inside this protected between-contact span.",
        )

    if context.previous_hard_distance == 1:
        if load_class in _MEANINGFUL_LOADS:
            return _decision(
                PlacementDirective.FORBID,
                "post_hard_contact_meaningful_stress",
                "The day immediately after effective hard contact cannot carry meaningful S&C.",
            )
        if load_class is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "post_hard_contact_microdose",
                "A neural microdose may survive only when no cleaner slot exists and the dose is genuinely tiny.",
            )
        if load_class is LoadClass.REDUCED_CONTACT:
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

    if context.next_hard_distance == 1:
        if load_class in _MEANINGFUL_LOADS or load_class is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "pre_hard_contact_managed_stress",
                "Meaningful or neural work before hard contact is a managed collision and should lose to a cleaner slot.",
            )
        if load_class is LoadClass.REDUCED_CONTACT:
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
        "No day-ownership or effective hard-contact spacing rule blocks this candidate.",
    )


def evaluate_candidate_at_position(
    candidate: CalendarLoadProfile,
    *,
    candidate_position: int,
    events: Sequence[CalendarEvent] | Iterable[CalendarEvent],
    candidate_scope: Hashable | None = None,
) -> PlacementDecision:
    context = build_calendar_context(
        candidate_position,
        events,
        candidate_scope=candidate_scope,
    )
    return evaluate_calendar_candidate(candidate, context)


__all__ = [
    "CalendarCollisionContext",
    "CalendarEvent",
    "CalendarLoadProfile",
    "DayOccupancy",
    "LoadClass",
    "PlacementDecision",
    "PlacementDirective",
    "build_calendar_context",
    "contact_load_class",
    "contact_load_profile",
    "evaluate_calendar_candidate",
    "evaluate_candidate_at_position",
    "is_effective_hard_contact",
    "role_load_class",
    "role_load_profile",
]
