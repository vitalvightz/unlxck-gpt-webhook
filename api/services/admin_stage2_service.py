from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import HTTPException, status
from fightcamp.stage2_pipeline import (
    build_stage2_retry,
    canonicalize_terminal_d0_protocol,
    review_stage2_output,
)
from fightcamp.stage2_policy import (
    apply_publish_blocking_review_gate,
    publish_blocking_review_findings,
)

from ..models import PlanDetail
from ..plan_mappers import _decode_structured_text, _lookup_plan_source, _map_plan_detail

from ..stage2_automation import (
    Stage2Automator,
    _structured_plan_enabled,
    attempt_structured_plan_for_result,
)
from ..structured_plan_generation import has_clean_structured_card
from ..store import AppStore

logger = logging.getLogger(__name__)

# How long the approval request will wait for the inline structured-card attempt
# before giving up and shipping the raw-markdown plan (the background task then
# finishes the card). Kept comfortably under the frontend/proxy request timeout
# so a slow conversion never surfaces as a false "Connection issue". Tunable via
# env for ops. Pre-warming (see prewarm_structured_plan) usually means the card is
# already built by approval time, so this budget is mostly a safety net for plans
# approved before their pre-warm finished.
_APPROVAL_STRUCTURED_PLAN_BUDGET_SECONDS = 40.0

# Held statuses whose card we pre-warm while the admin reviews the plan. These are
# the plans an admin can approve into the athlete view; safety-gated states
# (triage_blocked / medical_hold / restricted_rehab_only) and already-displayable
# states are deliberately excluded.
_PREWARMABLE_REVIEW_STATUSES = frozenset({"review_required", "held_for_review", "needs_review"})

# Plan ids whose pre-warm conversion is in flight, so repeated admin views of the
# review queue / a held plan never spawn duplicate model calls for the same plan.
_PREWARM_IN_FLIGHT: set[str] = set()


def should_prewarm_review_plan_row(row: Any) -> bool:
    """Whether a review-queue row is a candidate for structured-card pre-warm.

    A light, list-row-level gate (the row carries ``status`` but not the
    ``structured_plan``/``final_plan_text`` columns): it only filters by approvable
    held status and a present id. :func:`prewarm_structured_plan` re-reads the full
    row and enforces the real conditions (env on, text present, no card yet).
    """

    if not isinstance(row, dict):
        return False
    if not str(row.get("id") or "").strip():
        return False
    # Avoid scheduling redundant background tasks if the structured plan has already been attempted or generated
    report = row.get("stage2_validator_report")
    if isinstance(report, dict) and "structured_plan" in report:
        return False
    return str(row.get("status") or "").strip().lower() in _PREWARMABLE_REVIEW_STATUSES


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
    (:func:`attempt_structured_plan_for_result`): athlete-visible results with
    final plan_text and the env flag on are converted. A missing automator or any
    failure leaves plan_text intact and
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
    # Fast path: a card pre-warmed while the plan was held for review is reused
    # as-is (no model call), so the approval ships the live card instantly. Only
    # when the card was built from the exact text being approved — otherwise it is
    # a stale projection and we fall through to a fresh conversion.
    reused = _reuse_prewarmed_structured_card(result, plan_row)
    if reused is not None:
        logger.info("inline structured-plan reused pre-warmed card for plan_id=%s", plan_row.get("id"))
        return reused
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


def _reuse_prewarmed_structured_card(
    result: dict[str, Any], plan_row: dict[str, Any]
) -> dict[str, Any] | None:
    """Carry a pre-warmed card from the row onto the approval result, or None.

    Returns an updated ``result`` (card + schema version + structured debug
    attached) when the row already holds a clean structured card built from the
    exact text being approved, so the approval can ship it with no model call.
    Returns ``None`` when there is no reusable card (none present, not clean, or
    built from superseded text) so the caller runs a fresh conversion.
    """

    if not _structured_plan_enabled():
        return None
    if not has_clean_structured_card(plan_row):
        return None
    approved_text = str(result.get("final_plan_text") or result.get("plan_text") or "").strip()
    card_source_text = str(
        plan_row.get("final_plan_text") or plan_row.get("plan_text") or ""
    ).strip()
    if not approved_text or approved_text != card_source_text:
        return None

    result["structured_plan"] = plan_row.get("structured_plan")
    result["schema_version"] = plan_row.get("schema_version")
    row_report = plan_row.get("stage2_validator_report")
    row_debug = row_report.get("structured_plan") if isinstance(row_report, dict) else None
    report = result.get("stage2_validator_report")
    if isinstance(report, dict) and isinstance(row_debug, dict):
        report["structured_plan"] = row_debug
    return result


async def prewarm_structured_plan(
    *,
    plan_id: str,
    store: AppStore,
    stage2: Stage2Automator | None = None,
) -> None:
    """Build a held plan's structured card ahead of approval (best-effort).

    Admins approve held plans almost every time, and the structured-card
    conversion is the slow step at approval. Running it now — while the plan still
    sits in the review queue — means the card is usually already on the row by the
    time the admin clicks Approve, so :func:`_reuse_prewarmed_structured_card`
    ships it instantly instead of deferring to the post-approval background task.

    Idempotent and safe: short-circuits when structured plans are disabled, when a
    card already exists, when there is no text to convert, or when an identical
    pre-warm is already in flight. Persists only through the narrow structured
    writer keyed to the source text, so a concurrent edit/reject mid-conversion
    can never publish a stale card or clobber newer state. Never raises.
    """

    if stage2 is None or not _structured_plan_enabled():
        return
    if plan_id in _PREWARM_IN_FLIGHT:
        return
    converter = getattr(stage2, "_attempt_structured_plan", None)
    if converter is None:
        return
    _PREWARM_IN_FLIGHT.add(plan_id)
    try:
        plan_row = await asyncio.to_thread(store.get_plan, plan_id)
        if not plan_row:
            return
        plan_row = dict(plan_row)
        # Re-check status against the *fresh* row: the plan may have been
        # approved, rejected, or archived between the queue load that scheduled
        # this task and now. Bail before spending an LLM call on a plan that is no
        # longer an approvable held plan.
        if not should_prewarm_review_plan_row(plan_row):
            return
        if plan_row.get("structured_plan"):
            return  # already converted (or pre-warmed) — nothing to do
        source_text = str(
            plan_row.get("final_plan_text") or plan_row.get("plan_text") or ""
        ).strip()
        if not source_text:
            return
        planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
        outcome, _costs = await converter(
            final_plan_text=source_text,
            planning_brief=planning_brief,
            source="admin_prewarm",
        )
        if outcome.structured_plan is None:
            return
        report = plan_row.get("stage2_validator_report")
        report = dict(report) if isinstance(report, dict) else {}
        report["structured_plan"] = outcome.as_debug()
        await asyncio.to_thread(
            store.update_plan_structured_artifacts,
            plan_id,
            structured_plan=outcome.structured_plan,
            schema_version=outcome.schema_version,
            stage2_validator_report=report,
            expected_final_plan_text=source_text,
        )
    except Exception:  # noqa: BLE001 - pre-warm is best-effort and must never bubble up
        logger.exception("structured plan pre-warm failed for plan_id=%s", plan_id)
    finally:
        _PREWARM_IN_FLIGHT.discard(plan_id)


def _manual_stage2_result(plan_row: dict[str, Any], final_plan_text: str) -> dict[str, Any]:
    final_plan_text = canonicalize_terminal_d0_protocol(final_plan_text)
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    review = review_stage2_output(planning_brief=planning_brief, final_plan_text=final_plan_text)
    validator_report = apply_publish_blocking_review_gate(review["validator_report"])
    publish_blocking_findings = publish_blocking_review_findings(validator_report)
    next_attempt_count = int(plan_row.get("stage2_attempt_count") or 0) + 1
    had_retry_prompt = bool(str(plan_row.get("stage2_retry_text") or "").strip())

    if review["status"] == "PASS" and not publish_blocking_findings:
        return {
            "status": "ready",
            "plan_text": final_plan_text,
            "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
            "final_plan_text": final_plan_text,
            "pdf_url": None,
            "stage2_retry_text": "",
            "stage2_validator_report": validator_report,
            "stage2_status": "manual_stage2_retry_pass" if had_retry_prompt else "manual_stage2_pass",
            "stage2_attempt_count": next_attempt_count,
        }

    retry = build_stage2_retry(
        stage1_result={"planning_brief": planning_brief},
        final_plan_text=final_plan_text,
        validator_report=validator_report,
    )
    return {
        "status": "review_required",
        "plan_text": "",
        "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
        "final_plan_text": final_plan_text,
        "pdf_url": None,
        "stage2_retry_text": str(retry.get("repair_prompt") or ""),
        "stage2_validator_report": validator_report,
        "stage2_status": "manual_stage2_retry_required",
        "stage2_attempt_count": next_attempt_count,
    }


def _admin_approved_result(plan_row: dict[str, Any]) -> dict[str, Any]:
    approved_text = str(plan_row.get("final_plan_text") or plan_row.get("draft_plan_text") or plan_row.get("plan_text") or "").strip()
    approved_text = canonicalize_terminal_d0_protocol(approved_text)
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
    plan_row = await asyncio.to_thread(store.get_plan, plan_id)
    if not plan_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    plan_row = dict(plan_row)

    result = _manual_stage2_result(plan_row, final_plan_text)
    result = await _attach_structured_plan(result, plan_row, stage2=stage2)
    updated = await asyncio.to_thread(
        store.update_plan_stage2_if_unchanged, plan_id, result, plan_row
    )
    plan_source = await asyncio.to_thread(_lookup_plan_source, store, plan_id)
    return _map_plan_detail(
        updated,
        include_admin=True,
        plan_source=plan_source,
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

    plan_row = await asyncio.to_thread(store.get_plan, plan_id)
    if not plan_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    plan_row = dict(plan_row)

    result = _admin_approved_result(plan_row)
    result = await _attach_structured_plan_within_budget(result, plan_row, stage2=stage2)
    updated = await asyncio.to_thread(
        store.update_plan_stage2_if_unchanged, plan_id, result, plan_row
    )
    plan_source = await asyncio.to_thread(_lookup_plan_source, store, plan_id)
    return _map_plan_detail(
        updated,
        include_admin=True,
        plan_source=plan_source,
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
    :meth:`AppStore.update_plan_structured_artifacts`, which writes *only* the
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
        plan_row = dict(plan_row)
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
        # The exact text the card is converted from. The narrow writer rejects
        # the card if this text no longer matches the row at write time, so a
        # concurrent edit/reject mid-conversion can never publish a stale card.
        conversion_source_text = str(
            result.get("final_plan_text") or result.get("plan_text") or ""
        )
        result = await _attach_structured_plan(result, plan_row, stage2=stage2)
        # Only write when a structured plan was actually produced; a skip/failure
        # keeps the existing raw markdown row untouched. Persist via the narrow
        # structured-output writer so we never overwrite status/plan_text/stage2
        # fields that a concurrent admin action may have changed mid-conversion.
        if result.get("structured_plan") is not None:
            await asyncio.to_thread(
                store.update_plan_structured_artifacts,
                plan_id,
                structured_plan=result.get("structured_plan"),
                schema_version=result.get("schema_version"),
                stage2_validator_report=result.get("stage2_validator_report") or {},
                expected_final_plan_text=conversion_source_text,
            )
    except Exception:  # noqa: BLE001 - background work must never bubble up
        logger.exception("structured plan post-processing failed for plan_id=%s", plan_id)


async def list_structured_plan_backfill_candidates(
    *,
    store: AppStore,
    limit: int = 25,
) -> list[str]:
    """Plan ids that are athlete-displayable but still have no structured card.

    A fast, DB-only lookup the admin backfill endpoint runs before scheduling the
    (slow, model-bound) conversion work, so the request can return immediately
    with the set of plans that will be processed.
    """
    rows = await asyncio.to_thread(store.list_plans_missing_structured_plan, limit=limit)
    return [
        plan_id
        for row in rows
        if isinstance(row, dict) and (plan_id := str(row.get("id") or "").strip())
    ]


async def backfill_structured_plans(
    *,
    store: AppStore,
    stage2: Stage2Automator | None,
    plan_ids: list[str],
) -> None:
    """Convert a batch of already-released plans that have no structured card.

    Reuses :func:`run_structured_plan_post_processing` per plan, so each attempt is
    idempotent (short-circuits a plan that already has a card or is no longer
    displayable) and persists only through the narrow structured-output writer.
    Designed to run as a background task: never raises, and a single plan's failure
    does not stop the rest of the batch.
    """

    if stage2 is None:
        return
    for plan_id in plan_ids:
        try:
            await run_structured_plan_post_processing(plan_id=plan_id, store=store, stage2=stage2)
        except Exception:  # noqa: BLE001 - one bad plan must not abort the backfill
            logger.exception("structured plan backfill failed for plan_id=%s", plan_id)
