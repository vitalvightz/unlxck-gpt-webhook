from __future__ import annotations

import asyncio
import inspect
import json
import logging
import traceback
import os
import threading
import time
import multiprocessing as mp
import queue
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import BackgroundTasks, HTTPException, status

from fightcamp.main import generate_plan_sync

from .environment import is_production_environment
from .generation_config import generation_job_stale_after_seconds
from .models import PlanRequest, ProfileUpdateRequest
from .stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError, Stage2Automator
from .store import AppStore, is_pre_start_stale_generation_job

Planner = Callable[..., dict[str, Any]]
ProgressCallback = Callable[[str, str, str, dict[str, Any]], None]
logger = logging.getLogger(__name__)
_TRIAGE_RESUME_OVERRIDE_KEY = "_triage_resume_override"


class TriageResumeMissingPlanError(RuntimeError):
    """Raised when an admin_triage_resume job cannot find its linked plan.

    A resume job must update the original triage-blocked plan in place; if the
    linked plan is missing we fail loudly rather than silently creating a
    duplicate plan.
    """

    pass


class AdminLatestIntakeLinkageError(RuntimeError):
    """Raised when an admin_latest_intake job linkage/ownership validation fails."""

    pass


_DETACHED_GENERATION_TASKS: set[asyncio.Task[None]] = set()
_MAX_PERSISTED_MILESTONES = 40
_OPENAI_QUOTA_ADMIN_ERROR = "OpenAI quota exceeded. Check API billing, credits, project budget, or organization limits."
_OPENAI_QUOTA_ATHLETE_ERROR = "Generation is temporarily unavailable. Please try again later."
_FINAL_RESULT_PERSIST_TIMEOUT_SECONDS = 40.0
_FINAL_RESULT_PERSIST_TIMEOUT_ERROR = "Stage 2 result persistence timed out before final_result was saved."
_PLAN_PERSIST_VERIFICATION_ERROR = "Plan persistence verification failed after create_plan."
_POST_PERSIST_CLEANUP_TIMEOUT_SECONDS = 8.0
_TERMINAL_GENERATION_JOB_STATUSES = {"completed", "review_required", "failed"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generation_status_from_plan_status(plan_status: str) -> str:
    normalized = str(plan_status or "").strip().lower()
    if normalized in {"ready", "publishable_with_flags", "triage_blocked"}:
        return "completed"
    if normalized in {"review_required", "held_for_review"}:
        return "review_required"
    if normalized == "failed":
        return "failed"
    return "review_required"


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    try:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        normalized = json.dumps(str(payload), ensure_ascii=False)
    return normalized


def default_planner(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if progress_callback is not None:
        progress_callback(
            "stage1_default_planner_entered",
            "Stage 1 default planner entered",
            "",
            {},
        )
        progress_callback(
            "stage1_generate_plan_sync_entering",
            "Stage 1 generate_plan_sync entering",
            "",
            {},
        )
    return generate_plan_sync(payload, progress_callback=progress_callback)


def _planner_accepts_progress_callback(planner_fn: Planner) -> bool:
    try:
        signature = inspect.signature(planner_fn)
    except (TypeError, ValueError):
        return True

    parameters = signature.parameters
    if "progress_callback" in parameters:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values())


def _invoke_planner(
    planner_fn: Planner,
    payload: dict[str, Any],
    progress_callback: ProgressCallback | None,
) -> dict[str, Any]:
    """Call a planner that may or may not accept a ``progress_callback`` kwarg."""
    if progress_callback is not None:
        progress_callback(
            "stage1_planner_callable_entering",
            "Stage 1 planner callable entering",
            "",
            {},
        )
    if progress_callback is None:
        return planner_fn(payload)

    planner_supports_progress_callback = _planner_accepts_progress_callback(planner_fn)
    if planner_supports_progress_callback:
        progress_callback(
            "stage1_planner_callable_supports_progress_callback",
            "Stage 1 planner callable supports progress callback",
            "",
            {},
        )
        return planner_fn(payload, progress_callback=progress_callback)
    return planner_fn(payload)


def build_progress_recorder(
    *,
    job_id: str,
    store: AppStore,
    initial_milestones: list[dict[str, Any]] | None = None,
    should_persist: Callable[[], bool] | None = None,
) -> tuple[list[dict[str, Any]], ProgressCallback]:
    """Return a milestone list + callback that persists each emit to the job row.

    Emits are low-volume (~10 over several minutes), so writing on every event
    is fine. Persistence failures are logged and ignored — they must never
    surface into the planner pipeline.
    """
    milestones: list[dict[str, Any]] = list(initial_milestones or [])

    def _callback(code: str, label: str, detail: str, meta: dict[str, Any]) -> None:
        if should_persist is not None and not should_persist():
            return

        entry = {
            "code": code,
            "label": label,
            "detail": detail or "",
            "meta": dict(meta or {}),
            "at": utc_now_iso(),
        }
        milestones.append(entry)
        # Cap list size so a runaway emitter cannot bloat the row.
        if len(milestones) > _MAX_PERSISTED_MILESTONES:
            del milestones[:-_MAX_PERSISTED_MILESTONES]
        snapshot = list(milestones)
        try:
            store.update_generation_job(
                job_id,
                progress_milestones=snapshot,
                heartbeat_at=utc_now_iso(),
            )
        except Exception:
            logger.exception(
                "[jobs] generation:milestone_persist_failed job_id=%s code=%s",
                job_id,
                code,
            )

    return milestones, _callback


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def is_stale_job(job: dict[str, Any], *, stale_after_seconds: int | None = None) -> bool:
    if stale_after_seconds is None:
        stale_after_seconds = generation_job_stale_after_seconds(minimum=1)
    if str(job.get("status") or "") != "running":
        return False
    if is_pre_start_stale_generation_job(job, stale_after_seconds=stale_after_seconds):
        return True
    last_progress_at = parse_datetime(job.get("heartbeat_at")) or parse_datetime(job.get("started_at"))
    if last_progress_at is None:
        return False
    return (datetime.now(timezone.utc) - last_progress_at).total_seconds() >= stale_after_seconds


def recover_stale_running_job(
    *,
    job: dict[str, Any],
    store: AppStore,
    stale_after_seconds: int,
    error_message: str = "Generation job stalled. Please try again.",
) -> dict[str, Any]:
    if not is_stale_job(job, stale_after_seconds=stale_after_seconds):
        return job
    return store.update_generation_job(
        str(job["id"]),
        status="failed",
        error=error_message,
        completed_at=utc_now_iso(),
        heartbeat_at=utc_now_iso(),
    )


def parse_plan_request(value: Any) -> PlanRequest:
    if isinstance(value, PlanRequest):
        return value
    if isinstance(value, dict):
        return PlanRequest.model_validate(value)
    if isinstance(value, str):
        return PlanRequest.model_validate(json.loads(value))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="generation job payload is invalid",
    )


def _stage2_finalize_timeout_seconds() -> float | None:
    raw_value = os.getenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "240").strip()
    if raw_value in {"", "0", "none", "None", "NONE"}:
        return None
    try:
        return max(1.0, float(raw_value))
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_stage2_timeout value=%r; falling back to 300s",
            raw_value,
        )
        return 300.0


def _stage1_planner_timeout_seconds() -> float | None:
    raw_value = os.getenv("STAGE1_PLANNER_TIMEOUT_SECONDS")
    if raw_value is None:
        raw_value = os.getenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "600")
    raw_value = raw_value.strip()
    if raw_value in {"", "0", "none", "None", "NONE"}:
        if is_production_environment():
            logger.warning(
                "[jobs] generation:stage1_timeout_disabled_in_production value=%r; falling back to 600s",
                raw_value,
            )
            return 600.0
        return None
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_stage1_timeout value=%r; falling back to 600s",
            raw_value,
        )
        return 600.0
    if parsed <= 0:
        logger.warning(
            "[jobs] generation:invalid_stage1_timeout value=%r; falling back to 600s",
            raw_value,
        )
        return 600.0
    return parsed


def _compact_generation_job_final_result(final_result: dict[str, Any]) -> dict[str, Any]:
    """Keep generation_jobs.final_result lean; canonical full text lives on plans."""
    compact: dict[str, Any] = {}
    for key in (
        "status",
        "stage2_status",
        "stage2_attempt_count",
        "stage2_validator_report",
        "stage2_retry_text",
        "error",
    ):
        if key in final_result:
            compact[key] = final_result.get(key)
    return compact


def _use_fastapi_background_tasks() -> bool:
    scheduler = os.getenv("APP_GENERATION_SCHEDULER", "detached").strip().lower()
    return scheduler in {"fastapi", "background_tasks", "backgroundtasks"}


def is_in_process_generation_enabled() -> bool:
    return os.getenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "0").strip() == "1"


def generation_max_concurrent_jobs() -> int:
    raw_value = os.getenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_max_concurrent_jobs value=%r; falling back to 1",
            raw_value,
        )
        return 1
    return max(1, parsed)


def _cleanup_detached_generation_task(task: asyncio.Task[None]) -> None:
    _DETACHED_GENERATION_TASKS.discard(task)
    if task.cancelled():
        return
    with suppress(Exception):
        task.result()


def _schedule_detached_generation_task(
    *,
    job_id: str,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
) -> None:
    task = asyncio.create_task(
        run_generation_job(
            job_id=job_id,
            store=store,
            planner_fn=planner_fn,
            stage2=stage2,
            active_tasks=active_tasks,
        )
    )
    _DETACHED_GENERATION_TASKS.add(task)
    task.add_done_callback(_cleanup_detached_generation_task)




def _run_planner_in_subprocess(
    planner_fn: Planner,
    payload: dict[str, Any],
    result_queue: Any,
    progress_queue: Any,
) -> None:
    def _child_progress_callback(code: str, label: str, detail: str, meta: dict[str, Any]) -> None:
        progress_queue.put((code, label, detail, meta))

    try:
        result = _invoke_planner(planner_fn, payload, _child_progress_callback)
        result_queue.put(("ok", result))
    except Exception as exc:  # pragma: no cover - defensive relay
        result_queue.put(("error", {"message": str(exc), "traceback": traceback.format_exc()}))


async def _drain_stage1_progress_queue(
    progress_queue: Any,
    progress_callback: ProgressCallback | None,
) -> None:
    while True:
        try:
            code, label, detail, meta = progress_queue.get_nowait()
        except queue.Empty:
            return
        if progress_callback is not None:
            progress_callback(code, label, detail, meta)


def _stage1_mp_start_method() -> str:
    raw_value = os.getenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn").strip().lower()
    if raw_value in {"spawn", "fork", "forkserver"}:
        return raw_value
    logger.warning(
        "[jobs] generation:invalid_stage1_mp_start_method value=%r; falling back to spawn",
        raw_value,
    )
    return "spawn"


def _stop_stage1_process(process: Any) -> None:
    if not process.is_alive():
        return
    process.terminate()
    process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)


def _read_stage1_result_queue_nowait(result_queue: Any) -> tuple[str, Any] | None:
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return None


def _handle_stage1_result_message(message: tuple[str, Any]) -> dict[str, Any]:
    status, payload_or_error = message

    if status == "ok":
        if not isinstance(payload_or_error, dict):
            raise RuntimeError("Stage 1 planner returned a non-dict result.")
        return payload_or_error

    if isinstance(payload_or_error, dict):
        raise RuntimeError(payload_or_error.get("message") or "Stage 1 planner failed")

    raise RuntimeError("Stage 1 planner failed")


async def run_stage1_planner(
    planner_fn: Planner,
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    ctx = mp.get_context(_stage1_mp_start_method())
    result_queue = ctx.Queue()
    progress_queue = ctx.Queue()
    process = ctx.Process(
        target=_run_planner_in_subprocess,
        args=(planner_fn, payload, result_queue, progress_queue),
        daemon=True,
    )
    process.start()

    start = time.monotonic()
    try:
        while True:
            await _drain_stage1_progress_queue(progress_queue, progress_callback)
            result_message = _read_stage1_result_queue_nowait(result_queue)
            if result_message is not None:
                if progress_callback is not None:
                    progress_callback(
                        "stage1_result_queue_received",
                        "Stage 1 result queue received",
                        "Parent runtime received the Stage 1 planner result from the subprocess.",
                        {},
                    )
                return _handle_stage1_result_message(result_message)
            if not process.is_alive():
                await _drain_stage1_progress_queue(progress_queue, progress_callback)
                try:
                    result_message = result_queue.get(timeout=1)
                except queue.Empty as exc:
                    raise RuntimeError(
                        f"Stage 1 planner process exited without result. exitcode={process.exitcode}"
                    ) from exc
                return _handle_stage1_result_message(result_message)
            if timeout_seconds is not None and (time.monotonic() - start) >= timeout_seconds:
                await _drain_stage1_progress_queue(progress_queue, progress_callback)
                result_message = _read_stage1_result_queue_nowait(result_queue)
                if result_message is not None:
                    return _handle_stage1_result_message(result_message)
                _stop_stage1_process(process)
                raise asyncio.TimeoutError
            await asyncio.sleep(0.05)
    finally:
        _stop_stage1_process(process)
        for q in (result_queue, progress_queue):
            with suppress(Exception):
                q.close()
            with suppress(Exception):
                q.join_thread()


async def finalize_stage2_with_timeout(
    *,
    stage2: Stage2Automator,
    stage1_result: dict[str, Any],
) -> dict[str, Any]:
    finalize = stage2.finalize(stage1_result=stage1_result)
    timeout_seconds = _stage2_finalize_timeout_seconds()
    if timeout_seconds is None:
        return await finalize
    return await asyncio.wait_for(finalize, timeout=timeout_seconds)


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"1", "true", "yes", "y", "on"}
    return False


def is_openai_quota_error(error: Exception) -> bool:
    message = str(error or "").lower()
    if (
        "insufficient_quota" in message
        or "exceeded your current quota" in message
        or "openai quota/rate limit" in message
    ):
        return True
    return "429" in message and "quota" in message


def should_skip_stage2(stage1_result: dict[str, Any], *, allow_triage_resume_override: bool = False) -> bool:
    status_value = str(stage1_result.get("status") or "").strip().lower()
    if status_value == "triage_blocked":
        return not allow_triage_resume_override

    injury_triage = stage1_result.get("injury_triage")
    if isinstance(injury_triage, dict):
        if _is_truthy_flag(injury_triage.get("should_block_stage2")):
            return False if allow_triage_resume_override else True
        triage_mode = str(injury_triage.get("mode") or "").strip().lower()
        if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
            return False if allow_triage_resume_override else True

    why_log = stage1_result.get("why_log")
    if isinstance(why_log, dict):
        why_log_triage = why_log.get("injury_triage")
        if isinstance(why_log_triage, dict):
            if _is_truthy_flag(why_log_triage.get("should_block_stage2")):
                return False if allow_triage_resume_override else True
            triage_mode = str(why_log_triage.get("mode") or "").strip().lower()
            if triage_mode in {"medical_hold", "restricted_rehab_only", "needs_review"}:
                return False if allow_triage_resume_override else True

    return False


async def heartbeat_generation_job(job_id: str, store: AppStore, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15)
            return
        except asyncio.TimeoutError:
            try:
                await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    heartbeat_at=utc_now_iso(),
                )
            except Exception:
                logger.exception("[jobs] generation:heartbeat_failed job_id=%s", job_id)


async def run_generation_job(
    *,
    job_id: str,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
) -> None:
    t_start = time.perf_counter()
    stop_event = asyncio.Event()
    heartbeat_task: asyncio.Task[None] | None = None
    athlete_id = "unknown"
    progress_callback: ProgressCallback | None = None
    stage1_timed_out = threading.Event()
    seen_milestone_codes: set[str] = set()

    def _emit_milestone(code: str, label: str, detail: str = "", **meta: Any) -> None:
        if progress_callback is None:
            return
        if code == "stage1_planner_timeout" and code in seen_milestone_codes:
            return
        try:
            progress_callback(code, label, detail, meta)
            seen_milestone_codes.add(code)
        except Exception:
            logger.exception("[jobs] generation:milestone_emit_failed job_id=%s code=%s", job_id, code)

    async def _touch_heartbeat() -> None:
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                heartbeat_at=utc_now_iso(),
            )

    async def _to_thread_with_heartbeat(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        await _touch_heartbeat()
        result = await asyncio.to_thread(fn, *args, **kwargs)
        await _touch_heartbeat()
        return result

    async def _ensure_admin_resume_plan_exists(linked_plan_id: str | None) -> None:
        if job_source != "admin_triage_resume":
            return
        if not linked_plan_id:
            raise TriageResumeMissingPlanError(
                "admin triage resume job lost its linked plan_id; refusing to continue"
            )
        linked = await _to_thread_with_heartbeat(store.get_plan, linked_plan_id)
        if not linked:
            raise TriageResumeMissingPlanError(
                "admin triage resume job linked plan was deleted while generation was running"
            )

    try:
        # Claim the job for processing. This implements the worker-claim model
        # introduced in #1417 while preserving Main's heartbeat-on-read safety.
        job = await asyncio.to_thread(store.claim_generation_job_start, job_id)
        if not job:
            logger.warning("[jobs] generation:claim_unavailable job_id=%s", job_id)
            return

        # Use persisted milestones as the initial state for the progress recorder.
        persisted_milestones = job.get("progress_milestones")
        initial_milestones = persisted_milestones if isinstance(persisted_milestones, list) else []
        for milestone in initial_milestones:
            if isinstance(milestone, dict):
                milestone_code = str(milestone.get("code") or "").strip()
                if milestone_code:
                    seen_milestone_codes.add(milestone_code)
        _, progress_callback = build_progress_recorder(
            job_id=job_id,
            store=store,
            initial_milestones=initial_milestones,
            should_persist=lambda: not stage1_timed_out.is_set(),
        )
        heartbeat_task = asyncio.create_task(heartbeat_generation_job(job_id, store, stop_event))

        athlete_id = str(job["athlete_id"])
        raw_request_payload = job.get("request_payload") or {}

        # Triaging override information: track approval flag and any allowed modes.
        triage_resume_override_approved = False
        triage_override_allowed_modes: list[Any] = []
        if isinstance(raw_request_payload, dict):
            triage_override = raw_request_payload.get(_TRIAGE_RESUME_OVERRIDE_KEY)
            if isinstance(triage_override, dict):
                triage_resume_override_approved = triage_override.get("approved") is True
                modes = triage_override.get("allowed_modes")
                if isinstance(modes, list):
                    triage_override_allowed_modes = list(modes)

        # Normalize source and linked ids early for admin resume validation.
        job_source = str(job.get("source") or "").strip().lower()
        plan_id = str(job.get("plan_id") or "").strip() or None
        intake_id = str(job.get("intake_id") or "").strip() or None
        admin_resume_plan_row: dict[str, Any] | None = None

        if job_source == "admin_triage_resume":
            if not plan_id:
                raise TriageResumeMissingPlanError(
                    "admin triage resume job is missing plan_id; refusing to create a duplicate plan"
                )
            if not intake_id:
                raise TriageResumeMissingPlanError(
                    "admin triage resume job is missing intake_id; refusing to create a duplicate plan"
                )

            # Use a heartbeat-aware read for the linked plan so the store sees activity.
            admin_resume_plan_row = await _to_thread_with_heartbeat(store.get_plan, plan_id)
            if not admin_resume_plan_row:
                raise TriageResumeMissingPlanError(
                    "admin triage resume job linked plan was not found; refusing to create a duplicate plan"
                )

            linked_athlete_id = str(admin_resume_plan_row.get("athlete_id") or "").strip()
            linked_intake_id = str(admin_resume_plan_row.get("intake_id") or "").strip()

            if linked_athlete_id != athlete_id:
                raise TriageResumeMissingPlanError(
                    "admin triage resume job linked plan belongs to a different athlete"
                )

            if linked_intake_id != intake_id:
                raise TriageResumeMissingPlanError(
                    "admin triage resume job intake_id does not match linked plan intake_id"
                )

            _emit_milestone(
                "admin_resume_linkage_validated",
                "Admin resume linkage validated",
                "Linked plan and intake were verified before parsing the request payload.",
                plan_id=plan_id,
                intake_id=intake_id,
            )

        if job_source == "admin_latest_intake":
            if not intake_id:
                raise AdminLatestIntakeLinkageError("admin latest intake job is missing intake_id")
            linked_intake = await _to_thread_with_heartbeat(store.get_intake, intake_id)
            if not linked_intake:
                raise AdminLatestIntakeLinkageError("admin latest intake job intake_id was not found")
            linked_athlete_id = str(linked_intake.get("athlete_id") or "").strip()
            if linked_athlete_id != athlete_id:
                raise AdminLatestIntakeLinkageError("admin latest intake job intake belongs to a different athlete")
            linked_payload = linked_intake.get("intake")
            if not isinstance(linked_payload, dict):
                raise AdminLatestIntakeLinkageError("admin latest intake job linked intake payload is invalid")
            if _stable_payload_hash(linked_payload) != _stable_payload_hash(raw_request_payload):
                raise AdminLatestIntakeLinkageError(
                    "admin latest intake job request_payload does not match linked intake payload"
                )

        await _touch_heartbeat()
        request_body = parse_plan_request(raw_request_payload)
        await _touch_heartbeat()
        _emit_milestone(
            "request_payload_parsed",
            "Request payload parsed",
            "Stored intake payload passed request validation.",
        )
        logger.info(
            "[jobs] generation:start athlete_id=%s job_id=%s source=%s job_plan_id=%s job_intake_id=%s "
            "override_present=%s override_approved=%s override_allowed_modes=%s",
            athlete_id,
            job_id,
            job.get("source"),
            job.get("plan_id"),
            job.get("intake_id"),
            isinstance(raw_request_payload, dict)
            and _TRIAGE_RESUME_OVERRIDE_KEY in raw_request_payload,
            triage_resume_override_approved,
            triage_override_allowed_modes,
        )

        try:
            _emit_milestone(
                "profile_update_started",
                "Profile update started",
                "Refreshing athlete profile fields from the request payload.",
            )
            await _to_thread_with_heartbeat(
                store.update_profile,
                athlete_id,
                ProfileUpdateRequest(
                    full_name=request_body.athlete.full_name,
                    technical_style=request_body.athlete.technical_style,
                    tactical_style=request_body.athlete.tactical_style,
                    stance=request_body.athlete.stance,
                    professional_status=request_body.athlete.professional_status,
                    record=request_body.athlete.record,
                    athlete_timezone=request_body.athlete.athlete_timezone,
                    athlete_locale=request_body.athlete.athlete_locale,
                    onboarding_draft=request_body.model_dump(mode="json"),
                ),
            )
            _emit_milestone(
                "profile_update_finished",
                "Profile update finished",
                "Athlete profile fields were refreshed.",
            )
        except Exception:
            logger.exception("[jobs] generation:update_profile_failed athlete_id=%s job_id=%s", athlete_id, job_id)
            _emit_milestone(
                "profile_update_finished",
                "Profile update finished",
                "Profile refresh failed; generation is continuing with the stored payload.",
                failed=True,
            )
        if not intake_id:
            intake = await _to_thread_with_heartbeat(store.create_intake, athlete_id, request_body)
            intake_id = str(intake["id"])
            job = await _to_thread_with_heartbeat(
                store.update_generation_job,
                job_id,
                intake_id=intake_id,
                heartbeat_at=utc_now_iso(),
            )

        stage1_result = job.get("stage1_result")
        if not isinstance(stage1_result, dict):
            planner_payload = request_body.to_payload()
            if isinstance(raw_request_payload, dict):
                triage_override = raw_request_payload.get(_TRIAGE_RESUME_OVERRIDE_KEY)
                if isinstance(triage_override, dict):
                    planner_payload[_TRIAGE_RESUME_OVERRIDE_KEY] = triage_override
            _emit_milestone(
                "stage1_planner_starting",
                "Stage 1 planner starting",
                "Starting the deterministic planner pass.",
            )
            await _touch_heartbeat()
            _emit_milestone(
                "stage1_planner_invoked",
                "Stage 1 planner invoked",
                "Planner process was invoked and is waiting for its first result.",
            )
            stage1_timeout_seconds = _stage1_planner_timeout_seconds()
            try:
                stage1_result = await run_stage1_planner(
                    planner_fn,
                    planner_payload,
                    progress_callback=progress_callback,
                    timeout_seconds=stage1_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.exception("[jobs] generation:stage1_timeout athlete_id=%s job_id=%s", athlete_id, job_id)
                now_iso = utc_now_iso()
                _emit_milestone(
                    "stage1_planner_timeout",
                    "Stage 1 planner timed out",
                    "Planner did not return after invocation and the job was failed for recovery.",
                    timestamp=now_iso,
                    failed=True,
                )
                stage1_timed_out.set()
                with suppress(Exception):
                    await asyncio.to_thread(
                        store.update_generation_job,
                        job_id,
                        status="failed",
                        error="Stage 1 planner timed out before producing a result.",
                        completed_at=now_iso,
                        heartbeat_at=now_iso,
                    )
                return
            _emit_milestone(
                "stage1_planner_finished",
                "Stage 1 planner finished",
                "Planner returned a Stage 1 result.",
            )
            await _touch_heartbeat()
            if stage1_result.get("status") == "invalid_input":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "message": stage1_result.get("error", "invalid planning input"),
                        "missing_fields": stage1_result.get("missing_fields", []),
                    },
                )
            _stage1_why_log = stage1_result.get("why_log") if isinstance(stage1_result.get("why_log"), dict) else {}
            _injury_triage = _stage1_why_log.get("injury_triage") if isinstance(_stage1_why_log.get("injury_triage"), dict) else {}
            _override_marker = (
                _stage1_why_log.get("injury_triage_resume_override")
                if isinstance(_stage1_why_log.get("injury_triage_resume_override"), dict)
                else None
            )
            logger.info(
                "[jobs] generation:stage1_done athlete_id=%s job_id=%s stage1_status=%s "
                "triage_mode=%s should_block_stage2=%s override_applied=%s",
                athlete_id,
                job_id,
                stage1_result.get("status"),
                _injury_triage.get("mode"),
                _injury_triage.get("should_block_stage2"),
                bool(_override_marker and _override_marker.get("bypassed_blocking") is True),
            )
            _emit_milestone(
                "stage1_result_persist_started",
                "Stage 1 result persist started",
                "Saving Stage 1 planner result to the generation job.",
            )
            job = await _to_thread_with_heartbeat(
                store.update_generation_job,
                job_id,
                stage1_result=stage1_result,
                heartbeat_at=utc_now_iso(),
            )
            _emit_milestone(
                "stage1_result_persisted",
                "Stage 1 result persisted",
                "Stage 1 planner result was saved to the generation job.",
            )
            await _ensure_admin_resume_plan_exists(plan_id)

        final_result = job.get("final_result")
        if not isinstance(final_result, dict):
            await _ensure_admin_resume_plan_exists(plan_id)
            if should_skip_stage2(stage1_result, allow_triage_resume_override=triage_resume_override_approved):
                _emit_milestone(
                    "stage2_skipped",
                    "Stage 2 skipped",
                    "Triage routing held the plan at Stage 1 — no AI finalization needed.",
                )
                final_result = {**stage1_result, "full_name": request_body.athlete.full_name}
            else:
                _emit_milestone(
                    "stage2_drafting",
                    "Stage 2 finalizer drafting",
                    "Sending the planning brief to the AI finalizer.",
                )
                await _touch_heartbeat()
                stage1_result = {
                    **stage1_result,
                    "_generation_source": str(job.get("source") or ""),
                }
                finalized_result = await finalize_stage2_with_timeout(
                    stage2=stage2,
                    stage1_result=stage1_result,
                )
                await _touch_heartbeat()
                final_result = {**finalized_result, "full_name": request_body.athlete.full_name}
                _emit_milestone(
                    "stage2_result_ready",
                    "Stage 2 result ready",
                    "Finalizer result returned; saving review state.",
                )
                if str(final_result.get("status") or "").strip().lower() == "ready":
                    _emit_milestone(
                        "stage2_validated",
                        "Stage 2 finalizer complete",
                        "Validator passed. Final coach-voice plan ready for handoff.",
                    )
                else:
                    _emit_milestone(
                        "stage2_review_required",
                        "Stage 2 needs review",
                        "First-pass finalizer output did not pass validation. No automatic retry was sent.",
                    )
        _emit_milestone(
            "plan_persisting",
            "Saving plan row",
            "Creating or updating the saved plan from the Stage 2 result.",
        )
        plan_id = plan_id or (str(job.get("plan_id") or "") or None)
        plan_row: dict[str, Any] | None = None
        if job_source == "admin_triage_resume":
            plan_row = admin_resume_plan_row
        else:
            if plan_id:
                plan_row = await _to_thread_with_heartbeat(store.get_plan, plan_id)
            if job_source != "admin_latest_intake" and not plan_row and intake_id:
                latest_plan = await asyncio.to_thread(store.get_latest_plan, athlete_id)
                if (
                    latest_plan
                    and str(latest_plan.get("intake_id") or "") == intake_id
                    and str(latest_plan.get("status") or "").strip().lower() != "archived"
                ):
                    plan_row = latest_plan
                    plan_id = str(latest_plan.get("id") or "")

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
            plan_row = await _to_thread_with_heartbeat(
                store.update_plan_stage2,
                plan_id,
                final_result,
            )
        else:
            if job_source == "admin_triage_resume":
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
            plan_row = await _to_thread_with_heartbeat(
                store.create_plan,
                athlete_id=athlete_id,
                intake_id=intake_id,
                request=request_body,
                result=final_result,
            )
            created_plan_id = str(plan_row.get("id") or "").strip()
            verified_plan_row = await _to_thread_with_heartbeat(store.get_plan, created_plan_id) if created_plan_id else None
            verified_athlete_id = str((verified_plan_row or {}).get("athlete_id") or "").strip()
            verified_intake_id = str((verified_plan_row or {}).get("intake_id") or "").strip()
            expected_intake_id = str(intake_id or "").strip()
            intake_id_matches = (not expected_intake_id) or (verified_intake_id == expected_intake_id)
            if not created_plan_id or not verified_plan_row or verified_athlete_id != athlete_id or not intake_id_matches:
                now_iso = utc_now_iso()
                with suppress(Exception):
                    await asyncio.to_thread(
                        store.update_generation_job,
                        job_id,
                        status="failed",
                        error=_PLAN_PERSIST_VERIFICATION_ERROR,
                        completed_at=now_iso,
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
        _emit_milestone(
            "plan_persisted",
            "Plan row persisted",
            "Saved plan row was created or updated.",
            plan_id=plan_id,
        )
        _emit_milestone(
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
                    store.update_generation_job,
                    job_id,
                    status="failed",
                    error=_FINAL_RESULT_PERSIST_TIMEOUT_ERROR,
                    completed_at=now_iso,
                    heartbeat_at=now_iso,
                )
            return
        except Exception:
            logger.exception("[jobs] generation:final_result_persist_failed athlete_id=%s job_id=%s", athlete_id, job_id)
            now_iso = utc_now_iso()
            with suppress(Exception):
                await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    status="failed",
                    error="Stage 2 result persistence failed after plan persistence.",
                    completed_at=now_iso,
                    heartbeat_at=now_iso,
                )
            return
        _emit_milestone(
            "final_result_persisted",
            "Stage 2 result saved",
            "Finalizer output was saved to the generation job.",
        )
        persisted_plan_id = str(job.get("plan_id") or "").strip() if isinstance(job, dict) else ""
        if not persisted_plan_id:
            plan_id = None
        plan_status = str(plan_row.get("status") or "failed")
        final_status = generation_status_from_plan_status(plan_status)
        terminal_missing_plan_id_error = None
        if final_status not in _TERMINAL_GENERATION_JOB_STATUSES:
            final_status = "review_required"
            terminal_missing_plan_id_error = "Generation completed but produced an unmapped plan status."
        if final_status in {"completed", "review_required"} and not plan_id:
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
            _emit_milestone(
                "plan_saved",
                "Plan saved to your workspace",
                "Opening the saved plan for review.",
            )
        await _to_thread_with_heartbeat(
            store.update_generation_job,
            job_id,
            status=final_status,
            error=terminal_missing_plan_id_error,
            plan_id=plan_id,
            completed_at=utc_now_iso(),
            heartbeat_at=utc_now_iso(),
        )
        _emit_milestone(
            "generation_job_terminal_status_persisted",
            "Generation job terminal status persisted",
            "Terminal generation job lifecycle status was saved.",
            final_status=final_status,
            plan_status=plan_status,
            plan_id=plan_id,
        )
        try:
            await asyncio.wait_for(
                _to_thread_with_heartbeat(store.clear_onboarding_draft, athlete_id),
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
    except asyncio.TimeoutError:
        logger.exception("[jobs] generation:stage2_timeout athlete_id=%s job_id=%s", athlete_id, job_id)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error="Stage 2 finalization timed out. Retry the job or run manual review.",
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except Stage2AutomationUnavailableError as exc:
        logger.warning("[jobs] generation:stage2_unavailable athlete_id=%s job_id=%s detail=%s", athlete_id, job_id, exc)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except Stage2AutomationError as exc:
        logger.exception("[jobs] generation:stage2_failed athlete_id=%s job_id=%s", athlete_id, job_id)
        resolved_error = _OPENAI_QUOTA_ADMIN_ERROR if is_openai_quota_error(exc) else str(exc)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=resolved_error,
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
        logger.warning("[jobs] generation:http_error athlete_id=%s job_id=%s detail=%s", athlete_id, job_id, detail)
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=detail,
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except TriageResumeMissingPlanError as exc:
        logger.error(
            "[jobs] generation:resume_missing_plan_failure athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except AdminLatestIntakeLinkageError as exc:
        logger.error(
            "[jobs] generation:admin_latest_intake_linkage_failure athlete_id=%s job_id=%s",
            athlete_id,
            job_id,
        )
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error=str(exc),
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__)
        frame = tb[-1] if tb else None
        logger.exception(
            "[jobs] generation:unhandled_exception athlete_id=%s job_id=%s exception_type=%s exception_msg=%s file=%s line=%s function=%s",
            athlete_id,
            job_id,
            type(exc).__name__,
            str(exc),
            frame.filename if frame else "",
            frame.lineno if frame else "",
            frame.name if frame else "",
        )
        with suppress(Exception):
            await asyncio.to_thread(
                store.update_generation_job,
                job_id,
                status="failed",
                error="Plan generation failed unexpectedly. Check server logs with the request ID.",
                completed_at=utc_now_iso(),
                heartbeat_at=utc_now_iso(),
            )
    finally:
        stop_event.set()
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
        active_tasks.discard(job_id)


async def schedule_generation_job_if_needed(
    *,
    job: dict[str, Any],
    background_tasks: BackgroundTasks,
    store: AppStore,
    planner_fn: Planner,
    stage2: Stage2Automator,
    active_tasks: set[str],
    enable_in_process_generation: bool,
    stale_job_checker: Callable[..., bool],
    stale_after_seconds: int,
) -> dict[str, Any]:
    current_status = str(job.get("status") or "queued")
    if current_status not in {"queued", "running"}:
        return job

    if current_status == "running":
        if stale_job_checker(job, stale_after_seconds=stale_after_seconds):
            job = await asyncio.to_thread(
                recover_stale_running_job,
                job=job,
                store=store,
                stale_after_seconds=stale_after_seconds,
            )
            current_status = str(job.get("status") or "")
            if current_status != "queued":
                return job
        else:
            return job

    if not enable_in_process_generation:
        logger.info(
            "[api] generation:job_created_worker_will_process job_id=%s",
            str(job.get("id") or ""),
        )
        return job

    job_id = str(job["id"])
    if job_id in active_tasks:
        return job

    max_concurrent_jobs = generation_max_concurrent_jobs()
    try:
        active_running_jobs = await asyncio.to_thread(
            store.count_active_generation_jobs,
            stale_after_seconds=stale_after_seconds,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            logger.warning(
                "[jobs] generation:schedule_capacity_count_deferred job_id=%s detail=%s",
                job_id,
                exc.detail,
            )
            return job
        raise

    if active_running_jobs >= max_concurrent_jobs:
        logger.info(
            "[jobs] generation:schedule_capacity_reached job_id=%s active_running_jobs=%s max_concurrent_jobs=%s",
            job_id,
            active_running_jobs,
            max_concurrent_jobs,
        )
        return job

    active_tasks.add(job_id)
    try:
        if _use_fastapi_background_tasks():
            background_tasks.add_task(
                run_generation_job,
                job_id=job_id,
                store=store,
                planner_fn=planner_fn,
                stage2=stage2,
                active_tasks=active_tasks,
            )
        else:
            _schedule_detached_generation_task(
                job_id=job_id,
                store=store,
                planner_fn=planner_fn,
                stage2=stage2,
                active_tasks=active_tasks,
            )
    except Exception:
        active_tasks.discard(job_id)
        logger.exception("[jobs] generation:schedule_failed job_id=%s", job_id)
        return await asyncio.to_thread(
            store.update_generation_job,
            job_id,
            status="failed",
            error="Generation worker failed to schedule.",
            completed_at=utc_now_iso(),
            heartbeat_at=utc_now_iso(),
        )

    return job
