from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output

from ..models import PlanDetail
from ..plan_mappers import _decode_structured_text, _lookup_plan_source, _map_plan_detail
import asyncio

from ..stage2_automation import Stage2Automator, attempt_structured_plan_for_result
from ..store import AppStore


async def _attach_structured_plan(
    result: dict[str, Any],
    plan_row: dict[str, Any],
    *,
    stage2: Stage2Automator | None,
) -> dict[str, Any]:
    """Attach a structured_plan to an admin result when it became displayable.

    Uses the same canonical trigger as the automated path
    (:func:`attempt_structured_plan_for_result`): only ``ready`` /
    ``publishable_with_flags`` results with final plan_text and the env flag on
    are converted. A missing automator or any failure leaves plan_text intact and
    records ``not_attempted`` for admin debug. Never blocks the approval.
    """

    if stage2 is None:
        return result
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    result, _costs = await attempt_structured_plan_for_result(
        result,
        planning_brief=planning_brief,
        automator=stage2,
        source="admin_stage2",
    )
    return result


def _manual_stage2_result(plan_row: dict[str, Any], final_plan_text: str) -> dict[str, Any]:
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    review = review_stage2_output(planning_brief=planning_brief, final_plan_text=final_plan_text)
    next_attempt_count = int(plan_row.get("stage2_attempt_count") or 0) + 1
    had_retry_prompt = bool(str(plan_row.get("stage2_retry_text") or "").strip())

    if review["status"] == "PASS":
        return {
            "status": "ready",
            "plan_text": final_plan_text,
            "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
            "final_plan_text": final_plan_text,
            "pdf_url": None,
            "stage2_retry_text": "",
            "stage2_validator_report": review["validator_report"],
            "stage2_status": "manual_stage2_retry_pass" if had_retry_prompt else "manual_stage2_pass",
            "stage2_attempt_count": next_attempt_count,
        }

    retry = build_stage2_retry(
        stage1_result={"planning_brief": planning_brief},
        final_plan_text=final_plan_text,
        validator_report=review["validator_report"],
    )
    return {
        "status": "review_required",
        "plan_text": "",
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": final_plan_text,
        "pdf_url": None,
        "stage2_retry_text": str(retry.get("repair_prompt") or ""),
        "stage2_validator_report": review["validator_report"],
        "stage2_status": "manual_stage2_retry_required",
        "stage2_attempt_count": next_attempt_count,
    }


def _admin_approved_result(plan_row: dict[str, Any]) -> dict[str, Any]:
    approved_text = str(plan_row.get("final_plan_text") or plan_row.get("draft_plan_text") or plan_row.get("plan_text") or "").strip()
    if not approved_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No saved Stage 2 or draft text is available to approve.",
        )
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    validator_report = plan_row.get("stage2_validator_report") or {}
    if planning_brief:
        review = review_stage2_output(planning_brief=planning_brief, final_plan_text=approved_text)
        validator_report = review["validator_report"]
    return {
        "status": "ready",
        "plan_text": approved_text,
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": approved_text,
        "pdf_url": None,
        "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
        "stage2_validator_report": validator_report,
        "stage2_status": "admin_review_approved",
        "stage2_attempt_count": int(plan_row.get("stage2_attempt_count") or 0),
    }


async def submit_manual_stage2(
    *,
    plan_id: str,
    final_plan_text: str,
    store: AppStore,
    stage2: Stage2Automator | None = None,
) -> PlanDetail:
    plan_row = store.get_plan(plan_id)
    if not plan_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

    result = _manual_stage2_result(plan_row, final_plan_text)
    result = await _attach_structured_plan(result, plan_row, stage2=stage2)
    updated = store.update_plan_stage2(plan_id, result)
    return _map_plan_detail(
        updated,
        include_admin=True,
        plan_source=_lookup_plan_source(store, plan_id),
    )


async def approve_review_required_plan(
    *,
    plan_id: str,
    store: AppStore,
    stage2: Stage2Automator | None = None,
) -> PlanDetail:
    plan_row = store.get_plan(plan_id)
    if not plan_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

    result = _admin_approved_result(plan_row)
    result = await _attach_structured_plan(result, plan_row, stage2=stage2)
    updated = store.update_plan_stage2(plan_id, result)
    return _map_plan_detail(
        updated,
        include_admin=True,
        plan_source=_lookup_plan_source(store, plan_id),
    )
