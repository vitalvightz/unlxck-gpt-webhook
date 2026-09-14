from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from contextlib import suppress

from fightcamp.logging_utils import configure_logging

from .environment import apply_production_environment_defaults, should_default_to_production
from .error_sanitizer import sanitize_error_text
from .generation_runtime import default_planner, run_generation_job, utc_now_iso
from .generation_config import generation_job_stale_after_seconds
from .stage2_automation import build_default_stage2_automator
from .store import AppStore, SupabaseAppStore, is_pre_start_stale_generation_job
from .store_performance import list_claimable_generation_jobs
from .worker_recovery import recover_stale_generation_jobs

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        return max(minimum, int(raw_value))
    except ValueError:
        logger.warning("[worker] invalid integer env %s=%r; using %s", name, raw_value, default)
        return default


def _worker_stale_after_seconds() -> int:
    return generation_job_stale_after_seconds()


def _worker_max_concurrent_jobs() -> int:
    return _int_env("UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS", 1, minimum=1)


def _worker_shutdown_grace_seconds() -> int:
    return _int_env("UNLXCK_GENERATION_WORKER_SHUTDOWN_GRACE_SECONDS", 25, minimum=1)


def _worker_recovery_sweep_interval_seconds() -> int:
    return _int_env("UNLXCK_GENERATION_WORKER_RECOVERY_SWEEP_SECONDS", 15, minimum=5)


def _morning_push_sweep_interval_seconds() -> int:
    return _int_env("UNLXCK_MORNING_PUSH_SWEEP_INTERVAL_SECONDS", 600, minimum=60)


async def _run_morning_push_sweep_if_due(
    *,
    store: AppStore,
    state: dict[str, float],
    interval_seconds: int,
) -> None:
    """Piggyback the morning check-in push sweep on the worker's tick loop.

    The sweep itself is idempotent (per-device local-day dedupe), so the cadence
    only bounds delivery latency after the local morning hour. It runs in a
    worker thread (sync store + HTTP calls) and never raises into the loop.
    """

    now = time.monotonic()
    if now - state.get("last_sweep_at", 0.0) < interval_seconds:
        return
    state["last_sweep_at"] = now
    try:
        from .services.morning_push import morning_push_enabled, run_morning_push_sweep

        if not morning_push_enabled():
            return
        await asyncio.to_thread(run_morning_push_sweep, store)
    except Exception:  # noqa: BLE001 - the nudge sweep must never disturb generation
        logger.exception("[worker] morning push sweep failed")


async def _run_generation_recovery_sweep_if_due(
    *,
    store: AppStore,
    active_tasks: set[str],
    stale_after_seconds: int,
    state: dict[str, float],
    interval_seconds: int,
) -> None:
    """Resolve non-claimable stale jobs on a bounded worker cadence."""

    now = time.monotonic()
    if now - state.get("last_sweep_at", 0.0) < interval_seconds:
        return
    state["last_sweep_at"] = now
    await recover_stale_generation_jobs(
        store=store,
        active_tasks=active_tasks,
        stale_after_seconds=stale_after_seconds,
    )


def _install_shutdown_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
) -> None:
    """Trip ``shutdown_event`` on SIGTERM/SIGINT so the worker can drain cleanly."""

    def _request_shutdown(signal_name: str) -> None:
        if not shutdown_event.is_set():
            logger.info("[worker] shutdown:signal received=%s", signal_name)
            shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown, sig.name)
        except (NotImplementedError, RuntimeError, ValueError):
            # Signal handlers may be unavailable (e.g. non-main thread or some
            # platforms). Fall back to the default behaviour in that case.
            logger.debug("[worker] shutdown:add_signal_handler unsupported sig=%s", sig.name)


async def _drain_active_tasks(
    *,
    detached_tasks: set[asyncio.Task[None]],
    active_tasks: set[str],
    grace_seconds: int,
) -> None:
    """Give in-flight generation tasks a grace period, then cancel stragglers.

    Leaves both ``detached_tasks`` and ``active_tasks`` empty so shutdown does
    not pollute in-memory state. Jobs are intentionally not marked failed here:
    cancelled work is recovered via the heartbeat/stale-job path on restart.
    """
    pending = {task for task in detached_tasks if not task.done()}
    if pending:
        logger.info(
            "[worker] shutdown:draining pending_tasks=%s grace_seconds=%s",
            len(pending),
            grace_seconds,
        )
        _, still_pending = await asyncio.wait(pending, timeout=grace_seconds)
        if still_pending:
            logger.warning(
                "[worker] shutdown:cancelling unfinished_tasks=%s after grace period",
                len(still_pending),
            )
            for task in still_pending:
                task.cancel()
            with suppress(Exception):
                # Use a short timeout to prevent hanging indefinitely if a cancelled task blocks during cleanup
                await asyncio.wait(still_pending, timeout=5.0)

    detached_tasks.clear()
    active_tasks.clear()


async def _mark_job_failed_before_runtime(
    *,
    store: AppStore,
    job_id: str,
    error: str,
) -> None:
    with suppress(Exception):
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            return
        failed_at = utc_now_iso()
        await asyncio.to_thread(
            store.fail_generation_job,
            job_id,
            expected_status=str(job.get("status") or "queued"),
            expected_attempt_count=int(job.get("attempt_count") or 0),
            error=error,
            failed_at=failed_at,
            heartbeat_at=failed_at,
        )


async def _run_claimed_job(
    *,
    job_id: str,
    store: AppStore,
    active_tasks: set[str],
) -> None:
    try:
        stage2 = build_default_stage2_automator()
        await run_generation_job(
            job_id=job_id,
            store=store,
            planner_fn=default_planner,
            stage2=stage2,
            active_tasks=active_tasks,
        )
    except Exception as exc:
        logger.exception("[worker] job failed before generation runtime job_id=%s", job_id)
        # The full traceback is in the server log above. The stored job error is
        # athlete/admin-visible, so sanitize it (redacts tokens/PII/payloads and
        # truncates) to match the orchestrator's error-handling convention rather
        # than persisting the raw exception text.
        await _mark_job_failed_before_runtime(
            store=store,
            job_id=job_id,
            error=f"Worker failed before generation runtime: {sanitize_error_text(exc)}",
        )
        active_tasks.discard(job_id)


def _cleanup_worker_task(
    task: asyncio.Task[None],
    *,
    detached_tasks: set[asyncio.Task[None]],
) -> None:
    detached_tasks.discard(task)

    if task.cancelled():
        return

    with suppress(Exception):
        task.result()


async def _tick(
    *,
    store: AppStore,
    active_tasks: set[str],
    detached_tasks: set[asyncio.Task[None]],
    stale_after_seconds: int,
    max_concurrent_jobs: int,
    recovery_state: dict[str, float] | None = None,
    recovery_interval_seconds: int = 15,
) -> None:
    recovery_state = recovery_state if recovery_state is not None else {}
    await _run_generation_recovery_sweep_if_due(
        store=store,
        active_tasks=active_tasks,
        stale_after_seconds=stale_after_seconds,
        state=recovery_state,
        interval_seconds=recovery_interval_seconds,
    )

    remaining_capacity = max_concurrent_jobs - len(active_tasks)
    if remaining_capacity <= 0:
        return

    try:
        candidates = await asyncio.to_thread(
            list_claimable_generation_jobs,
            store,
            limit=remaining_capacity,
            stale_after_seconds=stale_after_seconds,
        )
    except Exception:
        logger.exception("[worker] failed to list claimable generation jobs")
        return

    for job in candidates:
        if len(active_tasks) >= max_concurrent_jobs:
            break

        job_id = str(job.get("id") or "")
        if not job_id or job_id in active_tasks:
            continue

        status = str(job.get("status") or "").strip().lower()
        if status == "running" and not is_pre_start_stale_generation_job(
            job,
            stale_after_seconds=stale_after_seconds,
        ):
            # Defense in depth: even if the compact RPC regresses, a job that
            # already reached worker-claim, Stage 1, mid-pipeline or persistence
            # must never be sent back through the claim/start path.
            continue
        if status not in {"", "queued", "running"}:
            continue

        active_tasks.add(job_id)

        try:
            task = asyncio.create_task(
                _run_claimed_job(
                    job_id=job_id,
                    store=store,
                    active_tasks=active_tasks,
                )
            )
        except Exception:
            logger.exception("[worker] failed to create task job_id=%s", job_id)
            active_tasks.discard(job_id)
            await _mark_job_failed_before_runtime(
                store=store,
                job_id=job_id,
                error="Generation worker failed to schedule.",
            )
            continue

        detached_tasks.add(task)
        task.add_done_callback(
            lambda completed_task: _cleanup_worker_task(
                completed_task,
                detached_tasks=detached_tasks,
            )
        )


async def run_worker() -> None:
    configure_logging()
    if should_default_to_production():
        apply_production_environment_defaults()

    store = SupabaseAppStore.from_env()
    store.validate_runtime_schema()
    mode = "supabase"

    interval_seconds = max(
        1.0,
        float(os.getenv("UNLXCK_GENERATION_WORKER_INTERVAL_SECONDS", "3")),
    )
    stale_after_seconds = _worker_stale_after_seconds()
    max_concurrent_jobs = _worker_max_concurrent_jobs()
    shutdown_grace_seconds = _worker_shutdown_grace_seconds()
    recovery_interval_seconds = _worker_recovery_sweep_interval_seconds()

    active_tasks: set[str] = set()
    detached_tasks: set[asyncio.Task[None]] = set()

    shutdown_event = asyncio.Event()
    _install_shutdown_handlers(asyncio.get_running_loop(), shutdown_event)

    logger.info(
        "[worker] started mode=%s interval_seconds=%s stale_after_seconds=%s max_concurrent_jobs=%s shutdown_grace_seconds=%s recovery_interval_seconds=%s",
        mode,
        interval_seconds,
        stale_after_seconds,
        max_concurrent_jobs,
        shutdown_grace_seconds,
        recovery_interval_seconds,
    )
    if os.getenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "0").strip() == "0":
        logger.info("[worker] generation:worker_only_mode enabled")

    recovery_sweep_state: dict[str, float] = {}
    morning_sweep_state: dict[str, float] = {}
    morning_sweep_interval = _morning_push_sweep_interval_seconds()

    try:
        while not shutdown_event.is_set():
            await _tick(
                store=store,
                active_tasks=active_tasks,
                detached_tasks=detached_tasks,
                stale_after_seconds=stale_after_seconds,
                max_concurrent_jobs=max_concurrent_jobs,
                recovery_state=recovery_sweep_state,
                recovery_interval_seconds=recovery_interval_seconds,
            )
            await _run_morning_push_sweep_if_due(
                store=store,
                state=morning_sweep_state,
                interval_seconds=morning_sweep_interval,
            )
            # Wake early if shutdown is requested mid-interval; otherwise this
            # preserves the existing poll cadence between ticks.
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(shutdown_event.wait(), timeout=interval_seconds)
    finally:
        logger.info(
            "[worker] shutdown:start active_tasks=%s grace_seconds=%s",
            len(active_tasks),
            shutdown_grace_seconds,
        )
        await _drain_active_tasks(
            detached_tasks=detached_tasks,
            active_tasks=active_tasks,
            grace_seconds=shutdown_grace_seconds,
        )
        logger.info("[worker] shutdown:complete")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
