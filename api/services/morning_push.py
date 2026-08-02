"""Profile-level coaching notification sweep in athlete-local time.

The worker calls this entrypoint every ten minutes. It always evaluates athlete-
selected session timing, because a saved training time may be early, late or after
midnight. Routine morning/session-log coaching keeps its own narrower windows,
and STOP remains constrained inside the session-timing resolver.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from api.store import AppStore

from .intelligent_notifications import (
    MORNING_NOTIFICATION_TYPES,
    SESSION_LOG_END_HOUR,
    SESSION_LOG_START_HOUR,
    dispatch_coaching_notification,
)
from .push_notifications import push_notifications_configured
from .session_timing_notifications import dispatch_session_timing_notification

logger = logging.getLogger(__name__)

DEFAULT_MORNING_PUSH_LOCAL_HOUR = 7
MORNING_SWEEP_BATCH_SIZE = 500
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
    return now_utc.astimezone(timezone.utc)


def is_morning_push_due(
    subscription: dict[str, Any],
    *,
    now_utc: datetime,
    local_hour: int,
    cutoff_local_hour: int,
) -> str | None:
    """Compatibility helper: return the athlete-local morning date when due."""

    local_now = _local_now(subscription, now_utc)
    if not (local_hour <= local_now.hour < cutoff_local_hour):
        return None
    local_day = local_now.date().isoformat()
    if str(subscription.get("morning_last_sent_day") or "") == local_day:
        return None
    return local_day


def _canonical_subscription_is_newer(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    candidate_updated = str(candidate.get("updated_at") or candidate.get("created_at") or "")
    current_updated = str(current.get("updated_at") or current.get("created_at") or "")
    if candidate_updated != current_updated:
        return candidate_updated > current_updated
    return str(candidate.get("id") or "") > str(current.get("id") or "")


def _list_canonical_profile_subscriptions(store: AppStore) -> list[dict[str, Any]]:
    canonical: dict[str, dict[str, Any]] = {}
    after_id: str | None = None
    while True:
        batch = store.list_all_push_subscriptions(
            limit=MORNING_SWEEP_BATCH_SIZE,
            after_id=after_id,
        )
        if not batch:
            break
        for subscription in batch:
            if not isinstance(subscription, dict):
                continue
            profile_id = str(subscription.get("profile_id") or "").strip()
            if not profile_id:
                continue
            current = canonical.get(profile_id)
            if current is None or _canonical_subscription_is_newer(subscription, current):
                canonical[profile_id] = subscription
        if len(batch) < MORNING_SWEEP_BATCH_SIZE:
            break
        after_id = str(batch[-1].get("id") or "")
        if not after_id:
            break
    return list(canonical.values())


def _mark_profile_morning_sent(
    store: AppStore,
    subscription: dict[str, Any],
    *,
    local_day: str,
) -> None:
    profile_id = str(subscription.get("profile_id") or "").strip()
    rows = store.list_push_subscriptions(profile_id)
    for row in rows:
        subscription_id = str(row.get("id") or "")
        if subscription_id:
            store.mark_push_subscription_morning_sent(subscription_id, sent_day=local_day)


def _is_routine_coaching_action_window(local_now: datetime) -> bool:
    return (
        morning_push_local_hour() <= local_now.hour < morning_push_cutoff_local_hour()
        or SESSION_LOG_START_HOUR <= local_now.hour < SESSION_LOG_END_HOUR
    )


def run_morning_push_sweep(
    store: AppStore,
    *,
    now_utc: datetime | None = None,
) -> int:
    """Resolve and send at most one coaching decision per profile. Never raises."""

    if not morning_push_enabled():
        return 0
    now = now_utc or datetime.now(timezone.utc)

    try:
        canonical_subscriptions = _list_canonical_profile_subscriptions(store)
    except Exception:  # noqa: BLE001
        logger.exception("[morning_push] subscription listing failed")
        return 0

    sent = 0
    for subscription in canonical_subscriptions:
        profile_id = str(subscription.get("profile_id") or "").strip()
        timezone_name = str(subscription.get("timezone") or "").strip() or "UTC"
        local_now = _local_now(subscription, now)
        try:
            # Always evaluate saved session timing. Its own window and the user's
            # quiet-hour preferences decide whether an early/late reminder exists.
            timed_result = dispatch_session_timing_notification(
                store,
                profile_id=profile_id,
                timezone_name=timezone_name,
                now_utc=now,
            )
            if timed_result is not None and timed_result.delivered_count > 0:
                sent += timed_result.delivered_count
                continue

            if not _is_routine_coaching_action_window(local_now):
                continue

            result = dispatch_coaching_notification(
                store,
                profile_id=profile_id,
                timezone_name=timezone_name,
                now_utc=now,
            )
            if result is None or result.delivered_count <= 0:
                continue
            sent += result.delivered_count
            if result.notification_type in MORNING_NOTIFICATION_TYPES:
                _mark_profile_morning_sent(
                    store,
                    subscription,
                    local_day=local_now.date().isoformat(),
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "[morning_push] coaching sweep failed profile_id=%s subscription_id=%s",
                profile_id,
                subscription.get("id"),
            )
    if sent:
        logger.info("[morning_push] coaching sweep sent=%s", sent)
    return sent
