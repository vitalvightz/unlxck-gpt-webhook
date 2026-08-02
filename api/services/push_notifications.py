"""Best-effort web push delivery to athlete browsers.

Sends VAPID-signed Web Push messages to subscriptions saved by the PWA. Every
account-level notification now passes through the notification foundation first:
preferences, quiet hours, expiry, priority and a profile-level delivery claim are
resolved before fan-out to the athlete's devices.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from api.services.notification_foundation import (
    NotificationCandidate,
    finalize_notification_delivery,
    prepare_notification_delivery,
)
from api.store import AppStore

logger = logging.getLogger(__name__)

DEFAULT_VAPID_SUBJECT = "mailto:unlxckedmind@gmail.com"
DEFAULT_PUSH_TTL_SECONDS = 12 * 3600

PLAN_READY_TAG = "plan-ready"
MORNING_CHECKIN_TAG = "morning-checkin"

PLAN_READY_TITLE = "Your camp is LXCKED IN"
PLAN_READY_BODY = "Your final camp is live."

MORNING_CHECKIN_TITLE = "Check in before we train"
MORNING_CHECKIN_BODY = "Give me sleep, body and pain so I can set today's call."


def vapid_private_key() -> str:
    return os.getenv("UNLXCK_VAPID_PRIVATE_KEY", "").strip()


def vapid_public_key() -> str:
    return os.getenv("UNLXCK_VAPID_PUBLIC_KEY", "").strip()


def vapid_subject() -> str:
    return os.getenv("UNLXCK_VAPID_SUBJECT", "").strip() or DEFAULT_VAPID_SUBJECT


def push_notifications_configured() -> bool:
    return bool(vapid_private_key() and vapid_public_key())


def _push_url(path: str) -> str:
    """Absolute-path deep link; the service worker resolves it on its own origin."""
    site = os.getenv("UNLXCK_PUSH_SITE_URL", "").strip().rstrip("/")
    return f"{site}{path}" if site else path


def build_push_payload(*, title: str, body: str, url: str, tag: str) -> str:
    return json.dumps({"title": title, "body": body, "url": url, "tag": tag})


def _remaining_push_ttl_seconds(*, expires_at: datetime, now_utc: datetime) -> int:
    """Candidate lifetime bounded by the existing 12-hour transport ceiling."""

    expires = expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    reference = now_utc
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    remaining = math.ceil(
        (expires.astimezone(timezone.utc) - reference.astimezone(timezone.utc)).total_seconds()
    )
    return max(0, min(DEFAULT_PUSH_TTL_SECONDS, remaining))


def _endpoint_is_gone(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code in (404, 410)


def send_push_to_subscription(
    subscription: dict[str, Any],
    payload: str,
    *,
    ttl_seconds: int = DEFAULT_PUSH_TTL_SECONDS,
) -> bool | None:
    """Send one push without raising.

    Returns ``True`` when the push service accepted the message, ``False`` only
    for a missing/dead endpoint that should be pruned, and ``None`` for a
    temporary or configuration failure. Keeping those outcomes separate lets
    the delivery ledger retry transient failures without deleting the device or
    falsely recording a successful notification.
    """

    endpoint = str(subscription.get("endpoint") or "")
    if not endpoint:
        return False
    try:
        from pywebpush import WebPushException, webpush

        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {
                    "p256dh": str(subscription.get("p256dh") or ""),
                    "auth": str(subscription.get("auth") or ""),
                },
            },
            data=payload,
            vapid_private_key=vapid_private_key(),
            vapid_claims={"sub": vapid_subject()},
            ttl=max(0, min(DEFAULT_PUSH_TTL_SECONDS, int(ttl_seconds))),
            timeout=10,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - push delivery must stay failure-isolated
        try:
            from pywebpush import WebPushException

            if isinstance(exc, WebPushException) and _endpoint_is_gone(exc):
                logger.info(
                    "[push] endpoint gone, pruning subscription_id=%s",
                    subscription.get("id"),
                )
                return False
        except Exception:  # noqa: BLE001 - even the import must not break the caller
            pass
        logger.warning(
            "[push] delivery failed subscription_id=%s error_class=%s",
            subscription.get("id"),
            type(exc).__name__,
        )
        return None


def _send_payload_to_profile(
    store: AppStore,
    profile_id: str,
    payload: str,
    *,
    ttl_seconds: int = DEFAULT_PUSH_TTL_SECONDS,
) -> tuple[int, int, int]:
    try:
        subscriptions = store.list_push_subscriptions(profile_id)
    except Exception:  # noqa: BLE001 - lookups must not break the triggering flow
        logger.exception("[push] subscription lookup failed profile_id=%s", profile_id)
        return 0, 0, 1

    attempted = 0
    sent = 0
    transient_failures = 0
    for subscription in subscriptions:
        if not isinstance(subscription, dict):
            continue
        attempted += 1
        outcome = send_push_to_subscription(
            subscription,
            payload,
            ttl_seconds=ttl_seconds,
        )
        if outcome is True:
            sent += 1
        elif outcome is False:
            try:
                store.delete_push_subscription_by_endpoint(
                    str(subscription.get("endpoint") or "")
                )
            except Exception:  # noqa: BLE001 - pruning is best-effort
                logger.warning(
                    "[push] failed to prune dead endpoint subscription_id=%s",
                    subscription.get("id"),
                )
        else:
            transient_failures += 1
    return sent, attempted, transient_failures


def send_push_to_profile(
    store: AppStore,
    profile_id: str,
    *,
    title: str,
    body: str,
    url: str,
    tag: str,
) -> int:
    """Low-level push fan-out with no preference or ledger decision.

    Kept for isolated delivery tests and internal compatibility. Product-level
    notifications should use :func:`dispatch_push_candidate` instead.
    """

    if not push_notifications_configured():
        return 0
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        return 0
    payload = build_push_payload(title=title, body=body, url=url, tag=tag)
    sent, _attempted, _transient_failures = _send_payload_to_profile(
        store,
        profile_id,
        payload,
    )
    if sent:
        logger.info("[push] sent tag=%s profile_id=%s count=%s", tag, profile_id, sent)
    return sent


def dispatch_push_candidate(
    store: AppStore,
    candidate: NotificationCandidate,
    *,
    now_utc: datetime | None = None,
) -> int:
    """Apply notification policy, claim one durable decision, then fan out."""

    if not push_notifications_configured():
        return 0
    reference = now_utc or datetime.now(timezone.utc)
    prepared = prepare_notification_delivery(store, [candidate], now_utc=reference)
    if prepared is None:
        return 0
    selected, claim = prepared
    ttl_seconds = _remaining_push_ttl_seconds(
        expires_at=selected.expires_at,
        now_utc=reference,
    )
    if ttl_seconds <= 0:
        finalize_notification_delivery(
            store,
            claim,
            status="failed",
            delivered_count=0,
            error_code="expired_before_delivery",
        )
        return 0
    payload = build_push_payload(
        title=selected.title,
        body=selected.body,
        url=_push_url(selected.url),
        tag=selected.tag,
    )
    sent, attempted, transient_failures = _send_payload_to_profile(
        store,
        selected.profile_id,
        payload,
        ttl_seconds=ttl_seconds,
    )
    if sent <= 0:
        final_status = "failed"
        if attempted == 0:
            error_code = "no_active_subscription"
        elif transient_failures:
            error_code = "delivery_failed"
        else:
            error_code = "dead_endpoint_pruned"
    elif sent < attempted:
        final_status = "partial"
        error_code = (
            "partial_delivery_failure"
            if transient_failures
            else "dead_endpoint_pruned"
        )
    else:
        final_status = "sent"
        error_code = None
    finalize_notification_delivery(
        store,
        claim,
        status=final_status,
        delivered_count=sent,
        error_code=error_code,
    )
    if sent:
        logger.info(
            "[push] sent type=%s profile_id=%s count=%s attempt=%s ttl_seconds=%s",
            selected.notification_type,
            selected.profile_id,
            sent,
            claim.attempt_count,
            ttl_seconds,
        )
    return sent


def send_plan_ready_push(store: AppStore, *, athlete_id: str, plan_id: str) -> int:
    """The enhanced camp card went live; dedupe once per athlete and plan."""

    plan_id = str(plan_id or "").strip()
    profile_id = str(athlete_id or "").strip()
    if not profile_id:
        return 0
    candidate = NotificationCandidate(
        profile_id=profile_id,
        notification_type="plan_ready",
        category="plan_update_alerts",
        priority=40,
        title=PLAN_READY_TITLE,
        body=PLAN_READY_BODY,
        url=f"/plans/{plan_id}" if plan_id else "/plans",
        tag=PLAN_READY_TAG,
        dedupe_key=f"plan-ready:{plan_id or 'latest'}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        # Plan completion is an explicit product event, not a routine coaching
        # nudge. Preserve the current immediate alert behaviour.
        respect_quiet_hours=False,
    )
    return dispatch_push_candidate(store, candidate)


def _local_day(now_utc: datetime, timezone_name: str) -> str:
    try:
        return now_utc.astimezone(ZoneInfo(timezone_name)).date().isoformat()
    except Exception:  # noqa: BLE001
        return now_utc.astimezone(timezone.utc).date().isoformat()


def send_morning_checkin_push(
    store: AppStore,
    subscription: dict[str, Any],
    *,
    local_day: str | None = None,
    now_utc: datetime | None = None,
    expires_at: datetime | None = None,
) -> int:
    """Submit one profile-level morning coaching candidate.

    The delivery ledger decides once per profile/day, then the winning decision
    fans out to every current device. A subscription without profile_id is only
    supported for the low-level unit-test compatibility path.
    """

    reference = now_utc or datetime.now(timezone.utc)
    profile_id = str(subscription.get("profile_id") or "").strip()
    timezone_name = str(subscription.get("timezone") or "").strip() or "UTC"
    day = str(local_day or "").strip() or _local_day(reference, timezone_name)
    if not profile_id:
        payload = build_push_payload(
            title=MORNING_CHECKIN_TITLE,
            body=MORNING_CHECKIN_BODY,
            url=_push_url("/today"),
            tag=MORNING_CHECKIN_TAG,
        )
        outcome = send_push_to_subscription(subscription, payload)
        return 1 if outcome is True else 0

    candidate = NotificationCandidate(
        profile_id=profile_id,
        notification_type="morning_checkin",
        category="checkin_reminders",
        priority=50,
        title=MORNING_CHECKIN_TITLE,
        body=MORNING_CHECKIN_BODY,
        url="/today#today-checkin",
        tag=MORNING_CHECKIN_TAG,
        dedupe_key=f"morning-checkin:{day}",
        expires_at=expires_at or (reference + timedelta(hours=4)),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
    )
    return dispatch_push_candidate(store, candidate, now_utc=reference)
