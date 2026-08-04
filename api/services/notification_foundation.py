"""Server-owned notification preferences, arbitration and delivery deduplication.

This module is deliberately independent from any one coaching trigger. Callers
submit typed candidates; the foundation applies account preferences, quiet
hours, expiry, priority and a profile-level delivery claim before Web Push is
attempted. The same delivery key therefore cannot fan out twice just because an
athlete has multiple devices or a worker restarts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from api.notification_models import NotificationCategory, NotificationPreferences

logger = logging.getLogger(__name__)

NOTIFICATION_TITLE_MAX_CHARS = 40
NOTIFICATION_BODY_MAX_CHARS = 90
NOTIFICATION_URL_MAX_CHARS = 500
NOTIFICATION_TAG_MAX_CHARS = 80
NOTIFICATION_DEDUPE_KEY_MAX_CHARS = 160
NOTIFICATION_TYPE_MAX_CHARS = 64
NOTIFICATION_MAX_ATTEMPTS = 3
NOTIFICATION_STALE_CLAIM_AFTER = timedelta(minutes=15)

DeliveryStatus = Literal["sent", "partial", "failed"]


class NotificationStoreError(RuntimeError):
    """The notification preference/ledger store could not be used."""


@dataclass(frozen=True)
class NotificationCandidate:
    profile_id: str
    notification_type: str
    category: NotificationCategory
    priority: int
    title: str
    body: str
    url: str
    tag: str
    dedupe_key: str
    expires_at: datetime
    timezone_name: str = "UTC"
    respect_quiet_hours: bool = True

    def __post_init__(self) -> None:
        normalized = {
            "profile_id": str(self.profile_id or "").strip(),
            "notification_type": str(self.notification_type or "").strip(),
            "title": str(self.title or "").strip(),
            "body": str(self.body or "").strip(),
            "url": str(self.url or "").strip(),
            "tag": str(self.tag or "").strip(),
            "dedupe_key": str(self.dedupe_key or "").strip(),
            "timezone_name": str(self.timezone_name or "").strip() or "UTC",
        }
        for key, value in normalized.items():
            object.__setattr__(self, key, value)

        if not self.profile_id:
            raise ValueError("notification profile_id is required")
        if not self.notification_type or len(self.notification_type) > NOTIFICATION_TYPE_MAX_CHARS:
            raise ValueError("notification_type is invalid")
        if not 1 <= int(self.priority) <= 100:
            raise ValueError("notification priority must be between 1 and 100")
        if not self.title or len(self.title) > NOTIFICATION_TITLE_MAX_CHARS:
            raise ValueError(f"notification title must be 1-{NOTIFICATION_TITLE_MAX_CHARS} characters")
        if not self.body or len(self.body) > NOTIFICATION_BODY_MAX_CHARS:
            raise ValueError(f"notification body must be 1-{NOTIFICATION_BODY_MAX_CHARS} characters")
        if not self.url.startswith("/") or len(self.url) > NOTIFICATION_URL_MAX_CHARS:
            raise ValueError("notification URL must be a bounded app-relative path")
        if not self.tag or len(self.tag) > NOTIFICATION_TAG_MAX_CHARS:
            raise ValueError("notification tag is invalid")
        if not self.dedupe_key or len(self.dedupe_key) > NOTIFICATION_DEDUPE_KEY_MAX_CHARS:
            raise ValueError("notification dedupe_key is invalid")
        if self.expires_at.tzinfo is None:
            object.__setattr__(self, "expires_at", self.expires_at.replace(tzinfo=timezone.utc))


@dataclass(frozen=True)
class NotificationDeliveryClaim:
    delivery_id: str
    claim_token: str
    attempt_count: int


def default_notification_preferences() -> NotificationPreferences:
    return NotificationPreferences()


def _store_key(store: Any) -> int:
    return id(store)


# Fallback storage is used by the in-memory test/dev store, which intentionally
# has no Supabase client. Production SupabaseAppStore always takes the durable
# table/RPC path below.
_MEMORY_PREFERENCES: dict[int, dict[str, dict[str, Any]]] = {}
_MEMORY_DELIVERIES: dict[int, dict[tuple[str, str], dict[str, Any]]] = {}


def _client(store: Any) -> Any | None:
    return getattr(store, "client", None)


def _rows(response: Any) -> list[dict[str, Any]]:
    payload = getattr(response, "data", None)
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def get_notification_preferences(store: Any, profile_id: str) -> NotificationPreferences:
    profile_id = str(profile_id or "").strip()
    if not profile_id:
        raise NotificationStoreError("profile_id is required")

    custom = getattr(store, "get_notification_preferences", None)
    if callable(custom):
        row = custom(profile_id)
        return NotificationPreferences.model_validate(row or {})

    client = _client(store)
    if client is None:
        row = _MEMORY_PREFERENCES.get(_store_key(store), {}).get(profile_id)
        return NotificationPreferences.model_validate(row or {})

    try:
        response = (
            client.table("notification_preferences")
            .select("*")
            .eq("profile_id", profile_id)
            .limit(1)
            .execute()
        )
        rows = _rows(response)
        return NotificationPreferences.model_validate(rows[0] if rows else {})
    except Exception as exc:  # noqa: BLE001 - adapter normalizes backend clients
        logger.warning(
            "[notification] preference read failed profile_id=%s error_class=%s",
            profile_id,
            type(exc).__name__,
        )
        raise NotificationStoreError("notification preferences unavailable") from exc


def update_notification_preferences(
    store: Any,
    profile_id: str,
    changes: dict[str, Any],
) -> NotificationPreferences:
    """Persist a preference patch.

    ``push_enabled`` is a gate, not a bulk write: pausing the account suppresses
    every category at delivery time (see ``candidate_is_allowed``) while leaving
    the per-category choices stored, so resuming restores exactly what the
    athlete had before rather than switching everything back on.
    """

    current = get_notification_preferences(store, profile_id)
    merged = current.model_dump()
    merged.update(changes)
    validated = NotificationPreferences.model_validate(merged)

    custom = getattr(store, "upsert_notification_preferences", None)
    if callable(custom):
        row = custom(profile_id, validated.model_dump())
        return NotificationPreferences.model_validate(row or validated.model_dump())

    client = _client(store)
    if client is None:
        bucket = _MEMORY_PREFERENCES.setdefault(_store_key(store), {})
        bucket[profile_id] = validated.model_dump()
        return validated

    try:
        response = (
            client.table("notification_preferences")
            .upsert(
                {"profile_id": profile_id, **validated.model_dump()},
                on_conflict="profile_id",
            )
            .execute()
        )
        rows = _rows(response)
        return NotificationPreferences.model_validate(rows[0] if rows else validated.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[notification] preference write failed profile_id=%s error_class=%s",
            profile_id,
            type(exc).__name__,
        )
        raise NotificationStoreError("notification preferences unavailable") from exc


def _local_now(now_utc: datetime, timezone_name: str) -> datetime:
    reference = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=timezone.utc)
    try:
        return reference.astimezone(ZoneInfo(timezone_name))
    except Exception:  # noqa: BLE001 - invalid client timezone falls back safely
        return reference.astimezone(timezone.utc)


def is_within_quiet_hours(local_now: datetime, preferences: NotificationPreferences) -> bool:
    if not preferences.quiet_hours_enabled:
        return False
    start_hour, start_minute = (int(part) for part in preferences.quiet_hours_start.split(":"))
    end_hour, end_minute = (int(part) for part in preferences.quiet_hours_end.split(":"))
    current = local_now.hour * 60 + local_now.minute
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


def candidate_is_allowed(
    candidate: NotificationCandidate,
    preferences: NotificationPreferences,
    *,
    now_utc: datetime,
) -> bool:
    reference = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=timezone.utc)
    if candidate.expires_at.astimezone(timezone.utc) <= reference.astimezone(timezone.utc):
        return False
    if not preferences.push_enabled:
        return False
    if not bool(getattr(preferences, candidate.category)):
        return False
    if candidate.respect_quiet_hours and is_within_quiet_hours(
        _local_now(reference, candidate.timezone_name), preferences
    ):
        return False
    return True


def select_notification_candidate(
    candidates: Iterable[NotificationCandidate],
    preferences: NotificationPreferences,
    *,
    now_utc: datetime,
) -> NotificationCandidate | None:
    eligible = [
        candidate
        for candidate in candidates
        if candidate_is_allowed(candidate, preferences, now_utc=now_utc)
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda candidate: (
            candidate.priority,
            candidate.notification_type,
            candidate.dedupe_key,
        ),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _memory_claim(
    store: Any,
    candidate: NotificationCandidate,
    *,
    now_utc: datetime,
) -> NotificationDeliveryClaim | None:
    bucket = _MEMORY_DELIVERIES.setdefault(_store_key(store), {})
    key = (candidate.profile_id, candidate.dedupe_key)
    row = bucket.get(key)
    now = now_utc.astimezone(timezone.utc)
    if row is not None:
        status = str(row.get("status") or "")
        attempts = int(row.get("attempt_count") or 0)
        claimed_at = _parse_datetime(row.get("claimed_at"))
        stale = claimed_at is None or now - claimed_at >= NOTIFICATION_STALE_CLAIM_AFTER
        retryable = status == "failed" and attempts < NOTIFICATION_MAX_ATTEMPTS
        if not retryable and not (status == "pending" and stale):
            return None
        row.update(
            {
                "status": "pending",
                "claim_token": str(uuid4()),
                "claimed_at": now.isoformat(),
                "attempt_count": attempts + 1,
                "expires_at": candidate.expires_at.isoformat(),
            }
        )
    else:
        row = {
            "id": str(uuid4()),
            "profile_id": candidate.profile_id,
            "dedupe_key": candidate.dedupe_key,
            "status": "pending",
            "claim_token": str(uuid4()),
            "claimed_at": now.isoformat(),
            "attempt_count": 1,
            "expires_at": candidate.expires_at.isoformat(),
        }
        bucket[key] = row
    return NotificationDeliveryClaim(
        delivery_id=str(row["id"]),
        claim_token=str(row["claim_token"]),
        attempt_count=int(row["attempt_count"]),
    )


def claim_notification_delivery(
    store: Any,
    candidate: NotificationCandidate,
    *,
    now_utc: datetime,
) -> NotificationDeliveryClaim | None:
    custom = getattr(store, "claim_notification_delivery", None)
    if callable(custom):
        row = custom(candidate, now_utc=now_utc)
        if not row:
            return None
        return NotificationDeliveryClaim(
            delivery_id=str(row["id"]),
            claim_token=str(row["claim_token"]),
            attempt_count=int(row.get("attempt_count") or 1),
        )

    client = _client(store)
    if client is None:
        return _memory_claim(store, candidate, now_utc=now_utc)

    try:
        response = client.rpc(
            "claim_notification_delivery",
            {
                "p_profile_id": candidate.profile_id,
                "p_notification_type": candidate.notification_type,
                "p_category": candidate.category,
                "p_priority": candidate.priority,
                "p_title": candidate.title,
                "p_body": candidate.body,
                "p_url": candidate.url,
                "p_tag": candidate.tag,
                "p_dedupe_key": candidate.dedupe_key,
                "p_expires_at": candidate.expires_at.isoformat(),
            },
        ).execute()
        rows = _rows(response)
        if not rows:
            return None
        row = rows[0]
        return NotificationDeliveryClaim(
            delivery_id=str(row.get("id") or ""),
            claim_token=str(row.get("claim_token") or ""),
            attempt_count=int(row.get("attempt_count") or 1),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[notification] delivery claim failed profile_id=%s type=%s error_class=%s",
            candidate.profile_id,
            candidate.notification_type,
            type(exc).__name__,
        )
        raise NotificationStoreError("notification delivery ledger unavailable") from exc


def finalize_notification_delivery(
    store: Any,
    claim: NotificationDeliveryClaim,
    *,
    status: DeliveryStatus,
    delivered_count: int,
    error_code: str | None = None,
) -> None:
    custom = getattr(store, "finalize_notification_delivery", None)
    if callable(custom):
        custom(
            claim,
            status=status,
            delivered_count=delivered_count,
            error_code=error_code,
        )
        return

    client = _client(store)
    if client is None:
        bucket = _MEMORY_DELIVERIES.get(_store_key(store), {})
        for row in bucket.values():
            if row.get("id") == claim.delivery_id and row.get("claim_token") == claim.claim_token:
                row.update(
                    {
                        "status": status,
                        "delivered_count": max(0, int(delivered_count)),
                        "error_code": str(error_code or "")[:120] or None,
                        "sent_at": datetime.now(timezone.utc).isoformat() if status in {"sent", "partial"} else None,
                    }
                )
                return
        return

    try:
        client.rpc(
            "finalize_notification_delivery",
            {
                "p_delivery_id": claim.delivery_id,
                "p_claim_token": claim.claim_token,
                "p_status": status,
                "p_delivered_count": max(0, int(delivered_count)),
                "p_error_code": str(error_code or "")[:120] or None,
            },
        ).execute()
    except Exception as exc:  # noqa: BLE001 - sending already happened; do not re-raise
        logger.warning(
            "[notification] delivery finalize failed delivery_id=%s error_class=%s",
            claim.delivery_id,
            type(exc).__name__,
        )


def prepare_notification_delivery(
    store: Any,
    candidates: Iterable[NotificationCandidate],
    *,
    now_utc: datetime | None = None,
) -> tuple[NotificationCandidate, NotificationDeliveryClaim] | None:
    candidate_list = list(candidates)
    if not candidate_list:
        return None
    profile_ids = {candidate.profile_id for candidate in candidate_list}
    if len(profile_ids) != 1:
        raise ValueError("notification arbitration must be scoped to one profile")
    reference = now_utc or datetime.now(timezone.utc)
    try:
        preferences = get_notification_preferences(store, candidate_list[0].profile_id)
        selected = select_notification_candidate(
            candidate_list,
            preferences,
            now_utc=reference,
        )
        if selected is None:
            return None
        claim = claim_notification_delivery(store, selected, now_utc=reference)
        if claim is None:
            return None
        return selected, claim
    except NotificationStoreError:
        # Fail closed: a preference or ledger failure must never bypass an opt-out
        # or send a duplicate notification.
        return None
