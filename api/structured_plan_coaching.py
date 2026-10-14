"""Recover missing coaching on saved generated cards without changing doses."""
from copy import deepcopy
from typing import Any

from fightcamp.calendar_context import role_d_day
from fightcamp.exercise_coaching import exercise_coaching


def recover_selected_coaching(plan: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    if not brief or brief.get("custom_plan"):
        return plan
    selected = {}
    for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
        for role in week.get("session_roles") or []:
            day = role_d_day(week, role)
            if day is None:
                continue
            for assignment in role.get("selected_exercise_assignments") or []:
                fields = exercise_coaching(
                    assignment, role, phase=str(week.get("phase") or week.get("phase_label") or ""),
                    d_day=day, athlete=brief.get("athlete_snapshot"),
                )
                name = str(assignment.get("name") or "").casefold()
                key = str(assignment.get("exercise_key") or "")
                selected[day, name] = fields
                if key:
                    selected[day, key] = fields
    if not selected:
        return plan
    # Never mutate the persisted object, which other services may still hold.
    recovered = deepcopy(plan)
    for week in recovered.get("weeks") or []:
        for day in week.get("days") or []:
            label = str(day.get("countdown_label") or "")
            if not label.startswith("D-") or not label[2:].isdigit():
                continue
            offset = int(label[2:])
            for session in day.get("sessions") or []:
                for block in session.get("blocks") or []:
                    fields = selected.get((offset, str(block.get("exercise_key") or ""))) or selected.get(
                        (offset, str(block.get("display_name") or "").casefold())
                    )
                    for field, value in (fields or {}).items():
                        if value and not block.get(field):
                            block[field] = deepcopy(value)
    return recovered
