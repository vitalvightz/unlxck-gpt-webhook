"""Best-effort, idempotent XP hooks for product actions."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone

from api.store import AppStore

logger = logging.getLogger(__name__)

MIN_FEEDBACK_COMMENT_CHARS = 20


def _award(
    store: AppStore,
    *,
    athlete_id: str,
    action: str,
    idempotency_key: str,
) -> dict | None:
    try:
        result = store.award_xp(
            athlete_id,
            action=action,
            idempotency_key=idempotency_key,
        )
        return result if isinstance(result, dict) else None
    except Exception:  # noqa: BLE001 - XP must never break the primary action
        logger.exception(
            "[xp] award failed athlete_id=%s action=%s key=%s",
            athlete_id,
            action,
            idempotency_key,
        )
        return None


def award_checkin_xp(
    store: AppStore,
    *,
    athlete_id: str,
    checkin: Mapping[str, object],
) -> list[dict]:
    checkin_id = str(checkin.get("id") or "").strip()
    training_day = str(checkin.get("training_day") or "").strip()
    if not checkin_id or not training_day:
        return []

    results: list[dict] = []
    first = _award(
        store,
        athlete_id=athlete_id,
        action="first_checkin_completed",
        idempotency_key=f"first-checkin:{athlete_id}",
    )
    if first:
        results.append(first)

    daily = _award(
        store,
        athlete_id=athlete_id,
        action="readiness_checkin_completed",
        idempotency_key=f"checkin:{athlete_id}:{training_day}",
    )
    if daily:
        results.append(daily)
    return results


def _normalized_comment(record: Mapping[str, object]) -> str:
    return " ".join(str(record.get("comment") or "").split())


def award_feedback_xp(
    store: AppStore,
    *,
    athlete_id: str,
    feedback: Mapping[str, object],
) -> dict | None:
    feedback_id = str(feedback.get("id") or "").strip()
    if not feedback_id:
        return None
    comment = _normalized_comment(feedback)
    action = (
        "feedback_with_comment"
        if len(comment) >= MIN_FEEDBACK_COMMENT_CHARS
        else "feedback_submitted"
    )
    return _award(
        store,
        athlete_id=athlete_id,
        action=action,
        idempotency_key=f"feedback:{feedback_id}",
    )


def award_injury_update_xp(
    store: AppStore,
    *,
    athlete_id: str,
    injury: Mapping[str, object],
    training_day: str,
) -> dict | None:
    injury_id = str(injury.get("id") or "").strip()
    if not injury_id or not training_day:
        return None
    return _award(
        store,
        athlete_id=athlete_id,
        action="injury_update_completed",
        idempotency_key=f"injury-update:{injury_id}:{training_day}",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
