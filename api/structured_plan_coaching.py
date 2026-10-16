"""Recover missing coaching on saved generated cards without changing doses."""
from copy import deepcopy
from typing import Any
import re

from fightcamp.calendar_context import role_d_day
from fightcamp.exercise_instructions import recover_execution_instructions
from fightcamp.coaching_copy import concise_coaching
from fightcamp.exercise_coaching import (
    exercise_coaching, has_measurable_step, is_profile_progression, is_profile_cue,
)
from fightcamp.exercise_progression import (
    authored_progression_matches, build_progression_context, numerical_guidance, occurrence_key,
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


def _recover_programming(block: dict, assignment: dict, context: dict | None, fields: dict) -> None:
    if context is None:
        return
    # The converter sees the final session. Keep its short adjustments rather
    # than replacing them with a dose-difference or generic fallback algorithm.
    if context["current"]["blocked"] or is_profile_progression(str(block.get("progression_rule") or "")):
        block.pop("progression_rule", None)
    elif has_measurable_step(str(block.get("progression_rule") or "")):
        # Wording may come from the model; a numerical advance still belongs
        # to the already planned future dose. Validate with the existing
        # progression owner, without manufacturing a replacement increment.
        current = context["current"]
        guidance = numerical_guidance(context, current["dose"], current["prescription"])
        target = (context.get("next") or {}).get("dose") or {}
        if not authored_progression_matches(block["progression_rule"], guidance, target):
            block.pop("progression_rule", None)


def recover_selected_coaching(plan: dict[str, Any], brief: dict[str, Any],
                              progression_context: dict | None = None) -> dict[str, Any]:
    if brief.get("custom_plan"):
        return plan
    plan = recover_execution_instructions(plan)
    if not brief:
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
                    programming_context = progression_context.get(occurrence_key(role, assignment, offset))
                    fields = exercise_coaching(
                        assignment, role,
                        progression_context=programming_context,
                        phase=str(source_week.get("phase") or source_week.get("phase_label") or ""),
                        d_day=offset, athlete=brief.get("athlete_snapshot"),
                    )
                    authored_cue = assignment.get("coaching_cues") or re.search(
                        r"^\s*(?:Cue|Coaching cues)\s*:", str(assignment.get("coaching_notes") or ""), re.I | re.M)
                    if authored_cue and all(is_profile_cue(cue) for cue in block.get("coaching_cues") or []):
                        block["coaching_cues"] = deepcopy(fields["coaching_cues"])
                    for field, value in (fields or {}).items():
                        if field in {"progression_rule", "regression_options"}:
                            continue  # Adjustment notes are owned by the final-session LLM.
                        if value and not block.get(field):
                            block[field] = deepcopy(value)
                    _recover_programming(block, assignment, progression_context.get(
                        occurrence_key(role, assignment, offset)), fields)
                    compact = concise_coaching({k: block.get(k) for k in (
                        "coaching_cues", "regression_options", "stop_rules")})
                    block.update(compact)
    return recovered
