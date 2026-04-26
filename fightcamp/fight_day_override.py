"""Shared fight-day (D-0) protocol guard.

The normal-camp pipeline (>21 days out) builds a ``weekly_role_map`` whose final
week can lock the fight weekday as a declared ``hard_sparring_day`` slot. That
caused the fight day to render as a coach-led boxing session rather than the
fight-day protocol.

This module provides the single authoritative D-0 override: given an athlete
model that carries ``plan_creation_weekday`` and ``days_until_fight``, it
computes the fight weekday and rewrites the matching session role on the final
week of the weekly role map into a ``fight_day_protocol`` placeholder.

The override is unconditional on D-0 — it suppresses any session role that
falls on the fight weekday, regardless of role key, so future role types remain
covered without further changes.
"""

from __future__ import annotations

from typing import Any

from .stage2_payload_late_fight import _fight_weekday_from_context


FIGHT_DAY_PROTOCOL_TEXT = (
    "Fight day protocol — follow coach warm-up and fight protocol; "
    "no additional app S&C."
)


def compute_fight_weekday(athlete_model: dict | None) -> str | None:
    """Return the lowercase fight weekday name, or None when undecidable."""
    if not isinstance(athlete_model, dict):
        return None
    return _fight_weekday_from_context(
        athlete_model.get("plan_creation_weekday"),
        athlete_model.get("days_until_fight"),
    )


def _make_fight_day_protocol_role(day: str) -> dict[str, Any]:
    """Build the placeholder session role that replaces a D-0 training slot."""
    return {
        "category": "fight_day",
        "role_key": "fight_day_protocol",
        "preferred_pool": "none",
        "selection_rule": (
            "Render this slot as the fight-day protocol only. Do not assign "
            "S&C, sparring, or any training role."
        ),
        "anchor": "fight_day_protocol",
        "placement_rule": (
            f"Fight is on {day.title()}. Render exactly: \"{FIGHT_DAY_PROTOCOL_TEXT}\""
        ),
        "scheduled_day_hint": day,
        "day_assignment_reason": (
            "Day matches the athlete's fight date; only the fight-day protocol "
            "may render here."
        ),
        "coach_owned": True,
        "display_text": FIGHT_DAY_PROTOCOL_TEXT,
        "athlete_facing_label": FIGHT_DAY_PROTOCOL_TEXT,
        "governance": {
            "authority": "fight_day_protocol_lock",
            "execution_only": False,
            "cannot_override": [
                "weekly_role_map",
                "declared_hard_sparring_days",
                "session_counts",
            ],
        },
    }


def _make_fight_day_suppression(role: dict[str, Any], day: str) -> dict[str, Any]:
    """Record the role that the D-0 override displaced."""
    return {
        "category": role.get("category"),
        "role_key": role.get("role_key"),
        "preferred_system": role.get("preferred_system", ""),
        "reasons": [
            "Fight day overrides every other role; this slot must render as "
            "the fight-day protocol only."
        ],
        "governance": dict(role.get("governance", {})),
        "locked_day": day,
        "scheduled_day_hint": day,
        "replacement_role_key": "fight_day_protocol",
        "downgraded_from_role_key": role.get("role_key"),
    }


def apply_fight_day_override_to_weekly_role_map(
    weekly_role_map: dict[str, Any],
    athlete_model: dict[str, Any],
) -> dict[str, Any]:
    """Clamp the fight day to the fight-day protocol on the final camp week.

    Only the last week of the progression is touched. Earlier instances of the
    same weekday are left alone so the anti-hardcode guarantee holds.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    weeks = weekly_role_map.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        return weekly_role_map
    fight_weekday = compute_fight_weekday(athlete_model)
    if not fight_weekday:
        return weekly_role_map

    final_idx = len(weeks) - 1
    final_week = weeks[final_idx]
    if not isinstance(final_week, dict):
        return weekly_role_map

    session_roles = list(final_week.get("session_roles") or [])
    suppressed_roles = list(final_week.get("suppressed_roles") or [])
    replaced_existing = False
    new_roles: list[dict[str, Any]] = []
    for role in session_roles:
        if not isinstance(role, dict):
            new_roles.append(role)
            continue
        scheduled_day = str(role.get("scheduled_day_hint") or "").strip().lower()
        if scheduled_day == fight_weekday and not replaced_existing:
            suppressed_roles.append(_make_fight_day_suppression(role, fight_weekday))
            new_roles.append(_make_fight_day_protocol_role(fight_weekday))
            replaced_existing = True
            continue
        if scheduled_day == fight_weekday:
            suppressed_roles.append(_make_fight_day_suppression(role, fight_weekday))
            continue
        new_roles.append(role)

    if not replaced_existing:
        new_roles.append(_make_fight_day_protocol_role(fight_weekday))

    for idx, role in enumerate(new_roles, start=1):
        if isinstance(role, dict):
            role["session_index"] = idx

    capped_hard = [
        day
        for day in (final_week.get("declared_hard_sparring_days") or [])
        if isinstance(day, str) and day.strip().lower() == fight_weekday
    ]
    if capped_hard:
        effective_days = [
            day
            for day in (final_week.get("effective_hard_sparring_days") or [])
            if isinstance(day, str) and day.strip().lower() != fight_weekday
        ]
        final_week["effective_hard_sparring_days"] = effective_days

    final_week["session_roles"] = new_roles
    final_week["suppressed_roles"] = suppressed_roles
    final_week["fight_day_override"] = {
        "active": True,
        "fight_weekday": fight_weekday,
        "fight_day_text": FIGHT_DAY_PROTOCOL_TEXT,
        "replaced_role": replaced_existing,
    }
    weeks[final_idx] = final_week

    weekly_role_map["weeks"] = weeks
    weekly_role_map["fight_day_override"] = {
        "active": True,
        "fight_weekday": fight_weekday,
        "fight_day_text": FIGHT_DAY_PROTOCOL_TEXT,
        "applied_to_week_index": final_week.get("week_index"),
    }
    return weekly_role_map
