"""Best-effort web push delivery to athlete browsers.

Sends VAPID-signed Web Push messages to the subscriptions saved by the PWA
(``push_subscriptions``). Delivery is always best-effort and failure-isolated:
a push must never break the flow that triggered it (plan approval, structured
card landing, the morning sweep). Dead endpoints reported by the push service
(404/410) are pruned so lists stay clean.

Configuration (all optional — push is silently disabled when unset):
  - ``UNLXCK_VAPID_PRIVATE_KEY``: base64url-encoded VAPID private key
    (as produced by ``npx web-push generate-vapid-keys`` / ``vapid``).
  - ``UNLXCK_VAPID_PUBLIC_KEY``: matching base64url public key; served to the
    browser for ``PushManager.subscribe``.
  - ``UNLXCK_VAPID_SUBJECT``: contact URI claim, defaults to the operator email.
  - ``UNLXCK_PUSH_SITE_URL``: origin used to build notification deep links.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from api.store import AppStore

logger = logging.getLogger(__name__)

DEFAULT_VAPID_SUBJECT = "mailto:unlxckedmind@gmail.com"

PLAN_READY_TAG = "plan-ready"
MORNING_CHECKIN_TAG = "morning-checkin"

PLAN_READY_TITLE = "Your camp is LXCKED IN"
PLAN_READY_BODY = "Your final camp is live."

MORNING_CHECKIN_TITLE = "Morning check-in"
MORNING_CHECKIN_BODY = "Log how you're feeling before today's session."


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


def _endpoint_is_gone(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code in (404, 410)


def send_push_to_subscription(subscription: dict[str, Any], payload: str) -> bool:
    """Send one push. Returns False when the endpoint is dead and should be pruned.

    Any other failure (transient network, misconfiguration) logs and returns
    True so the subscription is kept for future attempts. Never raises.
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
            ttl=12 * 3600,
            timeout=10,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - push delivery must stay failure-isolated
        try:
            from pywebpush import WebPushException

            if isinstance(exc, WebPushException) and _endpoint_is_gone(exc):
                logger.info("[push] endpoint gone, pruning subscription_id=%s", subscription.get("id"))
                return False
        except Exception:  # noqa: BLE001 - even the import must not break the caller
            pass
        logger.warning(
            "[push] delivery failed subscription_id=%s error_class=%s",
            subscription.get("id"),
            type(exc).__name__,
        )
        return True


def send_push_to_profile(
    store: AppStore,
    profile_id: str,
    *,
    title: str,
    body: str,
    url: str,
    tag: str,
) -> int:
    """Send a push to every subscription the profile has. Returns the send count.

    Best-effort throughout: a missing configuration or store failure logs and
    returns 0. Dead endpoints are pruned as they are discovered.
    """

    if not push_notifications_configured():
        return 0
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        return 0
    try:
        subscriptions = store.list_push_subscriptions(profile_id)
    except Exception:  # noqa: BLE001 - lookups must not break the triggering flow
        logger.exception("[push] subscription lookup failed profile_id=%s", profile_id)
        return 0

    payload = build_push_payload(title=title, body=body, url=url, tag=tag)
    sent = 0
    for subscription in subscriptions:
        if not isinstance(subscription, dict):
            continue
        if send_push_to_subscription(subscription, payload):
            sent += 1
        else:
            try:
                store.delete_push_subscription_by_endpoint(str(subscription.get("endpoint") or ""))
            except Exception:  # noqa: BLE001 - pruning is best-effort
                logger.warning(
                    "[push] failed to prune dead endpoint subscription_id=%s",
                    subscription.get("id"),
                )
    if sent:
        logger.info("[push] sent tag=%s profile_id=%s count=%s", tag, profile_id, sent)
    return sent


def send_plan_ready_push(store: AppStore, *, athlete_id: str, plan_id: str) -> int:
    """The lock-in card's "we'll notify you": the enhanced card just went live."""

    plan_id = str(plan_id or "").strip()
    return send_push_to_profile(
        store,
        athlete_id,
        title=PLAN_READY_TITLE,
        body=PLAN_READY_BODY,
        url=_push_url(f"/plans/{plan_id}" if plan_id else "/plans"),
        tag=PLAN_READY_TAG,
    )


def send_morning_checkin_push(store: AppStore, subscription: dict[str, Any]) -> bool:
    """One morning nudge to one subscription. Returns False when it should be pruned."""

    payload = build_push_payload(
        title=MORNING_CHECKIN_TITLE,
        body=MORNING_CHECKIN_BODY,
        url=_push_url("/today"),
        tag=MORNING_CHECKIN_TAG,
    )
    return send_push_to_subscription(subscription, payload)
