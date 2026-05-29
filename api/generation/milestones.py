"""Progress milestone recorder for the generation runtime.

The recorder appends each emitted milestone to an in-memory list and persists a
capped snapshot to the generation job row on every emit. Persistence failures
are logged and swallowed so they never surface into the planner pipeline.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from ..store import AppStore
from .time_utils import utc_now_iso
from .types import ProgressCallback

logger = logging.getLogger(__name__)

_MAX_PERSISTED_MILESTONES = 40


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
