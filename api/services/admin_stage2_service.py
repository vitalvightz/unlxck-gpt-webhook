from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import HTTPException, status
from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output

from ..models import PlanDetail
from ..plan_mappers import _decode_structured_text, _lookup_plan_source, _map_plan_detail

from ..stage2_automation import Stage2Automator, attempt_structured_plan_for_result
from ..store import AppStore

logger = logging.getLogger(__name__)

# How long the approval request will wait for the inline structured-card attempt
# before giving up and shipping the raw-markdown plan (the background task then
# finishes the card). Kept comfortably under the frontend/proxy request timeout
# so a slow conversion never surfaces as a false "Connection issue". Tunable via
# env for ops.
_APPROVAL_STRUCTURED_PLAN_BUDGET_SECONDS = 20.0


def _approval_structured_budget_seconds() -> float:
    raw = os.getenv("UNLXCK_APPROVAL_STRUCTURED_PLAN_BUDGET_SECONDS", "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return _APPROVAL_STRUCTURED_PLAN_BUDGET_SECONDS
    # Only a finite, positive budget is usable: inf would make wait_for() block
    # forever and nan compares False, so both fall back to the default.
    return value if 0 < value < float("inf") else _APPROVAL_STRUCTURED_PLAN_BUDGET_SECONDS


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


async def _attach_structured_plan_within_budget(
    result: dict[str, Any],
    plan_row: dict[str, Any],
    *,
    stage2: Stage2Automator | None,
) -> dict[str, Any]:
    """Attempt the structured card inline, but never let it stall the approval.

    Tries the conversion within a bounded time budget so the admin gets the live
    card with the approval response whenever it is fast enough. On timeout (or
    any failure) the raw-markdown ``result`` is returned unchanged and the
    deferred :func:`run_structured_plan_post_processing` background task finishes
    the card out-of-band. This is the "card first, fall back to text" contract.
    """

    if stage2 is None:
        return result
    budget = _approval_structured_budget_seconds()
    try:
        return await asyncio.wait_for(
            _attach_structured_plan(result, plan_row, stage2=stage2),
            timeout=budget,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "inline structured-plan attempt exceeded %.1fs budget for plan_id=%s; deferring to background",
            budget,
            plan_row.get("id"),
        )
        return result
    except Exception:  # noqa: BLE001 - approval must never fail on the inline attempt
        logger.exception(
            "inline structured-plan attempt failed for plan_id=%s; deferring to background",
            plan_row.get("id"),
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
    """Release a held/review-required plan to the athlete view.

    The approved plan is the structured card whenever one can be built in time:
    the conversion is attempted inline within a bounded budget
    (:func:`_attach_structured_plan_within_budget`) so the live card ships with
    the approval response in the common case. If the conversion is too slow or
    fails, the plan still releases immediately with ``plan_text`` populated (the
    athlete view falls back to raw markdown) and the deferred
    :func:`run_structured_plan_post_processing` background task finishes the card
    out-of-band. The bounded budget keeps the admin click well under the
    frontend/proxy request timeout that previously surfaced as a false
    "Connection issue".
    """

    plan_row = store.get_plan(plan_id)
    if not plan_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

    result = _admin_approved_result(plan_row)
    result = await _attach_structured_plan_within_budget(result, plan_row, stage2=stage2)
    updated = store.update_plan_stage2(plan_id, result)
    return _map_plan_detail(
        updated,
        include_admin=True,
        plan_source=_lookup_plan_source(store, plan_id),
    )


async def run_structured_plan_post_processing(
    *,
    plan_id: str,
    store: AppStore,
    stage2: Stage2Automator | None = None,
) -> None:
    """Best-effort, non-blocking structured-plan conversion for an approved plan.

    The fallback for approval's inline attempt: it runs after the response has
    been returned (e.g. as a FastAPI background task) and finishes the card for
    any plan whose inline conversion timed out or failed. Re-reads the freshly
    approved row, attempts the structured conversion through the canonical
    trigger (which short-circuits when the row already carries a card), and
    persists ``structured_plan`` only when one is actually produced. Never
    raises: any failure leaves the raw markdown fallback intact.

    The model conversion can take seconds, during which a concurrent admin action
    (reject, archive, rename, manual Stage 2 edit) may rewrite the plan's status /
    plan_text / stage2 fields. To avoid clobbering that newer state with the stale
    snapshot read here, persistence goes through
    :meth:`AppStore.update_plan_structured_output`, which writes *only* the
    structured-plan output columns and never the status/text/attempt fields. The
    synchronous store calls run in worker threads so the event loop is never
    blocked while this background task is in flight.
    """

    if stage2 is None:
        return
    try:
        plan_row = await asyncio.to_thread(store.get_plan, plan_id)
        if not plan_row:
            return
        result = {
            "status": str(plan_row.get("status") or ""),
            "plan_text": str(plan_row.get("plan_text") or ""),
            "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
            "final_plan_text": str(plan_row.get("final_plan_text") or plan_row.get("plan_text") or ""),
            "pdf_url": plan_row.get("pdf_url"),
            "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
            "stage2_validator_report": plan_row.get("stage2_validator_report") or {},
            "stage2_status": str(plan_row.get("stage2_status") or ""),
            "stage2_attempt_count": int(plan_row.get("stage2_attempt_count") or 0),
            # Carry any card the inline approval attempt already produced so the
            # canonical trigger is idempotent: a plan that is already converted
            # short-circuits here instead of paying for a redundant model call.
            "structured_plan": plan_row.get("structured_plan"),
        }
        result = await _attach_structured_plan(result, plan_row, stage2=stage2)
        # Only write when a structured plan was actually produced; a skip/failure
        # keeps the existing raw markdown row untouched. Persist via the narrow
        # structured-output writer so we never overwrite status/plan_text/stage2
        # fields that a concurrent admin action may have changed mid-conversion.
        if result.get("structured_plan") is not None:
            await asyncio.to_thread(
                store.update_plan_structured_output,
                plan_id,
                structured_plan=result.get("structured_plan"),
                schema_version=result.get("schema_version"),
                stage2_validator_report=result.get("stage2_validator_report") or {},
            )
    except Exception:  # noqa: BLE001 - background work must never bubble up
        logger.exception("structured plan post-processing failed for plan_id=%s", plan_id)
