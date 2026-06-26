"""Deterministic week-by-week schedule rendering.

Stage 1 historically emitted an exercise *pool* per phase plus "prescriptions by
exercise type", and left the day-by-day assignment for the Stage 2 LLM to derive
from the weekly role map. That is the single biggest structural job the finalizer
redoes, and the source of the validator's ``missing_week_session_role`` /
``late_camp_session_incomplete`` warnings (the draft has no ``## Week N``
sections at all).

This module renders that week->day->session spine deterministically from data
Stage 1 already owns:

* the weekly role map (which day each session role sits on, its athlete-facing
  label, and its category), and
* the per-phase candidate exercises with real doses (strength doses via
  ``strength._classify_prescription_type`` + ``strength._prescription_templates``;
  conditioning doses from each drill's own ``duration``).

It places real selected work onto the days the planner already chose. The only
exception is when the planner selected no drill for a required energy system: the
session would otherwise render empty (and be flagged incomplete), so a clearly
labelled *default* template is emitted for that slot instead. Everything else is
real selected work, so the result already reads like the final article and the
finalizer copies structure through instead of rebuilding it.

This first increment covers dated normal camps. Late-fight countdown weeks have
their own strict allowed-exercise contracts and are left to the existing path.
"""

from __future__ import annotations

import re
from typing import Any

from .normalization import clean_list
from .strength import _classify_prescription_type, _prescription_templates

# Clause in a phase dose that introduces contrast/explosive pairing — a secondary
# stressor the crowded-week governance forbids on a single-job anchor day.
_CONTRAST_CLAUSE = re.compile(r"\s*(?:with contrast[^.]*?\.?|\(pair[^)]*\)\.?)", re.IGNORECASE)


_WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# role_key / preferred_system -> conditioning energy system bucket. Aerobic is the
# default bucket in _system_for_role, so only the non-default hints are listed.
_GLYCOLYTIC_HINTS = ("fight_pace", "repeatability", "glycolytic")
_ALACTIC_HINTS = ("alactic", "neural_primer", "sharpness", "speed", "primer")

# Name/tag substrings that identify a "secondary stressor" the crowded-week
# governance forbids stacking onto an anchor or support/recovery day. Keyed by
# the governance ``forbidden_secondary_stressors`` token so exclusion follows the
# same contract the validator enforces.
_STRESSOR_TOKEN_SIGNALS = {
    "hinge_transfer": ("deadlift", "rdl", "romanian", "hip hinge", "hinge"),
    "jumps": ("jump", "plyo", "bound", " hop", "hops"),
    "contrast_work": ("contrast", "complex pair"),
    "sharpness_touch": ("primer", "sprint", "sharpness"),
    "standalone_glycolytic": ("shuttle", "bag sprint", "intervals"),
}

# Default templates used ONLY when the planner selected no drill for a required
# energy system. These are not selected work — they are clearly labelled defaults
# so a required session slot does not render empty (which would be flagged
# incomplete). The "Default" prefix keeps the rendered line honest about its
# origin.
_SYSTEM_DEFAULT_TEMPLATE = {
    "aerobic": "Default aerobic option — Zone 2 (run / bike / row) 25–35 min easy, nasal-breathing pace.",
    "glycolytic": "Default fight-pace option — 4–6 x 2–3 min @ RPE 7–8, work:rest 1:1.",
    "alactic": "Default alactic option — 6–8 x 6–10 sec max effort, full rest (60–120 sec).",
}


def fill_missing_session_days(weekly_role_map: dict[str, Any]) -> dict[str, Any]:
    """Assign a ``scheduled_day_hint`` to any session role the planner left blank.

    Dayless roles otherwise render without a weekday (or on a day the validator's
    calendar spine does not consider authorised). Filling the hint on the role
    map itself keeps the planning brief, the validator's authorised-day set, and
    the rendered schedule consistent — Stage 1 owns the placement deterministically
    instead of deferring it to the LLM. Mutates and returns the map.
    """
    if not isinstance(weekly_role_map, dict):
        return weekly_role_map
    for week in weekly_role_map.get("weeks", []) or []:
        if not isinstance(week, dict):
            continue
        roles = [role for role in (week.get("session_roles") or []) if isinstance(role, dict)]
        used = {
            normalized
            for role in roles
            if (normalized := str(role.get("scheduled_day_hint") or "").strip().lower())
        }
        declared = [
            normalized
            for day in clean_list(week.get("declared_training_days"))
            if (normalized := str(day).strip().lower()) in _WEEKDAY_ORDER
        ]
        free = iter(day for day in sorted(set(declared), key=_WEEKDAY_ORDER.index) if day not in used)
        for role in roles:
            if str(role.get("scheduled_day_hint") or "").strip():
                continue
            day = next(free, "")
            if day:
                role["scheduled_day_hint"] = day.title()
    return weekly_role_map


def _weekday_to_d_day(week: dict[str, Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for entry in week.get("calendar_days") or []:
        if not isinstance(entry, dict):
            continue
        weekday = str(entry.get("weekday") or "").strip().lower()
        d_day = entry.get("d_day")
        if weekday and isinstance(d_day, int):
            mapping[weekday] = d_day
    return mapping


def _countdown_label(d_to_day: dict[str, int]) -> str:
    if not d_to_day:
        return ""
    values = list(d_to_day.values())
    return f"D-{max(values)} → D-{min(values)}"


def _session_heading(role: dict[str, Any], weekday: str, d_to_day: dict[str, int]) -> tuple[str, int | None]:
    label = str(role.get("athlete_facing_label") or "").strip() or "Session"
    d_day = d_to_day.get(weekday.lower()) if weekday else None
    if weekday and d_day is not None:
        return f"### {weekday.title()} (D-{d_day}) — {label}", d_day
    if weekday:
        return f"### {weekday.title()} — {label}", None
    return f"### {label}", None


def _resolve_role_weekdays(
    session_roles: list[dict[str, Any]],
    week: dict[str, Any],
) -> dict[int, str]:
    """Assign a weekday to every session role, filling any the planner left blank.

    Roles without a ``scheduled_day_hint`` are placed on the week's remaining
    declared training days (in weekday order) so every rendered session maps to a
    real calendar day — Stage 1 owns the placement instead of leaving a dayless
    session for the LLM.
    """
    resolved: dict[int, str] = {}
    used: set[str] = set()
    for idx, role in enumerate(session_roles):
        weekday = str(role.get("scheduled_day_hint") or "").strip().lower()
        if weekday:
            resolved[idx] = weekday
            used.add(weekday)

    declared = [
        normalized
        for day in clean_list(week.get("declared_training_days"))
        if (normalized := str(day).strip().lower()) in _WEEKDAY_ORDER
    ]
    free = [day for day in sorted(set(declared), key=_WEEKDAY_ORDER.index) if day not in used]

    free_iter = iter(free)
    for idx, role in enumerate(session_roles):
        if idx in resolved:
            continue
        resolved[idx] = next(free_iter, "")
    return resolved


def _sanitize_dose(dose: str, forbidden: set[str]) -> str:
    if "contrast_work" in forbidden and "contrast" in dose.lower():
        dose = _CONTRAST_CLAUSE.sub("", dose).strip()
        if dose and not dose.endswith("."):
            dose = f"{dose}."
    return dose


def _strength_line(exercise: dict[str, Any], phase: str, forbidden: set[str]) -> str:
    name = str(exercise.get("name") or "").strip()
    if not name:
        return ""
    dose = _prescription_templates(phase).get(_classify_prescription_type(exercise), "")
    dose = _sanitize_dose(dose, forbidden)
    return f"- {name} — {dose}" if dose else f"- {name}"


def _exercise_matches_stressor(exercise: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return False
    name = f" {str(exercise.get('name') or '').lower()} "
    tags = {str(tag).strip().lower() for tag in clean_list(exercise.get("tags"))}
    for token in tokens:
        signals = _STRESSOR_TOKEN_SIGNALS.get(token)
        if not signals:
            continue
        if token in tags:
            return True
        if any(signal.strip() in name for signal in signals):
            return True
    return False


def _forbidden_stressor_tokens(role: dict[str, Any]) -> set[str]:
    governance = role.get("governance") or {}
    return {
        str(token).strip().lower()
        for token in clean_list(governance.get("forbidden_secondary_stressors"))
        if str(token).strip()
    }


def _split_anchor_support(exercises: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    anchors: list[dict] = []
    supports: list[dict] = []
    for exercise in exercises:
        if not isinstance(exercise, dict):
            continue
        quality = str(exercise.get("quality_class") or "").lower()
        is_anchor = bool(exercise.get("anchor_capable")) or quality.startswith("anchor")
        if is_anchor and not exercise.get("support_only"):
            anchors.append(exercise)
        else:
            supports.append(exercise)
    return anchors, supports


def _strength_session_lines(
    role: dict[str, Any],
    phase: str,
    strength_exercises: list[dict[str, Any]],
    *,
    is_primary: bool,
) -> list[str]:
    # Respect the role's governance: an anchor (or support/recovery) day must not
    # stack forbidden secondary stressors (e.g. a hinge transfer next to the main
    # lift), so drop those exercises before selecting.
    forbidden = _forbidden_stressor_tokens(role)
    eligible = [ex for ex in strength_exercises if not _exercise_matches_stressor(ex, forbidden)]
    if not eligible:
        eligible = list(strength_exercises)

    anchors, supports = _split_anchor_support(eligible)
    # Anchor-first: the primary/neural strength day leads with the anchor lift;
    # secondary strength leans on support work. Both stay decisive and short.
    if is_primary:
        chosen = (anchors[:1] or supports[:1]) + supports[:2]
    else:
        chosen = (anchors[:1] or supports[:1]) + supports[:1]

    lines: list[str] = []
    seen_names: set[str] = set()
    for exercise in chosen:
        name = str(exercise.get("name") or "").strip().lower()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        line = _strength_line(exercise, phase, forbidden)
        if line:
            lines.append(line)
    if not lines:
        lines = ["- Primary strength work from this phase's selection."]
    return lines


def _system_for_role(role: dict[str, Any]) -> str:
    system = str(role.get("preferred_system") or "").strip().lower()
    if system in {"aerobic", "glycolytic", "alactic"}:
        return system
    role_key = str(role.get("role_key") or "").strip().lower()
    if any(hint in role_key for hint in _GLYCOLYTIC_HINTS):
        return "glycolytic"
    if any(hint in role_key for hint in _ALACTIC_HINTS):
        return "alactic"
    return "aerobic"


def _conditioning_session_lines(
    role: dict[str, Any],
    grouped_drills: dict[str, list[dict[str, Any]]],
) -> list[str]:
    system = _system_for_role(role)
    drills = grouped_drills.get(system) or grouped_drills.get(system.upper()) or []
    lines: list[str] = []
    for drill in drills[:2]:
        if not isinstance(drill, dict):
            continue
        name = str(drill.get("name") or "").strip()
        if not name:
            continue
        duration = str(drill.get("duration") or "").strip()
        lines.append(f"- {name} — {duration}" if duration else f"- {name}")
    if not lines:
        default = _SYSTEM_DEFAULT_TEMPLATE.get(system, _SYSTEM_DEFAULT_TEMPLATE["aerobic"])
        lines = [f"- {default}"]
    return lines


def _recovery_session_lines() -> list[str]:
    return ["- Easy mobility, breathing, and tissue work. Keep it fully restorative."]


def _sparring_session_lines() -> list[str]:
    return ["- Coach owns this session (hard sparring). No app S&C today — keep freshness the priority."]


def _light_combat_session_lines() -> list[str]:
    return ["- Coach owns this Light Combat session. No app S&C today - keep freshness the priority."]


def _technical_session_lines() -> list[str]:
    return ["- Technical rhythm and shadow work. Stay sharp at low fatigue; no hard contact."]


def _session_body(
    role: dict[str, Any],
    phase: str,
    strength_exercises: list[dict[str, Any]],
    grouped_drills: dict[str, list[dict[str, Any]]],
    *,
    is_primary_strength: bool,
) -> list[str]:
    category = str(role.get("category") or "").strip().lower()
    role_key = str(role.get("role_key") or "").strip()
    if role_key == "light_combat_day":
        return _light_combat_session_lines()
    if category == "sparring":
        return _sparring_session_lines()
    if category == "recovery":
        return _recovery_session_lines()
    if category == "skill":
        return _technical_session_lines()
    if category == "strength":
        return _strength_session_lines(role, phase, strength_exercises, is_primary=is_primary_strength)
    if category == "conditioning":
        return _conditioning_session_lines(role, grouped_drills)
    # Unknown category: keep it decisive but generic rather than empty.
    return ["- Coach-led session aligned with this week's focus."]


def _is_primary_strength_role(role: dict[str, Any]) -> bool:
    role_key = str(role.get("role_key") or "").strip().lower()
    if "primary" in role_key or "neural_plus_strength" in role_key or "structural" in role_key:
        return True
    return bool(str(role.get("anchor") or "").strip())


def _phase_strength_exercises(blocks: Any, phase: str) -> list[dict[str, Any]]:
    block = (getattr(blocks, "strength_blocks", {}) or {}).get(phase) or {}
    return [ex for ex in (block.get("exercises") or []) if isinstance(ex, dict)]


def _phase_grouped_drills(blocks: Any, phase: str) -> dict[str, list[dict[str, Any]]]:
    block = (getattr(blocks, "conditioning_blocks", {}) or {}).get(phase) or {}
    grouped = block.get("grouped_drills") or {}
    normalized: dict[str, list[dict[str, Any]]] = {}
    if isinstance(grouped, dict):
        for system, drills in grouped.items():
            normalized[str(system).strip().lower()] = [d for d in (drills or []) if isinstance(d, dict)]
    return normalized


def _render_week(week: dict[str, Any], blocks: Any) -> list[str]:
    week_index = int(week.get("week_index", 0) or 0)
    if week_index <= 0:
        return []
    phase = str(week.get("phase") or "").strip().upper()
    session_roles = [role for role in (week.get("session_roles") or []) if isinstance(role, dict)]
    if not session_roles:
        return []

    d_to_day = _weekday_to_d_day(week)
    strength_exercises = _phase_strength_exercises(blocks, phase)
    grouped_drills = _phase_grouped_drills(blocks, phase)

    countdown = _countdown_label(d_to_day)
    header = f"## Week {week_index} — {phase}" + (f" ({countdown})" if countdown else "")

    role_weekday = _resolve_role_weekdays(session_roles, week)

    # Render in chronological order (furthest from fight first).
    def _sort_key(item: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        idx, _role = item
        weekday = role_weekday.get(idx, "")
        d_day = d_to_day.get(weekday)
        if isinstance(d_day, int):
            return (0, -d_day)
        order = _WEEKDAY_ORDER.index(weekday) if weekday in _WEEKDAY_ORDER else 99
        return (1, order)

    seen_primary_strength = False
    lines: list[str] = [header, ""]
    for idx, role in sorted(enumerate(session_roles), key=_sort_key):
        weekday = role_weekday.get(idx, "")
        heading, _d_day = _session_heading(role, weekday, d_to_day)
        is_primary_strength = False
        if str(role.get("category") or "").lower() == "strength":
            is_primary_strength = _is_primary_strength_role(role) or not seen_primary_strength
            if is_primary_strength:
                seen_primary_strength = True
        body = _session_body(
            role,
            phase,
            strength_exercises,
            grouped_drills,
            is_primary_strength=is_primary_strength,
        )
        lines.append(heading)
        lines.extend(body)
        lines.append("")
    return lines


def render_weekly_schedule_section(*, planning_brief: dict[str, Any], blocks: Any) -> str:
    """Render the deterministic week-by-week schedule, or ``""`` when N/A.

    Returns markdown beginning with a ``# Weekly Schedule`` banner followed by
    one ``## Week N`` block per active week. Returns an empty string for
    late-fight / open-ended variants that do not ship a normal weekly role map.
    """

    if not isinstance(planning_brief, dict):
        return ""
    variant = str(planning_brief.get("payload_variant") or "").strip().lower()
    if variant in {"late_fight_stage2_payload", "open_ongoing_stage2_payload"}:
        return ""
    weekly_role_map = planning_brief.get("weekly_role_map")
    if not isinstance(weekly_role_map, dict):
        return ""
    weeks = [week for week in (weekly_role_map.get("weeks") or []) if isinstance(week, dict)]
    if len(weeks) <= 1:
        return ""

    body: list[str] = []
    for week in weeks:
        body.extend(_render_week(week, blocks))
    rendered = [line for line in body]
    if not any(line.startswith("## Week ") for line in rendered):
        return ""
    return "\n".join(["# Weekly Schedule", "", *rendered]).strip()
