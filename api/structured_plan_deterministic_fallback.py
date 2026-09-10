"""One canonical structured plan built from deterministic planner state alone.

When Stage 2 fails there is no valid ``structured_plan`` column, and the athlete
client would otherwise rebuild its calendar from ``plan_text`` (see
``web/lib/plan-text-adapter.ts``). That hands the model authority over whether a
declared sparring day, a declared light-combat day or a Tactical Watch *exists* —
on the one path where the model has already proven unreliable.

This module builds the fallback from Stage 1's own resolved state instead:
selected session roles, their selected exercise assignments and authoritative
effective prescriptions. It owns no calendar and no classification of its own —
each kind of locked content is assembled by the module that already owns it:

    role sessions        -> here, from weekly_role_map.session_roles
    declared contact     -> reconcile_coach_led_sparring_days
    Tactical Watch       -> merge_locked_structured_content
    calendar continuity  -> reconcile_calendar_spine

Roles owned by one of those assemblers are deliberately NOT turned into sessions
here, so a day never carries two representations of the same role.

Identity is ``(d_day, role_key, session_index)``: distinct roles that share a day
(conditioning + light combat + Tactical Watch on one Wednesday) all survive.
Deterministic ownership protects the individual role, never the whole day —
existing collision rules still decide what may share a day, and this module
reads their verdict rather than re-deciding it.
"""

from __future__ import annotations

import logging
from typing import Any

from fightcamp.role_labels import athlete_facing_label_for

from .structured_plan_calendar_spine import reconcile_calendar_spine
from .structured_plan_locked_merge import merge_locked_structured_content
from .structured_plan_sparring_reconcile import reconcile_coach_led_sparring_days

logger = logging.getLogger(__name__)

# Roles another deterministic assembler already renders. Building sessions for
# them here would put the same role on the day twice.
_ROLES_OWNED_ELSEWHERE = frozenset(
    {
        "hard_sparring_day",  # reconcile_coach_led_sparring_days
        "light_combat_day",  # reconcile_coach_led_sparring_days
        "tactical_watch",  # merge_locked_structured_content
    }
)

_SESSION_TYPE_BY_CATEGORY = {
    "strength": "strength_power",
    "conditioning": "conditioning",
    "recovery": "recovery",
    "rehab": "rehab",
    "technical": "skill",
    "skill": "skill",
    "sparring": "sparring",
    "mindset": "skill",
    "support_insert": "recovery",
}
_BLOCK_TYPE_BY_CATEGORY = {
    "strength": "strength",
    "conditioning": "conditioning",
    "recovery": "cooldown_recovery",
    "rehab": "rehab",
    "technical": "skill",
    "skill": "skill",
    "sparring": "sparring",
    "mindset": "mindset",
    "support_insert": "mobility_activation",
}


def _dday(role: dict[str, Any]) -> int | None:
    raw = role.get("scheduled_d_day")
    if isinstance(raw, int) and raw >= 0:
        return raw
    for key in ("scheduled_countdown_label", "countdown_label"):
        label = str(role.get(key) or "").strip().upper()
        if label.startswith("D-"):
            try:
                return int(label[2:])
            except ValueError:
                continue
    return None


def _category(role: dict[str, Any]) -> str:
    return str(role.get("category") or "").strip().lower()


def _effective_prescription(role: dict[str, Any], assignment: dict[str, Any]) -> str:
    """The planner's authoritative dose for one assignment.

    ``effective_strength_prescriptions`` is the resolved authority (it carries any
    late-camp dose cap); the assignment's own bank dose is the fallback.
    """
    slot_id = str(assignment.get("slot_id") or "").strip()
    name = str(assignment.get("name") or "").strip()
    for resolved in role.get("effective_strength_prescriptions") or []:
        if not isinstance(resolved, dict):
            continue
        if (slot_id and str(resolved.get("slot_id") or "").strip() == slot_id) or (
            name and str(resolved.get("name") or "").strip() == name
        ):
            prescription = str(
                resolved.get("effective_prescription")
                or resolved.get("base_prescription")
                or ""
            ).strip()
            if prescription:
                return prescription
    return str(assignment.get("base_prescription") or "").strip()


# The weekly priority exposure floor attaches a microdose to the host role, not
# to its selected_exercise_assignments, so a renderer that reads only the
# assignment list drops it. Stage 2 is not allowed to be the only path that
# surfaces it: when Stage 2 fails there is no structured_plan and this fallback
# is the athlete-facing plan.
_MICRODOSE_BLOCK_TYPE_BY_GOAL = {
    "power": "plyometric_power",
    "speed": "speed",
    "strength": "strength",
    "footwork": "skill",
    "mobility": "mobility_activation",
}


def _microdose_block(role: dict[str, Any], d_day: int, role_key: str) -> dict[str, Any] | None:
    """The host's priority microdose, as subordinate work inside its session.

    Never its own session or card: it is rendered as the first block of the host
    the floor chose, and the host keeps its own identity, title and session type.
    """
    microdose = role.get("priority_microdose")
    if not isinstance(microdose, dict):
        return None
    name = str(microdose.get("name") or "").strip()
    if not name:
        return None
    goal = str(microdose.get("goal") or "").strip().lower()
    prescription = str(microdose.get("prescription") or "").strip()
    label = f"{goal.replace('_', ' ').title()} microdose" if goal else "Priority microdose"
    return {
        "block_id": f"deterministic-{d_day}-{role_key}-microdose",
        "block_type": _MICRODOSE_BLOCK_TYPE_BY_GOAL.get(goal, "accessory"),
        # The label travels in the display name so the athlete can see this is a
        # small priority touch rather than the session's main work.
        "display_name": f"{label} - {name}",
        "order_index": 0,
        "coaching_cues": [prescription] if prescription else [],
        "regression_options": [],
        "substitutions": [],
    }


def _blocks(role: dict[str, Any], d_day: int, role_key: str) -> list[dict[str, Any]]:
    category = _category(role)
    block_type = _BLOCK_TYPE_BY_CATEGORY.get(category, "accessory")
    blocks: list[dict[str, Any]] = []
    for index, assignment in enumerate(role.get("selected_exercise_assignments") or []):
        if not isinstance(assignment, dict):
            continue
        name = str(assignment.get("name") or "").strip()
        if not name:
            continue
        prescription = _effective_prescription(role, assignment)
        blocks.append(
            {
                "block_id": f"deterministic-{d_day}-{role_key}-{index}",
                "block_type": block_type,
                "display_name": name,
                "order_index": index,
                # The resolved dose is a planner string, not a parsed set/rep
                # structure. It is surfaced verbatim rather than guessed apart.
                "coaching_cues": [prescription] if prescription else [],
                "regression_options": [],
                "substitutions": [],
            }
        )
    # Only ever attached to a host that already renders. A role with no selected
    # exercise renders no session at all here, and a microdose must not be the
    # thing that brings one into existence - that would be a new session.
    microdose = _microdose_block(role, d_day, role_key) if blocks else None
    if microdose is not None:
        for block in blocks:
            block["order_index"] = int(block.get("order_index") or 0) + 1
        blocks.insert(0, microdose)
    return blocks


def _session(role: dict[str, Any], d_day: int) -> dict[str, Any] | None:
    role_key = str(role.get("role_key") or "").strip()
    blocks = _blocks(role, d_day, role_key or "role")
    if not blocks:
        # A role with no selected exercise has nothing deterministic to render;
        # inventing a session here would be the fallback making things up.
        return None
    category = _category(role)
    session_index = role.get("session_index")
    suffix = session_index if isinstance(session_index, int) else 0
    title = athlete_facing_label_for(
        role_key, fallback=str(role.get("athlete_facing_label") or "").strip() or None
    )
    return {
        "session_id": f"deterministic-{d_day}-{role_key}-{suffix}",
        "session_type": _SESSION_TYPE_BY_CATEGORY.get(category, "mixed"),
        "title": title or "Session",
        "objective": str(role.get("day_assignment_reason") or title or "Session"),
        "completion_status": "not_started",
        "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""},
        "blocks": blocks,
    }


def build_deterministic_structured_plan(planning_brief: Any) -> dict[str, Any] | None:
    """Assemble the canonical fallback plan, or ``None`` when not applicable.

    Never raises: an unusable brief returns ``None`` so the caller keeps whatever
    behaviour it had before.
    """
    try:
        return _build(planning_brief)
    except Exception:  # a fallback that raises is worse than no fallback
        logger.exception("[deterministic_fallback] assembly failed")
        return None


def _build(planning_brief: Any) -> dict[str, Any] | None:
    if not isinstance(planning_brief, dict):
        return None
    role_map = planning_brief.get("weekly_role_map")
    if not isinstance(role_map, dict):
        return None
    weeks = role_map.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        return None

    # Identity is (d_day, role_key, session_index): two distinct roles on one day
    # are two sessions, and the same role is never emitted twice.
    sessions_by_dday: dict[int, list[dict[str, Any]]] = {}
    seen: set[tuple[int, str, Any]] = set()
    for week in weeks:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict):
                continue
            role_key = str(role.get("role_key") or "").strip()
            if role_key in _ROLES_OWNED_ELSEWHERE:
                continue
            d_day = _dday(role)
            if d_day is None:
                continue
            identity = (d_day, role_key, role.get("session_index"))
            if identity in seen:
                continue
            session = _session(role, d_day)
            if session is None:
                continue
            seen.add(identity)
            sessions_by_dday.setdefault(d_day, []).append(session)

    # The spine builds every calendar day in its own schema-valid shape, so the
    # fallback never hand-rolls a day: the sessions are attached onto the days it
    # produced. This is also why a Tactical Watch on a day with no S&C still has
    # a day to be placed on.
    plan = reconcile_calendar_spine({"weeks": []}, planning_brief)
    if not isinstance(plan, dict):
        return None
    days = [
        day
        for week in plan.get("weeks") or []
        for day in week.get("days") or []
        if isinstance(day, dict)
    ]
    if not days:
        return None
    for day in days:
        d_day = _label_dday(day.get("countdown_label"))
        sessions = sessions_by_dday.get(d_day) if d_day is not None else None
        if sessions:
            day["sessions"] = sessions

    # Each remaining kind of locked content is added by the module that owns it.
    reconcile_coach_led_sparring_days(plan, planning_brief)
    plan = merge_locked_structured_content(plan, planning_brief).plan

    weeks_out = plan.get("weeks") if isinstance(plan, dict) else None
    if not isinstance(weeks_out, list) or not weeks_out:
        return None
    plan.update(_plan_envelope(planning_brief))
    return plan


def _label_dday(label: Any) -> int | None:
    text = str(label or "").strip().upper()
    if not text.startswith("D-"):
        return None
    try:
        return int(text[2:])
    except ValueError:
        return None


def _plan_envelope(planning_brief: dict[str, Any]) -> dict[str, Any]:
    """Schema-required plan-level sections, from deterministic state only.

    Nothing here is invented: fields with no deterministic source stay empty
    rather than carrying text the planner never produced. In particular the
    nutrition section is left blank -- the athlete-safe numbers already travel
    on ``deterministic_support``, and this fallback must not author guidance.
    """
    athlete = planning_brief.get("athlete_model")
    athlete = athlete if isinstance(athlete, dict) else {}
    sport = str(athlete.get("sport") or athlete.get("sport_profile") or "").strip()
    return {
        "plan_metadata": {
            "title": "Fight camp plan",
            "sport": sport or "combat_sports",
            "plan_type": "fight_camp",
            "timezone": str(athlete.get("athlete_timezone") or "UTC").strip() or "UTC",
            "status": "active",
        },
        "athlete_context": {
            "sport_profile": sport or "combat_sports",
            "equipment_access": [
                str(item)
                for item in athlete.get("equipment") or []
                if str(item).strip()
            ],
        },
        "nutrition": {
            "summary": "",
            "daily_focus": "",
            "training_day_guidance": "",
            "fight_week_guidance": "",
        },
    }
