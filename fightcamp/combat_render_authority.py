"""Canonical athlete-facing copy for declared combat days.

Declared combat days (hard sparring and declared light combat / technical) are
*coach-owned*: the athlete owns the contact work and the app must never author
its dose. What the app does own is the exact wording of the card that tells the
athlete the day exists and what its resolved contact status is.

Before this module that wording lived in four places — the Stage 2 prompt, the
Stage 2 repair prompt, the late-fight visible-calendar projection and the
structured-plan sparring reconciler — each with its own copy of the strings and,
worse, its own idea of how to turn *declared* hard sparring into *resolved*
contact status. This module is the single owner of both:

* :func:`resolve_declared_contact_load` — resolved truth (never raw declared
  days), shared by the structured-plan reconciler and the render authority.
* :func:`canonical_combat_render` — the exact label + note pair, or ``None``
  when the resolved state is not safe to server-render.

Fail-closed rules baked in here:

* A blocked / no-contact (medical) day never renders canonical combat copy. The
  server does not invent medical wording; the day is left to the layers that own
  safety messaging.
* A deloaded ("reduced") hard day is *not* canonically renderable either: it is
  still hard contact, but the reason/coach note is part of its meaning and this
  module will not flatten it into the plain hard-sparring card.
* Nothing here emits round counts, RPE, work:rest or any S&C prescription.
"""

from __future__ import annotations

from typing import Any

from .declared_combat_ownership import (
    LIGHT_COMBAT_ATHLETE_FACING_LABEL,
    LIGHT_COMBAT_ROLE_KEY,
    is_declared_light_combat_role,
)
from .sparring_dose_planner import contact_safety_reasons, hard_sparring_cutoff


CANONICAL_HARD_SPARRING_LABEL = "Hard sparring — controlled hard contact"
CANONICAL_HARD_SPARRING_BAN_LABEL = "Technical-only combat"
# Two distinct notes: a hard-sparring day and a converted technical-only day must never
# share wording, or a technical-only card would tell the athlete to spar hard. Both
# keep the "no extra S&C" + "freshness priority" tokens the validator's minimal
# coach-owned render check looks for.
CANONICAL_HARD_SPARRING_NOTE = "Your declared hard-sparring/contact session — no extra S&C. Keep freshness priority."
CANONICAL_TECHNICAL_ONLY_NOTE = "Technical-only contact today — no hard sparring and no extra S&C. Keep freshness priority."

CANONICAL_LIGHT_COMBAT_LABEL = LIGHT_COMBAT_ATHLETE_FACING_LABEL
CANONICAL_LIGHT_COMBAT_NOTE = (
    "Your declared light-combat / technical session. Keep it as scheduled."
)

HARD_SPARRING_ROLE_KEY = "hard_sparring_day"

_TECHNICAL_BAN_REASON_CODES = {"d14_hard_sparring_ban", "d17_hard_sparring_ban"}


def _reason_codes(role: dict[str, Any]) -> set[str]:
    raw = role.get("hard_sparring_reason_codes")
    if not isinstance(raw, (list, tuple)):
        return set()
    return {str(code).strip() for code in raw if str(code).strip()}


def is_declared_hard_sparring_role(role: dict[str, Any] | None) -> bool:
    """Whether ``role`` is a declared hard-sparring day (converted or not)."""
    if not isinstance(role, dict):
        return False
    return (
        str(role.get("role_key") or "").strip() == HARD_SPARRING_ROLE_KEY
        or str(role.get("downgraded_from_role_key") or "").strip() == HARD_SPARRING_ROLE_KEY
    )


def is_declared_combat_role(role: dict[str, Any] | None) -> bool:
    """Whether ``role`` is any coach-owned declared combat day."""
    return is_declared_hard_sparring_role(role) or is_declared_light_combat_role(role)


def resolve_declared_contact_load(
    role: dict[str, Any],
    *,
    d_day: int | None = None,
    athlete_snapshot: dict[str, Any] | None = None,
) -> str:
    """Effective contact load for a declared ``hard_sparring_day`` role.

    ``role_key`` records only that the day was *declared* hard — never what the
    sparring dose planner did with it. The late-fight planner marks a converted
    day with ``downgraded`` / ``downgraded_to_role_key``, while the normal-camp
    role map carries the planner's verdict in ``hard_sparring_status`` /
    ``hard_sparring_reason_codes``. Both must be read, or a normal-camp day
    inside the D-17 ban renders as "Hard sparring".

    Returns one of ``"none"`` (blocked), ``"technical"``, ``"reduced"`` or
    ``"hard"``.
    """
    if contact_safety_reasons(athlete_snapshot or {}) or role.get("hard_sparring_status") == "blocked":
        return "none"
    if bool(role.get("downgraded")) or str(
        role.get("downgraded_to_role_key") or ""
    ).strip() == "technical_touch_day":
        return "technical"

    status = str(role.get("hard_sparring_status") or "").strip()
    if status == "convert_to_technical_suggested" or _reason_codes(role) & _TECHNICAL_BAN_REASON_CODES:
        return "technical"
    if (
        status == "deload_suggested"
        or str(role.get("hard_sparring_class") or "").strip() == "managed_hard"
    ):
        return "reduced"
    if contact_safety_reasons(athlete_snapshot or {}):
        return "none"
    if d_day is not None and 0 <= d_day <= hard_sparring_cutoff(athlete_snapshot or {}):
        return "technical"
    return "hard"


def _hard_sparring_state_is_resolved(role: dict[str, Any]) -> bool:
    """Whether Stage 1 actually recorded a contact verdict for this day.

    A declared hard day with no ``hard_sparring_status``, no conversion flag and
    no reason codes is an *unresolved* combat state: the planner never ran its
    dose decision over it. Rendering the plain hard-sparring card for it would be
    the server asserting hard contact it was never told to assert, so it is
    treated as non-authoritative.
    """
    if str(role.get("hard_sparring_status") or "").strip():
        return True
    if bool(role.get("downgraded")) or str(role.get("downgraded_to_role_key") or "").strip():
        return True
    return bool(_reason_codes(role))


def canonical_combat_render(
    role: dict[str, Any],
    *,
    d_day: int | None = None,
    athlete_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Exact athlete-facing label + note for a declared combat day.

    ``None`` means "the server does not own this day's wording": an unresolved
    hard-sparring state, a deloaded hard day whose coach note carries meaning, or
    a blocked/no-contact medical state. Those fail closed rather than being given
    invented copy.
    """
    if not isinstance(role, dict):
        return None

    if is_declared_light_combat_role(role):
        return {
            "contact_load": "technical",
            "athlete_facing_label": CANONICAL_LIGHT_COMBAT_LABEL,
            "note": CANONICAL_LIGHT_COMBAT_NOTE,
            "role_key": LIGHT_COMBAT_ROLE_KEY,
        }

    if not is_declared_hard_sparring_role(role):
        return None
    if not _hard_sparring_state_is_resolved(role):
        return None

    load = resolve_declared_contact_load(
        role, d_day=d_day, athlete_snapshot=athlete_snapshot
    )
    if load == "hard":
        return {
            "contact_load": "hard",
            "athlete_facing_label": CANONICAL_HARD_SPARRING_LABEL,
            "note": CANONICAL_HARD_SPARRING_NOTE,
            "role_key": HARD_SPARRING_ROLE_KEY,
        }
    if load == "technical":
        return {
            "contact_load": "technical",
            "athlete_facing_label": CANONICAL_HARD_SPARRING_BAN_LABEL,
            "note": CANONICAL_TECHNICAL_ONLY_NOTE,
            "role_key": HARD_SPARRING_ROLE_KEY,
        }
    # "reduced" keeps its coach note; "none" is a medical block. Neither is the
    # server's to phrase.
    return None


__all__ = [
    "CANONICAL_HARD_SPARRING_LABEL",
    "CANONICAL_HARD_SPARRING_BAN_LABEL",
    "CANONICAL_HARD_SPARRING_NOTE",
    "CANONICAL_TECHNICAL_ONLY_NOTE",
    "CANONICAL_LIGHT_COMBAT_LABEL",
    "CANONICAL_LIGHT_COMBAT_NOTE",
    "HARD_SPARRING_ROLE_KEY",
    "canonical_combat_render",
    "is_declared_combat_role",
    "is_declared_hard_sparring_role",
    "resolve_declared_contact_load",
]
