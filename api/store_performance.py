"""Low-overhead generation-job reads for beta-scale API and worker traffic.

The canonical store keeps full generation rows available for generation and
recovery workflows. Routine UI polling and idle worker queue checks do not need
large ``stage1_result``/``final_result`` blobs, so this module uses compact SQL
RPCs with safe fallbacks to the existing store methods during rolling deploys.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PLAN_STATUS_SELECT = "id,status,stage2_status,intake_id"


def _positive_float_env(name: str, default: float, *, minimum: float = 1.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return max(minimum, default)
    try:
        parsed = float(raw.strip())
    except ValueError:
        logger.warning("[store-performance] invalid %s=%r; using %s", name, raw, default)
        return max(minimum, default)
    if parsed <= 0:
        logger.warning("[store-performance] non-positive %s=%r; using %s", name, raw, default)
        return max(minimum, default)
    return max(minimum, parsed)


def _execute(store: Any, *, operation: str, call: Callable[[], Any]) -> Any:
    runner: Callable[..., Any] | None = getattr(store, "_run_with_transient_retry", None)
    if callable(runner):
        return runner(operation=operation, fn=call)
    return call()


def _rpc_execute(store: Any, *, operation: str, rpc_name: str, params: dict[str, Any]) -> Any:
    return _execute(
        store,
        operation=operation,
        call=lambda: store.client.rpc(rpc_name, params).execute(),
    )


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


def _has_rpc_client(store: Any) -> bool:
    client = getattr(store, "client", None)
    return client is not None and callable(getattr(client, "rpc", None))


def _has_table_client(store: Any) -> bool:
    client = getattr(store, "client", None)
    return client is not None and callable(getattr(client, "table", None))


def _fallback_read(store: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
    method = getattr(store, method_name)
    return method(*args, **kwargs)


def _compact_status_read(
    store: Any,
    *,
    operation: str,
    rpc_name: str,
    params: dict[str, Any],
    fallback_method: str,
    fallback_args: tuple[Any, ...],
) -> dict[str, Any] | None:
    if not _has_rpc_client(store):
        return _fallback_read(store, fallback_method, *fallback_args)
    try:
        response = _rpc_execute(
            store,
            operation=operation,
            rpc_name=rpc_name,
            params=params,
        )
        return _single_mapping(_response_data(response))
    except Exception as exc:  # Rolling-deploy fallback: old DB or transient RPC failure.
        logger.warning(
            "[store-performance] compact status RPC failed operation=%s error_type=%s; falling back",
            operation,
            type(exc).__name__,
        )
        return _fallback_read(store, fallback_method, *fallback_args)


def get_generation_job_status(store: Any, job_id: str) -> dict[str, Any] | None:
    """Return the athlete-facing status shape without planner result blobs."""
    return _compact_status_read(
        store,
        operation="get_generation_job_status_v2",
        rpc_name="get_generation_job_status_v2",
        params={"p_job_id": job_id},
        fallback_method="get_generation_job",
        fallback_args=(job_id,),
    )


def get_visible_active_generation_job_status(
    store: Any,
    athlete_id: str,
) -> dict[str, Any] | None:
    return _compact_status_read(
        store,
        operation="get_visible_active_generation_job_status_v2",
        rpc_name="get_visible_active_generation_job_status_v2",
        params={"p_athlete_id": athlete_id},
        fallback_method="get_visible_active_generation_job_for_athlete",
        fallback_args=(athlete_id,),
    )


def get_latest_generation_job_status(
    store: Any,
    athlete_id: str,
) -> dict[str, Any] | None:
    return _compact_status_read(
        store,
        operation="get_latest_generation_job_status_v2",
        rpc_name="get_latest_generation_job_status_v2",
        params={"p_athlete_id": athlete_id},
        fallback_method="get_latest_generation_job_for_athlete",
        fallback_args=(athlete_id,),
    )


class _CompactStatusStore:
    """Delegate store operations while making plan lookups metadata-only.

    ``_job_response`` validates linked plans and reads their release status. It
    does not need plan text, structured plans or Stage 2 payloads. This proxy
    preserves the mapper's existing interface while selecting four small fields
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
        if normalized in self._plan_cache:
            return self._plan_cache[normalized]
        try:
            response = _execute(
                self._store,
                operation=f"get_plan_status_metadata plan_id={normalized}",
                call=lambda: self._store.client.table("plans")
                .select(_PLAN_STATUS_SELECT)
                .eq("id", normalized)
                .limit(1)
                .execute(),
            )
            row = _single_mapping(_response_data(response))
        except Exception as exc:
            logger.warning(
                "[store-performance] compact plan lookup failed plan_id=%s error_type=%s; falling back",
                normalized,
                type(exc).__name__,
            )
            row = self._store.get_plan(normalized)
        self._plan_cache[normalized] = row
        return row

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any] | None:
        normalized = str(athlete_id or "").strip()
        if not normalized:
            return None
        if normalized in self._latest_plan_cache:
            return self._latest_plan_cache[normalized]
        try:
            response = _execute(
                self._store,
                operation=f"get_latest_plan_status_metadata athlete_id={normalized}",
                call=lambda: self._store.client.table("plans")
                .select(_PLAN_STATUS_SELECT)
                .eq("athlete_id", normalized)
                .order("created_at", desc=True)
                .limit(1)
                .execute(),
            )
            row = _single_mapping(_response_data(response))
        except Exception as exc:
            logger.warning(
                "[store-performance] compact latest-plan lookup failed athlete_id=%s error_type=%s; falling back",
                normalized,
                type(exc).__name__,
            )
            row = self._store.get_latest_plan(normalized)
        self._latest_plan_cache[normalized] = row
        return row


def compact_status_store(store: Any) -> Any:
    """Wrap production stores; leave lightweight test stores unchanged."""
    if not _has_table_client(store):
        return store
    return _CompactStatusStore(store)


def _idle_poll_bounds() -> tuple[float, float]:
    initial = _positive_float_env(
        "UNLXCK_GENERATION_WORKER_IDLE_POLL_INITIAL_SECONDS",
        6.0,
    )
    maximum = _positive_float_env(
        "UNLXCK_GENERATION_WORKER_IDLE_POLL_MAX_SECONDS",
        15.0,
    )
    return initial, max(initial, maximum)


def _reset_idle_poll(store: Any) -> None:
    setattr(store, "_claimable_idle_delay_seconds", 0.0)
    setattr(store, "_claimable_next_poll_at", 0.0)


def _schedule_idle_poll(store: Any, *, now: float) -> float:
    initial, maximum = _idle_poll_bounds()
    previous = float(getattr(store, "_claimable_idle_delay_seconds", 0.0) or 0.0)
    delay = initial if previous <= 0 else min(maximum, max(initial, previous * 2))
    setattr(store, "_claimable_idle_delay_seconds", delay)
    setattr(store, "_claimable_next_poll_at", now + delay)
    if delay != previous:
        logger.info("[worker] queue idle; next database poll in %.1fs", delay)
    return delay


def list_claimable_generation_jobs(
    store: Any,
    *,
    limit: int = 20,
    stale_after_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Run one compact queue scan and back off while the queue is empty.

    The worker loop may still wake every few seconds for shutdown handling and
    other duties. During an idle queue this function skips database traffic until
    the adaptive deadline, rising from 6 seconds to a maximum of 15 seconds by
    default. Any returned job resets the backoff immediately.
    """
    fallback = getattr(store, "list_claimable_generation_jobs")
    if not _has_rpc_client(store):
        return fallback(limit=limit, stale_after_seconds=stale_after_seconds)

    now = time.monotonic()
    next_poll_at = float(getattr(store, "_claimable_next_poll_at", 0.0) or 0.0)
    if now < next_poll_at:
        return []

    stale_seconds = max(1, int(stale_after_seconds or 90))
    stale_before = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
    include_legacy_blank = os.getenv("UNLXCK_CLAIM_LEGACY_BLANK_STATUS_JOBS", "").strip() == "1"

    try:
        response = _rpc_execute(
            store,
            operation="list_claimable_generation_jobs_v2",
            rpc_name="list_claimable_generation_jobs_v2",
            params={
                "p_limit": max(1, min(int(limit), 100)),
                "p_stale_before": stale_before,
                "p_include_legacy_blank": include_legacy_blank,
            },
        )
        data = _response_data(response)
        rows = [item for item in (data or []) if isinstance(item, dict)] if isinstance(data, list) else []
    except Exception as exc:  # Keep a rolling deploy functional if the RPC is not present yet.
        logger.warning(
            "[store-performance] compact queue RPC failed error_type=%s; falling back",
            type(exc).__name__,
        )
        _reset_idle_poll(store)
        return fallback(limit=limit, stale_after_seconds=stale_after_seconds)

    if rows:
        _reset_idle_poll(store)
        return rows

    _schedule_idle_poll(store, now=now)
    return []
