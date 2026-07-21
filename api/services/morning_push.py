"""Daily morning check-in push, scheduled per-device in athlete-local time.

The generation worker calls :func:`run_morning_push_sweep` periodically. Each
subscription row carries the device's IANA timezone (captured at subscribe
time); a nudge goes out once per athlete-local day, at or after the configured
local morning hour. ``morning_last_sent_day`` on the row is the dedupe key, so
the sweep is idempotent regardless of cadence and safe across restarts.

A subscription with an unknown/empty timezone falls back to UTC rather than
being skipped — a slightly offset nudge beats none.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from api.store import AppStore

from .push_notifications import push_notifications_configured, send_morning_checkin_push

logger = logging.getLogger(__name__)

DEFAULT_MORNING_PUSH_LOCAL_HOUR = 7
# Keyset page size for walking the whole subscription table; the sweep keeps
# paging until a short batch, so growth past any one page is never truncated.
MORNING_SWEEP_BATCH_SIZE = 500
# Past this local hour the nudge is stale: check-in value drops once the
# training day is underway, and a "morning" ping in the evening reads as noise.
DEFAULT_MORNING_PUSH_CUTOFF_LOCAL_HOUR = 11


def _int_env(name: str, default: int, *, minimum: int = 0, maximum: int = 23) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return min(maximum, max(minimum, int(raw)))
    except ValueError:
        logger.warning("[morning_push] invalid integer env %s=%r; using %s", name, raw, default)
        return default


def morning_push_local_hour() -> int:
    return _int_env("UNLXCK_MORNING_PUSH_LOCAL_HOUR", DEFAULT_MORNING_PUSH_LOCAL_HOUR)


def morning_push_cutoff_local_hour() -> int:
    return _int_env(
        "UNLXCK_MORNING_PUSH_CUTOFF_LOCAL_HOUR", DEFAULT_MORNING_PUSH_CUTOFF_LOCAL_HOUR
    )


def morning_push_enabled() -> bool:
    raw = os.getenv("UNLXCK_MORNING_PUSH_ENABLED", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"} and push_notifications_configured()


def _local_now(subscription: dict[str, Any], now_utc: datetime) -> datetime:
    tz_name = str(subscription.get("timezone") or "").strip()
    if tz_name:
        try:
            return now_utc.astimezone(ZoneInfo(tz_name))
        except Exception:  # noqa: BLE001 - a bad device timezone must not kill the sweep
            logger.debug("[morning_push] unknown timezone %r; falling back to UTC", tz_name)
    return now_utc


def is_morning_push_due(
    subscription: dict[str, Any],
    *,
    now_utc: datetime,
    local_hour: int,
    cutoff_local_hour: int,
) -> str | None:
    """Return the athlete-local ISO date to stamp when a nudge is due, else None."""

    local_now = _local_now(subscription, now_utc)
    if not (local_hour <= local_now.hour < cutoff_local_hour):
        return None
    local_day = local_now.date().isoformat()
    if str(subscription.get("morning_last_sent_day") or "") == local_day:
        return None
    return local_day


def run_morning_push_sweep(
    store: AppStore,
    *,
    now_utc: datetime | None = None,
) -> int:
    """Send due morning nudges across all subscriptions. Returns the send count.

    Never raises: each subscription is handled independently so one bad row
    cannot stop the sweep, and any store failure logs and aborts quietly.
    """

    if not morning_push_enabled():
        return 0
    now = now_utc or datetime.now(timezone.utc)
    local_hour = morning_push_local_hour()
    cutoff = morning_push_cutoff_local_hour()

    sent = 0
    after_id: str | None = None
    while True:
        try:
            batch = store.list_all_push_subscriptions(
                limit=MORNING_SWEEP_BATCH_SIZE, after_id=after_id
            )
        except Exception:  # noqa: BLE001 - the sweep must never crash its host loop
            logger.exception("[morning_push] subscription listing failed")
            return sent
        if not batch:
            break
        sent += _sweep_batch(
            store, batch, now=now, local_hour=local_hour, cutoff=cutoff
        )
        if len(batch) < MORNING_SWEEP_BATCH_SIZE:
            break
        after_id = str(batch[-1].get("id") or "")
        if not after_id:
            break
    if sent:
        logger.info("[morning_push] sweep sent=%s", sent)
    return sent


def _sweep_batch(
    store: AppStore,
    batch: list[dict[str, Any]],
    *,
    now: datetime,
    local_hour: int,
    cutoff: int,
) -> int:
    sent = 0
    for subscription in batch:
        if not isinstance(subscription, dict):
            continue
        try:
            local_day = is_morning_push_due(
                subscription,
                now_utc=now,
                local_hour=local_hour,
                cutoff_local_hour=cutoff,
            )
            if local_day is None:
                continue
            # Stamp BEFORE sending: a crash between stamp and send costs one
            # nudge, while the reverse order could re-ping a device on retry.
            store.mark_push_subscription_morning_sent(
                str(subscription.get("id") or ""), sent_day=local_day
            )
            if send_morning_checkin_push(store, subscription):
                sent += 1
            else:
                store.delete_push_subscription_by_endpoint(
                    str(subscription.get("endpoint") or "")
                )
        except Exception:  # noqa: BLE001 - one bad subscription must not stop the sweep
            logger.exception(
                "[morning_push] sweep failed for subscription_id=%s", subscription.get("id")
            )
    return sent
