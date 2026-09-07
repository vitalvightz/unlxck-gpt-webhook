"""Bounded plan-text repair at the Stage 2 automation boundary."""
from __future__ import annotations

from typing import Any

from fightcamp.closed_conditioning_render import (
    MISSING_CODE, RENDER_REPAIR_CODES, findings_with_codes,
    restore_missing_conditioning,
)
from fightcamp.stage2_retry_contract import (
    PLANNER_FAILURE_CODES, apply_mandatory_render_guard, mandatory_findings,
)


def _finding_key(item: dict) -> tuple:
    return (item.get("code"), item.get("scheduled_d_day"), item.get("role_key"),
            item.get("exercise"), item.get("goal"), item.get("line"))


def _merge_findings(*reports: dict) -> list[dict]:
    seen = set()
    merged = []
    for report in reports:
        for item in report.get("errors", []) or []:
            if not isinstance(item, dict):
                continue
            key = _finding_key(item)
            if key not in seen:
                seen.add(key)
                merged.append(dict(item))
    return merged


def _held_review(review: dict, *, original_report: dict, reason: str,
                 attempted_text: str = "") -> dict:
    report = dict(review["validator_report"])
    report["errors"] = _merge_findings(original_report, report)
    report = apply_mandatory_render_guard(report, preserve_hold=True)
    report["render_repair_failure"] = {"reason": reason}
    if attempted_text:
        report["render_repair_failure"]["attempted_text"] = attempted_text
    return {**review, "status": "FAIL", "needs_retry": False,
            "validator_report": report}


async def run_stage2_render_repair(*, automator: Any, stage1_result: dict,
                                   planning_brief: dict, first_review: dict,
                                   first_pass_text: str, first_pass_cost: dict,
                                   reviewed_report: Any, source: str,
                                   log_context: dict | None = None) -> dict:
    """Restore known membership first, then permit at most one model repair.

    The first pass and all independent findings remain auditable. A failed
    repair never replaces the original with unverified text or triggers a third
    plan-text model call.
    """
    from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output
    from .stage2_automation import Stage2AutomationError, _merge_stage2_costs

    original_report = dict(first_review["validator_report"])
    review = first_review
    text = first_pass_text
    cost = first_pass_cost
    attempt_count = 1
    retry_text = ""
    audit: dict[str, Any] = {"status": "not_needed", "applied": [], "unresolved": []}
    codes = {item.get("code") for item in findings_with_codes(original_report, RENDER_REPAIR_CODES)}
    if not codes:
        return {"text": text, "cost": cost, "attempt_count": attempt_count,
                "retry_text": retry_text, "review": review, "audit": audit,
                "original_report": original_report}

    if original_report.get("planner_preflight_failed"):
        audit["status"] = "planner_preflight_failed"
        return {"text": text, "cost": cost, "attempt_count": 1,
                "retry_text": "", "review": review, "audit": audit,
                "original_report": original_report}

    # A partial or empty response cannot be a safe source for in-place repair.
    if not text.strip() or "stage2_output_truncated" in codes:
        audit["status"] = "incomplete_source"
        review = _held_review(review, original_report=original_report, reason="incomplete_source")
        return {"text": text, "cost": cost, "attempt_count": 1,
                "retry_text": "", "review": review, "audit": audit,
                "original_report": original_report}

    if MISSING_CODE in codes:
        restoration = restore_missing_conditioning(
            planning_brief=planning_brief, final_plan_text=text,
            validator_report=original_report,
        )
        audit["applied"] = restoration.get("applied") or []
        audit["unresolved"] = restoration.get("unresolved") or []
        if restoration["text"] != text:
            candidate = restoration["text"]
            candidate_review = reviewed_report(review_stage2_output(
                planning_brief=planning_brief, final_plan_text=candidate,
            ))
            remaining = findings_with_codes(candidate_review["validator_report"],
                                            frozenset({MISSING_CODE}))
            if not remaining:
                text = candidate
                review = candidate_review
                audit["status"] = "deterministic_applied"
            else:
                audit["status"] = "deterministic_revalidation_failed"
                audit["unresolved"].extend(remaining)

    retry = build_stage2_retry(
        stage1_result=stage1_result, final_plan_text=text,
        validator_report=review["validator_report"],
    )
    retry_text = str(retry.get("repair_prompt") or "")
    if retry.get("requires_planner_regeneration"):
        audit["requires_planner_regeneration"] = True
    if retry.get("needs_retry") and retry_text:
        try:
            candidate, repair_cost = await automator._generate_text(
                retry_text, attempt_label="effective_dose_repair", source=source,
                log_context=log_context,
            )
        except Stage2AutomationError as exc:
            attempt_count = 2
            cost = _merge_stage2_costs(first_pass_cost, exc.stage2_cost)
            audit["status"] = "model_request_failed"
            review = _held_review(review, original_report=original_report,
                                  reason="model_request_failed")
        else:
            attempt_count = 2
            cost = _merge_stage2_costs(first_pass_cost, repair_cost)
            if repair_cost.get("stage2_incomplete_response"):
                audit["status"] = "model_incomplete"
                review = _held_review(review, original_report=original_report,
                                      reason="model_incomplete", attempted_text=candidate)
            else:
                candidate_review = reviewed_report(review_stage2_output(
                    planning_brief=planning_brief, final_plan_text=candidate,
                ))
                candidate_report = candidate_review["validator_report"]
                remaining = findings_with_codes(candidate_report, RENDER_REPAIR_CODES)
                original_keys = {_finding_key(item) for item in mandatory_findings(original_report)}
                new_hard = [item for item in mandatory_findings(candidate_report)
                            if _finding_key(item) not in original_keys
                            and item.get("code") not in PLANNER_FAILURE_CODES]
                if remaining or new_hard:
                    audit["status"] = "model_revalidation_failed"
                    audit["unresolved"] = [*remaining, *new_hard]
                    review = _held_review(review, original_report=original_report,
                                          reason="model_revalidation_failed",
                                          attempted_text=candidate)
                else:
                    text = candidate
                    review = candidate_review
                    audit["status"] = "model_applied"
    elif findings_with_codes(review["validator_report"], RENDER_REPAIR_CODES):
        audit["status"] = "planner_or_authority_required"
        audit["unresolved"] = findings_with_codes(review["validator_report"], RENDER_REPAIR_CODES)
        # No legitimate render prompt exists. Preserve the source, not an
        # invented repair or a new model attempt.
        review = _held_review(review, original_report=original_report,
                              reason="planner_or_authority_required")

    return {"text": text, "cost": cost, "attempt_count": attempt_count,
            "retry_text": retry_text, "review": review, "audit": audit,
            "original_report": original_report}
