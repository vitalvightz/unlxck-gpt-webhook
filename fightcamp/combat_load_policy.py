"""Canonical calendar-load vocabulary and collision-legality queries.

This module is the shared policy seam described by PLANNER_ARCHITECTURE_CONTRACT.md.
It is intentionally not wired into the existing allocators yet. Importing this
module has no planner side effects and current production output is unchanged.

The goal of this first increment is to give normal-camp placement, late-fight
placement, fillers, and the future final calendar integrity pass one vocabulary
for answering the same question: "is this load legal around effective hard
contact?"

Important boundary:
- ``sparring_dose_planner`` remains the source of truth for resolving declared
  contact into effective hard / technical / reduced / suppressed contact.
- this module consumes that resolved state; it does not re-decide sparring dose.
- renderers and labels are never inputs to legality decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class LoadClass(str, Enum):
    """Small semantic vocabulary used by calendar collision policy."""

    OFF = "off"
    ZERO_LOAD_TACTICAL = "zero_load_tactical"
    TECHNICAL_CONTACT = "technical_contact"
    LOW_LOAD_SUPPORT = "low_load_support"
    NEURAL_MICRODOSE = "neural_microdose"
    MEANINGFUL_STRENGTH = "meaningful_strength"
    MEANINGFUL_CONDITIONING = "meaningful_conditioning"
    HARD_CONTACT = "hard_contact"


class CollisionRelation(str, Enum):
    """Candidate day's relationship to an effective hard-contact day."""

    SAME_DAY = "same_day"
    DAY_AFTER = "day_after"
    DAY_BEFORE = "day_before"
    SANDWICHED = "sandwiched"
    UNRELATED = "unrelated"


class Legality(str, Enum):
    ALLOWED = "allowed"
    ALLOWED_WITH_CAUTION = "allowed_with_caution"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class LegalityDecision:
    verdict: Legality
    reason_code: str
    reason: str

    @property
    def allowed(self) -> bool:
        return self.verdict is not Legality.FORBIDDEN


_MEANINGFUL_LOADS = frozenset(
    {
        LoadClass.MEANINGFUL_STRENGTH,
        LoadClass.MEANINGFUL_CONDITIONING,
    }
)

_LOW_COST_LOADS = frozenset(
    {
        LoadClass.OFF,
        LoadClass.ZERO_LOAD_TACTICAL,
        LoadClass.LOW_LOAD_SUPPORT,
    }
)

_CONTACT_EFFECTIVE_LOAD_TO_CLASS = {
    "hard": LoadClass.HARD_CONTACT,
    "technical": LoadClass.TECHNICAL_CONTACT,
    # Reduced contact is no longer an effective hard-contact exposure. Keep it
    # in the contact bucket rather than pretending it is generic S&C support.
    "reduced": LoadClass.TECHNICAL_CONTACT,
    "none": LoadClass.OFF,
    "suppressed": LoadClass.OFF,
}

_CONTACT_STATUS_TO_CLASS = {
    "hard_as_planned": LoadClass.HARD_CONTACT,
    "convert_to_technical_suggested": LoadClass.TECHNICAL_CONTACT,
    "deload_suggested": LoadClass.TECHNICAL_CONTACT,
    "suppressed": LoadClass.OFF,
}


def contact_load_class(entry: Mapping[str, Any] | None) -> LoadClass | None:
    """Translate *resolved* sparring-plan state into the shared load vocabulary.

    ``None`` means the record does not contain enough canonical contact state to
    classify safely. The function deliberately does not infer from athlete-facing
    labels or raw declared weekdays.
    """

    if not isinstance(entry, Mapping):
        return None

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


def relation_to_hard_contact(
    *,
    same_day_loads: Iterable[LoadClass] = (),
    previous_day_loads: Iterable[LoadClass] = (),
    next_day_loads: Iterable[LoadClass] = (),
) -> CollisionRelation:
    """Resolve the strongest hard-contact relationship for a candidate day.

    Technical/reduced contact is intentionally ignored here: only
    ``HARD_CONTACT`` creates hard-contact collision pressure.
    """

    same = set(same_day_loads)
    previous = set(previous_day_loads)
    following = set(next_day_loads)

    if LoadClass.HARD_CONTACT in same:
        return CollisionRelation.SAME_DAY
    if LoadClass.HARD_CONTACT in previous and LoadClass.HARD_CONTACT in following:
        return CollisionRelation.SANDWICHED
    if LoadClass.HARD_CONTACT in previous:
        return CollisionRelation.DAY_AFTER
    if LoadClass.HARD_CONTACT in following:
        return CollisionRelation.DAY_BEFORE
    return CollisionRelation.UNRELATED


def evaluate_hard_contact_collision(
    candidate: LoadClass,
    relation: CollisionRelation,
) -> LegalityDecision:
    """Evaluate one candidate load against the shared hard-contact contract.

    This is a policy query only. It does not relocate, suppress, or mutate a
    session. Those actions remain allocator/integrity-layer responsibilities.

    Contract encoded here:
    - effective hard contact owns its physical day;
    - zero-load tactical work may coexist with hard contact;
    - the day after hard contact contains no meaningful S&C;
    - a day between two hard contacts is low-load/support by default;
    - meaningful S&C before hard contact is possible but must be treated as a
      deliberate collision choice rather than an unconstrained preferred slot;
    - technical/reduced contact does not create hard-load pressure by itself.
    """

    if relation is CollisionRelation.UNRELATED:
        return LegalityDecision(
            Legality.ALLOWED,
            "no_effective_hard_contact_collision",
            "No effective hard-contact collision applies to this candidate day.",
        )

    if relation is CollisionRelation.SAME_DAY:
        if candidate in {LoadClass.OFF, LoadClass.ZERO_LOAD_TACTICAL, LoadClass.HARD_CONTACT}:
            return LegalityDecision(
                Legality.ALLOWED,
                "hard_contact_day_owner_or_zero_load",
                "Effective hard contact owns the physical day; only the contact itself or zero-load work may coexist.",
            )
        return LegalityDecision(
            Legality.FORBIDDEN,
            "hard_contact_same_day_physical_conflict",
            "Do not schedule programmed physical work on an effective hard-contact day.",
        )

    if relation is CollisionRelation.DAY_AFTER:
        if candidate in _MEANINGFUL_LOADS:
            return LegalityDecision(
                Legality.FORBIDDEN,
                "post_hard_contact_meaningful_stress",
                "The day immediately after effective hard contact cannot carry meaningful S&C.",
            )
        if candidate is LoadClass.NEURAL_MICRODOSE:
            return LegalityDecision(
                Legality.ALLOWED_WITH_CAUTION,
                "post_hard_contact_microdose_only",
                "A neural microdose may survive only if it is genuinely tiny and recovery-compatible.",
            )
        if candidate is LoadClass.HARD_CONTACT:
            return LegalityDecision(
                Legality.FORBIDDEN,
                "consecutive_effective_hard_contact",
                "Back-to-back effective hard-contact days are not legal calendar neighbours.",
            )
        return LegalityDecision(
            Legality.ALLOWED,
            "post_hard_contact_low_cost",
            "Technical, recovery, tactical, or other low-cost work may follow hard contact.",
        )

    if relation is CollisionRelation.SANDWICHED:
        if candidate in _LOW_COST_LOADS:
            return LegalityDecision(
                Legality.ALLOWED,
                "sandwiched_low_cost_support",
                "A day between effective hard contacts is reserved for off, zero-load, or low-load support work.",
            )
        if candidate is LoadClass.TECHNICAL_CONTACT:
            return LegalityDecision(
                Legality.ALLOWED_WITH_CAUTION,
                "sandwiched_technical_contact",
                "Technical-only contact may fit between hard contacts when it remains genuinely low-contact and low-fatigue.",
            )
        return LegalityDecision(
            Legality.FORBIDDEN,
            "sandwiched_meaningful_or_hard_stress",
            "Do not place meaningful S&C, neural stress, or additional hard contact between two effective hard-contact days.",
        )

    # DAY_BEFORE is intentionally asymmetric with DAY_AFTER. A useful strength
    # exposure can precede hard sparring when the week has no cleaner option,
    # but it must not be treated as a neutral slot.
    if relation is CollisionRelation.DAY_BEFORE:
        if candidate is LoadClass.HARD_CONTACT:
            return LegalityDecision(
                Legality.FORBIDDEN,
                "consecutive_effective_hard_contact",
                "Back-to-back effective hard-contact days are not legal calendar neighbours.",
            )
        if candidate in _MEANINGFUL_LOADS or candidate is LoadClass.NEURAL_MICRODOSE:
            return LegalityDecision(
                Legality.ALLOWED_WITH_CAUTION,
                "pre_hard_contact_managed_stress",
                "Meaningful or neural work before hard contact is a managed collision and should lose to a cleaner slot when available.",
            )
        return LegalityDecision(
            Legality.ALLOWED,
            "pre_hard_contact_low_cost",
            "Low-cost or technical work may precede effective hard contact.",
        )

    raise ValueError(f"Unsupported collision relation: {relation!r}")


def evaluate_calendar_candidate(
    candidate: LoadClass,
    *,
    same_day_loads: Iterable[LoadClass] = (),
    previous_day_loads: Iterable[LoadClass] = (),
    next_day_loads: Iterable[LoadClass] = (),
) -> LegalityDecision:
    """Convenience query for future allocator/filler/integrity call sites."""

    relation = relation_to_hard_contact(
        same_day_loads=same_day_loads,
        previous_day_loads=previous_day_loads,
        next_day_loads=next_day_loads,
    )
    return evaluate_hard_contact_collision(candidate, relation)


__all__ = [
    "CollisionRelation",
    "Legality",
    "LegalityDecision",
    "LoadClass",
    "contact_load_class",
    "evaluate_calendar_candidate",
    "evaluate_hard_contact_collision",
    "is_effective_hard_contact",
    "relation_to_hard_contact",
]
