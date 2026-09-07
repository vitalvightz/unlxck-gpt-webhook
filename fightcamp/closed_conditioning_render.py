"""Source-backed repair of closed conditioning assignments.

This module does not select exercises, change doses, or create sessions. It
restores only already-authorised work on an unambiguous existing calendar day.
"""
from __future__ import annotations

import json
import re
from typing import Any

MISSING_CODE = "missing_selected_conditioning_assignment"
RENDER_REPAIR_CODES = frozenset({
    MISSING_CODE,
    "goal_preservation_render_mismatch",
    "late_camp_effective_prescription_exceeded",
})


def findings_with_codes(report: dict, codes: set[str] | frozenset[str]) -> list[dict]:
    seen: set[tuple] = set()
    result: list[dict] = []
    for field in ("errors", "blocking_warnings", "warnings", "review_flags"):
        for item in report.get(field, []) or []:
            if not isinstance(item, dict) or item.get("code") not in codes:
                continue
            identity = (item.get("code"), item.get("scheduled_d_day"),
                        item.get("role_key"), item.get("exercise"),
                        item.get("line"), item.get("goal"))
            if identity not in seen:
                seen.add(identity)
                result.append(dict(item))
    return result


def _dose_text(assignment: dict) -> str:
    value = assignment.get("effective_prescription")
    if isinstance(value, dict):
        value = value.get("display") or value.get("dose") or value.get("text")
    return str(value or "").strip()


def _selected_roles(brief: dict):
    from .stage2_validator import _scheduled_role_d_day
    for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
        if not isinstance(week, dict):
            continue
        for role in week.get("session_roles") or []:
            if not isinstance(role, dict) or role.get("render_mandatory") is False:
                continue
            if str(role.get("category") or "").lower() != "conditioning":
                continue
            assignments = role.get("selected_exercise_assignments")
            if not isinstance(assignments, list) or not assignments:
                continue
            day = _scheduled_role_d_day(week, role)
            if day is not None:
                yield week, role, day, assignments


def restore_missing_conditioning(*, planning_brief: dict, final_plan_text: str,
                                 validator_report: dict) -> dict[str, Any]:
    """Atomically restore complete assignments inside an existing owned card.

    A missing week, ambiguous day, incomplete dose, or explicit safety conflict
    is not repaired by guessing. The original text is retained in those cases.
    """
    from .stage2_pipeline import (
        _week_section_layout, _normalise_render_match_text, _canonical_weekday,
    )
    from .stage2_validator import _line_has_exercise

    missing = findings_with_codes(validator_report, frozenset({MISSING_CODE}))
    if not missing:
        return {"text": final_plan_text, "applied": [], "unresolved": []}
    lines = final_plan_text.splitlines()
    layout = _week_section_layout(lines)
    pending: list[tuple[int, list[str]]] = []
    applied: list[dict] = []
    unresolved: list[dict] = []
    handled: set[tuple] = set()
    header_re = re.compile(r"^\s*(?:#{1,6}\s*)?D-(\d{1,2})\s*\(([^)]+)\)\s*[—–:-]\s*(.+)$", re.I)
    for week, role, day, assignments in _selected_roles(planning_brief):
        relevant = [f for f in missing if f.get("scheduled_d_day") == day
                    and f.get("role_key") == role.get("role_key")]
        if not relevant:
            continue
        identity = (week.get("week_index"), role.get("role_key"), day)
        handled.add(identity)
        reason = None
        section = layout.get(week.get("week_index"))
        if not section:
            reason = "canonical_week_missing"
        elif role.get("late_fight_tail_owned") or day <= 13:
            reason = "late_fight_contract_owned"
        elif any(not isinstance(a, dict) or not str(a.get("name") or "").strip()
                 or not _dose_text(a) for a in assignments):
            reason = "incomplete_assignment_authority"
        elif len({str(a.get("name")).strip().lower() for a in assignments}) != len(assignments):
            reason = "duplicate_assignment_identity"
        elif any(f.get("code") in {"restriction_violation", "late_fight_countdown_blocked_drill",
                                           "late_fight_window_forbidden_exercise", "late_camp_effective_prescription_exceeded"}
                 and (f.get("scheduled_d_day") == day or f.get("scheduled_d_day") is None)
                 for f in findings_with_codes(validator_report, frozenset({
                     "restriction_violation", "late_fight_countdown_blocked_drill",
                     "late_fight_window_forbidden_exercise", "late_camp_effective_prescription_exceeded"}))):
            reason = "safety_finding_requires_review"
        if reason:
            unresolved.append({"week_index": week.get("week_index"), "role_key": role.get("role_key"),
                               "scheduled_d_day": day, "reason": reason})
            continue
        start = section["header_idx"] + 1
        end = section["section_end"]
        expected_weekday = _canonical_weekday(role.get("scheduled_day_hint"))
        matches: list[tuple[int, int, str]] = []
        for index in range(start, end):
            match = header_re.match(lines[index])
            if not match or int(match.group(1)) != day:
                continue
            if expected_weekday and _canonical_weekday(match.group(2)) != expected_weekday:
                continue
            next_index = next((j for j in range(index + 1, end)
                              if header_re.match(lines[j]) or re.match(r"^\s*#{1,6}\s+", lines[j])), end)
            matches.append((index, next_index, match.group(3)))
        if len(matches) != 1:
            unresolved.append({"week_index": week.get("week_index"), "role_key": role.get("role_key"),
                               "scheduled_d_day": day, "reason": "missing_or_ambiguous_day"})
            continue
        start, end, title = matches[0]
        # A same-day stacked session must not receive another role's work.
        day_roles = [r for r in week.get("session_roles") or [] if isinstance(r, dict)
                     and _scheduled_day(week, r) == day]
        if len(day_roles) > 1:
            label = str(role.get("athlete_facing_label") or "").strip()
            if not label or _normalise_render_match_text(title) != _normalise_render_match_text(label):
                unresolved.append({"week_index": week.get("week_index"), "role_key": role.get("role_key"),
                                   "scheduled_d_day": day, "reason": "ambiguous_role_ownership"})
                continue
        body = lines[start + 1:end]
        names = [str(a["name"]).strip() for a in assignments]
        present = [any(_line_has_exercise(line, name) for line in body) for name in names]
        # A reported omission that is already present needs no second copy.
        additions = [f"- {name}: {_dose_text(a)}" for a, name, exists in zip(assignments, names, present)
                     if not exists]
        if not additions:
            continue
        # Put new work before trailing coaching/stop notes; never make new days.
        insert_at = end
        for index in range(start + 1, end):
            if re.match(r"^\s*(?:[-*]\s*)?(?:Easier|Stop|Coach(?:'s)? (?:call|note)|Progression|Regression)\s*:", lines[index], re.I):
                insert_at = index
                break
        pending.append((insert_at, additions))
        applied.extend({"week_index": week.get("week_index"), "role_key": role.get("role_key"),
                        "scheduled_d_day": day, "exercise": name}
                       for name, exists in zip(names, present) if not exists)
    # Never silently discard a finding that could not be bound to one source role.
    for finding in missing:
        if not any(entry.get("scheduled_d_day") == finding.get("scheduled_d_day")
                   and entry.get("role_key") == finding.get("role_key") for entry in applied):
            if not any(entry.get("scheduled_d_day") == finding.get("scheduled_d_day")
                       and entry.get("role_key") == finding.get("role_key") for entry in unresolved):
                unresolved.append({"scheduled_d_day": finding.get("scheduled_d_day"),
                                   "role_key": finding.get("role_key"), "reason": "unresolved_assignment"})
    if unresolved:
        return {"text": final_plan_text, "applied": [], "unresolved": unresolved}
    for index, additions in sorted(pending, key=lambda item: item[0], reverse=True):
        lines[index:index] = additions
    return {"text": "\n".join(lines), "applied": applied, "unresolved": []}


def _scheduled_day(week: dict, role: dict) -> int | None:
    from .stage2_validator import _scheduled_role_d_day
    return _scheduled_role_d_day(week, role)


def build_closed_conditioning_repair_prompt(*, planning_brief: dict,
                                            failed_plan_text: str,
                                            validator_report: dict) -> str:
    """A small render-only packet, without candidate pools or reselection menus."""
    from .stage2_finalizer_packet import build_stage2_finalizer_packet
    from .stage2_policy import prompt_safe_validator_report
    packet = build_stage2_finalizer_packet(stage2_payload={}, planning_brief=planning_brief)
    safe_report = prompt_safe_validator_report(validator_report)
    # Preserve the new membership code even in installations with older policy JSON.
    safe_report["errors"] = [*safe_report.get("errors", []), *findings_with_codes(
        validator_report, frozenset({MISSING_CODE}))]
    instructions = (
        "Repair only rendering defects in the previous athlete-facing plan. "
        "The selected exercise assignments are closed and authoritative. Render every "
        "selected conditioning exercise on its existing scheduled day, with its exact "
        "effective prescription. One prescription per exercise does not mean one "
        "exercise per session. Never choose alternates, add sessions, move exercises, "
        "increase dose, or invent goal evidence. Preserve existing legal content. "
        "Do not repair genuine planner goal failures by inventing work. Preserve every "
        "safety, injury, contact, taper, and calendar constraint. If a required item "
        "is illegal or its authority is incomplete, leave it out and do not replace it. "
        "Do not reconstruct a missing canonical week or ambiguous day. Return only "
        "the revised athlete-facing plan."
    )
    sections = [instructions, "FINALIZER PACKET\n" + json.dumps(packet, ensure_ascii=False),
                "RENDER FINDINGS\n" + json.dumps(safe_report, ensure_ascii=False),
                "PREVIOUS FINAL PLAN\n" + failed_plan_text]
    return "\n\n---\n\n".join(sections)
