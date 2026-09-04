"""Shared calendar-load and combat-collision policy.

This is the canonical collision-legality owner named in
``PLANNER_ARCHITECTURE_CONTRACT.md``. It is consumed in production by both
placement owners (``stage2_role_map`` / ``normal_calendar_placement`` for normal
camp, ``stage2_payload_late_fight`` for the countdown), by the support fillers
(``camp_week_fillers`` / ``gap_fill_inserts``), and by the final calendar governor
(``calendar_integrity``) — all through the canonical ``calendar_context`` adapter.
No other module may decide ALLOW / DEPRIORITIZE / FORBID.

Rules of ownership:
- ``sparring_dose_planner`` resolves declared contact to hard/reduced/technical/off;
- this module consumes that resolved state and never infers contact from labels or
  raw weekday declarations;
- planner roles are translated to a small load vocabulary plus independent day
  occupancy semantics;
- calendar positions are monotonically increasing chronological integers. Raw
  D-day counts must be converted by callers because they run in reverse;
- tight gaps of one or two intervening days use the nearest hard contacts
  globally, independently of planner scope. Wider spans use normal adjacency;
- bad explicit canonical stamps fail loudly instead of becoming a second source
  of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Hashable, Iterable, Mapping, Sequence


class LoadClass(str, Enum):
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
    COEXISTABLE = "coexistable"
    PHYSICAL = "physical"
    EXCLUSIVE_PHYSICAL = "exclusive_physical"


class PlacementDirective(str, Enum):
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
    # Always the nearest global pair; scope must not hide a tighter hard gap.
    hard_contact_gap_intervening_days: int | None


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
# Canonical contact/combat-load vocabulary. This is the single source of truth
# for "which load classes are contact"; the shared adapter (calendar_context) and
# the final governor (calendar_integrity) import this instead of redefining it, so
# the set can never drift between the pre-insertion filler view and the governor.
CONTACT_LOAD_CLASSES = frozenset(
    {LoadClass.TECHNICAL_CONTACT, LoadClass.REDUCED_CONTACT, LoadClass.HARD_CONTACT}
)
_MEANINGFUL_LOADS = frozenset(
    {LoadClass.MEANINGFUL_STRENGTH, LoadClass.MEANINGFUL_CONDITIONING}
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
    {"technical_shadow_rhythm", "footwork_walkthrough", "movement_quality"}
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
_LOW_LOAD_ALACTIC_ROLE_KEYS = frozenset(
    {"alactic_support_day", "alactic_coordination_day"}
)
_NEURAL_ALACTIC_ROLE_KEYS = frozenset(
    {"alactic_speed_day", "alactic_sharpness_day"}
)
_TECHNICAL_CONTACT_ROLE_KEYS = frozenset(
    {"technical_touch_day", "light_combat_day"}
)
_DAY_EXCLUSIVE_STRESSOR_ROLE_KEYS = frozenset(
    {
        "strength_touch_day",
        "neural_primer_day",
        "alactic_sharpness_day",
        "light_fight_pace_touch_day",
    }
)

# Known keys whose category is stable enough to derive semantics even if a
# compatibility caller omitted ``category``. This prevents an explicit stamp from
# taking ownership simply because one redundant field was missing.
_KNOWN_STRENGTH_ROLE_KEYS = frozenset(
    {"strength_touch_day", "neural_primer_day", "small_strength_touch_day"}
)
_KNOWN_CONDITIONING_ROLE_KEYS = frozenset(
    {
        "alactic_speed_day",
        "alactic_sharpness_day",
        "alactic_support_day",
        "alactic_coordination_day",
        "light_fight_pace_touch_day",
    }
)


def _enum_value(enum_type: type[Enum], value: Any):
    if isinstance(value, enum_type):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    try:
        return enum_type(text)
    except ValueError:
        return None


def _explicit_enum(mapping: Mapping[str, Any], key: str, enum_type: type[Enum]):
    raw = mapping.get(key)
    if raw is None or not str(raw).strip():
        return None
    parsed = _enum_value(enum_type, raw)
    if parsed is None:
        raise ValueError(f"Invalid {key}: {raw!r}")
    return parsed


def _default_occupancy(load_class: LoadClass) -> DayOccupancy:
    if load_class in {LoadClass.OFF, LoadClass.ZERO_LOAD}:
        return DayOccupancy.COEXISTABLE
    if load_class in CONTACT_LOAD_CLASSES:
        return DayOccupancy.EXCLUSIVE_PHYSICAL
    return DayOccupancy.PHYSICAL


def _validate_profile_compatibility(
    load_class: LoadClass, occupancy: DayOccupancy
) -> None:
    if load_class in {LoadClass.OFF, LoadClass.ZERO_LOAD}:
        if occupancy is not DayOccupancy.COEXISTABLE:
            raise ValueError("Off/zero-load work must use coexistable occupancy.")
        return
    if load_class in CONTACT_LOAD_CLASSES:
        if occupancy is not DayOccupancy.EXCLUSIVE_PHYSICAL:
            raise ValueError("Contact load must own an exclusive physical slot.")
        return
    if load_class is not LoadClass.RECOVERY_ONLY and occupancy is DayOccupancy.COEXISTABLE:
        raise ValueError("Physical training load cannot be stamped as coexistable support.")


def _profile(
    load_class: LoadClass, occupancy: DayOccupancy | None = None
) -> CalendarLoadProfile:
    occupancy = occupancy or _default_occupancy(load_class)
    _validate_profile_compatibility(load_class, occupancy)
    return CalendarLoadProfile(load_class=load_class, occupancy=occupancy)


def _resolved_contact_class(entry: Mapping[str, Any]) -> LoadClass | None:
    effective = _CONTACT_EFFECTIVE_LOAD_TO_CLASS.get(
        str(entry.get("effective_load") or "").strip().lower()
    )
    status = _CONTACT_STATUS_TO_CLASS.get(
        str(entry.get("status") or "").strip().lower()
    )
    if effective is not None and status is not None and effective is not status:
        raise ValueError(
            "Resolved contact fields disagree: effective_load and status map to different contact classes."
        )
    return effective or status


def contact_load_profile(entry: Mapping[str, Any] | None) -> CalendarLoadProfile | None:
    if not isinstance(entry, Mapping):
        return None

    resolved = _resolved_contact_class(entry)
    explicit_load = _explicit_enum(entry, "calendar_load_class", LoadClass)
    explicit_occupancy = _explicit_enum(
        entry, "calendar_day_occupancy", DayOccupancy
    )

    if explicit_load is not None and explicit_load not in CONTACT_LOAD_CLASSES and explicit_load is not LoadClass.OFF:
        raise ValueError("Contact calendar_load_class must be a contact class or off.")
    if resolved is not None and explicit_load is not None and resolved is not explicit_load:
        raise ValueError("calendar_load_class conflicts with resolved sparring contact state.")

    load_class = resolved or explicit_load
    if load_class is None:
        if explicit_occupancy is not None:
            raise ValueError("calendar_day_occupancy requires resolved contact/load class.")
        return None

    canonical = _profile(load_class)
    if explicit_occupancy is not None and explicit_occupancy is not canonical.occupancy:
        raise ValueError("calendar_day_occupancy conflicts with contact ownership semantics.")
    return canonical


def contact_load_class(entry: Mapping[str, Any] | None) -> LoadClass | None:
    profile = contact_load_profile(entry)
    return profile.load_class if profile else None


def is_effective_hard_contact(entry: Mapping[str, Any] | None) -> bool:
    return contact_load_class(entry) is LoadClass.HARD_CONTACT


def _exclusive_if_needed(
    role_key: str, profile: CalendarLoadProfile
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
            return _profile(LoadClass.RECOVERY_ONLY)
        if max_sets == 1:
            return _profile(LoadClass.NEURAL_MICRODOSE)
        return _profile(LoadClass.MEANINGFUL_STRENGTH)

    if str(role.get("role_key") or "").strip().lower() == "small_strength_touch_day":
        return _profile(LoadClass.NEURAL_MICRODOSE)
    return _profile(LoadClass.MEANINGFUL_STRENGTH)


def _conditioning_role_profile(role: Mapping[str, Any]) -> CalendarLoadProfile:
    role_key = str(role.get("role_key") or "").strip().lower()
    system = str(role.get("preferred_system") or "").strip().lower()
    stress_class = str(role.get("stress_class") or "").strip().lower()
    cost_class = str(role.get("cost_class") or "").strip().lower()
    governance = role.get("governance") if isinstance(role.get("governance"), Mapping) else {}
    meaningful = role.get("meaningful_stress")
    if meaningful is None:
        meaningful = governance.get("meaningful_stress")

    if role.get("counts_toward_conditioning_cap") is False or role.get("late_camp_role_morph") is True:
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if role.get("recovery_compatible") and system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if meaningful is False and system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if stress_class == "support" and cost_class == "low" and system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)

    # Current late-fight roles explicitly stamp meaningful/medium cost. Preserve
    # that before applying normal-camp low-noise alactic semantics.
    if meaningful is True or stress_class == "meaningful_stress" or cost_class in {"medium", "high"}:
        return _profile(LoadClass.MEANINGFUL_CONDITIONING)

    if role_key in _LOW_LOAD_AEROBIC_ROLE_KEYS or system == "aerobic":
        return _profile(LoadClass.LOW_LOAD_AEROBIC)
    if role_key in _LOW_LOAD_ALACTIC_ROLE_KEYS:
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    if role_key in _NEURAL_ALACTIC_ROLE_KEYS or system in {"alactic", "atp-pcr", "atp_pcr"}:
        return _profile(LoadClass.NEURAL_MICRODOSE)
    if system == "glycolytic":
        return _profile(LoadClass.MEANINGFUL_CONDITIONING)
    return _profile(LoadClass.MEANINGFUL_CONDITIONING)


def _derived_role_profile(role: Mapping[str, Any]) -> CalendarLoadProfile | None:
    role_key = str(role.get("role_key") or "").strip().lower()
    category = str(role.get("category") or "").strip().lower()
    if not category and role_key in _KNOWN_STRENGTH_ROLE_KEYS:
        category = "strength"
    elif not category and role_key in _KNOWN_CONDITIONING_ROLE_KEYS:
        category = "conditioning"

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
    governance = role.get("governance") if isinstance(role.get("governance"), Mapping) else {}
    meaningful = role.get("meaningful_stress")
    if meaningful is None:
        meaningful = governance.get("meaningful_stress")
    if meaningful is False and cost_class == "low":
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    if stress_class == "support" and cost_class == "low":
        return _profile(LoadClass.LOW_LOAD_PHYSICAL)
    return None


def _reconcile_role_stamp(
    role: Mapping[str, Any], derived: CalendarLoadProfile | None
) -> CalendarLoadProfile | None:
    explicit_load = _explicit_enum(role, "calendar_load_class", LoadClass)
    explicit_occupancy = _explicit_enum(
        role, "calendar_day_occupancy", DayOccupancy
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
    if explicit_load in CONTACT_LOAD_CLASSES:
        raise ValueError("Only contact-owned roles may carry a contact calendar_load_class.")
    return _profile(explicit_load, explicit_occupancy)


def role_load_profile(role: Mapping[str, Any] | None) -> CalendarLoadProfile | None:
    if not isinstance(role, Mapping):
        return None

    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key == "hard_sparring_day":
        return contact_load_profile(role)

    if role_key in _TECHNICAL_CONTACT_ROLE_KEYS:
        canonical = _profile(LoadClass.TECHNICAL_CONTACT)
        explicit_load = _explicit_enum(role, "calendar_load_class", LoadClass)
        explicit_occupancy = _explicit_enum(
            role, "calendar_day_occupancy", DayOccupancy
        )
        if explicit_load is not None and explicit_load is not canonical.load_class:
            raise ValueError("Technical contact role has a conflicting calendar_load_class stamp.")
        if explicit_occupancy is not None and explicit_occupancy is not canonical.occupancy:
            raise ValueError("Technical contact role has conflicting day occupancy.")
        return canonical

    return _reconcile_role_stamp(role, _derived_role_profile(role))


def role_load_class(role: Mapping[str, Any] | None) -> LoadClass | None:
    profile = role_load_profile(role)
    return profile.load_class if profile else None


def build_calendar_context(
    candidate_position: int,
    events: Sequence[CalendarEvent] | Iterable[CalendarEvent],
    *,
    candidate_scope: Hashable | None = None,
) -> CalendarCollisionContext:
    position = int(candidate_position)
    snapshot = tuple(events)
    for event in snapshot:
        if not isinstance(event, CalendarEvent):
            raise TypeError("events must contain CalendarEvent instances")
        if not isinstance(event.profile, CalendarLoadProfile):
            raise TypeError("CalendarEvent.profile must be CalendarLoadProfile")
        _validate_profile_compatibility(event.profile.load_class, event.profile.occupancy)

    same_day = tuple(event.profile for event in snapshot if int(event.position) == position)
    hard_positions = sorted(
        {
            int(event.position)
            for event in snapshot
            if event.profile.load_class is LoadClass.HARD_CONTACT
        }
    )
    before = [p for p in hard_positions if p < position]
    after = [p for p in hard_positions if p > position]
    previous_distance = position - before[-1] if before else None
    next_distance = after[0] - position if after else None

    between = False
    scoped_previous_distance = None
    scoped_next_distance = None
    if candidate_scope is not None:
        scoped_hard = sorted(
            {
                int(event.position)
                for event in snapshot
                if event.collision_scope == candidate_scope
                and event.profile.load_class is LoadClass.HARD_CONTACT
            }
        )
        scoped_before = [p for p in scoped_hard if p < position]
        scoped_after = [p for p in scoped_hard if p > position]
        scoped_previous_distance = position - scoped_before[-1] if scoped_before else None
        scoped_next_distance = scoped_after[0] - position if scoped_after else None
        between = (
            scoped_previous_distance is not None
            and scoped_next_distance is not None
        )

    return CalendarCollisionContext(
        candidate_position=position,
        candidate_scope=candidate_scope,
        same_day_profiles=same_day,
        previous_hard_distance=previous_distance,
        next_hard_distance=next_distance,
        between_effective_hard_contacts=between,
        hard_contact_gap_intervening_days=(
            previous_distance + next_distance - 1
            if previous_distance is not None and next_distance is not None
            else None
        ),
    )


def _decision(
    directive: PlacementDirective, reason_code: str, reason: str
) -> PlacementDecision:
    return PlacementDecision(directive, reason_code, reason)


def _same_day_decision(
    candidate: CalendarLoadProfile,
    existing: tuple[CalendarLoadProfile, ...],
) -> PlacementDecision | None:
    if not existing:
        return None

    existing_contact = any(p.load_class in CONTACT_LOAD_CLASSES for p in existing)
    existing_exclusive = any(
        p.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL for p in existing
    )
    existing_physical = any(
        p.occupancy in {DayOccupancy.PHYSICAL, DayOccupancy.EXCLUSIVE_PHYSICAL}
        for p in existing
    )

    if candidate.load_class in CONTACT_LOAD_CLASSES and existing_physical:
        return _decision(
            PlacementDirective.FORBID,
            "contact_candidate_physical_conflict",
            "Do not add contact to a day that already contains a physical/contact session.",
        )
    if candidate.occupancy is DayOccupancy.EXCLUSIVE_PHYSICAL and existing_physical:
        return _decision(
            PlacementDirective.FORBID,
            "exclusive_physical_slot_conflict",
            "This candidate owns an exclusive physical slot and the day is already physically occupied.",
        )
    if existing_exclusive and candidate.occupancy is not DayOccupancy.COEXISTABLE:
        return _decision(
            PlacementDirective.FORBID,
            "contact_day_extra_physical_conflict"
            if existing_contact
            else "exclusive_day_extra_physical_conflict",
            "An exclusive physical/contact session owns this day; only coexistable support may be added.",
        )
    return None


def evaluate_calendar_candidate(
    candidate: CalendarLoadProfile,
    context: CalendarCollisionContext,
) -> PlacementDecision:
    if not isinstance(candidate, CalendarLoadProfile):
        raise TypeError("candidate must be CalendarLoadProfile")
    _validate_profile_compatibility(candidate.load_class, candidate.occupancy)

    same_day = _same_day_decision(candidate, context.same_day_profiles)
    if same_day:
        return same_day

    load = candidate.load_class
    if load is LoadClass.HARD_CONTACT and (
        context.previous_hard_distance == 1 or context.next_hard_distance == 1
    ):
        return _decision(
            PlacementDirective.FORBID,
            "consecutive_effective_hard_contact",
            "Back-to-back effective hard-contact days are not legal neighbours.",
        )

    gap_days = context.hard_contact_gap_intervening_days
    if gap_days is not None and gap_days <= 2:
        if load in _SANDWICH_ALLOW_LOADS:
            return _decision(
                PlacementDirective.ALLOW,
                "between_hard_contacts_low_cost",
                "Tight between-contact days prefer off, zero-load, recovery, or low-aerobic support.",
            )
        if load is LoadClass.LOW_LOAD_PHYSICAL:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_low_load_physical",
                "Low-load movement may survive only when a cleaner recovery/aerobic option is unavailable.",
            )
        if load is LoadClass.TECHNICAL_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_technical_contact",
                "Technical-only contact should lose to a lower-cost option between hard contacts.",
            )
        if load is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_reduced_contact",
                "Reduced contact retains residual collision cost between hard contacts.",
            )
        if load is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_neural_microdose",
                "A true neural microdose may survive a tight contact gap only when no cleaner slot exists.",
            )
        if gap_days == 2 and load is LoadClass.MEANINGFUL_STRENGTH:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "between_hard_contacts_managed_strength",
                "Managed strength may survive a two-day contact gap when no cleaner slot exists.",
            )
        return _decision(
            PlacementDirective.FORBID,
            "between_hard_contacts_tight_gap_meaningful_stress",
            "Do not place meaningful S&C or additional hard contact in this tight contact gap.",
        )

    if context.previous_hard_distance == 1:
        if load in _MEANINGFUL_LOADS:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "post_hard_contact_managed_stress",
                "Meaningful S&C after hard contact should lose to a cleaner slot.",
            )
        if load is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "post_hard_contact_microdose",
                "A true neural microdose survives only when no cleaner slot exists.",
            )
        if load is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "post_hard_contact_reduced_contact",
                "Reduced contact retains collision cost immediately after hard contact.",
            )
        return _decision(
            PlacementDirective.ALLOW,
            "post_hard_contact_low_cost",
            "Technical, recovery, tactical, or low-cost work may follow hard contact.",
        )

    if context.next_hard_distance == 1:
        if load in _MEANINGFUL_LOADS or load is LoadClass.NEURAL_MICRODOSE:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "pre_hard_contact_managed_stress",
                "Meaningful/neural work before hard contact should lose to a cleaner slot.",
            )
        if load is LoadClass.REDUCED_CONTACT:
            return _decision(
                PlacementDirective.DEPRIORITIZE,
                "pre_hard_contact_reduced_contact",
                "Reduced contact carries residual collision cost before hard contact.",
            )
        return _decision(
            PlacementDirective.ALLOW,
            "pre_hard_contact_low_cost",
            "Low-cost or technical work may precede hard contact.",
        )

    return _decision(
        PlacementDirective.ALLOW,
        "no_calendar_collision",
        "No day-ownership or hard-contact spacing rule blocks this candidate.",
    )


def evaluate_candidate_at_position(
    candidate: CalendarLoadProfile,
    *,
    candidate_position: int,
    events: Sequence[CalendarEvent] | Iterable[CalendarEvent],
    candidate_scope: Hashable | None = None,
) -> PlacementDecision:
    return evaluate_calendar_candidate(
        candidate,
        build_calendar_context(
            candidate_position, events, candidate_scope=candidate_scope
        ),
    )


# Canonical legality tier a placement owner ranks candidates by. Lower is better;
# ``FORBID`` is the excluded tier. This is the one shared ordering the contract
# recommends — ALLOW preferred, DEPRIORITIZE legal fallback, FORBID excluded — so
# every owner ranks the same way and none invents its own tier numbers.
_PLACEMENT_RANK = {
    PlacementDirective.ALLOW: 0,
    PlacementDirective.DEPRIORITIZE: 1,
    PlacementDirective.FORBID: 2,
}


def placement_rank(decision: PlacementDecision | PlacementDirective) -> int:
    """Legality tier for a decision/directive: ALLOW=0, DEPRIORITIZE=1, FORBID=2."""
    directive = decision.directive if isinstance(decision, PlacementDecision) else decision
    return _PLACEMENT_RANK[directive]


__all__ = [
    "CONTACT_LOAD_CLASSES",
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
    "placement_rank",
    "role_load_class",
    "role_load_profile",
]
