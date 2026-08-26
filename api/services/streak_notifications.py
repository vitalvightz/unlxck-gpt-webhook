"""Low-noise streak-at-risk notifications for retention and training consistency."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from api.contracts.command_view import CommandView
from api.services.active_plan import resolve_active_plan
from api.services.notification_foundation import NotificationCandidate, get_notification_preferences
from api.services.notification_timing import ResolvedTrainingTime, resolve_training_time
from api.services.push_notifications import dispatch_push_candidates
from api.services.streaks import _training_schedule, get_streak_state, qualifying_training_days
from api.services.today_readiness_boundary import build_today_command_view
from api.store import AppStore

MIN_STREAK_FOR_RISK_PUSH = 3
TERMINAL_SESSION_STATUSES = frozenset({"done", "modified", "skipped"})


@dataclass(frozen=True)
class StreakDispatchResult:
    delivered_count: int
    candidate_count: int


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001 - device timezone is untrusted metadata
        return ZoneInfo("UTC")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _today_session(view: CommandView) -> bool:
    session = view.today.next_session or {}
    session_id = str(session.get("session_id") or session.get("id") or "").strip()
    return bool(
        str(view.active_plan.get("id") or "").strip()
        and view.today.session_scope == "today"
        and session_id
    )


def _session_id(view: CommandView) -> str:
    session = view.today.next_session or {}
    return str(session.get("session_id") or session.get("id") or "").strip()


def _fight_day(view: CommandView, training_day: str) -> bool:
    value = view.active_plan.get("fight_date")
    if not value:
        return False
    return str(value)[:10] == training_day


def _training_risk_due(
    local_now: datetime,
    timing: ResolvedTrainingTime | None,
) -> bool:
    if not (20 <= local_now.hour < 22):
        return False
    if timing is not None and timing.timing_confidence in {"medium", "high"}:
        scheduled_local = timing.resolved_training_time.astimezone(local_now.tzinfo)
        return local_now >= scheduled_local + timedelta(minutes=90)
    # With weak timing evidence, wait until the final hour instead of guessing
    # that an athlete has already trained.
    return local_now.hour >= 21


def _app_streak_is_at_risk(
    state: Mapping[str, Any],
    *,
    training_day: str,
) -> bool:
    try:
        current = int(state.get("current") or 0)
        today = date.fromisoformat(training_day)
        last_active = date.fromisoformat(str(state.get("last_active_date") or ""))
    except (TypeError, ValueError):
        return False
    return current >= MIN_STREAK_FOR_RISK_PUSH and last_active == today - timedelta(days=1)


def _authoritative_training_current(
    store: AppStore,
    *,
    profile_id: str,
    training_day: str,
) -> int | None:
    """Rebuild the current Training Streak without mutating streak state.

    Persisted streak counters advance on completions, so an athlete who simply
    disappears after missing a scheduled day can temporarily have a stale value.
    A retention push must not tell them a dead streak is still alive. This mirrors
    ``reconcile_training_streak`` using the same active-plan schedule and
    qualifying completion history, but remains read-only for the ten-minute push
    sweep.
    """

    try:
        today = date.fromisoformat(training_day)
        resolution = resolve_active_plan(store, profile_id, current_training_day=today)
        if resolution.plan is None:
            return 0 if resolution.source != "read_failure" else None
        expected = set(_training_schedule(resolution.plan, training_day))
        qualifying, skipped = qualifying_training_days(
            store,
            athlete_id=profile_id,
            today=today,
        )
    except Exception:  # noqa: BLE001 - uncertainty suppresses the streak claim
        return None

    current = 0
    for activity_day in sorted(expected | qualifying | skipped):
        if activity_day > today:
            continue
        if activity_day in qualifying:
            current += 1
        elif activity_day < today or activity_day in skipped:
            current = 0
    return current


def build_streak_at_risk_candidates(
    store: AppStore,
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> list[NotificationCandidate]:
    """Build at most one streak-risk candidate for this athlete and sweep.

    Training consistency wins over app engagement. No training-risk push is ever
    created for a STOP call, a completed/skipped session, a rest day, or fight
    day. The app streak is also suppressed when a meaningful training streak has
    today's scheduled work still open, reserving the evening for the more useful
    coach message rather than stacking two streak nudges.
    """

    reference = _aware_utc(now_utc)
    local_now = reference.astimezone(_timezone(timezone_name))
    training_day = str(view.today.training_day)
    try:
        streaks = get_streak_state(
            store,
            athlete_id=profile_id,
            athlete_timezone=timezone_name,
            now=reference,
        )
    except Exception:  # noqa: BLE001 - streak reads must never break the push sweep
        return []

    login_state = streaks.get("login") if isinstance(streaks, Mapping) else None
    training_state = streaks.get("adherence") if isinstance(streaks, Mapping) else None
    login_state = login_state if isinstance(login_state, Mapping) else {}
    training_state = training_state if isinstance(training_state, Mapping) else {}

    try:
        persisted_training_current = int(training_state.get("current") or 0)
    except (TypeError, ValueError):
        persisted_training_current = 0

    today_session = _today_session(view)
    session_id = _session_id(view) or training_day
    terminal = str(view.today.completion_status or "").strip().lower() in TERMINAL_SESSION_STATUSES
    stop_call = str(view.today.decision_tier or "").strip().lower() == "stop"
    fight_day = _fight_day(view, training_day)

    training_current = persisted_training_current
    if (
        persisted_training_current >= MIN_STREAK_FOR_RISK_PUSH
        and today_session
        and not terminal
        and not stop_call
        and not fight_day
        and 19 <= local_now.hour < 22
    ):
        verified = _authoritative_training_current(
            store,
            profile_id=profile_id,
            training_day=training_day,
        )
        # Never make a streak-preservation claim when the history read is
        # uncertain. A false "keep it alive" push is worse than silence.
        training_current = verified if verified is not None else 0

    reserves_training_message = (
        training_current >= MIN_STREAK_FOR_RISK_PUSH
        and today_session
        and not terminal
        and not stop_call
        and not fight_day
    )

    if reserves_training_message:
        timing: ResolvedTrainingTime | None = None
        try:
            timing = resolve_training_time(
                store,
                view,
                get_notification_preferences(store, profile_id),
                profile_id=profile_id,
                timezone_name=timezone_name,
            )
        except Exception:  # noqa: BLE001 - low-confidence timing fallback is safer than no sweep
            timing = None

        if _training_risk_due(local_now, timing):
            expires_local = local_now.replace(hour=22, minute=0, second=0, microsecond=0)
            return [
                NotificationCandidate(
                    profile_id=profile_id,
                    notification_type="training_streak_at_risk",
                    intent="training_streak_at_risk",
                    category="session_reminders",
                    priority=50,
                    title="KEEP THE RUN GOING.",
                    body="Today's session is still open.",
                    url="/today#today-session",
                    tag="training-streak-at-risk",
                    dedupe_key=f"training-streak-at-risk:{training_day}",
                    expires_at=_aware_utc(expires_local),
                    timezone_name=timezone_name,
                    respect_quiet_hours=True,
                    training_day=training_day,
                    timing_source=timing.timing_source if timing else None,
                    timing_confidence=timing.timing_confidence if timing else None,  # type: ignore[arg-type]
                    variant_id="tsr-01",
                    source_event_metadata={
                        "streak_current": training_current,
                        "template_version": 1,
                    },
                    action_key=f"complete-session:{session_id}",
                    notification_class="routine",
                    min_spacing_minutes=45,
                    merged_intents=("app_streak_at_risk",),
                )
            ]
        # A real training streak has precedence even when the session is too late
        # for a safe reminder. Do not fall back to a generic app-streak nudge.
        return []

    if (
        not stop_call
        and not fight_day
        and 19 <= local_now.hour < 21
        and _app_streak_is_at_risk(login_state, training_day=training_day)
    ):
        expires_local = local_now.replace(hour=21, minute=0, second=0, microsecond=0)
        return [
            NotificationCandidate(
                profile_id=profile_id,
                notification_type="app_streak_at_risk",
                intent="app_streak_at_risk",
                category="progress_milestones",
                priority=70,
                title="LXCK IN.",
                body="Keep your streak alive.",
                url="/today",
                tag="app-streak-at-risk",
                dedupe_key=f"app-streak-at-risk:{training_day}",
                expires_at=_aware_utc(expires_local),
                timezone_name=timezone_name,
                respect_quiet_hours=True,
                training_day=training_day,
                variant_id="asr-01",
                source_event_metadata={
                    "streak_current": int(login_state.get("current") or 0),
                    "template_version": 1,
                },
                notification_class="routine",
                min_spacing_minutes=45,
            )
        ]

    return []


def dispatch_streak_at_risk_notifications(
    store: AppStore,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> StreakDispatchResult:
    """Dispatch streak-risk pushes only while the new notification system is live."""

    rollout_mode = os.getenv("UNLXCK_FIGHT_CAMP_NOTIFICATIONS_MODE", "observe").strip().lower()
    if rollout_mode != "send":
        return StreakDispatchResult(0, 0)
    try:
        view = build_today_command_view(
            store,
            athlete_id=profile_id,
            athlete_timezone=timezone_name,
            now=now_utc,
        )
        candidates = build_streak_at_risk_candidates(
            store,
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            now_utc=now_utc,
        )
        if not candidates:
            return StreakDispatchResult(0, 0)
        delivered = dispatch_push_candidates(store, candidates, now_utc=now_utc)
        return StreakDispatchResult(delivered, len(candidates))
    except Exception:  # noqa: BLE001 - one athlete must not break the sweep
        return StreakDispatchResult(0, 0)


__all__ = [
    "MIN_STREAK_FOR_RISK_PUSH",
    "StreakDispatchResult",
    "build_streak_at_risk_candidates",
    "dispatch_streak_at_risk_notifications",
]
