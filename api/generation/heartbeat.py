"""Heartbeat loop and stale-job detection/recovery for the generation runtime."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable

from ..generation_config import generation_job_stale_after_seconds
from ..store import AppStore, is_pre_start_stale_generation_job
from ..store_performance import get_generation_job_status
from .time_utils import utc_now_iso

logger = logging.getLogger(__name__)


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def is_stale_job(job: dict[str, Any], *, stale_after_seconds: int | None = None) -> bool:
    if stale_after_seconds is None:
        stale_after_seconds = generation_job_stale_after_seconds()
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


async def heartbeat_generation_job(
    job_id: str,
    store: AppStore,
    stop_event: asyncio.Event,
    *,
    on_cancelled: Callable[[], None] | None = None,
    interval_seconds: float = 15,
) -> None:
    """Refresh ``heartbeat_at`` on a timer, and stop as soon as someone else
    moves the job off ``running`` (a manual cancel, or the hard-runtime-
    ceiling recovery in ``_classify_running_job_staleness``).

    Blindly writing ``heartbeat_at`` on every tick regardless of the job's
    actual status is what let a cancelled/recovered job look perpetually
    "alive": the heartbeat loop is independent of the generation work, so a
    hang downstream never showed up as stale. Checking status here, in the
    same loop that owns the heartbeat, means the loop itself notices a
    cancellation within one tick and exits — instead of writing heartbeats
    for a job nobody is waiting on anymore.
    """
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except asyncio.TimeoutError:
            try:
                current = await asyncio.to_thread(get_generation_job_status, store, job_id)
            except Exception:
                logger.exception("[jobs] generation:heartbeat_status_check_failed job_id=%s", job_id)
                current = None
            if current is not None and str(current.get("status") or "") != "running":
                logger.info(
                    "[jobs] generation:heartbeat_detected_external_terminal job_id=%s status=%s",
                    job_id,
                    current.get("status"),
                )
                if on_cancelled is not None:
                    with suppress(Exception):
                        on_cancelled()
                return
            try:
                await asyncio.to_thread(
                    store.update_generation_job,
                    job_id,
                    heartbeat_at=utc_now_iso(),
                )
            except Exception:
                logger.exception("[jobs] generation:heartbeat_failed job_id=%s", job_id)