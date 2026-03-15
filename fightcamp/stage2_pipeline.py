from __future__ import annotations

from typing import Any

from .stage2_repair import build_stage2_repair_prompt
from .stage2_validator import validate_stage2_output


_STATUS_READY = "READY"
_STATUS_PASS = "PASS"
_STATUS_WARN = "WARN"
_STATUS_FAIL = "FAIL"



def _require_dict(value: Any, *, name: str) -> dict:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a dict")
    return value



def _require_stage1_field(stage1_result: dict, field: str) -> Any:
    if field not in stage1_result:
        raise KeyError(f"stage1_result missing required field: {field}")
    return stage1_result[field]



def _count_candidate_slots(planning_brief: dict) -> int:
    total = 0
    for phase_pool in (planning_brief.get("candidate_pools") or {}).values():
        total += len(phase_pool.get("strength_slots", []) or [])
        total += len(phase_pool.get("conditioning_slots", []) or [])
        total += len(phase_pool.get("rehab_slots", []) or [])
    return total



def _review_status(validator_report: dict) -> str:
    if validator_report.get("errors"):
        return _STATUS_FAIL
    if validator_report.get("warnings"):
        return _STATUS_WARN
    return _STATUS_PASS



def _build_review_summary(validator_report: dict, status: str) -> tuple[str, list[str]]:
    errors = list(validator_report.get("errors", []) or [])
    warnings = list(validator_report.get("warnings", []) or [])
    summary_parts: list[str] = []
    detail_lines: list[str] = []

    if errors:
        summary_parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
        for error in errors:
            if error.get("code") == "restriction_violation":
                detail_lines.append(
                    f"Remove or replace restricted line '{error.get('line', '')}' ({error.get('restriction', 'unknown restriction')})."
                )
            else:
                detail_lines.append(str(error.get("message", "Unknown validation error.")))

    if warnings:
        summary_parts.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
        for warning in warnings:
            if warning.get("code") == "missing_required_element":
                phase = warning.get("phase", "Unknown phase")
                requirement = str(warning.get("requirement", "required element")).replace("_", " ")
                detail_lines.append(f"Restore {requirement} in {phase}.")
            elif warning.get("code") == "weak_anchor_session":
                detail_lines.append(
                    f"Strength session quality drifted in {warning.get('phase', 'Unknown phase')} session {warning.get('session_index', '?')}; restore a real anchor."
                )
            elif warning.get("code") == "support_takeover_before_anchor":
                detail_lines.append(
                    f"Move support work behind the anchor in {warning.get('phase', 'Unknown phase')} session {warning.get('session_index', '?')}."
                )
            elif warning.get("code") == "conditional_conditioning_choice":
                detail_lines.append("Resolve conditioning choices into one primary prescription and at most one fallback.")
            elif warning.get("code") == "too_many_fallbacks":
                detail_lines.append("Collapse extra fallback branches so the session reads like a final prescription.")
            elif warning.get("code") == "unresolved_access_fallback":
                detail_lines.append("Remove fallback branches unless a real unresolved access contingency remains.")
            elif warning.get("code") == "template_like_session_render":
                detail_lines.append("Rewrite template-like session blocks into one clean athlete-facing prescription.")
            elif warning.get("code") == "taper_option_overload":
                detail_lines.append("Simplify taper sessions so they stay short, decisive, and low-noise.")
            elif warning.get("code") == "equipment_incongruent_selection":
                detail_lines.append("Replace equipment-invalid selections with same-role options that match the athlete profile.")
            elif warning.get("code") == "missing_week_session_role":
                detail_lines.append("Restore the missing weekly session role so each active week stays structurally complete.")
            elif warning.get("code") == "late_camp_session_incomplete":
                detail_lines.append("Restore late-camp week structure so the final weeks stay complete and athlete-ready.")
            elif warning.get("code") == "weekly_rhythm_broken":
                detail_lines.append("Restore the default boxer weekly rhythm with recovery immediately before the primary strength day.")
            elif warning.get("code") in {"gimmick_name", "overstyled_drill_name"}:
                detail_lines.append("Replace overstyled drill naming with plain coach-readable language.")
            elif warning.get("code") == "sport_language_leak":
                detail_lines.append("Rewrite cross-sport language so the plan reads cleanly for the athlete's sport.")
            else:
                detail_lines.append(str(warning.get("message", "Unknown validation warning.")))

    if status == _STATUS_PASS:
        summary = "PASS: final plan cleared validation."
    elif status == _STATUS_WARN:
        summary = "WARN: final plan is usable but missing some phase-critical structure"
        if summary_parts:
            summary += f" ({', '.join(summary_parts)})."
        else:
            summary += "."
    else:
        summary = "FAIL: final plan needs revision before use"
        if summary_parts:
            summary += f" ({', '.join(summary_parts)})."
        else:
            summary += "."

    return summary, detail_lines



def build_stage2_package(*, stage1_result: dict) -> dict:
    stage1_result = _require_dict(stage1_result, name="stage1_result")
    planning_brief = _require_dict(_require_stage1_field(stage1_result, "planning_brief"), name="planning_brief")
    stage2_payload = _require_dict(_require_stage1_field(stage1_result, "stage2_payload"), name="stage2_payload")
    handoff_text = str(_require_stage1_field(stage1_result, "stage2_handoff_text") or "")

    phase_count = len((planning_brief.get("phase_strategy") or {}).keys())
    restriction_count = len((planning_brief.get("restrictions") or []))
    slot_count = _count_candidate_slots(planning_brief)

    return {
        "status": _STATUS_READY,
        "planning_brief": planning_brief,
        "stage2_payload": stage2_payload,
        "handoff_text": handoff_text,
        "draft_plan_text": str(stage1_result.get("plan_text", "") or ""),
        "coach_notes": str(stage1_result.get("coach_notes", "") or ""),
        "summary": f"Stage 2 package ready: {phase_count} phase(s), {restriction_count} restriction(s), {slot_count} candidate slot(s).",
    }



def review_stage2_output(*, planning_brief: dict, final_plan_text: str) -> dict:
    planning_brief = _require_dict(planning_brief, name="planning_brief")
    validator_report = validate_stage2_output(
        planning_brief=planning_brief,
        final_plan_text=final_plan_text,
    )
    status = _review_status(validator_report)
    summary, summary_lines = _build_review_summary(validator_report, status)
    return {
        "status": status,
        "validator_report": validator_report,
        "summary": summary,
        "summary_lines": summary_lines,
        "needs_retry": status != _STATUS_PASS,
    }



def build_stage2_retry(
    *,
    stage1_result: dict,
    final_plan_text: str,
    validator_report: dict | None = None,
) -> dict:
    stage1_result = _require_dict(stage1_result, name="stage1_result")
    planning_brief = _require_dict(_require_stage1_field(stage1_result, "planning_brief"), name="planning_brief")

    if validator_report is None:
        review = review_stage2_output(planning_brief=planning_brief, final_plan_text=final_plan_text)
        validator_report = review["validator_report"]
        status = review["status"]
        summary = review["summary"]
        summary_lines = review["summary_lines"]
    else:
        validator_report = _require_dict(validator_report, name="validator_report")
        status = _review_status(validator_report)
        summary, summary_lines = _build_review_summary(validator_report, status)

    if status == _STATUS_PASS:
        return {
            "status": status,
            "validator_report": validator_report,
            "summary": summary,
            "summary_lines": summary_lines,
            "needs_retry": False,
            "repair_prompt": None,
        }

    repair_prompt = build_stage2_repair_prompt(
        planning_brief=planning_brief,
        failed_plan_text=final_plan_text,
        validator_report=validator_report,
    )
    return {
        "status": status,
        "validator_report": validator_report,
        "summary": summary,
        "summary_lines": summary_lines,
        "needs_retry": True,
        "repair_prompt": repair_prompt,
    }
