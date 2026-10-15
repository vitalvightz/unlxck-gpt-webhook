"""Recover missing coaching on saved generated cards without changing doses."""
from copy import deepcopy
from typing import Any
import re

from fightcamp.calendar_context import role_d_day
from fightcamp.coaching_copy import concise_coaching
from fightcamp.exercise_coaching import (
    exercise_coaching, is_profile_progression, is_profile_regression, is_profile_cue,
    is_execution_quality_instruction,
)
from fightcamp.exercise_progression import (
    authored_progression_matches, build_progression_context,
    numerical_guidance, occurrence_key,
)
from fightcamp.structured_session_identity import deterministic_session_id, identity_tokens


def _matching_assignment(candidates, session, day):
    """Never borrow context from a second occurrence of the same exercise."""
    if len(candidates) == 1:
        return candidates[0]
    session_id = str(session.get("session_id") or "").lower()
    exact = [c for c in candidates if session_id == deterministic_session_id(c[0], day)]
    if len(exact) == 1:
        return exact[0]
    title = identity_tokens(session.get("title"))
    exact = [c for c in candidates if title and title == identity_tokens(c[0].get("athlete_facing_label"))]
    if len(exact) == 1:
        return exact[0]
    # Converter ids sometimes retain the role key; use it only when unique.
    exact = [c for c in candidates if c[0].get("role_key")
             and str(c[0]["role_key"]).lower() in session_id]
    return exact[0] if len(exact) == 1 else None


def _visible_dose(block: dict, authority: dict) -> dict:
    """Current card quantities are unchanged; never assume an unknown range/load."""
    dose = dict(authority)
    for key in ("sets", "reps", "rounds", "duration", "work", "distance", "rest"):
        value = block.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            number, unit = value.get("value"), str(value.get("unit") or "")
            if isinstance(number, (int, float)):
                dose[key] = number * (60 if unit.startswith("min") else 1)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            dose[key] = value
        else:
            dose.pop(key, None)
    load = block.get("load")
    if isinstance(load, dict) and isinstance(load.get("value"), (int, float)):
        unit = load.get("unit")
        if unit in {"kg", "lb"}:
            dose.update(load=load["value"], load_unit=unit)
        elif load.get("method") == "percentage" and load.get("ref") == "1RM":
            dose.update(load=load["value"], load_unit="% 1RM")
    effort = block.get("effort")
    if isinstance(effort, dict) and effort.get("method") == "RPE":
        dose["rpe"] = effort.get("value")
    return dose


def _recover_programming(block: dict, assignment: dict, context: dict | None, fields: dict) -> None:
    if context is None:
        return
    dose = _visible_dose(block, context["current"]["dose"])
    block["coaching_cues"] = block.get("coaching_cues") or []
    guidance = numerical_guidance(context, dose, context["current"]["prescription"])
    existing = str(block.get("progression_rule") or "")
    if existing and is_execution_quality_instruction(existing) and not is_profile_progression(existing):
        if not _has_cue(block, existing):
            block["coaching_cues"].append(existing)
    # Reconcile a numeric next-step only when it is in the planner schedule.
    # Otherwise keep a computed non-increasing maintenance line from
    # exercise_coaching, never the converter's invented load progression.
    block.pop("progression_rule", None)
    if guidance.get("progression_rule"):
        bank = str(assignment.get("progression_rule") or "")
        if not bank and (m := re.search(r"^\s*Progress(?:ion)?\s*:\s*(.+)$",
                                        str(assignment.get("coaching_notes") or ""), re.I | re.M)):
            bank = m[1]
        approved = next((rule for rule in (bank, existing) if rule
                         and authored_progression_matches(rule, guidance, context["next"]["dose"])), None)
        block["progression_rule"] = approved or guidance["progression_rule"]
    if not block.get("progression_rule") and fields.get("progression_rule"):
        block["progression_rule"] = fields["progression_rule"]
    # Existing actionable Easier advice owns the card. Never append another
    # description of the same reduction (including "reps per set to 1").
    authored = assignment.get("regression_options") or re.search(
        r"^\s*(?:Easier|Regression)\s*:", str(assignment.get("coaching_notes") or ""), re.I | re.M)
    if authored and all(is_profile_regression(x) for x in block.get("regression_options") or []):
        block["regression_options"] = fields["regression_options"]


def _has_cue(block: dict, text: str) -> bool:
    return any(re.sub(r"^Cue:\s*", "", cue, flags=re.I) == text
               for cue in block.get("coaching_cues") or [])


def recover_selected_coaching(plan: dict[str, Any], brief: dict[str, Any],
                              progression_context: dict | None = None) -> dict[str, Any]:
    if not brief or brief.get("custom_plan"):
        return plan
    selected = {}
    for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
        for role in week.get("session_roles") or []:
            day = role_d_day(week, role)
            if day is None:
                continue
            for assignment in role.get("selected_exercise_assignments") or []:
                name = str(assignment.get("name") or "").casefold()
                key = str(assignment.get("exercise_key") or "")
                candidate = (role, week, assignment)
                for identity in {name, key} - {""}:
                    selected.setdefault((day, identity), []).append(candidate)
    if not selected:
        return plan
    if progression_context is None:
        progression_context = build_progression_context(brief)
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
                    if block.get("athlete_change") or block.get("prescription_source") == "athlete":
                        continue
                    candidates = selected.get((offset, str(block.get("exercise_key") or ""))) or selected.get(
                        (offset, str(block.get("display_name") or "").casefold())
                    )
                    match = _matching_assignment(candidates or [], session, offset)
                    if match is None:
                        continue  # Ambiguous legacy duplicate: preserve its existing coaching.
                    role, source_week, assignment = match
                    fields = exercise_coaching(
                        assignment, role,
                        phase=str(source_week.get("phase") or source_week.get("phase_label") or ""),
                        d_day=offset, athlete=brief.get("athlete_snapshot"),
                    )
                    authored_cue = assignment.get("coaching_cues") or re.search(
                        r"^\s*(?:Cue|Coaching cues)\s*:", str(assignment.get("coaching_notes") or ""), re.I | re.M)
                    if authored_cue and all(is_profile_cue(cue) for cue in block.get("coaching_cues") or []):
                        block["coaching_cues"] = deepcopy(fields["coaching_cues"])
                    for field, value in (fields or {}).items():
                        if value and not block.get(field):
                            block[field] = deepcopy(value)
                    _recover_programming(block, assignment, progression_context.get(
                        occurrence_key(role, assignment, offset)), fields)
                    compact = concise_coaching({k: block.get(k) for k in (
                        "coaching_cues", "regression_options", "stop_rules")})
                    block.update(compact)
    return recovered
