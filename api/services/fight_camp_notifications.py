"""State-aware daily fight-camp notification orchestration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from api.contracts.command_view import CommandView
from api.contracts.training_day import resolve_training_day_str
from api.services.notification_foundation import (
    NOTIFICATION_MAX_ATTEMPTS,
    NOTIFICATION_STALE_CLAIM_AFTER,
    NotificationCandidate,
    candidate_is_allowed,
    get_notification_preferences,
    list_notification_evaluations,
    list_recent_notification_deliveries,
    record_notification_evaluation,
    simulate_notification_delivery_decision,
)
from api.services.notification_templates import select_notification_template
from api.services.notification_timing import ResolvedTrainingTime, resolve_training_time
from api.services.push_notifications import dispatch_push_candidates
from api.services.today_readiness_boundary import build_today_command_view
from api.store import AppStore

logger = logging.getLogger(__name__)

TERMINAL_SESSION_STATUSES = frozenset({"done", "modified", "skipped"})
ALL_ORCHESTRATED_INTENTS = (
    "morning_readiness",
    "missed_checkin",
    "daily_camp_briefing",
    "session_preparation",
    "session_near",
    "session_ready",
    "session_modified",
    "session_stop",
    "post_session_log",
    "injury_recheck",
    "high_pain_followup",
    "recovery_checkin",
    "recovery_nudge",
    "hydration_nudge",
    "fuel_nudge",
    "weight_check",
    "plan_ready",
    "plan_updated",
    "training_week_complete",
    "training_phase_complete",
    "xp_level_up",
    "first_plan_complete",
    "plan_complete",
    "fight_camp_complete",
    "fight_countdown",
    "coach_message",
)


@dataclass(frozen=True)
class FightCampDispatchResult:
    delivered_count: int
    candidate_count: int


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _aware_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _aware_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _session_id(view: CommandView) -> str:
    session = view.today.next_session or {}
    return str(session.get("session_id") or session.get("id") or "").strip()


def _session_title(view: CommandView) -> str:
    session = view.today.next_session or {}
    return str(session.get("title") or session.get("name") or "today's session").strip()[:42]


def _has_active_plan(view: CommandView) -> bool:
    return bool(str(view.active_plan.get("id") or "").strip())


def _has_today_session(view: CommandView) -> bool:
    return bool(
        _has_active_plan(view)
        and view.today.session_scope == "today"
        and _session_id(view)
    )


def _checkin_complete(view: CommandView) -> bool:
    return str(view.today.recommendation_state or "").strip().lower() != "not_checked_in"


def _session_terminal(view: CommandView) -> bool:
    return str(view.today.completion_status or "").strip().lower() in TERMINAL_SESSION_STATUSES


def _window(local_now: datetime, start_hour: int, end_hour: int) -> bool:
    return start_hour <= local_now.hour < end_hour


def _window_around(
    local_now: datetime,
    scheduled: datetime,
    *,
    start_minutes: int,
    end_minutes: int,
) -> bool:
    delta = (local_now - scheduled).total_seconds() / 60.0
    return start_minutes <= delta < end_minutes


def _candidate(
    store: AppStore,
    *,
    profile_id: str,
    intent: str,
    category: str,
    priority: int,
    dedupe_key: str,
    expires_at: datetime,
    timezone_name: str,
    training_day: str,
    url: str,
    tag: str,
    context: Mapping[str, Any] | None = None,
    scheduled_for: datetime | None = None,
    timing: ResolvedTrainingTime | None = None,
    action_key: str | None = None,
    notification_class: str = "routine",
    daily_cap: int | None = None,
    min_spacing_minutes: int | None = None,
    merged_intents: tuple[str, ...] = (),
    source_event_metadata: Mapping[str, Any] | None = None,
) -> NotificationCandidate:
    render_context = dict(context or {})
    if timing is not None:
        render_context["_timing_confidence"] = timing.timing_confidence
    title, body, variant_id, template_version = select_notification_template(
        store,
        profile_id=profile_id,
        intent=intent,
        dedupe_key=dedupe_key,
        context=render_context,
    )
    metadata = {
        **dict(source_event_metadata or {}),
        "template_version": template_version,
    }
    if timing is not None:
        metadata["timing_sample_count"] = timing.sample_count
        if timing.median_absolute_deviation_minutes is not None:
            metadata["timing_mad_minutes"] = timing.median_absolute_deviation_minutes
    return NotificationCandidate(
        profile_id=profile_id,
        notification_type=intent,
        intent=intent,
        category=category,  # type: ignore[arg-type]
        priority=priority,
        title=title[:40],
        body=body[:90],
        url=url,
        tag=tag,
        dedupe_key=dedupe_key,
        expires_at=_aware_utc(expires_at),
        timezone_name=timezone_name,
        respect_quiet_hours=True,
        training_day=training_day,
        scheduled_for=_aware_utc(scheduled_for) if scheduled_for else None,
        timing_source=timing.timing_source if timing else None,
        timing_confidence=timing.timing_confidence if timing else None,  # type: ignore[arg-type]
        variant_id=variant_id,
        source_event_metadata=metadata,
        action_key=action_key,
        notification_class=notification_class,  # type: ignore[arg-type]
        daily_cap=daily_cap,
        min_spacing_minutes=min_spacing_minutes,
        merged_intents=merged_intents,
    )


def _record_reason(
    store: AppStore,
    *,
    profile_id: str,
    training_day: str,
    intent: str,
    now_utc: datetime,
    reason: str,
    decision: str = "not_applicable",
    source_metadata: Mapping[str, Any] | None = None,
) -> None:
    record_notification_evaluation(
        store,
        profile_id=profile_id,
        training_day=training_day,
        intent=intent,
        now_utc=now_utc,
        decision=decision,
        rejection_reasons=(reason,),
        eligible=False,
        source_event_metadata=source_metadata,
    )


def _latest_actionable_injury(view: CommandView, timezone_name: str) -> Mapping[str, Any] | None:
    actionable: list[Mapping[str, Any]] = []
    for injury in view.open_injuries:
        if str(injury.get("status") or "").lower() not in {"open", "monitoring"}:
            continue
        severity = str(injury.get("severity") or "").lower()
        latest = str(injury.get("latest_reported_status") or "").lower()
        surface = str(injury.get("surface_class") or "")
        if not (
            severity == "severe"
            or latest == "worse"
            or surface in {
                "surface_local_restriction",
                "surface_no_contact",
                "surface_medical_review",
            }
        ):
            continue
        updated = _parse_datetime(injury.get("updated_at") or injury.get("created_at"))
        if updated and resolve_training_day_str(updated, athlete_timezone=timezone_name) == view.today.training_day:
            continue
        actionable.append(injury)
    if not actionable:
        return None
    return max(
        actionable,
        key=lambda injury: (
            3 if str(injury.get("surface_class") or "") == "surface_medical_review" else 0,
            2 if str(injury.get("severity") or "").lower() == "severe" else 0,
            str(injury.get("updated_at") or ""),
        ),
    )


def _recent_high_pain(
    store: AppStore,
    *,
    profile_id: str,
    training_day: str,
    now_utc: datetime,
) -> Mapping[str, Any] | None:
    try:
        rows = store.list_session_completions(profile_id, limit=10)
    except Exception:  # noqa: BLE001
        return None
    for row in rows or []:
        if not isinstance(row, Mapping) or str(row.get("training_day") or "") == training_day:
            continue
        try:
            pain = int(row.get("pain_after"))
        except (TypeError, ValueError):
            continue
        completed_at = _parse_datetime(row.get("completed_at"))
        if pain < 7 or completed_at is None:
            continue
        age = _aware_utc(now_utc) - completed_at
        if timedelta(0) <= age <= timedelta(hours=48):
            return row
    return None


def _fight_countdown(view: CommandView, training_day: str) -> int | None:
    value = view.active_plan.get("fight_date")
    if not value:
        return None
    try:
        remaining = (date.fromisoformat(str(value)[:10]) - date.fromisoformat(training_day)).days
    except ValueError:
        return None
    return remaining if remaining in {14, 7, 3, 1} else None


def _deferred_event_candidates(
    store: AppStore,
    *,
    profile_id: str,
    training_day: str,
    timezone_name: str,
    now_utc: datetime,
) -> list[NotificationCandidate]:
    """Rehydrate quiet-hour-deferred source events without extending TTLs."""

    candidates: list[NotificationCandidate] = []
    evaluation_rows: list[dict[str, Any]] = []
    days = [training_day]
    try:
        days.append((date.fromisoformat(training_day) - timedelta(days=1)).isoformat())
    except ValueError:
        pass
    for day in days:
        try:
            rows = list_notification_evaluations(
                store,
                profile_id=profile_id,
                training_day=day,
            )
        except Exception:  # noqa: BLE001
            continue
        evaluation_rows.extend(rows)

    deferred_rows = [
        row
        for row in evaluation_rows
        if row.get("decision") == "deferred_until_quiet_end"
        and not row.get("resulting_delivery_id")
    ]
    if not deferred_rows:
        return candidates
    delivery_rows = list_recent_notification_deliveries(
        store,
        profile_id=profile_id,
        limit=500,
    )
    deliveries_by_key = {
        str(row.get("dedupe_key") or ""): row
        for row in delivery_rows
        if row.get("dedupe_key")
    }
    observed_selected_keys = {
        str(row.get("dedupe_key") or "")
        for row in evaluation_rows
        if row.get("decision") == "would_select" and row.get("dedupe_key")
    }
    reference = _aware_utc(now_utc)

    for row in deferred_rows:
        metadata = row.get("source_event_metadata")
        if not isinstance(metadata, Mapping):
            continue
        snapshot = metadata.get("_candidate_snapshot")
        if not isinstance(snapshot, Mapping):
            continue
        if str(snapshot.get("notification_class") or "") != "event":
            continue
        expires_at = _parse_datetime(snapshot.get("expires_at"))
        if expires_at is None or expires_at <= _aware_utc(now_utc):
            continue
        intent = str(row.get("intent") or "").strip()
        category = str(row.get("category") or "").strip()
        dedupe_key = str(row.get("dedupe_key") or "").strip()
        if not intent or not category or not dedupe_key:
            continue
        delivery = deliveries_by_key.get(dedupe_key)
        if delivery is None:
            # In observe mode a prior selection is the terminal lifecycle
            # fact. Rebuilding it as a stale shadow claim every sweep only
            # measures the rehydrator, not a new source event.
            if dedupe_key in observed_selected_keys:
                continue
        else:
            status = str(delivery.get("status") or "")
            attempts = int(delivery.get("attempt_count") or 0)
            claimed_at = _parse_datetime(delivery.get("claimed_at"))
            stale = (
                claimed_at is None
                or reference - claimed_at >= NOTIFICATION_STALE_CLAIM_AFTER
            )
            retryable = attempts < NOTIFICATION_MAX_ATTEMPTS and (
                status == "failed" or (status == "pending" and stale)
            )
            if not retryable:
                continue
        candidates.append(
            NotificationCandidate(
                profile_id=profile_id,
                notification_type=str(row.get("notification_type") or intent),
                intent=intent,
                category=category,  # type: ignore[arg-type]
                priority=int(row.get("priority") or 100),
                title=str(snapshot.get("title") or "")[:40],
                body=str(snapshot.get("body") or "")[:90],
                url=str(snapshot.get("url") or "/today"),
                tag=str(snapshot.get("tag") or intent)[:80],
                dedupe_key=dedupe_key,
                expires_at=expires_at,
                timezone_name=timezone_name,
                respect_quiet_hours=bool(snapshot.get("respect_quiet_hours", True)),
                training_day=training_day,
                scheduled_for=_parse_datetime(row.get("scheduled_for")),
                timing_source=str(row.get("timing_source") or "") or None,
                timing_confidence=str(row.get("timing_confidence") or "") or None,  # type: ignore[arg-type]
                variant_id=str(row.get("variant_id") or "") or None,
                source_event_metadata={
                    **dict(metadata),
                    "deferred_from_training_day": str(
                        row.get("training_day") or training_day
                    ),
                },
                action_key=str(snapshot.get("action_key") or "") or None,
                notification_class="event",
                daily_cap=int(snapshot.get("daily_cap") or 3),
                min_spacing_minutes=max(
                    30, int(snapshot.get("min_spacing_minutes") or 0)
                ),
                merged_intents=tuple(
                    str(value) for value in snapshot.get("merged_intents") or ()
                ),
            )
        )
    return candidates


def build_fight_camp_candidates(
    store: AppStore,
    view: CommandView,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> list[NotificationCandidate]:
    preferences = get_notification_preferences(store, profile_id)
    reference = _aware_utc(now_utc)
    local_now = reference.astimezone(_timezone(timezone_name))
    training_day = view.today.training_day
    candidates: list[NotificationCandidate] = []
    handled: set[str] = set()
    active_plan = _has_active_plan(view)
    today_session = _has_today_session(view)
    checked_in = _checkin_complete(view)
    terminal = _session_terminal(view)
    session_id = _session_id(view) or training_day
    session_title = _session_title(view)
    timing = resolve_training_time(
        store,
        view,
        preferences,
        profile_id=profile_id,
        timezone_name=timezone_name,
    ) if today_session else None

    def reason(intent: str, code: str, *, decision: str = "not_applicable") -> None:
        handled.add(intent)
        _record_reason(
            store,
            profile_id=profile_id,
            training_day=training_day,
            intent=intent,
            now_utc=reference,
            reason=code,
            decision=decision,
        )

    decision_tier = str(view.today.decision_tier or "").lower()
    recommendation = str(view.today.recommendation_state or "").lower()

    # Safety STOP is a separate bounded class and replaces every normal session touch.
    if today_session and checked_in and decision_tier == "stop" and _window(local_now, 7, 22):
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="session_stop",
                category="session_reminders",
                priority=5,
                dedupe_key=f"session-stop:{training_day}:primary",
                expires_at=reference + timedelta(hours=2),
                timezone_name=timezone_name,
                training_day=training_day,
                url="/today#today-command",
                tag="session-stop",
                action_key=f"acknowledge-stop:{session_id}",
                notification_class="safety",
                daily_cap=2,
                min_spacing_minutes=30,
            )
        )
        handled.add("session_stop")
        for intent in (
            "session_preparation", "session_near", "session_ready",
            "session_modified", "hydration_nudge", "fuel_nudge", "post_session_log",
            "daily_camp_briefing",
        ):
            reason(intent, "merged_into_other_intent", decision="replaced_by_session_stop")
    else:
        reason("session_stop", "outside_due_window" if decision_tier == "stop" else "no_stop_state")

    if "session_modified" not in handled:
        if today_session and checked_in and not terminal and recommendation in {"modify", "pull_back"}:
            candidates.append(
                _candidate(
                    store,
                    profile_id=profile_id,
                    intent="session_modified",
                    category="session_reminders",
                    priority=8,
                    dedupe_key=f"session-modified:{training_day}:{recommendation}",
                    expires_at=reference + timedelta(hours=4),
                    timezone_name=timezone_name,
                    training_day=training_day,
                    url="/today#today-session",
                    tag="session-modified",
                    action_key=f"review-modification:{session_id}",
                    notification_class="event",
                    min_spacing_minutes=30,
                )
            )
            handled.add("session_modified")
            reason("session_ready", "merged_into_other_intent", decision="replaced_by_session_modified")
        else:
            reason("session_modified", "session_terminal" if terminal else "no_modified_state")

    injury = _latest_actionable_injury(view, timezone_name)
    high_pain = _recent_high_pain(
        store,
        profile_id=profile_id,
        training_day=training_day,
        now_utc=reference,
    )
    morning_fallback_intent: str | None = None
    if active_plan and not checked_in:
        if today_session and _window(local_now, 7, 10):
            morning_fallback_intent = "morning_readiness"
        elif not today_session and _window(local_now, 8, 10):
            morning_fallback_intent = "recovery_checkin"
    merged_morning_intents = (
        (morning_fallback_intent,) if morning_fallback_intent is not None else ()
    )

    if injury is not None and _window(local_now, 7, 20):
        injury_id = str(injury.get("id") or "tracked")
        body_area = str(injury.get("body_area") or injury.get("label") or "your injury")[:24]
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="injury_recheck",
                category="injury_followups",
                priority=10,
                dedupe_key=f"injury-recheck:{injury_id}:{training_day}",
                expires_at=reference + timedelta(hours=3),
                timezone_name=timezone_name,
                training_day=training_day,
                url="/today#today-injury",
                tag=f"injury-recheck-{injury_id}"[:80],
                context={"body_area": body_area},
                action_key=f"update-injury:{injury_id}",
                merged_intents=merged_morning_intents,
                source_event_metadata={"injury_id": injury_id},
            )
        )
        handled.add("injury_recheck")
    else:
        reason(
            "injury_recheck",
            "outside_due_window" if injury is not None else "injury_not_actionable",
        )

    if high_pain is not None and _window(local_now, 7, 11) and not checked_in:
        source = str(high_pain.get("id") or high_pain.get("session_id") or "recent")
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="high_pain_followup",
                category="injury_followups",
                priority=12,
                dedupe_key=f"high-pain-followup:{source}:{training_day}",
                expires_at=local_now.replace(hour=11, minute=0, second=0, microsecond=0),
                timezone_name=timezone_name,
                training_day=training_day,
                url="/today#today-checkin",
                tag="high-pain-followup",
                action_key=f"checkin:{training_day}",
                merged_intents=merged_morning_intents,
                source_event_metadata={"completion_id": source},
            )
        )
        handled.add("high_pain_followup")
    else:
        reason(
            "high_pain_followup",
            "already_checked_in" if checked_in else (
                "outside_due_window" if high_pain is not None else "pain_below_threshold"
            ),
        )

    eligible_morning_replacement = any(
        candidate.intent in {"injury_recheck", "high_pain_followup"}
        and candidate_is_allowed(candidate, preferences, now_utc=reference)
        for candidate in candidates
    )

    if morning_fallback_intent == "morning_readiness":
        if eligible_morning_replacement:
            reason(
                "morning_readiness",
                "merged_into_other_intent",
                decision="merged_into_eligible_injury_followup",
            )
        else:
            candidates.append(
                _candidate(
                    store,
                    profile_id=profile_id,
                    intent="morning_readiness",
                    category="checkin_reminders",
                    priority=20,
                    dedupe_key=f"morning-readiness:{training_day}",
                    expires_at=local_now.replace(hour=10, minute=0, second=0, microsecond=0),
                    timezone_name=timezone_name,
                    training_day=training_day,
                    url="/today#today-checkin",
                    tag="morning-readiness",
                    context={"session": session_title},
                    action_key=f"checkin:{training_day}",
                )
            )
            handled.add("morning_readiness")
    else:
        reason(
            "morning_readiness",
            "no_active_plan" if not active_plan else (
                "already_checked_in" if checked_in else (
                    "no_today_session" if not today_session else "outside_due_window"
                )
            ),
        )

    if morning_fallback_intent == "recovery_checkin":
        if eligible_morning_replacement:
            reason(
                "recovery_checkin",
                "merged_into_other_intent",
                decision="merged_into_eligible_injury_followup",
            )
        else:
            candidates.append(
                _candidate(
                    store,
                    profile_id=profile_id,
                    intent="recovery_checkin",
                    category="checkin_reminders",
                    priority=20,
                    dedupe_key=f"recovery-checkin:{training_day}",
                    expires_at=local_now.replace(hour=10, minute=0, second=0, microsecond=0),
                    timezone_name=timezone_name,
                    training_day=training_day,
                    url="/today#today-checkin",
                    tag="recovery-checkin",
                    action_key=f"checkin:{training_day}",
                )
            )
            handled.add("recovery_checkin")
    else:
        reason(
            "recovery_checkin",
            "no_active_plan" if not active_plan else (
                "already_checked_in" if checked_in else (
                    "today_session" if today_session else "outside_due_window"
                )
            ),
        )

    if active_plan and today_session and not checked_in and _window(local_now, 10, 14):
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="missed_checkin",
                category="checkin_reminders",
                priority=22,
                dedupe_key=f"missed-checkin:{training_day}",
                expires_at=local_now.replace(hour=14, minute=0, second=0, microsecond=0),
                timezone_name=timezone_name,
                training_day=training_day,
                url="/today#today-checkin",
                tag="missed-checkin",
                context={"session": session_title},
                action_key=f"checkin:{training_day}",
            )
        )
        handled.add("missed_checkin")
    else:
        reason(
            "missed_checkin",
            "already_checked_in" if checked_in else (
                "no_today_session" if not today_session else "outside_due_window"
            ),
        )

    if (
        "daily_camp_briefing" not in handled
        and active_plan and today_session and checked_in and not terminal
        and _window(local_now, 9, 14)
    ):
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="daily_camp_briefing",
                category="checkin_reminders",
                priority=35,
                dedupe_key=f"daily-camp-briefing:{training_day}",
                expires_at=local_now.replace(hour=14, minute=0, second=0, microsecond=0),
                timezone_name=timezone_name,
                training_day=training_day,
                url="/today#today-command",
                tag="daily-camp-briefing",
                context={"session": session_title},
                action_key=f"review-briefing:{training_day}",
            )
        )
        handled.add("daily_camp_briefing")
    elif "daily_camp_briefing" not in handled:
        reason(
            "daily_camp_briefing",
            "not_checked_in" if not checked_in else (
                "session_terminal" if terminal else "outside_due_window"
            ),
        )

    if timing is not None and "session_preparation" not in handled:
        scheduled = timing.resolved_training_time
        if today_session and checked_in and not terminal and _window_around(
            local_now, scheduled, start_minutes=-120, end_minutes=-60
        ):
            candidates.append(
                _candidate(
                    store,
                    profile_id=profile_id,
                    intent="session_preparation",
                    category="session_reminders",
                    priority=38,
                    dedupe_key=f"session-preparation:{session_id}:{training_day}",
                    expires_at=(scheduled - timedelta(minutes=60)),
                    timezone_name=timezone_name,
                    training_day=training_day,
                    url="/today#today-session",
                    tag="session-preparation",
                    context={"session": session_title},
                    scheduled_for=scheduled,
                    timing=timing,
                    action_key=f"complete-session:{session_id}",
                    merged_intents=("hydration_nudge", "fuel_nudge"),
                )
            )
            handled.add("session_preparation")
            reason("hydration_nudge", "merged_into_other_intent", decision="merged_into_session_preparation")
            reason("fuel_nudge", "merged_into_other_intent", decision="merged_into_session_preparation")
        else:
            reason(
                "session_preparation",
                "already_logged" if terminal else (
                    "not_checked_in" if not checked_in else "outside_due_window"
                ),
            )

        if "session_near" not in handled:
            if timing.timing_confidence == "low":
                reason("session_near", "low_timing_confidence")
            elif today_session and checked_in and not terminal and _window_around(
                local_now, scheduled, start_minutes=-40, end_minutes=-20
            ):
                candidates.append(
                    _candidate(
                        store,
                        profile_id=profile_id,
                        intent="session_near",
                        category="session_reminders",
                        priority=40,
                        dedupe_key=f"session-near:{session_id}:{training_day}",
                        expires_at=scheduled - timedelta(minutes=20),
                        timezone_name=timezone_name,
                        training_day=training_day,
                        url="/today#today-session",
                        tag="session-near",
                        scheduled_for=scheduled,
                        timing=timing,
                        action_key=f"complete-session:{session_id}",
                    )
                )
                handled.add("session_near")
            else:
                reason("session_near", "outside_due_window")

        if "session_ready" not in handled:
            if timing.timing_confidence != "high":
                reason("session_ready", "low_timing_confidence")
            elif today_session and checked_in and not terminal and _window_around(
                local_now, scheduled, start_minutes=-5, end_minutes=15
            ):
                candidates.append(
                    _candidate(
                        store,
                        profile_id=profile_id,
                        intent="session_ready",
                        category="session_reminders",
                        priority=42,
                        dedupe_key=f"session-ready:{session_id}:{training_day}",
                        expires_at=scheduled + timedelta(minutes=15),
                        timezone_name=timezone_name,
                        training_day=training_day,
                        url="/today#today-session",
                        tag="session-ready",
                        context={"session": session_title},
                        scheduled_for=scheduled,
                        timing=timing,
                        action_key=f"complete-session:{session_id}",
                    )
                )
                handled.add("session_ready")
            else:
                reason("session_ready", "outside_due_window")

        if "post_session_log" not in handled:
            completion = None
            try:
                completion = store.get_session_completion(profile_id, session_id, training_day)
            except Exception:  # noqa: BLE001
                completion = None
            status = str((completion or {}).get("status") or view.today.completion_status or "")
            started_at = _parse_datetime((completion or {}).get("started_at"))
            due_at = (
                started_at.astimezone(_timezone(timezone_name)) + timedelta(minutes=90)
                if started_at is not None
                else scheduled + timedelta(minutes=105)
            )
            if status in TERMINAL_SESSION_STATUSES:
                reason("post_session_log", "already_logged")
            elif _window(local_now, 10, 23) and _window_around(
                local_now, due_at, start_minutes=0, end_minutes=105
            ):
                repeat = 2 if (local_now - due_at) >= timedelta(minutes=80) else 1
                candidates.append(
                    _candidate(
                        store,
                        profile_id=profile_id,
                        intent="post_session_log",
                        category="session_reminders",
                        priority=45,
                        dedupe_key=f"post-session-log:{session_id}:{training_day}:{repeat}",
                        expires_at=due_at + timedelta(minutes=105),
                        timezone_name=timezone_name,
                        training_day=training_day,
                        url="/today#today-session",
                        tag="post-session-log",
                        context={"_session_started": started_at is not None},
                        scheduled_for=due_at,
                        timing=timing,
                        action_key=f"complete-session:{session_id}",
                    )
                )
                handled.add("post_session_log")
            else:
                reason("post_session_log", "outside_due_window")
    elif "session_preparation" not in handled:
        for intent in ("session_preparation", "session_near", "session_ready", "post_session_log"):
            if intent not in handled:
                reason(intent, "no_today_session")

    if "hydration_nudge" not in handled:
        reason("hydration_nudge", "outside_due_window")
    if "fuel_nudge" not in handled:
        reason("fuel_nudge", "outside_due_window")

    if active_plan and not today_session and _window(local_now, 14, 18):
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="recovery_nudge",
                category="session_reminders",
                priority=60,
                dedupe_key=f"recovery-nudge:{training_day}",
                expires_at=local_now.replace(hour=18, minute=0, second=0, microsecond=0),
                timezone_name=timezone_name,
                training_day=training_day,
                url="/today",
                tag="recovery-nudge",
                action_key=f"recovery-day:{training_day}",
                daily_cap=2,
            )
        )
        handled.add("recovery_nudge")
    else:
        reason(
            "recovery_nudge",
            "no_active_plan" if not active_plan else (
                "no_today_session" if not today_session else "outside_due_window"
            ),
        )

    # Weight prompts require an authoritative target/event. Until that signal is
    # present they remain a distinct observable intent and never become filler.
    reason("weight_check", "no_actionable_weight_event")

    countdown = _fight_countdown(view, training_day)
    if countdown is not None and _window(local_now, 9, 18):
        label = f"D-{countdown}"
        plan_id = str(view.active_plan.get("id") or "")
        candidates.append(
            _candidate(
                store,
                profile_id=profile_id,
                intent="fight_countdown",
                category="plan_update_alerts",
                priority=48,
                dedupe_key=f"fight-countdown:{plan_id}:{label}",
                expires_at=local_now.replace(hour=18, minute=0, second=0, microsecond=0),
                timezone_name=timezone_name,
                training_day=training_day,
                url=f"/plans/{plan_id}" if plan_id else "/plans",
                tag="fight-countdown",
                context={"countdown": label},
                notification_class="event",
                min_spacing_minutes=30,
                source_event_metadata={"plan_id": plan_id, "countdown": label},
            )
        )
        handled.add("fight_countdown")
    else:
        reason("fight_countdown", "outside_due_window" if countdown is not None else "no_milestone_today")

    candidates.extend(
        _deferred_event_candidates(
            store,
            profile_id=profile_id,
            training_day=training_day,
            timezone_name=timezone_name,
            now_utc=reference,
        )
    )
    if any(candidate.intent == "plan_ready" for candidate in candidates):
        handled.add("plan_ready")

    # Event-driven producers record their own source-backed candidates. Recording
    # no_source_event here makes diagnostics complete without inventing a push.
    for intent in ALL_ORCHESTRATED_INTENTS:
        if intent not in handled and not any(candidate.intent == intent for candidate in candidates):
            reason(intent, "no_source_event")
    return candidates


def dispatch_fight_camp_notifications(
    store: AppStore,
    *,
    profile_id: str,
    timezone_name: str,
    now_utc: datetime,
) -> FightCampDispatchResult:
    try:
        rollout_mode = os.getenv(
            "UNLXCK_FIGHT_CAMP_NOTIFICATIONS_MODE", "observe"
        ).strip().lower()
        if rollout_mode not in {"send", "observe", "legacy"}:
            logger.warning(
                "[notification] unknown rollout mode=%s; defaulting to observe",
                rollout_mode,
            )
            rollout_mode = "observe"
        if rollout_mode == "legacy":
            return FightCampDispatchResult(0, 0)
        view = build_today_command_view(
            store,
            athlete_id=profile_id,
            athlete_timezone=timezone_name,
            now=now_utc,
        )
        candidates = build_fight_camp_candidates(
            store,
            view,
            profile_id=profile_id,
            timezone_name=timezone_name,
            now_utc=now_utc,
        )
        if rollout_mode == "observe":
            simulate_notification_delivery_decision(store, candidates, now_utc=now_utc)
            # Returning zero candidates intentionally allows the existing worker
            # path to continue sending legacy notifications during observation.
            return FightCampDispatchResult(0, 0)
        delivered = dispatch_push_candidates(store, candidates, now_utc=now_utc) if candidates else 0
        return FightCampDispatchResult(delivered, len(candidates))
    except Exception:  # noqa: BLE001 - one athlete must not break the sweep
        logger.exception("[notification] fight-camp orchestration failed profile_id=%s", profile_id)
        return FightCampDispatchResult(0, 0)


__all__ = [
    "ALL_ORCHESTRATED_INTENTS",
    "FightCampDispatchResult",
    "build_fight_camp_candidates",
    "dispatch_fight_camp_notifications",
]
