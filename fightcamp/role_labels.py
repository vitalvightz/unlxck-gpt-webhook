"""Deterministic ``role_key`` -> athlete-facing session label mapping.

Stage 1 already knows the exact role of every session it schedules
(``primary_strength_day``, ``alactic_sharpness_day``, ``fight_pace_repeatability_day``,
...). Historically only a handful of *converted* roles carried an
``athlete_facing_label``; every other role left the athlete-facing session title
for the Stage 2 LLM to invent. That invention is one of the structural jobs that
makes the finalizer drift and leak internal ``role_key`` tokens into the plan
(validator codes ``internal_render_contract_leak`` / role-key leaks) and forces
the LLM to re-derive titles the planner already determined.

This module makes the title a *deterministic Stage 1 output*. Every session role
gets a clean, coach-readable label that is also recognised by the Stage 2
validator's ``_SESSION_TITLE_HINTS`` so the rendered plan keeps a valid session
heading. The labels are intentionally plain (no overstyled "gimmick" names) so
they survive the validator's overstyled-name checks too.

The mapping is the single source of truth for role titles. As Stage 1 takes over
more of the rendering (and the LLM does less), the same labels can be used to
render the final plan deterministically.
"""

from __future__ import annotations

from typing import Any, Iterable


# Canonical role_key -> athlete-facing label.
#
# Labels are aligned with fightcamp/stage2_validator.py:_SESSION_TITLE_HINTS so a
# session heading built from them is recognised as a real session (not template
# scaffolding). Keep them plain and decisive.
ROLE_LABELS: dict[str, str] = {
    # --- Strength ---------------------------------------------------------
    "primary_strength_day": "Strength",
    "secondary_strength_day": "Strength",
    "structural_strength_day": "Strength",
    "transfer_strength_day": "Strength",
    "neural_plus_strength_day": "Strength",
    "strength_touch_day": "Neural speed touch",
    "small_strength_touch_day": "Neural speed touch",
    "neural_primer_day": "Neural speed touch",
    # --- Aerobic / base conditioning -------------------------------------
    "aerobic_base_day": "Aerobic support",
    "aerobic_support_day": "Aerobic support",
    "aerobic_flush_day": "Rhythm flush",
    "aerobic_coordination_day": "Aerobic support",
    # --- Alactic / speed --------------------------------------------------
    "alactic_sharpness_day": "Freshness primer",
    "alactic_speed_day": "Alactic sharpness",
    "alactic_support_day": "Alactic sharpness",
    "alactic_coordination_day": "Alactic sharpness",
    # --- Glycolytic / fight-pace conditioning ----------------------------
    "fight_pace_repeatability_day": "Fight-pace conditioning",
    "main_fight_pace_day": "Fight-pace conditioning",
    "highest_glycolytic_day": "Fight-pace conditioning",
    "controlled_repeatability_day": "Fight-pace conditioning",
    "light_fight_pace_touch_day": "Rhythm flush",
    "repeatability_support_day": "Conditioning",
    # --- Recovery / tissue / mobility ------------------------------------
    "recovery_reset_day": "Recovery",
    "recovery_only_day": "Recovery",
    "tissue_recovery_day": "Recovery",
    # --- Skill / technical -----------------------------------------------
    "technical_touch_day": "Technical touch",
    # --- Taper / fight week ----------------------------------------------
    "fight_week_freshness_day": "Fight-week freshness",
    "fight_day_protocol": "Fight-day warm-up",
    # --- Coach-owned ------------------------------------------------------
    "hard_sparring_day": "Coach-led sparring",
    "light_combat_day": "Light technical combat",
}


# Roles that are internal/plan markers, not athlete-facing sessions. They must
# never receive a rendered session title.
_NON_SESSION_CATEGORIES = frozenset({"plan", "override", "marker"})
_NON_SESSION_ROLE_KEYS = frozenset(
    {
        "fight_week_override",
    }
)

# role_key suffixes stripped when humanising an unknown key.
_HUMANISE_SUFFIXES = ("_day", "_protocol", "_override")


def humanize_role_key(role_key: str | None) -> str:
    """Best-effort plain label for a role_key with no explicit mapping.

    ``"double_stress_day"`` -> ``"Double Stress"``. Deterministic and safe: it
    never invents domain language, it only cleans the key into title case.
    """

    key = str(role_key or "").strip().lower()
    if not key:
        return ""
    for suffix in _HUMANISE_SUFFIXES:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break
    key = key.strip("_")
    if not key:
        return ""
    return " ".join(part.capitalize() for part in key.split("_") if part)


def athlete_facing_label_for(role_key: str | None, *, fallback: str | None = None) -> str:
    """Return the athlete-facing label for ``role_key``.

    Resolution order: explicit mapping -> caller fallback -> humanised key.
    """

    key = str(role_key or "").strip().lower()
    if key in ROLE_LABELS:
        return ROLE_LABELS[key]
    fallback_label = str(fallback or "").strip()
    if fallback_label:
        return fallback_label
    return humanize_role_key(key)


def _is_session_role(role: dict[str, Any]) -> bool:
    if not isinstance(role, dict):
        return False
    role_key = str(role.get("role_key") or "").strip().lower()
    if role_key in _NON_SESSION_ROLE_KEYS:
        return False
    category = str(role.get("category") or "").strip().lower()
    if category in _NON_SESSION_CATEGORIES:
        return False
    return bool(role_key)


def stamp_role_label(role: dict[str, Any]) -> dict[str, Any]:
    """Set ``athlete_facing_label`` on ``role`` in place if it is missing.

    Existing labels (e.g. converted low-load support roles that already carry a
    bespoke label) are preserved.
    """

    if not _is_session_role(role):
        return role
    existing = str(role.get("athlete_facing_label") or "").strip()
    if existing:
        return role
    role["athlete_facing_label"] = athlete_facing_label_for(role.get("role_key"))
    return role


def _stamp_roles(roles: Iterable[Any]) -> None:
    for role in roles or []:
        if isinstance(role, dict):
            stamp_role_label(role)


def stamp_weekly_role_map_labels(weekly_role_map: dict[str, Any]) -> dict[str, Any]:
    """Stamp athlete-facing labels onto every session role in the map.

    Mutates ``weekly_role_map`` in place and returns it. Suppressed roles are
    stamped too so admin/debug views stay readable, but plan-level markers are
    skipped by :func:`_is_session_role`.
    """

    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        _stamp_roles(week.get("session_roles"))
        _stamp_roles(week.get("suppressed_roles"))
    return weekly_role_map
