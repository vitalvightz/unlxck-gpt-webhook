from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from .generation.heartbeat import is_stale_job
from .generation.time_utils import utc_now_iso
from .store import (
    AppStore,
    is_job_loaded_stalled_generation_job,
    is_pre_start_stale_generation_job,
    is_stage1_planner_stalled_generation_job,
)

logger = logging.getLogger(__name__)

WorkerRecoveryCategory = Literal[
    "startup_stale",
    "worker_claim_stalled",
    "stage1_stalled",
    "mid_pipeline_stale",
    "persisted_output_recovery",
]

_TERMINAL_OUTPUT_MILESTONES = {
    "final_result_persisted",
    "plan_saved",
    "generation_job_terminal_status_persisted",
}
_RELEASED_PLAN_STATUSES = {"ready", "publishable_with_flags"}
_RELEASED_STAGE2_STATUSES = {"stage2_pass", "stage2_failed"}


def _milestones(job: dict[str, Any]) -> list[Any]:
    value = job.get("progress_milestones")
    return list(value) if isinstance(value, list) else []


def _has_persisted_output(job: dict[str, Any]) -> bool:
    if isinstance(job.get("final_result"), dict):
        return True
    if str(job.get("plan_id") or "").strip():
        return True
    return any(
        isinstance(entry, dict)
        and str(entry.get("code") or "") in _TERMINAL_OUTPUT_MILESTONES
        for entry in _milestones(job)
    )


def classify_worker_recovery_category(
    job: dict[str, Any],
    *,
    stale_after_seconds: int,
) -> WorkerRecoveryCategory | None:
    """Classify a running job without mutating it.

    Only a completely pre-start stale job remains reclaimable. Every other stale
    category belongs to the explicit recovery path.
    """

    if str(job.get("status") or "") != "running":
        return None
    if is_pre_start_stale_generation_job(
        job,
        stale_after_seconds=stale_after_seconds,
    ):
        return "startup_stale"
    if is_job_loaded_stalled_generation_job(
        job,
        stale_after_seconds=stale_after_seconds,
    ):
        return "worker_claim_stalled"
    if is_stage1_planner_stalled_generation_job(job):
        return "stage1_stalled"
    if not is_stale_job(job, stale_after_seconds=stale_after_seconds):
        return None
    if _has_persisted_output(job):
        return "persisted_output_recovery"
    return "mid_pipeline_stale"


def _list_recovery_candidate_summaries(
    store: AppStore,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Use the compact worker RPC when available, with a rolling-deploy fallback."""

    client = getattr(store, "client", None)
    rpc = getattr(client, "rpc", None)
    if callable(rpc):
        try:
            call = lambda: client.rpc(  # noqa: E731 - passed into retry wrapper
                "list_active_generation_jobs_for_recovery_v1",
                {"p_limit": max(1, min(int(limit), 100))},
            ).execute()
            runner = getattr(store, "_run_with_transient_retry", None)
            response = (
                runner(
                    operation="list_active_generation_jobs_for_recovery_v1",
                    fn=call,
                )
                if callable(runner)
                else call()
            )
            data = getattr(response, "data", None)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception as exc:  # noqa: BLE001 - fallback is deliberate during rolling deploys
            logger.warning(
                "[worker] compact recovery scan failed error_type=%s; falling back",
                type(exc).__name__,
            )

    fallback = getattr(store, "list_admin_active_generation_jobs", None)
    if not callable(fallback):
        return []
    return list(fallback(limit=limit))


def _persisted_plan_id(job: dict[str, Any]) -> str | None:
    direct = str(job.get("plan_id") or "").strip()
    if direct:
        return direct
    final_result = job.get("final_result")
    if isinstance(final_result, dict):
        nested = str(final_result.get("plan_id") or "").strip()
        if nested:
            return nested
    for entry in reversed(_milestones(job)):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("code") or "") not in _TERMINAL_OUTPUT_MILESTONES:
            continue
        meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
        milestone_plan_id = str(meta.get("plan_id") or "").strip()
        if milestone_plan_id:
            return milestone_plan_id
    return None


def _plan_is_releasable(plan: dict[str, Any] | None) -> bool:
    if not isinstance(plan, dict):
        return False
    if str(plan.get("status") or "") not in _RELEASED_PLAN_STATUSES:
        return False
    if str(plan.get("stage2_status") or "") not in _RELEASED_STAGE2_STATUSES:
        return False
    return bool(
        str(plan.get("final_plan_text") or "").strip()
        or str(plan.get("plan_text") or "").strip()
        or isinstance(plan.get("structured_plan"), dict)
    )


def _recovery_final_result(
    job: dict[str, Any],
    plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    existing = job.get("final_result")
    if isinstance(existing, dict):
        return existing
    if not isinstance(plan, dict):
        return None
    return {
        "status": str(plan.get("status") or "") or None,
        "stage2_status": str(plan.get("stage2_status") or "") or None,
        "why_log": plan.get("why_log") if isinstance(plan.get("why_log"), dict) else {},
        "recovery_reason": "persisted_plan",
    }


def _append_recovery_milestone(
    job: dict[str, Any],
    *,
    category: WorkerRecoveryCategory,
    now_iso: str,
) -> list[Any]:
    milestones = _milestones(job)
    code = "stalled_job_recovered" if category == "persisted_output_recovery" else "stale_job_reaped"
    if not any(
        isinstance(entry, dict) and str(entry.get("code") or "") == code
        for entry in milestones
    ):
        milestones.append(
            {
                "code": code,
                "label": "Stalled job recovered" if code == "stalled_job_recovered" else "Stale job reaped",
                "detail": (
                    "Recovered from durable persisted output."
                    if category == "persisted_output_recovery"
                    else "The generation job stopped making progress and was resolved by the worker recovery sweep."
                ),
                "meta": {"recovery_category": category},
                "at": now_iso,
            }
        )
    return milestones


def _resolve_mid_pipeline_or_persisted_job(
    store: AppStore,
    job: dict[str, Any],
    *,
    category: WorkerRecoveryCategory,
) -> dict[str, Any] | None:
    job_id = str(job.get("id") or "")
    attempt_count = int(job.get("attempt_count") or 0)
    plan_id = _persisted_plan_id(job)
    plan = store.get_plan(plan_id) if plan_id else None
    now_iso = utc_now_iso()

    if category == "persisted_output_recovery":
        final_status = "completed" if _plan_is_releasable(plan) else "review_required"
        return store.complete_generation_job(
            job_id,
            expected_status="running",
            expected_attempt_count=attempt_count,
            final_status=final_status,
            final_result=_recovery_final_result(job, plan),
            plan_id=plan_id,
            error=None,
            completed_at=now_iso,
            heartbeat_at=now_iso,
            enforce_worker_ownership=False,
        )

    return store.fail_generation_job(
        job_id,
        expected_status="running",
        expected_attempt_count=attempt_count,
        error="Generation job stalled mid-pipeline and was failed for recovery.",
        final_result=job.get("final_result") if isinstance(job.get("final_result"), dict) else None,
        plan_id=plan_id,
        progress_milestones=_append_recovery_milestone(
            job,
            category=category,
            now_iso=now_iso,
        ),
        failed_at=now_iso,
        heartbeat_at=now_iso,
        enforce_worker_ownership=False,
    )


async def recover_stale_generation_jobs(
    *,
    store: AppStore,
    active_tasks: set[str],
    stale_after_seconds: int,
    limit: int = 100,
) -> list[dict[str, str]]:
    """Resolve stale jobs that must never be sent into the claim/start path."""

    try:
        summaries = await asyncio.to_thread(
            _list_recovery_candidate_summaries,
            store,
            limit=limit,
        )
    except Exception:  # noqa: BLE001 - recovery is fail-soft for the worker loop
        logger.exception("[worker] failed to list generation jobs for recovery")
        return []

    outcomes: list[dict[str, str]] = []
    for summary in summaries:
        job_id = str(summary.get("id") or "")
        if not job_id or job_id in active_tasks:
            continue
        try:
            job = await asyncio.to_thread(store.get_generation_job, job_id)
            if not isinstance(job, dict):
                continue
            category = classify_worker_recovery_category(
                job,
                stale_after_seconds=stale_after_seconds,
            )
            if category in {None, "startup_stale"}:
                continue

            # Reuse the store's established job-loaded and Stage 1 recovery
            # semantics first. It returns unchanged for mid-pipeline/persisted
            # output jobs, which are resolved explicitly below.
            recovered = await asyncio.to_thread(store.recover_generation_job_if_stale, job)
            recovered_status = str((recovered or {}).get("status") or "")
            if recovered_status and recovered_status != "running":
                outcomes.append(
                    {"job_id": job_id, "category": category, "status": recovered_status}
                )
                logger.warning(
                    "[worker] recovered stale generation job job_id=%s category=%s status=%s",
                    job_id,
                    category,
                    recovered_status,
                )
                continue

            if category not in {"mid_pipeline_stale", "persisted_output_recovery"}:
                continue
            resolved = await asyncio.to_thread(
                _resolve_mid_pipeline_or_persisted_job,
                store,
                job,
                category=category,
            )
            resolved_status = str((resolved or {}).get("status") or "")
            outcomes.append(
                {"job_id": job_id, "category": category, "status": resolved_status}
            )
            logger.warning(
                "[worker] resolved stale generation job job_id=%s category=%s status=%s",
                job_id,
                category,
                resolved_status,
            )
        except Exception:  # noqa: BLE001 - one malformed/stale row must not stop the sweep
            logger.exception("[worker] failed to recover generation job job_id=%s", job_id)

    return outcomes
