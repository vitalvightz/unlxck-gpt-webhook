"""Daily profile-level morning notification sweep in athlete-local time.

Subscriptions still carry the device timezone captured at opt-in, but the sweep
now chooses one canonical subscription per profile, creates one coaching
decision, and lets the notification delivery ledger fan that decision out to all
current devices. Per-device morning stamps remain as a compatibility hint; the
profile-level ledger is the authoritative dedupe boundary.
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
    """Return the athlete-local ISO date to stamp when a nudge is due, else None."""

    local_now = _local_now(subscription, now_utc)
    if not (local_hour <= local_now.hour < cutoff_local_hour):
        return None
    local_day = local_now.date().isoformat()
    if str(subscription.get("morning_last_sent_day") or "") == local_day:
        return None
    return local_day


def _canonical_subscription_is_newer(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """Prefer the most recently refreshed device as the profile timezone hint."""

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
            # A missing profile id should not happen in production, but keep an
            # isolated key so a malformed row cannot suppress another athlete.
            key = profile_id or f"subscription:{subscription.get('id') or subscription.get('endpoint')}"
            current = canonical.get(key)
            if current is None or _canonical_subscription_is_newer(subscription, current):
                canonical[key] = subscription
        if len(batch) < MORNING_SWEEP_BATCH_SIZE:
            break
        after_id = str(batch[-1].get("id") or "")
        if not after_id:
            break
    return list(canonical.values())


def _cutoff_utc(
    subscription: dict[str, Any],
    *,
    now_utc: datetime,
    cutoff_local_hour: int,
) -> datetime:
    local_now = _local_now(subscription, now_utc)
    local_cutoff = local_now.replace(
        hour=cutoff_local_hour,
        minute=0,
        second=0,
        microsecond=0,
    )
    return local_cutoff.astimezone(timezone.utc)


def _mark_profile_morning_sent(
    store: AppStore,
    subscription: dict[str, Any],
    *,
    local_day: str,
) -> None:
    profile_id = str(subscription.get("profile_id") or "").strip()
    rows = store.list_push_subscriptions(profile_id) if profile_id else [subscription]
    for row in rows:
        subscription_id = str(row.get("id") or "")
        if subscription_id:
            store.mark_push_subscription_morning_sent(subscription_id, sent_day=local_day)


def run_morning_push_sweep(
    store: AppStore,
    *,
    now_utc: datetime | None = None,
) -> int:
    """Send at most one morning decision per profile and local day. Never raises."""

    if not morning_push_enabled():
        return 0
    now = now_utc or datetime.now(timezone.utc)
    local_hour = morning_push_local_hour()
    cutoff = morning_push_cutoff_local_hour()

    try:
        canonical_subscriptions = _list_canonical_profile_subscriptions(store)
    except Exception:  # noqa: BLE001 - the sweep must never crash its host loop
        logger.exception("[morning_push] subscription listing failed")
        return 0

    sent = 0
    for subscription in canonical_subscriptions:
        try:
            local_day = is_morning_push_due(
                subscription,
                now_utc=now,
                local_hour=local_hour,
                cutoff_local_hour=cutoff,
            )
            if local_day is None:
                continue
            delivered = send_morning_checkin_push(
                store,
                subscription,
                local_day=local_day,
                now_utc=now,
                expires_at=_cutoff_utc(
                    subscription,
                    now_utc=now,
                    cutoff_local_hour=cutoff,
                ),
            )
            if delivered > 0:
                sent += delivered
                _mark_profile_morning_sent(store, subscription, local_day=local_day)
        except Exception:  # noqa: BLE001 - one bad profile must not stop the sweep
            logger.exception(
                "[morning_push] sweep failed for profile_id=%s subscription_id=%s",
                subscription.get("profile_id"),
                subscription.get("id"),
            )
    if sent:
        logger.info("[morning_push] sweep sent=%s", sent)
    return sent
