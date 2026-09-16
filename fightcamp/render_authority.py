"""One decision: has Stage 1 already decided this session's athlete-facing body?

Stage 2 is a *formatter* for content the deterministic planner resolved, and an
*author* only for content it did not. Before this module that boundary was
re-derived in three places — the locked render manifest in
:mod:`fightcamp.stage2_payload` (which recognised only
``selected_exercise_assignments``), the deterministic source repair in
:mod:`fightcamp.stage2_pipeline`, and the structured-plan deterministic fallback
— and they disagreed. A Recovery Reset with a complete planner-written
``display_text`` but no selected assignments was authoritative to one layer and
invisible to the others, so Stage 2 could silently drop it and repair could not
put it back.

``authoritative_render_for_role`` is the single answer. It recognises four kinds
of server-owned content:

``fight_day_protocol``
    The D-0 protocol constant. There is nothing for a model to author.
``canonical_combat``
    A declared combat day whose *resolved* contact state has canonical copy
    (see :mod:`fightcamp.combat_render_authority`). Label + one note, never a
    dose.
``deterministic_display_text``
    A planner-stamped exact body: gap-fill / camp-week support inserts, the
    bank-selected Tactical Watch, coordination support, bank footwork. Gated on
    explicit authority signals, never on "the role happens to carry prose".
``closed_selected_assignments``
    Closed exercise membership where every member carries an approved effective
    prescription.

Deliberately NOT authoritative: an open role whose content Stage 1 left to
Stage 2. A category such as "recovery" or "technical" is not authority, and this
module never synthesises a body from ``preferred_exercise_names``, from the
category, or from any prose field that could have come from a draft. When the
resolved state is ambiguous it returns ``None`` and the caller fails closed.
"""

from __future__ import annotations

from typing import Any

from .combat_render_authority import canonical_combat_render, is_declared_combat_role
from .fight_day_override import FIGHT_DAY_PROTOCOL_TEXT


AUTHORITY_FIGHT_DAY_PROTOCOL = "fight_day_protocol"
AUTHORITY_CANONICAL_COMBAT = "canonical_combat"
AUTHORITY_DETERMINISTIC_DISPLAY_TEXT = "deterministic_display_text"
AUTHORITY_CLOSED_SELECTED_ASSIGNMENTS = "closed_selected_assignments"

# ``governance.authority`` values stamped by deterministic content owners. Each
# of these writes the athlete-facing body itself; none of them leaves wording to
# the model.
_DETERMINISTIC_GOVERNANCE_AUTHORITIES = frozenset(
    {
        "gap_fill_support_insert",
        "camp_week_support_insert",
        "coordination_support_library",
        "tactical_watch_library",
        "fight_visualization_library",
        "fight_day_protocol_lock",
    }
)

_FIGHT_DAY_ROLE_KEY = "fight_day_protocol"


def _governance(role: dict[str, Any]) -> dict[str, Any]:
    governance = role.get("governance")
    return governance if isinstance(governance, dict) else {}


def _body_lines(display_text: Any) -> list[str]:
    return [line.rstrip() for line in str(display_text or "").splitlines() if line.strip()]


def _is_fight_day_protocol_role(role: dict[str, Any]) -> bool:
    if str(role.get("role_key") or "").strip() == _FIGHT_DAY_ROLE_KEY:
        return True
    return _governance(role).get("authority") == "fight_day_protocol_lock"


def has_deterministic_display_text_authority(role: dict[str, Any]) -> bool:
    """Whether this role's ``display_text`` is planner-owned exact content.

    Gated on explicit authority signals only. ``display_text`` on a role with no
    such signal is treated as draft prose, not as server truth.
    """
    governance = _governance(role)
    if governance.get("selected_drill_locked") is True:
        return True
    if governance.get("render_selected_drill_exactly") is True:
        return True
    if str(governance.get("authority") or "") in _DETERMINISTIC_GOVERNANCE_AUTHORITIES:
        return True
    if role.get("camp_week_filler") is True:
        return True
    # ``support_insert`` is only ever stamped by the deterministic insert builders
    # (gap-fill inserts and camp-week fillers), each of which writes the exact
    # athlete-facing body itself. It is a structural authority signal that, unlike
    # ``governance.authority``, survives the finalizer packet's compaction.
    if str(role.get("category") or "").strip() == "support_insert":
        return True
    return False


def _closed_membership_lines(role: dict[str, Any]) -> list[str] | None:
    """Exact lines for closed membership, or ``None`` when not fully resolved.

    A single member missing its name or its approved effective prescription makes
    the whole role non-authoritative: a partially priced session is not something
    the server may assert on its own.
    """
    assignments = role.get("selected_exercise_assignments")
    if not isinstance(assignments, list) or not assignments:
        return None
    lines: list[str] = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            return None
        name = str(assignment.get("name") or assignment.get("exercise_name") or "").strip()
        prescription = assignment.get("effective_prescription")
        if isinstance(prescription, dict):
            display = str(
                prescription.get("display")
                or prescription.get("dose")
                or prescription.get("text")
                or ""
            ).strip()
        else:
            display = str(prescription or "").strip()
        if not name or not display:
            return None
        lines.append(f"- {name} — {display}")
    return lines or None


def priority_microdose_line(role: dict[str, Any]) -> str | None:
    """The host's priority microdose as one subordinate line, or ``None``.

    Never its own session and never a second copy: goal preservation already
    mirrors an attached microdose into the host's closed membership, so this
    returns ``None`` whenever the microdose is not complete.
    """
    microdose = role.get("priority_microdose")
    if not isinstance(microdose, dict):
        return None
    name = str(microdose.get("name") or "").strip()
    prescription = str(microdose.get("prescription") or "").strip()
    if not name or not prescription:
        return None
    goal = str(microdose.get("goal") or "").strip().lower()
    label = f"{goal.replace('_', ' ').title()} microdose" if goal else "Priority microdose"
    return f"- {label} — {name}: {prescription}"


def _append_microdose_once(role: dict[str, Any], lines: list[str]) -> list[str]:
    """Add the microdose line only when the body does not already carry it."""
    microdose = role.get("priority_microdose")
    line = priority_microdose_line(role)
    if not line or not isinstance(microdose, dict):
        return lines
    name = str(microdose.get("name") or "").strip().lower()
    if any(name in existing.lower() for existing in lines):
        return lines
    return [*lines, line]


def _week_d_day(week: dict[str, Any] | None, role: dict[str, Any]) -> int | None:
    """The role's D-day from its owning week's calendar, when not stamped on it."""
    for key in ("scheduled_d_day", "countdown_offset"):
        value = role.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    if not isinstance(week, dict):
        return None
    weekday = str(role.get("scheduled_day_hint") or role.get("real_weekday") or "").strip().lower()
    if not weekday:
        return None
    for day in week.get("calendar_days") or []:
        if not isinstance(day, dict):
            continue
        if str(day.get("weekday") or "").strip().lower() != weekday:
            continue
        value = day.get("d_day")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def authoritative_render_for_role(
    role: dict[str, Any] | None,
    *,
    week: dict[str, Any] | None = None,
    athlete_snapshot: dict[str, Any] | None = None,
    d_day: int | None = None,
    display_text_fallback: str | None = None,
) -> dict[str, Any] | None:
    """Return the server-owned render for ``role``, or ``None``.

    ``display_text_fallback`` lets a caller reading a *compacted* role (the
    finalizer packet drops the long ``display_text`` of a ``selected_drill_locked``
    role, because the server renders it) supply the exact body from the rich
    Stage 1 role without reopening selection freedom.
    """
    if not isinstance(role, dict):
        return None
    if role.get("render_mandatory") is False:
        return None

    label = str(
        role.get("athlete_facing_label")
        or role.get("label")
        or ""
    ).strip()

    if _is_fight_day_protocol_role(role):
        return {
            "authority": AUTHORITY_FIGHT_DAY_PROTOCOL,
            "athlete_facing_label": label or FIGHT_DAY_PROTOCOL_TEXT,
            "body_lines": [FIGHT_DAY_PROTOCOL_TEXT],
            "exercise_lines": [],
            "priority_microdose": None,
            "zero_physical_load": True,
        }

    if is_declared_combat_role(role):
        # The contact ceiling is date-driven, so a D-day the caller did not pass
        # is recovered from the role's own week before the state is resolved.
        combat = canonical_combat_render(
            role,
            d_day=d_day if d_day is not None else _week_d_day(week, role),
            athlete_snapshot=athlete_snapshot,
        )
        if combat is None:
            return None
        return {
            "authority": AUTHORITY_CANONICAL_COMBAT,
            "athlete_facing_label": combat["athlete_facing_label"],
            "body_lines": _append_microdose_once(role, [combat["note"]]),
            "exercise_lines": [],
            "contact_load": combat["contact_load"],
            "priority_microdose": role.get("priority_microdose")
            if isinstance(role.get("priority_microdose"), dict)
            else None,
            "zero_physical_load": False,
        }

    display_text = str(role.get("display_text") or "").strip() or str(
        display_text_fallback or ""
    ).strip()
    if display_text and has_deterministic_display_text_authority(role):
        return {
            "authority": AUTHORITY_DETERMINISTIC_DISPLAY_TEXT,
            "athlete_facing_label": label,
            "body_lines": _append_microdose_once(role, _body_lines(display_text)),
            "exercise_lines": [],
            "priority_microdose": role.get("priority_microdose")
            if isinstance(role.get("priority_microdose"), dict)
            else None,
            "zero_physical_load": bool(
                str(role.get("support_insert_cost_category") or "") == "zero_cost"
                or _governance(role).get("meaningful_stress") is False
            ),
        }

    lines = _closed_membership_lines(role)
    if lines:
        return {
            "authority": AUTHORITY_CLOSED_SELECTED_ASSIGNMENTS,
            "athlete_facing_label": label,
            "body_lines": _append_microdose_once(role, list(lines)),
            "exercise_lines": list(lines),
            "selected_count": len(lines),
            "priority_microdose": role.get("priority_microdose")
            if isinstance(role.get("priority_microdose"), dict)
            else None,
            "zero_physical_load": False,
        }

    return None


__all__ = [
    "AUTHORITY_CANONICAL_COMBAT",
    "AUTHORITY_CLOSED_SELECTED_ASSIGNMENTS",
    "AUTHORITY_DETERMINISTIC_DISPLAY_TEXT",
    "AUTHORITY_FIGHT_DAY_PROTOCOL",
    "authoritative_render_for_role",
    "has_deterministic_display_text_authority",
    "priority_microdose_line",
]
