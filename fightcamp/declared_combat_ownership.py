"""Shared ownership of declared coach-owned light-combat / technical days.

Declared light-combat days (``support_work_days`` / ``technical_skill_days``) are
coach-owned, immutable calendar context — exactly like declared hard-sparring
days. This module is the single definition, consumed by *both* placement owners
(normal camp: :mod:`stage2_role_map`; D-13 inward: :mod:`stage2_payload_late_fight`),
of:

- which weekdays the athlete declared as light combat, and
- the canonical coach-owned ``light_combat_day`` role stamp locked onto them.

The invariant it exists to protect:

    declared light combat
        -> mandatory coach-owned role on that exact weekday
        -> cannot be dropped / replaced / moved
        -> planner considers any app-owned S&C for the same day
        -> combat_load_policy: LEGAL -> stack ; ILLEGAL -> move/drop the S&C
        -> the light-combat slot remains

This module owns *identity only*. It is deliberately **not** a second collision
engine and **not** a second placement engine (see the architecture freeze in
``PLANNER_ARCHITECTURE_CONTRACT.md`` §12). ``light_combat_day`` is classified
TECHNICAL_CONTACT / exclusive-physical by :mod:`combat_load_policy`, which stays
the sole authority on whether app-owned S&C may share a light-combat day. Each
placement owner still generates its own candidate days and queries that shared
legality; this module only hands them one agreed answer to "what is a declared
light-combat day and what coach-owned role sits on it".
"""

from __future__ import annotations

from typing import Any, Iterable

from .normalization import clean_list, ordered_weekdays as _ordered_weekdays


LIGHT_COMBAT_ROLE_KEY = "light_combat_day"

# The athlete-facing name used for the declared light-combat / technical slot in
# the countdown calendar. Kept here so both owners describe the same appointment.
LIGHT_COMBAT_ATHLETE_FACING_LABEL = "Light Combat / Technical"

LIGHT_COMBAT_SELECTION_RULE = (
    "Keep the declared light-combat / technical slot fixed on the athlete's stated "
    "day. App-owned S&C may share the day only when the shared combat-load policy "
    "allows it; otherwise move or drop the S&C — never the light-combat slot."
)

LIGHT_COMBAT_DAY_ASSIGNMENT_REASON = (
    "Declared light-combat / technical day is a coach-owned immutable calendar "
    "lock; app-owned S&C yields to it when the combat-load policy forbids sharing "
    "the day."
)


def _normalise_days(values: Iterable[Any] | None) -> list[str]:
    return [
        normalised
        for value in _ordered_weekdays(clean_list(list(values or [])))
        if (normalised := str(value or "").strip().lower())
    ]


def declared_light_combat_weekdays(
    athlete_model: dict[str, Any],
    *,
    training_days: Iterable[Any] | None = None,
    exclude_hard_sparring: bool = True,
) -> list[str]:
    """Ordered, de-duplicated, lower-cased declared light-combat weekdays.

    ``support_work_days`` (falling back to the legacy ``technical_skill_days``)
    are the declared light-combat / technical days.

    - A day the athlete also declared as hard sparring is owned by the
      hard-sparring lock (hard sparring is a strict superset of combat load), so
      it is excluded by default.
    - When ``training_days`` is supplied the result is intersected with it: a
      declared combat day outside the training week has no calendar slot.
    """
    support = _normalise_days(
        athlete_model.get("support_work_days")
        or athlete_model.get("technical_skill_days")
        or []
    )
    hard = set(_normalise_days(athlete_model.get("hard_sparring_days", [])))
    training = (
        set(_normalise_days(training_days)) if training_days is not None else None
    )

    out: list[str] = []
    seen: set[str] = set()
    for day in support:
        if day in seen:
            continue
        if exclude_hard_sparring and day in hard:
            continue
        if training is not None and day not in training:
            continue
        seen.add(day)
        out.append(day)
    return out


def is_declared_light_combat_role(role: dict[str, Any] | None) -> bool:
    """Whether ``role`` is the coach-owned declared light-combat lock."""
    if not isinstance(role, dict):
        return False
    return (
        str(role.get("role_key") or "").strip().lower() == LIGHT_COMBAT_ROLE_KEY
        and bool(role.get("coach_owned"))
    )


def build_declared_light_combat_role(day: str, **overrides: Any) -> dict[str, Any]:
    """Canonical coach-owned, immutable ``light_combat_day`` role for ``day``.

    Returns the weekday-based core shared by both placement owners. Countdown /
    payload specifics (countdown labels, ``session_index``, ``placement_source``,
    the late-fight ``governance`` stamp) are layered on by the caller through
    ``overrides`` so each owner keeps its own downstream contract while the role's
    *identity* — coach-owned, declared-day-locked, technical-contact — stays
    defined in exactly one place.
    """
    day_l = str(day or "").strip().lower()
    # Canonical coach-owned governance shared by both owners. A caller's
    # ``governance`` override is *merged* into this base (not replaced), so every
    # variant carries the same declared_schedule_lock identity plus whatever extra
    # keys that owner needs (e.g. the late-fight ``late_fight_payload`` marker).
    governance: dict[str, Any] = {
        "authority": "declared_schedule_lock",
        "coach_owned": True,
        "locked_day": day_l,
        "suppression_rules": [
            "Declared light-combat days are immutable coach-owned weekly role locks."
        ],
        "hard_suppression_reasons": [],
    }
    governance_override = overrides.pop("governance", None)
    if isinstance(governance_override, dict):
        governance.update(governance_override)

    role: dict[str, Any] = {
        "category": "technical",
        "role_key": LIGHT_COMBAT_ROLE_KEY,
        "preferred_pool": "declared_support_work_days",
        "anchor": "support_day",
        "cost_class": "low",
        "stress_class": "support",
        "scheduled_day_hint": day_l,
        "real_weekday": day_l,
        "coach_owned": True,
        "declared_day_locked": True,
        "placement_basis": "locked",
        "selection_rule": LIGHT_COMBAT_SELECTION_RULE,
        "day_assignment_reason": LIGHT_COMBAT_DAY_ASSIGNMENT_REASON,
        "governance": governance,
    }
    role.update(overrides)
    return role


__all__ = [
    "LIGHT_COMBAT_ROLE_KEY",
    "LIGHT_COMBAT_ATHLETE_FACING_LABEL",
    "LIGHT_COMBAT_SELECTION_RULE",
    "LIGHT_COMBAT_DAY_ASSIGNMENT_REASON",
    "build_declared_light_combat_role",
    "declared_light_combat_weekdays",
    "is_declared_light_combat_role",
]
