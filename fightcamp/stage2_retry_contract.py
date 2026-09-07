"""Stage 2 render-repair routing and narrow mandatory release authority.

The general quality policy remains observational. This boundary keeps actual
planner, safety, and closed-membership failures from being published while
allowing already-authorised rendering omissions to be repaired independently.
"""
from __future__ import annotations

from typing import Any

from .closed_conditioning_render import (
    MISSING_CODE,
    RENDER_REPAIR_CODES,
    build_closed_conditioning_repair_prompt,
    findings_with_codes,
)
from .stage2_policy import apply_stage2_release_policy, is_hard_stage2_blocker

PLANNER_FAILURE_CODES = frozenset({
    "goal_preservation_failed",
    "goal_preservation_contract_stale",
    "missing_late_camp_effective_strength_authority",
    "selected_exercise_phase_unresolved",
    "selected_exercise_phase_ineligible",
    "selected_exercise_late_window_ineligible",
    "selected_loaded_exercise_forbidden",
    "late_physical_role_missing_assignment",
})
MANDATORY_RENDER_CODES = frozenset({MISSING_CODE})


def _findings(report: dict) -> list[dict]:
    result = []
    for field in ("errors", "blocking_warnings"):
        result.extend(item for item in report.get(field, []) or [] if isinstance(item, dict))
    return result


def mandatory_findings(report: dict) -> list[dict]:
    return [item for item in _findings(report)
            if item.get("code") in MANDATORY_RENDER_CODES | PLANNER_FAILURE_CODES
            or is_hard_stage2_blocker(str(item.get("code") or ""))
            or item.get("code") == "structural_integrity_failure"]


def apply_mandatory_render_guard(report: dict, *, preserve_hold: bool = False) -> dict:
    """Apply the existing policy, then retain only explicit mandatory vetoes."""
    original = report if isinstance(report, dict) else {}
    normalized = apply_stage2_release_policy(original)
    blocking = mandatory_findings(normalized)
    if blocking or preserve_hold or original.get("release_decision") == "hold":
        normalized.update(
            release_decision="hold", is_athlete_releasable=False,
            is_publishable=False, validator_findings_observational=False,
            mandatory_render_blockers=blocking,
        )
    return normalized


def _source_backed_render_findings(brief: dict, report: dict) -> list[dict]:
    """A render retry requires a real scheduled assignment or goal witness."""
    from .stage2_validator import _scheduled_role_d_day
    valid = []
    for finding in findings_with_codes(report, RENDER_REPAIR_CODES):
        code = finding.get("code")
        day = finding.get("scheduled_d_day")
        name = str(finding.get("exercise") or "").strip()
        if not isinstance(day, int) or not name:
            continue
        if code == "goal_preservation_render_mismatch":
            witnesses = [w for goal in brief.get("goal_preservation") or []
                         if isinstance(goal, dict) for w in goal.get("evidence") or []
                         if isinstance(w, dict)]
            if any(w.get("d_day") == day and w.get("name") == name
                   and w.get("effective_prescription") for w in witnesses):
                valid.append(finding)
            continue
        for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
            if not isinstance(week, dict):
                continue
            for role in week.get("session_roles") or []:
                if not isinstance(role, dict) or _scheduled_role_d_day(week, role) != day:
                    continue
                if code == "late_camp_effective_prescription_exceeded":
                    prescriptions = role.get("effective_strength_prescriptions") or []
                    if any(p.get("name") == name and p.get("effective_prescription")
                           for p in prescriptions if isinstance(p, dict)):
                        valid.append(finding)
                        break
                else:
                    if any(a.get("name") == name and a.get("effective_prescription")
                           for a in role.get("selected_exercise_assignments") or []
                           if isinstance(a, dict)):
                        valid.append(finding)
                        break
            else:
                continue
            break
    return valid


def build_stage2_retry(*, stage1_result: dict, final_plan_text: str,
                       validator_report: dict | None = None) -> dict[str, Any]:
    """Return independent render-retry and planner-regeneration decisions."""
    from .stage2_pipeline import review_stage2_output
    from .stage2_repair import build_stage2_repair_prompt
    from .stage2_policy import prompt_safe_validator_report

    brief = stage1_result.get("planning_brief")
    if not isinstance(brief, dict):
        raise TypeError("planning_brief must be a dict")
    report = validator_report if isinstance(validator_report, dict) else review_stage2_output(
        planning_brief=brief, final_plan_text=final_plan_text)["validator_report"]
    report = apply_mandatory_render_guard(report)
    planner = findings_with_codes(report, PLANNER_FAILURE_CODES)
    if report.get("planner_preflight_failed"):
        planner.append({"code": "planner_preflight_failed"})
    render = _source_backed_render_findings(brief, report)
    missing = [f for f in render if f.get("code") == MISSING_CODE]
    has_render = bool(render)
    requires_planner = bool(planner)
    # A missing/invalid source is not permission for the model to invent it.
    unrepairable = [f for f in findings_with_codes(report, RENDER_REPAIR_CODES) if f not in render]
    if unrepairable:
        requires_planner = True
    if has_render:
        prompt = build_closed_conditioning_repair_prompt(
            planning_brief=brief, failed_plan_text=final_plan_text,
            validator_report={**report, "errors": [*render, *planner]},
        ) if missing else build_stage2_repair_prompt(
            planning_brief=brief, failed_plan_text=final_plan_text,
            validator_report=prompt_safe_validator_report(report),
        )
    else:
        prompt = None
    # Manual repair can still use the legacy general repair path for an explicit
    # non-planner hold, but automatic finalization only calls on its known codes.
    if not has_render and report.get("release_decision") == "hold" and not requires_planner:
        if not unrepairable and not mandatory_findings(report):
            prompt = build_stage2_repair_prompt(
                planning_brief=brief, failed_plan_text=final_plan_text,
                validator_report=prompt_safe_validator_report(report),
            )
    needs_retry = bool(prompt)
    status = "FAIL" if report.get("errors") else "WARN" if report.get("blocking_warnings") else "PASS"
    return {
        "status": status,
        "validator_report": report,
        "summary": "FAIL: selected goal coverage requires deterministic planner repair" if requires_planner else
                   "Stage 2 rendering repair required." if needs_retry else "Stage 2 review complete.",
        "summary_lines": [str(item.get("message") or item.get("code")) for item in _findings(report)],
        "needs_retry": needs_retry,
        "requires_planner_regeneration": requires_planner,
        "repair_prompt": prompt,
        "render_repair_findings": render,
        "unrepairable_render_findings": unrepairable,
    }
