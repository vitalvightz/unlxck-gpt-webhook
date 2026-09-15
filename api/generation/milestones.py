"""Progress milestone recorder for the generation runtime.

The recorder appends each emitted milestone to an in-memory list and persists a
capped snapshot to the generation job row. Writes are rate-limited and
coalesced: the snapshot is cumulative, so a skipped write loses nothing as long
as a later write (or the end-of-run flush) lands. Persistence failures are
logged and swallowed so they never surface into the planner pipeline.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

from ..store import AppStore
from .time_utils import utc_now_iso
from .types import ProgressCallback

logger = logging.getLogger(__name__)

_MAX_PERSISTED_MILESTONES = 40
_DEFAULT_PERSIST_MIN_INTERVAL_SECONDS = 5.0
# Never let the throttle approach the staleness window. heartbeat_at is owned by
# the independent heartbeat loop (see heartbeat_generation_job, 15s ticks), so
# milestone throttling cannot by itself make a live job look stale — this cap is
# a second belt on top of that.
_MAX_PERSIST_MIN_INTERVAL_SECONDS = 30.0


def _persist_min_interval_seconds() -> float:
    raw = os.getenv("UNLXCK_PROGRESS_PERSIST_MIN_INTERVAL_SECONDS")
    if raw is None or not raw.strip():
        return _DEFAULT_PERSIST_MIN_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "[jobs] generation:invalid_progress_persist_interval value=%r; using default",
            raw,
        )
        return _DEFAULT_PERSIST_MIN_INTERVAL_SECONDS
    if value < 0:
        return 0.0
    return min(value, _MAX_PERSIST_MIN_INTERVAL_SECONDS)


def build_progress_recorder(
    *,
    job_id: str,
    store: AppStore,
    initial_milestones: list[dict[str, Any]] | None = None,
    should_persist: Callable[[], bool] | None = None,
    min_persist_interval_seconds: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[list[dict[str, Any]], ProgressCallback, Callable[[], None]]:
    """Return ``(milestones, callback, flush)``.

    The callback appends a milestone and persists the cumulative snapshot at
    most once per ``min_persist_interval_seconds``. ``flush`` forces a write of
    any milestones recorded since the last persist; the orchestrator calls it
    when the run ends so the closing milestones are never dropped.

    The previous implementation wrote on every emit on the assumption that
    emits were "low-volume (~10 over several minutes)". That assumption did not
    hold: on 2026-09-15 a single job produced ~280 writes in five minutes, and
    each write also triggered a full-row read-back.
    """
    milestones: list[dict[str, Any]] = list(initial_milestones or [])
    interval = (
        _persist_min_interval_seconds()
        if min_persist_interval_seconds is None
        else max(0.0, min(float(min_persist_interval_seconds), _MAX_PERSIST_MIN_INTERVAL_SECONDS))
    )
    # pending_since: None means "nothing recorded since the last SUCCESSFUL
    # persist". last_attempt_at tracks the last ATTEMPT, successful or not —
    # the two differ precisely when the store is failing, which is when the
    # rate limit matters most.
    pending_since: list[float | None] = [None]
    last_attempt_at: list[float | None] = [None]

    def _persist(code: str, *, touch_heartbeat: bool = True) -> None:
        snapshot = list(milestones)
        changes: dict[str, Any] = {"progress_milestones": snapshot}
        if touch_heartbeat:
            changes["heartbeat_at"] = utc_now_iso()
        # Stamp the ATTEMPT, not the success. If the store is down, every
        # subsequent emit would otherwise see last_attempt_at unset and fire
        # another PATCH immediately — the same unbounded write rate this
        # throttle exists to prevent, at the worst possible moment.
        last_attempt_at[0] = monotonic()
        try:
            store.update_generation_job(job_id, refresh=False, **changes)
        except Exception:
            logger.exception(
                "[jobs] generation:milestone_persist_failed job_id=%s code=%s",
                job_id,
                code,
            )
            # pending_since stays set so a later emit or the flush retries, and
            # the snapshot is cumulative so nothing recorded so far is lost.
            return
        pending_since[0] = None

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

        now = monotonic()
        if pending_since[0] is None:
            pending_since[0] = now
        previous = last_attempt_at[0]
        if previous is not None and (now - previous) < interval:
            # Coalesced into the next write; the snapshot is cumulative.
            return
        _persist(code)

    def _flush() -> None:
        """Persist anything recorded since the last write. Safe to call twice.

        Every pending milestone was accepted by the callback while
        ``should_persist`` was still open, so a later timeout/cancel must not
        discard it — that would silently lose the closing milestones of a
        timed-out run. The guard still applies to ``heartbeat_at``: a job that
        has been cancelled or timed out must never look freshly alive.
        """
        if pending_since[0] is None:
            return
        touch_heartbeat = should_persist is None or should_persist()
        _persist("flush", touch_heartbeat=touch_heartbeat)

    return milestones, _callback, _flush
