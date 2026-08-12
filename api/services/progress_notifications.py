"""Meaningful progress and genuine coach/admin push notifications.

Daily-login XP is intentionally excluded. Progress pushes are created only when
training-derived awards cross a named level or when a full training week award
is granted. Coach messages require an explicit backend/admin call and are never
generated from generic engagement heuristics.
"""

from __future__ import annotations

import logging
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from api.services.notification_foundation import NotificationCandidate
from api.services.push_notifications import dispatch_push_candidate
from api.services.xp_awards import ensure_xp_abuse_hardening
from api.store import AppStore
from api.xp_levels import XP_LEVELS, resolve_xp_level

logger = logging.getLogger(__name__)

TERMINAL_TRAINING_STATUSES = frozenset({"done", "modified"})


def _local_day(reference: datetime, timezone_name: str) -> str:
    try:
        return reference.astimezone(ZoneInfo(timezone_name or "UTC")).date().isoformat()
    except Exception:  # noqa: BLE001
        return reference.astimezone(timezone.utc).date().isoformat()


def _result_totals(result: Mapping[str, Any]) -> tuple[int, int]:
    state = result.get("state") if isinstance(result.get("state"), Mapping) else {}
    try:
        previous = max(0, int(result.get("previous_total_xp") or 0))
    except (TypeError, ValueError):
        previous = 0
    try:
        total = max(0, int(state.get("total_xp") or previous))
    except (TypeError, ValueError):
        total = previous
    return previous, total


def build_level_up_candidate(
    *,
    athlete_id: str,
    previous_total_xp: int,
    total_xp: int,
    source_key: str,
    timezone_name: str = "UTC",
    now_utc: datetime | None = None,
) -> NotificationCandidate | None:
    previous_level = resolve_xp_level(previous_total_xp)
    current_level = resolve_xp_level(total_xp)
    if current_level[0] <= previous_level[0]:
        return None
    reference = now_utc or datetime.now(timezone.utc)
    return NotificationCandidate(
        profile_id=athlete_id,
        notification_type="xp_level_up",
        category="progress_milestones",
        priority=50,
        title=f"Level {current_level[0]}: {current_level[1]}",
        body="Earned through completed work. See what moved you forward.",
        url="/#progress",
        tag="xp-level-up",
        dedupe_key=f"xp-level-up:{current_level[0]}:{source_key}"[:160],
        expires_at=reference + timedelta(days=3),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
        training_day=_local_day(reference, timezone_name),
        notification_class="event",
        min_spacing_minutes=30,
        action_key="review-progress",
        source_event_metadata={"source_key": source_key, "level": current_level[0]},
    )


def build_week_complete_candidate(
    *,
    athlete_id: str,
    week_key: str,
    timezone_name: str = "UTC",
    now_utc: datetime | None = None,
) -> NotificationCandidate:
    reference = now_utc or datetime.now(timezone.utc)
    return NotificationCandidate(
        profile_id=athlete_id,
        notification_type="training_week_complete",
        category="progress_milestones",
        priority=55,
        title="Week complete",
        body="The work is banked. Review it before we progress the next week.",
        url="/history",
        tag="training-week-complete",
        dedupe_key=f"training-week-complete:{week_key}"[:160],
        expires_at=reference + timedelta(days=3),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
        training_day=_local_day(reference, timezone_name),
        notification_class="event",
        min_spacing_minutes=30,
        action_key="review-progress",
        source_event_metadata={"week_key": week_key},
    )


def merge_progress_candidates(
    candidates: list[NotificationCandidate],
    *,
    now_utc: datetime,
) -> NotificationCandidate | None:
    """Merge simultaneous achievements into one auditable athlete moment."""

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    rank = {
        "xp_level_up": 1,
        "fight_camp_complete": 2,
        "plan_complete": 3,
        "first_plan_complete": 3,
        "training_phase_complete": 4,
        "training_week_complete": 5,
    }
    ordered = sorted(candidates, key=lambda candidate: (rank.get(candidate.intent, 9), candidate.priority))
    primary = ordered[0]
    intents = tuple(dict.fromkeys(candidate.intent for candidate in ordered))
    labels = {
        "fight_camp_complete": "CAMP COMPLETE",
        "plan_complete": "PLAN COMPLETE",
        "first_plan_complete": "FIRST PLAN COMPLETE",
        "training_phase_complete": "PHASE COMPLETE",
        "training_week_complete": "WEEK COMPLETE",
        "xp_level_up": "LEVEL UP",
    }
    secondary_labels = [
        labels.get(intent, intent.replace("_", " ").upper())
        for intent in intents
        if intent != primary.intent
    ]
    body = primary.body
    if secondary_labels:
        body = f"{primary.body.rstrip('.')} Also banked: {', '.join(secondary_labels).lower()}."[:90]
    digest = hashlib.sha256(
        "|".join(sorted(candidate.dedupe_key for candidate in candidates)).encode("utf-8")
    ).hexdigest()[:24]
    metadata = {
        **dict(primary.source_event_metadata),
        "compound_intents": list(intents),
        "source_dedupe_keys": [candidate.dedupe_key for candidate in candidates],
    }
    suffix = f":compound:{digest}"
    compound_key = f"{primary.dedupe_key[:160 - len(suffix)]}{suffix}"
    return replace(
        primary,
        notification_type=primary.intent,
        title=primary.title,
        body=body,
        dedupe_key=compound_key,
        tag="compound-progress",
        expires_at=max(candidate.expires_at for candidate in candidates),
        merged_intents=tuple(intent for intent in intents if intent != primary.intent),
        source_event_metadata=metadata,
        notification_class="event",
        min_spacing_minutes=30,
    )


def dispatch_progress_award_notification(
    store: AppStore,
    *,
    athlete_id: str,
    action: str,
    award_result: Mapping[str, Any],
    source_key: str,
    timezone_name: str = "UTC",
    now_utc: datetime | None = None,
) -> int:
    if not bool(award_result.get("awarded")):
        return 0
    if action == "daily_login":
        return 0
    reference = now_utc or datetime.now(timezone.utc)
    candidates: list[NotificationCandidate] = []
    if action == "full_training_week_completed":
        candidates.append(
            build_week_complete_candidate(
                athlete_id=athlete_id,
                week_key=source_key,
                timezone_name=timezone_name,
                now_utc=reference,
            )
        )
    previous, total = _result_totals(award_result)
    level_candidate = build_level_up_candidate(
        athlete_id=athlete_id,
        previous_total_xp=previous,
        total_xp=total,
        source_key=source_key,
        timezone_name=timezone_name,
        now_utc=reference,
    )
    if level_candidate is not None:
        candidates.append(level_candidate)
    if not candidates:
        return 0
    selected = merge_progress_candidates(candidates, now_utc=reference)
    if selected is None:
        return 0
    return dispatch_push_candidate(store, selected, now_utc=reference)


def award_session_progress(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    completion: Mapping[str, Any],
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    status = str(completion.get("status") or "").strip().lower()
    if status not in TERMINAL_TRAINING_STATUSES:
        return []
    completion_id = str(completion.get("id") or "").strip()
    training_day = str(completion.get("training_day") or "").strip()
    if not completion_id or not training_day:
        return []
    try:
        ensure_xp_abuse_hardening(store)
    except Exception:  # noqa: BLE001 - session persistence must remain available
        logger.exception(
            "[xp] session awards disabled because hardening is unavailable athlete_id=%s",
            athlete_id,
        )
        return []

    results: list[dict[str, Any]] = []
    for action in ("training_logged", "planned_session_completed"):
        try:
            result = store.award_xp(
                athlete_id,
                action=action,
                idempotency_key=f"{action}:{completion_id}",
                calendar_date=training_day,
            )
        except Exception:  # noqa: BLE001 - XP must never break session completion
            logger.exception(
                "[xp] session progress award failed athlete_id=%s action=%s completion_id=%s",
                athlete_id,
                action,
                completion_id,
            )
            continue
        if isinstance(result, Mapping):
            normalized = dict(result)
            results.append(normalized)
            try:
                dispatch_progress_award_notification(
                    store,
                    athlete_id=athlete_id,
                    action=action,
                    award_result=normalized,
                    source_key=completion_id,
                    timezone_name=athlete_timezone or "UTC",
                    now_utc=now_utc,
                )
            except Exception:  # noqa: BLE001 - push must never break XP/session persistence
                logger.exception(
                    "[notification] XP milestone delivery failed athlete_id=%s action=%s",
                    athlete_id,
                    action,
                )
    return results


def send_coach_message_notification(
    store: AppStore,
    *,
    athlete_id: str,
    message_id: str,
    title: str,
    body: str,
    url: str = "/today",
    timezone_name: str = "UTC",
    urgent: bool = False,
    now_utc: datetime | None = None,
) -> int:
    reference = now_utc or datetime.now(timezone.utc)
    candidate = NotificationCandidate(
        profile_id=athlete_id,
        notification_type="coach_message",
        category="coach_messages",
        priority=12 if urgent else 50,
        title=title,
        body=body,
        url=url,
        tag="coach-message",
        dedupe_key=f"coach-message:{message_id}"[:160],
        expires_at=reference + timedelta(days=2),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
        training_day=_local_day(reference, timezone_name),
        notification_class="event",
        min_spacing_minutes=30,
        action_key=f"coach-message:{message_id}",
        source_event_metadata={"message_id": message_id, "urgent": urgent},
    )
    return dispatch_push_candidate(store, candidate, now_utc=reference)


__all__ = [
    "XP_LEVELS",
    "award_session_progress",
    "build_level_up_candidate",
    "build_week_complete_candidate",
    "dispatch_progress_award_notification",
    "merge_progress_candidates",
    "resolve_xp_level",
    "send_coach_message_notification",
]
