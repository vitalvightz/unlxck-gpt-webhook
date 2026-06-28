"""Plan and final-result persistence for the generation runtime.

Encapsulates the two terminal persistence paths invoked by run_generation_job:
the triage-blocked review_required outcome (no plan row) and the Stage 2 success
path (create/update the plan, persist final_result, resolve terminal status, and
clear the onboarding draft).
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import Any, Callable

from fightcamp.plan_contract_validator import contract_report_requires_review, validate_plan_contract

from ..models import PlanRequest
from ..state_machine import job_status_for_plan_status
from ..store import AppStore
from ..structured_plan_generation import has_clean_structured_card
from .errors import TriageResumeMissingPlanError
from .time_utils import utc_now_iso
from .triage import _compact_generation_job_final_result

logger = logging.getLogger(__name__)

_FINAL_RESULT_PERSIST_TIMEOUT_SECONDS = 40.0
_FINAL_RESULT_PERSIST_TIMEOUT_ERROR = "Stage 2 result persistence timed out before final_result was saved."
_PLAN_PERSIST_VERIFICATION_ERROR = "Plan persistence verification failed after create_plan."
_POST_PERSIST_CLEANUP_TIMEOUT_SECONDS = 8.0

# Statuses that surface the plan to the athlete. A contract violation on one of
# these is routed to review_required (an admin sees it first); a violation on an
# already-non-visible status is recorded without changing the status.
_CONTRACT_VISIBLE_PLAN_STATUSES = {"ready", "publishable_with_flags"}
_CONTRACT_REVIEW_PLAN_STATUS = "review_required"

# Contract findings a clean structured card CAN vouch for: markdown
# render/extraction misses where a schema-valid card already proves the plan is
# well-formed. This is an explicit allowlist - anything not listed here
# (notably ``plan_text_empty``, which is unrecoverable output integrity, plus
# any future/unknown contract code) routes to review by default.
_CONTRACT_CARD_RESCUABLE_ERROR_CODES = {
    "weekly_schedule_blank",
    "calendar_unrenderable",
    "fight_day_missing",
    "late_fight_session_sequence_empty",
}


def _contract_report_is_card_rescuable(report: Any) -> bool:
    """Whether every error-level contract finding is a known render/extraction miss.

    Defensive and allowlisted: returns True only when ``report`` is a dict with a
    well-formed ``violations`` list, there is at least one error-level finding,
    and every error-level code is in :data:`_CONTRACT_CARD_RESCUABLE_ERROR_CODES`.
    A malformed report, an unknown code, or an unrescuable code (e.g.
    ``plan_text_empty``) all return False so the plan routes to review.
    """

    if not isinstance(report, dict):
        return False
    violations = report.get("violations")
    if not isinstance(violations, list):
        return False
    error_codes: list[str] = []
    for violation in violations:
        if not isinstance(violation, dict):
            return False
        if violation.get("severity") != "error":
            continue
        code = violation.get("code")
        if not isinstance(code, str) or not code.strip():
            return False
        error_codes.append(code.strip())
    if not error_codes:
        return False
    return all(code in _CONTRACT_CARD_RESCUABLE_ERROR_CODES for code in error_codes)


def _record_stage2_cost_if_available(
    store: AppStore, job_id: str, final_result: dict[str, Any]
) -> None:
    """Persist Stage 2 token/cost telemetry for a successful finalization.

    The metadata rides on ``final_result["stage2_cost"]`` (built by the Stage 2
    automator). ``store.record_stage2_cost`` is itself best-effort and never
    raises, so this is safe to call on the critical persistence path.
    """
    cost = final_result.get("stage2_cost") if isinstance(final_result, dict) else None
    if isinstance(cost, dict) and cost:
        store.record_stage2_cost(job_id, cost)


def _contract_fight_date(request_body: Any) -> Any:
    """Resolve the fight date the contract validator should use.

    Mirrors ``PlanRequest.to_payload``: open camps (``no_scheduled_fight``) have
    no fight day even when ``fight_date`` still holds a stale value, so return
    None to avoid falsely tripping the missing-D-0 invariant.
    """
    if getattr(request_body, "no_scheduled_fight", False):
        return None
    return getattr(request_body, "fight_date", None)


def _apply_plan_contract_validation(
    final_result: dict[str, Any],
    *,
    fight_date: Any,
    athlete_id: str,
    job_id: str,
    emit_milestone: Callable[..., None],
) -> dict[str, Any]:
    """Validate plan invariants before persistence and route hard violations to review.

    Runs the post-generation contract validator, attaches its report to
    ``why_log`` for visibility, and — when a would-be-visible plan has
    error-severity findings — downgrades the status to ``review_required`` so an
    admin reviews the plan before the athlete sees it. Returns the (possibly
    updated) final_result. Never raises: a validator failure leaves the plan
    untouched so generation is never blocked by a defect in this layer.
    """
    try:
        report = validate_plan_contract(final_result, fight_date=fight_date)

        existing_why_log = final_result.get("why_log")
        why_log = dict(existing_why_log) if isinstance(existing_why_log, dict) else {}
        why_log["plan_contract_validation"] = report
        final_result = {**final_result, "why_log": why_log}

        if not contract_report_requires_review(report):
            return final_result

        error_codes = ",".join(
            str(v.get("code"))
            for v in report.get("violations", [])
            if isinstance(v, dict) and v.get("severity") == "error"
        )
        current_status = str(final_result.get("status") or "").strip().lower()
        if current_status not in _CONTRACT_VISIBLE_PLAN_STATUSES:
            # Already non-visible (e.g. held_for_review); the report is recorded but
            # the status is left as-is — there is nothing to gate.
            logger.warning(
                "[jobs] generation:plan_contract_violation_noop athlete_id=%s job_id=%s status=%s codes=%s",
                athlete_id,
                job_id,
                current_status or "unknown",
                error_codes,
            )
            return final_result

        # Structured-card rescue: a plan that produced a schema-valid card is
        # trusted. The card is the athlete-facing artifact, so render/extraction
        # contract findings (blank calendar, missing D-0, empty sequence) are
        # treated as false positives and the plan keeps its visible status. Only
        # an unrecoverable empty body still forces review.
        if has_clean_structured_card(final_result) and _contract_report_is_card_rescuable(report):
            logger.info(
                "[jobs] generation:plan_contract_rescued_by_structured_card athlete_id=%s job_id=%s status=%s codes=%s",
                athlete_id,
                job_id,
                current_status,
                error_codes,
            )
            emit_milestone(
                "plan_contract_structured_card_rescue",
                "Plan kept publishable",
                "Post-generation contract checks flagged the rendered calendar, but the plan "
                "has a schema-valid structured card; trusting the card instead of routing to review.",
                violation_codes=error_codes,
            )
            return final_result

        final_result = {**final_result, "status": _CONTRACT_REVIEW_PLAN_STATUS}
        logger.warning(
            "[jobs] generation:plan_contract_routed_to_review athlete_id=%s job_id=%s from_status=%s codes=%s",
            athlete_id,
            job_id,
            current_status,
            error_codes,
        )
        emit_milestone(
            "plan_contract_review_required",
            "Plan held for review",
            "Post-generation contract checks found calendar/payload issues; "
            "routing to admin review before the athlete sees it.",
            violation_codes=error_codes,
        )
        return final_result
    except Exception:
        # Honour the "never raises" contract for the whole gate, not just the
        # validator call: status routing and the emit_milestone callback are
        # external surfaces that must never crash the persistence flow. Returns
        # the latest final_result binding (already carrying any review downgrade
        # applied before the failure).
        logger.exception(
            "[jobs] generation:plan_contract_validation_failed athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        return final_result


async def persist_triage_review_required(
    *,
    job_id: str,
    athlete_id: str,
    plan_id: str | None,
    expected_attempt_count: int,
    job_source: str,
    final_result: dict[str, Any],
    admin_resume_plan_row: dict[str, Any] | None,
    store: AppStore,
    emit_milestone: Callable[..., None],
    to_thread_with_heartbeat: Callable[..., Any],
    t_start: float,
) -> None:
    """Persist a triage-blocked Stage 1 outcome as a review_required job.

    Triage holds are not plans: the outcome lives on the generation job's
    final_result and no plan row is created or updated. On persistence
    timeout/failure the job is marked failed and we return early (the caller
    then returns from run_generation_job too).
    """
    # admin_triage_resume keeps its linked legacy plan row visible
    # for backwards compat (it stays at its prior status), but we
    # do NOT re-write the plan with another triage_blocked result.
    if job_source == "admin_triage_resume" and plan_id:
        _ = admin_resume_plan_row or await to_thread_with_heartbeat(
            store.get_plan, plan_id
        )
    emit_milestone(
        "triage_review_required",
        "Planning paused for admin review",
        "Stage 1 triage held the request; no plan row was created. "
        "Admin must approve & resume before generation continues.",
    )
    compact_final_result = _compact_generation_job_final_result(final_result)
    now_iso = utc_now_iso()
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                store.complete_generation_job,
                job_id,
                expected_attempt_count=expected_attempt_count,
                final_status="review_required",
                final_result=compact_final_result,
                plan_id=plan_id,
                error=None,
                completed_at=now_iso,
                heartbeat_at=now_iso,
            ),
            timeout=_FINAL_RESULT_PERSIST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.exception(
            "[jobs] generation:triage_final_result_persist_timeout athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        now_iso = utc_now_iso()
        with suppress(Exception):
            await asyncio.to_thread(
                store.fail_generation_job,
                job_id,
                expected_attempt_count=expected_attempt_count,
                error=_FINAL_RESULT_PERSIST_TIMEOUT_ERROR,
                failed_at=now_iso,
                heartbeat_at=now_iso,
            )
        return
    except Exception:
        logger.exception(
            "[jobs] generation:triage_final_result_persist_failed athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        now_iso = utc_now_iso()
        with suppress(Exception):
            await asyncio.to_thread(
                store.fail_generation_job,
                job_id,
                expected_attempt_count=expected_attempt_count,
                error="Stage 1 triage result persistence failed.",
                failed_at=now_iso,
                heartbeat_at=now_iso,
            )
        return
    emit_milestone(
        "generation_job_terminal_status_persisted",
        "Generation job terminal status persisted",
        "Terminal generation job lifecycle status was saved.",
        final_status="review_required",
        plan_status=str((final_result or {}).get("status") or ""),
        plan_id=plan_id,
    )
    try:
        await asyncio.wait_for(
            to_thread_with_heartbeat(store.clear_onboarding_draft, athlete_id),
            timeout=_POST_PERSIST_CLEANUP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[jobs] generation:clear_onboarding_draft_timeout athlete_id=%s job_id=%s timeout_seconds=%s",
            athlete_id,
            job_id,
            _POST_PERSIST_CLEANUP_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception(
            "[jobs] generation:clear_onboarding_draft_failed athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
    logger.info(
        "[jobs] generation:complete_triage_review athlete_id=%s job_id=%s plan_id=%s "
        "final_result_status=%s duration_ms=%s",
        athlete_id,
        job_id,
        plan_id,
        (final_result or {}).get("status"),
        round((time.perf_counter() - t_start) * 1000, 2),
    )


async def persist_plan_and_finalize(
    *,
    job: dict[str, Any],
    job_id: str,
    athlete_id: str,
    plan_id: str | None,
    intake_id: str | None,
    job_source: str,
    resume_from_job_only: bool,
    admin_resume_plan_row: dict[str, Any] | None,
    final_result: dict[str, Any],
    request_body: PlanRequest,
    store: AppStore,
    emit_milestone: Callable[..., None],
    to_thread_with_heartbeat: Callable[..., Any],
    t_start: float,
) -> None:
    """Persist the Stage 2 plan and finalize the generation job (success path).

    Creates or updates the plan row, persists the compact final_result, resolves
    the terminal job status (downgrading to failed if the plan_id is missing or
    the plan row disappeared), and clears the onboarding draft. On any
    persistence timeout/failure the job is marked failed and we return early
    (the caller then falls through to its finally block, as before).
    """
    plan_row: dict[str, Any] | None = None
    emit_milestone(
        "plan_persisting",
        "Saving plan row",
        "Creating or updating the saved plan from the Stage 2 result.",
    )
    if job_source == "admin_triage_resume":
        plan_row = admin_resume_plan_row
    else:
        if plan_id:
            plan_row = await to_thread_with_heartbeat(store.get_plan, plan_id)
        if job_source != "admin_latest_intake" and not plan_row and intake_id:
            latest_plan = await asyncio.to_thread(store.get_latest_plan, athlete_id)
            if (
                latest_plan
                and str(latest_plan.get("intake_id") or "") == intake_id
                and str(latest_plan.get("status") or "").strip().lower() != "archived"
            ):
                plan_row = latest_plan
                plan_id = str(latest_plan.get("id") or "")

    # Post-generation contract/invariant gate: validate the finalized plan
    # before it is written. Hard violations (blank calendar week, missing D-0,
    # empty late-fight sequence) downgrade a would-be-visible plan to
    # review_required so an admin sees it before the athlete does.
    #
    # Open camps (no_scheduled_fight) have no fight day even when fight_date
    # carries a stale value; mirror PlanRequest.to_payload and pass None so the
    # missing-D-0 invariant is not falsely tripped.
    final_result = _apply_plan_contract_validation(
        final_result,
        fight_date=_contract_fight_date(request_body),
        athlete_id=athlete_id,
        job_id=job_id,
        emit_milestone=emit_milestone,
    )

    if plan_row and plan_id:
        # Preserve triage-approval audit markers so they aren't lost when
        # updating the existing plan in-place (important for admin resume flows).
        existing_why_log = plan_row.get("why_log") if isinstance(plan_row.get("why_log"), dict) else {}
        preserved_keys = ("triage_regeneration_cleared", "triage_resume_approval")
        preserved = {key: existing_why_log[key] for key in preserved_keys if key in existing_why_log}
        if preserved:
            merged_why_log = dict(final_result.get("why_log") or {})
            merged_why_log.update(preserved)
            final_result = {**final_result, "why_log": merged_why_log}
        plan_row = await to_thread_with_heartbeat(
            store.update_plan_stage2,
            plan_id,
            final_result,
        )
    else:
        if job_source == "admin_triage_resume" and not resume_from_job_only:
            logger.error(
                "[jobs] generation:resume_missing_plan job_id=%s athlete_id=%s intake_id=%s job_plan_id=%s",
                job_id,
                athlete_id,
                intake_id,
                job.get("plan_id"),
            )
            raise TriageResumeMissingPlanError(
                "admin triage resume job is missing its linked plan; refusing to create a duplicate plan"
            )
        plan_row = await to_thread_with_heartbeat(
            store.create_plan,
            athlete_id=athlete_id,
            intake_id=intake_id,
            request=request_body,
            result=final_result,
        )
        created_plan_id = str(plan_row.get("id") or "").strip()
        verified_plan_row = await to_thread_with_heartbeat(store.get_plan, created_plan_id) if created_plan_id else None
        verified_athlete_id = str((verified_plan_row or {}).get("athlete_id") or "").strip()
        verified_intake_id = str((verified_plan_row or {}).get("intake_id") or "").strip()
        expected_intake_id = str(intake_id or "").strip()
        intake_id_matches = (not expected_intake_id) or (verified_intake_id == expected_intake_id)
        if not created_plan_id or not verified_plan_row or verified_athlete_id != athlete_id or not intake_id_matches:
            now_iso = utc_now_iso()
            with suppress(Exception):
                await asyncio.to_thread(
                    store.fail_generation_job,
                    job_id,
                    expected_attempt_count=int(job.get("attempt_count") or 0),
                    error=_PLAN_PERSIST_VERIFICATION_ERROR,
                    failed_at=now_iso,
                    heartbeat_at=now_iso,
                )
            return
        plan_id = str(plan_row.get("id") or "") or None
    if not plan_id:
        raise RuntimeError("Plan persistence failed: final_result exists but no linked plan_id was created.")
    job = await asyncio.to_thread(
        store.update_generation_job,
        job_id,
        plan_id=plan_id,
        heartbeat_at=utc_now_iso(),
    )
    emit_milestone(
        "plan_persisted",
        "Plan row persisted",
        "Saved plan row was created or updated.",
        plan_id=plan_id,
    )
    emit_milestone(
        "final_result_persisting",
        "Saving Stage 2 result",
        "Persisting finalizer output to the generation job.",
    )
    compact_final_result = _compact_generation_job_final_result(final_result)
    try:
        job = await asyncio.wait_for(
            asyncio.to_thread(
                store.update_generation_job,
                job_id,
                final_result=compact_final_result,
                plan_id=plan_id,
                heartbeat_at=utc_now_iso(),
            ),
            timeout=_FINAL_RESULT_PERSIST_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.exception("[jobs] generation:final_result_persist_timeout athlete_id=%s job_id=%s", athlete_id, job_id)
        now_iso = utc_now_iso()
        with suppress(Exception):
            await asyncio.to_thread(
                store.fail_generation_job,
                job_id,
                expected_attempt_count=int(job.get("attempt_count") or 0),
                error=_FINAL_RESULT_PERSIST_TIMEOUT_ERROR,
                failed_at=now_iso,
                heartbeat_at=now_iso,
            )
        return
    except Exception:
        logger.exception("[jobs] generation:final_result_persist_failed athlete_id=%s job_id=%s", athlete_id, job_id)
        now_iso = utc_now_iso()
        with suppress(Exception):
            await asyncio.to_thread(
                store.fail_generation_job,
                job_id,
                expected_attempt_count=int(job.get("attempt_count") or 0),
                error="Stage 2 result persistence failed after plan persistence.",
                failed_at=now_iso,
                heartbeat_at=now_iso,
            )
        return
    emit_milestone(
        "final_result_persisted",
        "Stage 2 result saved",
        "Finalizer output was saved to the generation job.",
    )
    # Audit trail: store Stage 2 token/cost metadata on the generation job so
    # high-cost jobs can be identified per athlete/job from the database. Runs
    # after the canonical final_result is persisted and never blocks finalize.
    await asyncio.to_thread(_record_stage2_cost_if_available, store, job_id, final_result)
    persisted_plan_id = str(job.get("plan_id") or "").strip() if isinstance(job, dict) else ""
    if not persisted_plan_id:
        plan_id = None
    plan_status = str(plan_row.get("status") or "failed")
    final_status = job_status_for_plan_status(plan_status)
    terminal_missing_plan_id_error = None
    missing_or_invalid_terminal_plan_id = False
    if final_status in {"completed", "review_required"} and plan_id:
        persisted_plan_row = await to_thread_with_heartbeat(store.get_plan, plan_id)
        if not persisted_plan_row:
            missing_or_invalid_terminal_plan_id = True
            logger.error(
                "[jobs] generation:terminal_plan_row_missing athlete_id=%s job_id=%s plan_id=%s plan_status=%s",
                athlete_id,
                job_id,
                plan_id,
                plan_status,
            )
    if final_status in {"completed", "review_required"} and not plan_id:
        missing_or_invalid_terminal_plan_id = True
    if missing_or_invalid_terminal_plan_id:
        final_status = "failed"
        terminal_missing_plan_id_error = (
            "Plan was saved but the generation job lost its plan_id. Open plan history or contact support."
        )
        logger.error(
            "[jobs] generation:terminal_missing_plan_id athlete_id=%s job_id=%s plan_status=%s",
            athlete_id,
            job_id,
            plan_status,
        )
    if final_status == "completed":
        emit_milestone(
            "plan_saved",
            "Plan saved to your workspace",
            "Opening the saved plan for review.",
        )
    terminal_at = utc_now_iso()
    if final_status == "failed":
        await asyncio.to_thread(
            store.fail_generation_job,
            job_id,
            expected_attempt_count=int(job.get("attempt_count") or 0),
            error=terminal_missing_plan_id_error or "Generation job failed.",
            plan_id=plan_id,
            failed_at=terminal_at,
            heartbeat_at=terminal_at,
        )
    else:
        await asyncio.to_thread(
            store.complete_generation_job,
            job_id,
            expected_attempt_count=int(job.get("attempt_count") or 0),
            final_status=final_status,
            error=terminal_missing_plan_id_error,
            plan_id=plan_id,
            completed_at=terminal_at,
            heartbeat_at=terminal_at,
        )
    emit_milestone(
        "generation_job_terminal_status_persisted",
        "Generation job terminal status persisted",
        "Terminal generation job lifecycle status was saved.",
        final_status=final_status,
        plan_status=plan_status,
        plan_id=plan_id,
    )
    try:
        await asyncio.wait_for(
            to_thread_with_heartbeat(store.clear_onboarding_draft, athlete_id),
            timeout=_POST_PERSIST_CLEANUP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[jobs] generation:clear_onboarding_draft_timeout athlete_id=%s job_id=%s timeout_seconds=%s",
            athlete_id,
            job_id,
            _POST_PERSIST_CLEANUP_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("[jobs] generation:clear_onboarding_draft_failed athlete_id=%s job_id=%s", athlete_id, job_id)
    _plan_why_log = plan_row.get("why_log") if isinstance(plan_row.get("why_log"), dict) else {}
    logger.info(
        "[jobs] generation:complete athlete_id=%s job_id=%s plan_id=%s status=%s "
        "plan_status=%s final_result_status=%s plan_triage_mode=%s plan_override_applied=%s "
        "plan_override_approval=%s duration_ms=%s",
        athlete_id,
        job_id,
        plan_id,
        final_status,
        plan_status,
        (final_result or {}).get("status") if isinstance(final_result, dict) else None,
        (_plan_why_log.get("injury_triage") or {}).get("mode")
        if isinstance(_plan_why_log.get("injury_triage"), dict)
        else None,
        bool(
            isinstance(_plan_why_log.get("injury_triage_resume_override"), dict)
            and _plan_why_log["injury_triage_resume_override"].get("bypassed_blocking") is True
        ),
        isinstance(_plan_why_log.get("triage_resume_approval"), dict),
        round((time.perf_counter() - t_start) * 1000, 2),
    )
