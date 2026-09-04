from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from ..models import PlanDetail
from ..plan_mappers import (
    _decode_structured_plan,
    _decode_structured_text,
    _lookup_plan_source,
    _map_plan_detail,
)
from ..state_machine import is_athlete_displayable_plan_status
from ..structured_card_lifecycle import (
    STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY,
    has_fresh_structured_card_attempt,
    mark_structured_card_attempt_started,
)
from ..structured_plan_generation import (
    StructuredPlanOutcome,
    has_clean_structured_card,
    should_attempt_structured_plan,
)
from ..store import AppStore

if TYPE_CHECKING:
    from ..stage2_automation import Stage2Automator

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
    # Avoid scheduling redundant background tasks when a conversion already RAN
    # for this plan. A recorded ``not_attempted`` means the opposite — held plans
    # always carry one (the worker records it when the plan is not displayable),
    # so treating its mere presence as "already attempted" disabled pre-warm for
    # exactly the plans it exists to serve.
    report = row.get("stage2_validator_report")
    if has_fresh_structured_card_attempt(report):
        return False
    debug = report.get("structured_plan") if isinstance(report, dict) else None
    debug_status = str(debug.get("status") or "").strip() if isinstance(debug, dict) else ""
    if debug_status and debug_status != "not_attempted":
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


def _inline_approval_card_conversion_enabled() -> bool:
    """Whether approval runs a FRESH structured-card conversion inline.

    OFF by default. A pre-warmed card that matches the approved text is still
    reused instantly (no model call) regardless of this flag — this only governs
    the *fresh* conversion attempted when no reusable card exists. For the
    configured model that conversion regularly runs for minutes, so the inline
    attempt almost always burns its budget and times out, and the background
    :func:`run_structured_plan_post_processing` task (scheduled after every
    approval) then runs a *second* full conversion — roughly 1.5x the cost and
    latency for no user-visible gain now that the admin UI shows a live
    "building" state and polls the card in. Leaving it off means one conversion
    per approval. Set ``UNLXCK_STAGE2_INLINE_APPROVAL_CARD`` truthy to restore
    the inline fresh attempt (e.g. if a faster model makes it land in-budget).
    """

    raw = os.getenv("UNLXCK_STAGE2_INLINE_APPROVAL_CARD")
    if raw is None:
        return False  # unset → default off (defer the single conversion)
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _structured_card_source_text(plan: dict[str, Any]) -> str:
    # This value is also used as the narrow writer's optimistic text guard. Keep
    # it byte-for-byte identical to the persisted source; trimming here would
    # silently skip marker/terminal writes for legacy rows with trailing space.
    return str(plan.get("final_plan_text") or plan.get("plan_text") or "")


def _has_live_structured_card(plan: dict[str, Any]) -> bool:
    """Require both a clean outcome and a card that still decodes today."""

    if not has_clean_structured_card(plan):
        return False
    decoded, _schema_version = _decode_structured_plan(
        plan.get("structured_plan"),
        raw_markdown=_structured_card_source_text(plan),
    )
    return decoded is not None


def _structured_card_rebuild_status_is_eligible(plan: dict[str, Any]) -> bool:
    plan_status = str(plan.get("status") or "").strip().lower()
    return is_athlete_displayable_plan_status(plan_status) or plan_status in _PREWARMABLE_REVIEW_STATUSES


async def _persist_structured_card_attempt_started(
    *,
    plan_id: str,
    store: AppStore,
    plan_row: dict[str, Any],
    result: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    """Persist an in-flight marker without touching plan lifecycle/text fields."""

    mark_structured_card_attempt_started(result)
    report = result.get("stage2_validator_report")
    if not isinstance(report, dict):  # defensive; marker helper always normalizes
        report = {}
        result["stage2_validator_report"] = report
    updated = await asyncio.to_thread(
        store.update_plan_structured_artifacts,
        plan_id,
        # Preserve a pre-existing artifact while updating only its lifecycle
        # report. Passing the same artifact also avoids the writer's intentional
        # "do not overwrite an existing card with None" race guard.
        structured_plan=plan_row.get("structured_plan"),
        schema_version=plan_row.get("schema_version"),
        stage2_validator_report=report,
        expected_final_plan_text=source_text,
    )
    return dict(updated) if isinstance(updated, dict) else {}


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
    from ..stage2_automation import attempt_structured_plan_for_result

    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    result, _costs = await attempt_structured_plan_for_result(
        result,
        planning_brief=planning_brief,
        automator=stage2,
        source="admin_stage2",
    )
    return result


async def _attach_structured_plan_rebuild(
    result: dict[str, Any],
    plan_row: dict[str, Any],
    *,
    stage2: Stage2Automator | None,
) -> dict[str, Any]:
    """Re-run the audited converter without changing the plan's held/live status.

    The canonical trigger intentionally excludes held rows and any row that
    already has an artifact. An explicit admin rebuild may retry those rows, but
    it still calls the same ``_attempt_structured_plan`` implementation used by
    pre-warm/worker conversion, including its deterministic safety audit. This
    helper only attaches the conversion outcome; persistence remains narrow and
    never releases a held plan.
    """

    if stage2 is None:
        return result
    from ..stage2_automation import _record_structured_outcome

    converter = getattr(stage2, "_attempt_structured_plan", None)
    if converter is None:
        reason = str(getattr(stage2, "reason", "") or "").strip() or (
            f"Stage 2 automator {type(stage2).__name__} cannot convert structured plans."
        )
        return _record_structured_outcome(
            result,
            StructuredPlanOutcome(
                status="not_attempted",
                errors=[f"structured conversion unavailable: {reason}"],
            ),
        )

    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    outcome, _costs = await converter(
        final_plan_text=_structured_card_source_text(result),
        planning_brief=planning_brief,
        source="admin_rebuild",
    )
    return _record_structured_outcome(result, outcome)


async def _attach_structured_plan_within_budget(
    result: dict[str, Any],
    plan_row: dict[str, Any],
    *,
    store: AppStore,
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
    plan_id = str(plan_row.get("id") or "").strip()
    source_text = _structured_card_source_text(plan_row)
    # Persist the durable in-flight marker regardless of whether the inline fresh
    # conversion runs: the admin UI reads it as "building", and the startup
    # self-heal sweep uses it to re-queue a plan whose background build was
    # orphaned by a deploy/restart.
    if plan_id and _structured_card_source_text(result).strip():
        try:
            await _persist_structured_card_attempt_started(
                plan_id=plan_id,
                store=store,
                plan_row=plan_row,
                result=result,
                source_text=source_text,
            )
        except Exception:  # noqa: BLE001 - lifecycle diagnostics must not block approval
            # ``result`` still carries the marker, so the guarded approval write
            # below can persist it even if this best-effort narrow write failed.
            logger.exception(
                "inline structured-plan marker persistence failed for plan_id=%s",
                plan_id,
            )
    # By default we do NOT run a fresh conversion inline: it near-always times out
    # for the configured model and the deferred background task then redoes the
    # whole conversion. Deferring the single conversion to that task keeps approval
    # to one model call while the "building" chip + poll reveal the card.
    if not _inline_approval_card_conversion_enabled():
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

    from ..stage2_automation import _structured_plan_enabled

    if not _structured_plan_enabled():
        return None
    if not _has_live_structured_card(plan_row):
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

    from ..stage2_automation import _structured_plan_enabled

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
        source_text = _structured_card_source_text(plan_row)
        if not source_text.strip():
            return
        planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
        attempt_result: dict[str, Any] = {
            "stage2_validator_report": plan_row.get("stage2_validator_report"),
        }
        await _persist_structured_card_attempt_started(
            plan_id=plan_id,
            store=store,
            plan_row=plan_row,
            result=attempt_result,
            source_text=source_text,
        )
        outcome, _costs = await converter(
            final_plan_text=source_text,
            planning_brief=planning_brief,
            source="admin_prewarm",
        )
        from ..stage2_automation import _record_structured_outcome

        _record_structured_outcome(attempt_result, outcome)
        report = attempt_result["stage2_validator_report"]
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


def _manual_stage2_result(
    plan_row: dict[str, Any], final_plan_text: str
) -> dict[str, Any]:
    from fightcamp.stage2_pipeline import build_stage2_retry, review_stage2_output
    from fightcamp.stage2_policy import apply_stage2_release_policy
    from ..stage2_automation import _reviewed_result

    if not final_plan_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No usable Stage 2 plan text.",
        )
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    review = review_stage2_output(
        planning_brief=planning_brief, final_plan_text=final_plan_text
    )
    report = apply_stage2_release_policy(review["validator_report"])
    retry = (
        build_stage2_retry(
            stage1_result={"planning_brief": planning_brief},
            final_plan_text=final_plan_text,
            validator_report=report,
        )
        if report["release_decision"] == "hold"
        else {}
    )
    return _reviewed_result(
        {},
        draft_plan_text=str(
            plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""
        ),
        final_plan_text=final_plan_text,
        validator_report=report,
        attempt_count=int(plan_row.get("stage2_attempt_count") or 0) + 1,
        retry_text=str(retry.get("repair_prompt") or ""),
    )


def _admin_approved_result(plan_row: dict[str, Any]) -> dict[str, Any]:
    approved_text = str(
        plan_row.get("final_plan_text")
        or plan_row.get("draft_plan_text")
        or plan_row.get("plan_text")
        or ""
    ).strip()
    if not approved_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No saved Stage 2 or draft text is available to approve.",
        )
    planning_brief = _decode_structured_text(plan_row.get("planning_brief")) or {}
    prior_report = plan_row.get("stage2_validator_report")
    prior_report = dict(prior_report) if isinstance(prior_report, dict) else {}
    validator_report = dict(prior_report)
    if planning_brief:
        from fightcamp.stage2_pipeline import review_stage2_output

        review = review_stage2_output(planning_brief=planning_brief, final_plan_text=approved_text)
        fresh_report = review.get("validator_report")
        validator_report = dict(fresh_report) if isinstance(fresh_report, dict) else {}
        # Revalidation intentionally rebuilds the Stage 2 report, but the
        # structured-card lifecycle is an independent projection. Carry its
        # terminal debug and/or in-flight marker across approval so the admin UI
        # never goes blank between the release write and background completion.
        for key in ("structured_plan", STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY):
            if key in prior_report:
                validator_report[key] = prior_report[key]
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
    try:
        from .push_notifications import notify_plan_published_if_transition

        await asyncio.to_thread(
            notify_plan_published_if_transition,
            store,
            before=plan_row,
            after=updated,
        )
    except Exception:  # noqa: BLE001 - push must never break admin approval
        logger.exception("plan publication notification failed for plan_id=%s", plan_id)
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
    result = await _attach_structured_plan_within_budget(
        result,
        plan_row,
        store=store,
        stage2=stage2,
    )
    updated = await asyncio.to_thread(
        store.update_plan_stage2_if_unchanged, plan_id, result, plan_row
    )
    try:
        from .push_notifications import notify_plan_published_if_transition

        await asyncio.to_thread(
            notify_plan_published_if_transition,
            store,
            before=plan_row,
            after=updated,
        )
    except Exception:  # noqa: BLE001 - push must never break admin approval
        logger.exception("plan publication notification failed for plan_id=%s", plan_id)
    plan_source = await asyncio.to_thread(_lookup_plan_source, store, plan_id)
    return _map_plan_detail(
        updated,
        include_admin=True,
        plan_source=plan_source,
    )


async def prepare_structured_plan_rebuild(
    *,
    plan_id: str,
    store: AppStore,
) -> dict[str, Any]:
    """Reserve one explicit admin rebuild and persist its durable marker."""

    plan_row = await asyncio.to_thread(store.get_plan, plan_id)
    if not plan_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    plan_row = dict(plan_row)
    if _has_live_structured_card(plan_row):
        return {"queued": False, "plan_id": plan_id}

    report = plan_row.get("stage2_validator_report")
    if has_fresh_structured_card_attempt(report):
        return {"queued": False, "plan_id": plan_id}

    from ..stage2_automation import _structured_plan_enabled

    if not _structured_plan_enabled():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Structured-card generation is disabled.",
        )
    if not _structured_card_rebuild_status_is_eligible(plan_row):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This plan is not eligible for an enhanced-card rebuild.",
        )
    source_text = _structured_card_source_text(plan_row)
    if not source_text.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No final plan text is available to rebuild the enhanced card.",
        )

    attempt_result = {"stage2_validator_report": report}
    updated = await _persist_structured_card_attempt_started(
        plan_id=plan_id,
        store=store,
        plan_row=plan_row,
        result=attempt_result,
        source_text=source_text,
    )
    if not has_fresh_structured_card_attempt(updated.get("stage2_validator_report")):
        if _has_live_structured_card(updated):
            return {"queued": False, "plan_id": plan_id}
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan changed while the enhanced-card rebuild was being queued; reload and try again.",
        )
    return {"queued": True, "plan_id": plan_id}


async def run_structured_plan_post_processing(
    *,
    plan_id: str,
    store: AppStore,
    stage2: Stage2Automator | None = None,
    continue_existing_attempt: bool = False,
    rebuild: bool = False,
    notify: bool = True,
) -> None:
    """Best-effort, non-blocking structured-plan conversion for an approved plan.

    The fallback for approval's inline attempt: it runs after the response has
    been returned (e.g. as a FastAPI background task) and finishes the card for
    any plan whose inline conversion timed out or failed. Re-reads the freshly
    approved row, attempts the structured conversion through the canonical
    trigger (which short-circuits when the row already carries a card), and
    persists ``structured_plan`` when one is produced, or the structured debug
    report when conversion ran but failed. Never raises: any failure leaves the
    raw markdown fallback intact.

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
        validator_report = plan_row.get("stage2_validator_report")
        if not isinstance(validator_report, dict):
            validator_report = {}
        if has_fresh_structured_card_attempt(validator_report) and not continue_existing_attempt:
            return

        from ..stage2_automation import _structured_plan_enabled

        if rebuild:
            can_attempt = (
                _structured_plan_enabled()
                and _structured_card_rebuild_status_is_eligible(plan_row)
                and bool(_structured_card_source_text(plan_row).strip())
                and not _has_live_structured_card(plan_row)
            )
        else:
            can_attempt = should_attempt_structured_plan(plan_row, _structured_plan_enabled())
        if not can_attempt:
            return
        result = {
            "status": str(plan_row.get("status") or ""),
            "plan_text": str(plan_row.get("plan_text") or ""),
            "draft_plan_text": str(plan_row.get("draft_plan_text") or plan_row.get("plan_text") or ""),
            "final_plan_text": str(plan_row.get("final_plan_text") or plan_row.get("plan_text") or ""),
            "pdf_url": plan_row.get("pdf_url"),
            "stage2_retry_text": str(plan_row.get("stage2_retry_text") or ""),
            "stage2_validator_report": validator_report,
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
        await _persist_structured_card_attempt_started(
            plan_id=plan_id,
            store=store,
            plan_row=plan_row,
            result=result,
            source_text=conversion_source_text,
        )
        if rebuild:
            result = await _attach_structured_plan_rebuild(result, plan_row, stage2=stage2)
        else:
            result = await _attach_structured_plan(result, plan_row, stage2=stage2)
        # Persist successful cards, and also persist a failed/skipped structured
        # debug result when conversion actually ran. This keeps athlete-visible
        # text untouched while making missed enhanced cards diagnosable.
        report = result.get("stage2_validator_report")
        if not isinstance(report, dict):
            report = {}
        if rebuild and result.get("structured_plan") is None and plan_row.get("structured_plan") is not None:
            result["structured_plan"] = plan_row.get("structured_plan")
            result["schema_version"] = plan_row.get("schema_version")
        structured_debug = report.get("structured_plan")
        debug_status = structured_debug.get("status") if isinstance(structured_debug, dict) else None
        debug_errors = (
            structured_debug.get("errors") if isinstance(structured_debug, dict) else None
        )
        # A bare gate-skip (already converted / not displayable) stays unpersisted,
        # but a not_attempted that CARRIES errors means the conversion could not
        # run (converter unavailable, crash) — persist it so the admin diagnostic
        # explains the missing card instead of showing a stale, reasonless state.
        should_persist_debug = debug_status not in {None, "not_attempted"} or bool(debug_errors)
        attempt_finished = STRUCTURED_CARD_ATTEMPT_STARTED_AT_KEY not in report
        if result.get("structured_plan") is not None or should_persist_debug or attempt_finished:
            await asyncio.to_thread(
                store.update_plan_structured_artifacts,
                plan_id,
                structured_plan=result.get("structured_plan"),
                schema_version=result.get("schema_version"),
                stage2_validator_report=report,
                expected_final_plan_text=conversion_source_text,
            )
            # Plan publication is the authoritative notification trigger. A
            # later structured-card attachment changes presentation only and
            # must not create a second "plan ready" athlete moment.
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
            # Backfill targets old plans the athlete has long been living with;
            # a "your final plan is ready" push there would be noise.
            await run_structured_plan_post_processing(
                plan_id=plan_id, store=store, stage2=stage2, notify=False
            )
        except Exception:  # noqa: BLE001 - one bad plan must not abort the backfill
            logger.exception("structured plan backfill failed for plan_id=%s", plan_id)


async def self_heal_orphaned_structured_cards(
    *,
    store: AppStore,
    stage2: Stage2Automator | None = None,
    limit: int = 25,
) -> int:
    """Re-queue structured-card builds orphaned by a process restart/deploy.

    A conversion stamps a durable in-flight marker that is cleared only on a
    terminal outcome. If the process running the deferred background build dies
    mid-flight (a deploy swap is the common cause), the plan is left with the
    marker and no card — the admin UI shows "building", then "failed". Run once at
    startup, this finds those orphaned plans and re-runs the single deferred
    conversion through :func:`run_structured_plan_post_processing`
    (``continue_existing_attempt=True`` so it proceeds past the freshness guard).

    Best-effort and idempotent: the re-queue short-circuits a plan that already
    has a card or is no longer eligible, and persistence stays on the narrow
    structured-artifacts writer with the source-text guard. Never raises; returns
    the number of plans re-queued. The Stage 2 automator is built lazily and ONLY
    when there is orphaned work, so a clean startup pays neither the lookup's
    conversion cost nor the OpenAI Stage 2 import.
    """

    try:
        rows = await asyncio.to_thread(
            store.list_plans_with_orphaned_structured_card_attempt, limit=limit
        )
    except Exception:  # noqa: BLE001 - self-heal must never crash startup
        logger.exception("structured-card self-heal: candidate lookup failed")
        return 0
    plan_ids = [
        plan_id
        for row in rows
        if isinstance(row, dict) and (plan_id := str(row.get("id") or "").strip())
    ]
    if not plan_ids:
        return 0
    if stage2 is None:
        from ..stage2_automation import build_default_stage2_automator

        stage2 = build_default_stage2_automator()
    logger.info(
        "structured-card self-heal: re-queuing %s orphaned build(s)", len(plan_ids)
    )
    healed = 0
    for plan_id in plan_ids:
        try:
            await run_structured_plan_post_processing(
                plan_id=plan_id,
                store=store,
                stage2=stage2,
                continue_existing_attempt=True,
            )
            healed += 1
        except Exception:  # noqa: BLE001 - one bad plan must not abort the sweep
            logger.exception("structured-card self-heal failed for plan_id=%s", plan_id)
    logger.info("structured-card self-heal: re-queued %s orphaned build(s)", healed)
    return healed
