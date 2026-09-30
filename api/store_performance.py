"""Low-overhead generation-job reads for beta-scale API and worker traffic.

The canonical store keeps full generation rows available for generation and
recovery workflows. Routine UI polling, heartbeats and idle worker queue checks
do not need large ``stage1_result``/``final_result`` blobs, so
``SupabaseAppStore`` reads them through compact SQL RPCs and narrow selects,
defined here as a mixin. Each read falls back to the store's full-row method if
the compact read fails (an old database during a rolling deploy, or a transient
error).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from .settings import env_flag, env_float

logger = logging.getLogger(__name__)

_PLAN_STATUS_SELECT = "id,status,stage2_status,intake_id"


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _single_mapping(data: Any) -> dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
    return None


def _idle_poll_bounds() -> tuple[float, float]:
    initial = env_float("UNLXCK_GENERATION_WORKER_IDLE_POLL_INITIAL_SECONDS", 6.0, minimum=1.0, positive=True)
    maximum = env_float("UNLXCK_GENERATION_WORKER_IDLE_POLL_MAX_SECONDS", 15.0, minimum=1.0, positive=True)
    return initial, max(initial, maximum)


class CompactGenerationReads:
    """Compact generation-job and plan-status reads for ``SupabaseAppStore``.

    Relies on the store's ``client``, ``_run_with_transient_retry`` and the
    full-row methods each read falls back to.
    """

    client: Any
    _run_with_transient_retry: Callable[..., Any]

    def _compact_rpc(self, rpc_name: str, params: dict[str, Any]) -> Any:
        response = self._run_with_transient_retry(
            operation=rpc_name,
            fn=lambda: self.client.rpc(rpc_name, params).execute(),
        )
        return _response_data(response)

    def _compact_status(
        self,
        rpc_name: str,
        params: dict[str, Any],
        fallback: Callable[[], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        try:
            return _single_mapping(self._compact_rpc(rpc_name, params))
        except Exception as exc:  # Rolling-deploy fallback: old DB or transient RPC failure.
            logger.warning(
                "[store-performance] compact status RPC failed operation=%s error_type=%s; falling back",
                rpc_name,
                type(exc).__name__,
            )
            return fallback()

    def get_generation_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Return the athlete-facing status shape without planner result blobs."""
        return self._compact_status(
            "get_generation_job_status_v2",
            {"p_job_id": job_id},
            lambda: self.get_generation_job(job_id),  # type: ignore[attr-defined]
        )

    def get_visible_active_generation_job_status(self, athlete_id: str) -> dict[str, Any] | None:
        return self._compact_status(
            "get_visible_active_generation_job_status_v2",
            {"p_athlete_id": athlete_id},
            lambda: self.get_visible_active_generation_job_for_athlete(athlete_id),  # type: ignore[attr-defined]
        )

    def get_latest_generation_job_status(self, athlete_id: str) -> dict[str, Any] | None:
        return self._compact_status(
            "get_latest_generation_job_status_v2",
            {"p_athlete_id": athlete_id},
            lambda: self.get_latest_generation_job_for_athlete(athlete_id),  # type: ignore[attr-defined]
        )

    def get_plan_status(self, plan_id: str) -> dict[str, Any] | None:
        """Return a plan's ``id,status,stage2_status,intake_id`` without its content."""
        try:
            response = self._run_with_transient_retry(
                operation=f"get_plan_status_metadata plan_id={plan_id}",
                fn=lambda: self.client.table("plans")
                .select(_PLAN_STATUS_SELECT)
                .eq("id", plan_id)
                .limit(1)
                .execute(),
            )
            return _single_mapping(_response_data(response))
        except Exception as exc:
            logger.warning(
                "[store-performance] compact plan lookup failed plan_id=%s error_type=%s; falling back",
                plan_id,
                type(exc).__name__,
            )
            return self.get_plan(plan_id)  # type: ignore[attr-defined]

    def get_latest_plan_status(self, athlete_id: str) -> dict[str, Any] | None:
        """Return the newest plan's ``id,status,stage2_status,intake_id`` for an athlete."""
        try:
            response = self._run_with_transient_retry(
                operation=f"get_latest_plan_status_metadata athlete_id={athlete_id}",
                fn=lambda: self.client.table("plans")
                .select(_PLAN_STATUS_SELECT)
                .eq("athlete_id", athlete_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute(),
            )
            return _single_mapping(_response_data(response))
        except Exception as exc:
            logger.warning(
                "[store-performance] compact latest-plan lookup failed athlete_id=%s error_type=%s; falling back",
                athlete_id,
                type(exc).__name__,
            )
            return self.get_latest_plan(athlete_id)  # type: ignore[attr-defined]

    def _reset_idle_poll(self) -> None:
        self._claimable_idle_delay_seconds = 0.0
        self._claimable_next_poll_at = 0.0

    def _schedule_idle_poll(self, *, now: float) -> float:
        initial, maximum = _idle_poll_bounds()
        previous = float(getattr(self, "_claimable_idle_delay_seconds", 0.0) or 0.0)
        delay = initial if previous <= 0 else min(maximum, max(initial, previous * 2))
        self._claimable_idle_delay_seconds = delay
        self._claimable_next_poll_at = now + delay
        if delay != previous:
            logger.info("[worker] queue idle; next database poll in %.1fs", delay)
        return delay

    def poll_claimable_generation_jobs(
        self,
        *,
        limit: int = 20,
        stale_after_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        """Run one compact queue scan and back off while the queue is empty.

        The worker loop may still wake every few seconds for shutdown handling and
        other duties. During an idle queue this method skips database traffic until
        the adaptive deadline, rising from 6 seconds to a maximum of 15 seconds by
        default. Any returned job resets the backoff immediately.
        """
        now = time.monotonic()
        next_poll_at = float(getattr(self, "_claimable_next_poll_at", 0.0) or 0.0)
        if now < next_poll_at:
            return []

        stale_seconds = max(1, int(stale_after_seconds or 90))
        stale_before = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
        include_legacy_blank = env_flag("UNLXCK_CLAIM_LEGACY_BLANK_STATUS_JOBS")

        try:
            data = self._compact_rpc(
                "list_claimable_generation_jobs_v2",
                {
                    "p_limit": max(1, min(int(limit), 100)),
                    "p_stale_before": stale_before,
                    "p_include_legacy_blank": include_legacy_blank,
                },
            )
            rows = [item for item in (data or []) if isinstance(item, dict)] if isinstance(data, list) else []
        except Exception as exc:  # Keep a rolling deploy functional if the RPC is not present yet.
            logger.warning(
                "[store-performance] compact queue RPC failed error_type=%s; falling back",
                type(exc).__name__,
            )
            self._reset_idle_poll()
            return self.list_claimable_generation_jobs(  # type: ignore[attr-defined]
                limit=limit, stale_after_seconds=stale_after_seconds
            )

        if rows:
            self._reset_idle_poll()
            return rows

        self._schedule_idle_poll(now=now)
        return []

    def list_generation_job_recovery_candidates(self, *, limit: int) -> list[dict[str, Any]]:
        """Summaries of active jobs for the worker's stale-job recovery sweep."""
        try:
            data = self._compact_rpc(
                "list_active_generation_jobs_for_recovery_v1",
                {"p_limit": max(1, min(int(limit), 100))},
            )
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except Exception as exc:  # noqa: BLE001 - fallback is deliberate during rolling deploys
            logger.warning(
                "[worker] compact recovery scan failed error_type=%s; falling back",
                type(exc).__name__,
            )
        return list(self.list_admin_active_generation_jobs(limit=limit))  # type: ignore[attr-defined]


class _CompactStatusStore:
    """Delegate store operations while making plan lookups metadata-only.

    ``_job_response`` validates linked plans and reads their release status. It
    does not need plan text, structured plans or Stage 2 payloads. This proxy
    preserves the mapper's existing interface while reading only plan status
    and caching duplicate lookups within one response.
    """

    def __init__(self, store: Any):
        self._store = store
        self._plan_cache: dict[str, dict[str, Any] | None] = {}
        self._latest_plan_cache: dict[str, dict[str, Any] | None] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        normalized = str(plan_id or "").strip()
        if not normalized:
            return None
        if normalized not in self._plan_cache:
            self._plan_cache[normalized] = self._store.get_plan_status(normalized)
        return self._plan_cache[normalized]

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any] | None:
        normalized = str(athlete_id or "").strip()
        if not normalized:
            return None
        if normalized not in self._latest_plan_cache:
            self._latest_plan_cache[normalized] = self._store.get_latest_plan_status(normalized)
        return self._latest_plan_cache[normalized]


def compact_status_store(store: Any) -> Any:
    """Wrap a store so job responses read plan status instead of whole plans."""
    return _CompactStatusStore(store)
