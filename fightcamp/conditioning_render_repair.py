"""Narrow authority checks for rendering already-selected conditioning work.

No exercise selection, dose calculation, or calendar construction occurs here.
The general Stage 2 quality policy is unchanged; mandatory planner and safety
failures retain their existing explicit hold at the automatic release boundary.
"""
from __future__ import annotations

import json
from typing import Any

from .stage2_policy import apply_stage2_release_policy, is_hard_stage2_blocker
from .stage2_validator import _scheduled_role_d_day

MISSING_CODE = "missing_selected_conditioning_assignment"
PLANNER_CODES = frozenset({
    "goal_preservation_failed", "goal_preservation_contract_stale",
    "missing_late_camp_effective_strength_authority",
    "selected_exercise_phase_unresolved", "selected_exercise_phase_ineligible",
    "selected_exercise_late_window_ineligible", "selected_loaded_exercise_forbidden",
    "late_physical_role_missing_assignment", "missing_selected_conditioning_authority",
})
RENDER_CODES = frozenset({
    MISSING_CODE, "goal_preservation_render_mismatch",
    "late_camp_effective_prescription_exceeded",
})


def findings(report: dict, codes: set[str] | frozenset[str]) -> list[dict]:
    seen = set()
    result = []
    for field in ("errors", "blocking_warnings", "warnings", "review_flags"):
        for item in report.get(field, []) or []:
            if not isinstance(item, dict) or item.get("code") not in codes:
                continue
            key = (item.get("code"), item.get("scheduled_d_day"), item.get("role_key"),
                   item.get("exercise"), item.get("goal"), item.get("line"))
            if key not in seen:
                seen.add(key)
                result.append(dict(item))
    return result


def mandatory_release_report(report: dict, *, preserve_hold: bool = False) -> dict:
    """Keep genuine mandatory failures held without changing global policy."""
    original = report if isinstance(report, dict) else {}
    result = apply_stage2_release_policy(original)
    blockers = [item for item in findings(result, {
        *(PLANNER_CODES | frozenset({MISSING_CODE, "structural_integrity_failure"})),
        *[item.get("code") for item in result.get("errors", []) or []
          if isinstance(item, dict) and is_hard_stage2_blocker(str(item.get("code") or ""))],
        *[item.get("code") for item in result.get("blocking_warnings", []) or []
          if isinstance(item, dict) and is_hard_stage2_blocker(str(item.get("code") or ""))],
    })]
    if blockers or preserve_hold or original.get("release_decision") == "hold" or original.get("planner_preflight_failed"):
        result.update(release_decision="hold", is_athlete_releasable=False,
                      is_publishable=False, mandatory_render_blockers=blockers)
    return result


def selected_missing_assignments(brief: dict, report: dict) -> tuple[list[dict], list[dict]]:
    """Resolve each missing finding to exactly one scheduled effective assignment."""
    resolved, unresolved = [], []
    for finding in findings(report, frozenset({MISSING_CODE})):
        day, name, role_key = (finding.get("scheduled_d_day"),
                               str(finding.get("exercise") or "").strip(),
                               str(finding.get("role_key") or "").strip())
        matches = []
        for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
            if not isinstance(week, dict):
                continue
            for role in week.get("session_roles") or []:
                if (not isinstance(role, dict) or role.get("render_mandatory") is False
                        or str(role.get("category") or "").lower() != "conditioning"
                        or _scheduled_role_d_day(week, role) != day
                        or str(role.get("role_key") or "").strip() != role_key):
                    continue
                for assignment in role.get("selected_exercise_assignments") or []:
                    if isinstance(assignment, dict) and str(assignment.get("name") or "").strip() == name:
                        matches.append((role, assignment))
        if len(matches) != 1:
            unresolved.append({**finding, "reason": "selected_assignment_unresolved"})
            continue
        role, assignment = matches[0]
        dose = assignment.get("effective_prescription")
        if isinstance(dose, dict):
            dose = dose.get("display") or dose.get("dose") or dose.get("text")
        dose = str(dose or "").strip()
        if not dose or not name:
            unresolved.append({**finding, "reason": "effective_dose_missing"})
            continue
        resolved.append({"scheduled_d_day": day, "role_key": role_key, "name": name,
                         "effective_prescription": dose, "slot_id": assignment.get("slot_id"),
                         "source_phase": assignment.get("source_phase")})
    return resolved, unresolved


def build_conditioning_repair_prompt(*, planning_brief: dict, failed_plan_text: str,
                                     validator_report: dict, assignments: list[dict]) -> str:
    """Use the existing complete finalizer contract, not an open candidate menu."""
    from .stage2_finalizer_packet import build_stage2_finalizer_packet
    packet = build_stage2_finalizer_packet(stage2_payload={}, planning_brief=planning_brief)
    instructions = (
        "Repair only the existing athlete-facing plan. Restore every listed selected "
        "conditioning assignment on its original scheduled day, using its exact "
        "effective prescription. One prescription per exercise does not mean one "
        "exercise per session. Closed membership overrides primary/fallback and "
        "replacement guidance. Do not add candidates, alternates, substitutes, "
        "new sessions, or extra work; do not move exercises or increase any dose. "
        "Preserve legal existing content and every restriction, recovery, sparring, "
        "calendar, and late-fight constraint in the finalizer packet. If an item "
        "is illegal or its authority is incomplete, leave it out and do not replace "
        "it. Do not invent goal coverage or rebuild missing/ambiguous weeks. "
        "Return only the revised athlete-facing plan."
    )
    return "\n\n---\n\n".join([
        instructions,
        "FINALIZER PACKET\n" + json.dumps(packet, ensure_ascii=False),
        "EXACT MISSING ASSIGNMENTS\n" + json.dumps(assignments, ensure_ascii=False),
        "VALIDATION FINDINGS\n" + json.dumps(validator_report, ensure_ascii=False),
        "PREVIOUS FINAL PLAN\n" + failed_plan_text,
    ])
