"""Meaningful progress and genuine coach/admin push notifications.

Daily-login XP is intentionally excluded. Progress pushes are created only when
training-derived awards cross a named level or when a full training week award
is granted. Coach messages require an explicit backend/admin call and are never
generated from generic engagement heuristics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from api.services.notification_foundation import NotificationCandidate
from api.services.push_notifications import dispatch_push_candidate
from api.store import AppStore

logger = logging.getLogger(__name__)

XP_LEVELS: tuple[tuple[int, str, int], ...] = (
    (1, "Rookie", 0),
    (2, "Prospect", 100),
    (3, "Amateur", 250),
    (4, "Challenger", 450),
    (5, "Ranked", 700),
    (6, "Contender", 1_000),
    (7, "Elite", 1_300),
    (8, "Champion", 1_700),
)

TERMINAL_TRAINING_STATUSES = frozenset({"done", "modified"})


def resolve_xp_level(total_xp: Any) -> tuple[int, str, int]:
    try:
        total = max(0, int(total_xp))
    except (TypeError, ValueError):
        total = 0
    current = XP_LEVELS[0]
    for level in XP_LEVELS[1:]:
        if total < level[2]:
            break
        current = level
    return current


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
        priority=60,
        title=f"Level {current_level[0]}: {current_level[1]}",
        body="Earned through completed work. See what moved you forward.",
        url="/#progress",
        tag="xp-level-up",
        dedupe_key=f"xp-level-up:{current_level[0]}:{source_key}"[:160],
        expires_at=reference + timedelta(days=3),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
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
    # Opening the app is not a milestone and must never create a push.
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
    # A level-up outranks the weekly recap if both happen on one award.
    selected = min(candidates, key=lambda candidate: candidate.priority)
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
    completion_id = str(
        completion.get("id")
        or f"{completion.get('session_id') or 'session'}:{completion.get('training_day') or 'day'}"
    ).strip()
    if not completion_id:
        return []

    results: list[dict[str, Any]] = []
    for action in ("training_logged", "planned_session_completed"):
        try:
            result = store.award_xp(
                athlete_id,
                action=action,
                idempotency_key=f"{action}:{completion_id}",
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
        # Even urgent coach copy is not an emergency-services channel. Respect
        # the athlete's quiet hours and category opt-out.
        respect_quiet_hours=True,
    )
    return dispatch_push_candidate(store, candidate, now_utc=reference)


__all__ = [
    "XP_LEVELS",
    "award_session_progress",
    "build_level_up_candidate",
    "build_week_complete_candidate",
    "dispatch_progress_award_notification",
    "resolve_xp_level",
    "send_coach_message_notification",
]
