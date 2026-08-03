"""Best-effort, idempotent XP hooks for product actions."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from api.store import AppStore

logger = logging.getLogger(__name__)

MIN_FEEDBACK_COMMENT_CHARS = 20
ACTIVATION_READY_PLAN_STATUSES = frozenset({"ready", "publishable_with_flags"})
# Keep aligned with the combat sports that are selectable in the private beta.
# Disabled coming-soon options and arbitrary persisted strings do not complete
# the activation profile milestone.
ACTIVATION_COMBAT_SPORTS = frozenset({"boxing", "kickboxing", "mma"})


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


def _value(source: object, key: str) -> object:
    try:
        if isinstance(source, Mapping):
            return source.get(key)
        return getattr(source, key, None)
    except Exception:  # noqa: BLE001 - eligibility must fail closed
        return None


def _normalized_values(value: object) -> frozenset[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return frozenset()
    try:
        return frozenset(
            normalized
            for item in value
            if (normalized := str(item or "").strip().lower())
        )
    except Exception:  # noqa: BLE001 - malformed persisted state fails closed
        return frozenset()


def profile_activation_complete(profile: object) -> bool:
    """Return whether the persisted profile has a live combat sport and name."""

    try:
        full_name = str(_value(profile, "full_name") or "").strip()
        technical_styles = _normalized_values(_value(profile, "technical_style"))
        return bool(full_name and technical_styles.intersection(ACTIVATION_COMBAT_SPORTS))
    except Exception:  # noqa: BLE001 - malformed profile state fails closed
        return False


def plan_activation_ready(plan: object) -> bool:
    """Return whether a persisted athlete-visible plan is ready for use."""

    try:
        plan_id = str(_value(plan, "plan_id") or _value(plan, "id") or "").strip()
        status = str(_value(plan, "status") or "").strip().lower()
        return bool(plan_id and status in ACTIVATION_READY_PLAN_STATUSES)
    except Exception:  # noqa: BLE001 - malformed plan state fails closed
        return False


def _reconcile_activation_milestone(
    store: AppStore,
    *,
    athlete_id: str,
    action: str,
    idempotency_key: str,
    eligible: Callable[[], bool],
) -> dict | None:
    """Reconcile one activation milestone without affecting later milestones."""

    try:
        if not eligible():
            return None
        return _award(
            store,
            athlete_id=athlete_id,
            action=action,
            idempotency_key=idempotency_key,
        )
    except Exception:  # noqa: BLE001 - one milestone cannot block another
        logger.exception(
            "[xp] activation milestone failed athlete_id=%s action=%s key=%s",
            athlete_id,
            action,
            idempotency_key,
        )
        return None


def reconcile_activation_xp(
    store: AppStore,
    *,
    athlete_id: str,
    profile: object,
    latest_intake: object | None,
    latest_plan: object | None,
) -> list[dict]:
    """Repair athlete-wide activation awards from persisted authoritative state.

    This deliberately runs on repeatable state reads rather than a one-shot
    mutation callback. A transient XP failure is therefore retried on the next
    ``/api/me`` request, while athlete-wide idempotency keys prevent duplicates.
    Each milestone is isolated so a failure in one cannot block reconciliation
    of the remaining eligible milestones. Awards are monotonic: later profile
    edits or plan archival never remove XP.
    """

    results: list[dict] = []

    profile_result = _reconcile_activation_milestone(
        store,
        athlete_id=athlete_id,
        action="profile_completed",
        idempotency_key=f"profile-completed:{athlete_id}",
        eligible=lambda: profile_activation_complete(profile),
    )
    if profile_result:
        results.append(profile_result)

    # ``latest_intake`` is supplied only when _build_me_response found a
    # persisted athlete_intakes row. The intake payload itself does not need
    # to expose the row id because the reward is athlete-wide and first-only.
    intake_result = _reconcile_activation_milestone(
        store,
        athlete_id=athlete_id,
        action="first_intake_completed",
        idempotency_key=f"first-intake-completed:{athlete_id}",
        eligible=lambda: latest_intake is not None,
    )
    if intake_result:
        results.append(intake_result)

    plan_result = _reconcile_activation_milestone(
        store,
        athlete_id=athlete_id,
        action="first_plan_ready",
        idempotency_key=f"first-plan-ready:{athlete_id}",
        eligible=lambda: latest_plan is not None and plan_activation_ready(latest_plan),
    )
    if plan_result:
        results.append(plan_result)

    return results


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


def _feedback_reconcile_result(
    store: AppStore,
    *,
    athlete_id: str,
    feedback_id: str,
    target_amount: int,
) -> dict | None:
    custom = getattr(store, "reconcile_feedback_xp", None)
    if callable(custom):
        result = custom(
            athlete_id,
            feedback_id=feedback_id,
            target_amount=target_amount,
        )
        return result if isinstance(result, dict) else None

    client: Any | None = getattr(store, "client", None)
    if client is None:
        logger.error("[xp] feedback reconciliation unavailable athlete_id=%s", athlete_id)
        return None

    response = client.rpc(
        "reconcile_feedback_xp",
        {
            "p_athlete_id": athlete_id,
            "p_feedback_id": feedback_id,
            "p_target_amount": target_amount,
        },
    ).execute()
    payload = getattr(response, "data", None)
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    return payload if isinstance(payload, dict) else None


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
    target_amount = 3 if len(comment) >= MIN_FEEDBACK_COMMENT_CHARS else 1
    try:
        return _feedback_reconcile_result(
            store,
            athlete_id=athlete_id,
            feedback_id=feedback_id,
            target_amount=target_amount,
        )
    except Exception:  # noqa: BLE001 - XP must never break feedback persistence
        logger.exception(
            "[xp] feedback reconciliation failed athlete_id=%s feedback_id=%s target_amount=%s",
            athlete_id,
            feedback_id,
            target_amount,
        )
        return None


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
