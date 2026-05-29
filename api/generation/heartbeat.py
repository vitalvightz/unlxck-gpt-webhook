"""Heartbeat loop and stale-job detection/recovery for the generation runtime."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from ..generation_config import generation_job_stale_after_seconds
from ..store import AppStore, is_pre_start_stale_generation_job
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
