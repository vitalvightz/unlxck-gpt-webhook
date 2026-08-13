"""Auditable athlete-local training-time inference for notification timing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from api.contracts.command_view import CommandView
from api.notification_models import NotificationPreferences
from api.store import AppStore

TRAINING_DAY_ROLLOVER_HOUR = 3
DEFAULT_FALLBACK_TRAINING_TIME = "18:00"
HIGH_CONFIDENCE_MAD_MINUTES = 30
MEDIUM_CONFIDENCE_MAD_MINUTES = 90
MIN_HISTORY_SAMPLES = 3


@dataclass(frozen=True)
class ResolvedTrainingTime:
    resolved_training_time: datetime
    timing_source: str
    timing_confidence: str
    sample_count: int = 0
    median_absolute_deviation_minutes: float | None = None

    @property
    def allows_exact_copy(self) -> bool:
        return self.timing_confidence == "high"


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001 - device timezone is untrusted metadata
        return ZoneInfo("UTC")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_clock(value: Any) -> time | None:
    text = str(value or "").strip()
    if "T" in text:
        parsed = _parse_datetime(text)
        return parsed.timetz().replace(tzinfo=None) if parsed else None
    if len(text) >= 5:
        text = text[:5]
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


def _training_at(training_day: str, clock: time, timezone_name: str) -> datetime:
    day = date.fromisoformat(training_day)
    if clock.hour < TRAINING_DAY_ROLLOVER_HOUR:
        day += timedelta(days=1)
    return datetime.combine(day, clock, tzinfo=_timezone(timezone_name))


def _session_clock(view: CommandView, timezone_name: str) -> time | None:
    session = view.today.next_session or {}
    for key in (
        "scheduled_start",
        "scheduled_time",
        "start_time",
        "training_time",
        "coach_start_time",
    ):
        value = session.get(key)
        parsed_datetime = _parse_datetime(value)
        if parsed_datetime is not None and "T" in str(value):
            return parsed_datetime.astimezone(_timezone(timezone_name)).timetz().replace(tzinfo=None)
        parsed_clock = _parse_clock(value)
        if parsed_clock is not None:
            return parsed_clock
    return None


def _logical_minutes(local_started_at: datetime) -> int:
    minutes = local_started_at.hour * 60 + local_started_at.minute
    if local_started_at.hour < TRAINING_DAY_ROLLOVER_HOUR:
        minutes += 24 * 60
    return minutes


def _clock_from_logical_minutes(value: float) -> time:
    rounded = int(round(value / 5.0) * 5) % (24 * 60)
    return time(hour=rounded // 60, minute=rounded % 60)


def _iter_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _iter_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child)


def _session_type_from_plan(plan: Mapping[str, Any], session_id: str) -> str:
    structured = plan.get("structured_plan")
    for row in _iter_mappings(structured):
        if str(row.get("session_id") or "").strip() == session_id:
            return str(row.get("session_type") or row.get("type") or "").strip().lower()
    return ""


def _history_samples(
    store: AppStore,
    *,
    profile_id: str,
    timezone_name: str,
) -> list[dict[str, Any]]:
    try:
        rows = store.list_session_completions(profile_id, limit=60)
    except Exception:  # noqa: BLE001 - fallback timing remains available
        return []
    local_tz = _timezone(timezone_name)
    plans: dict[str, Mapping[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, Mapping):
            continue
        started_at = _parse_datetime(row.get("started_at"))
        if started_at is None:
            continue
        local_started = started_at.astimezone(local_tz)
        session_type = str(row.get("session_type") or "").strip().lower()
        plan_id = str(row.get("plan_id") or "").strip()
        session_id = str(row.get("session_id") or "").strip()
        if not session_type and plan_id and session_id:
            if plan_id not in plans:
                try:
                    plans[plan_id] = store.get_plan(plan_id) or {}
                except Exception:  # noqa: BLE001
                    plans[plan_id] = {}
            session_type = _session_type_from_plan(plans[plan_id], session_id)
        training_day = str(row.get("training_day") or "")
        try:
            weekday = date.fromisoformat(training_day).weekday()
        except ValueError:
            weekday = (local_started - timedelta(hours=TRAINING_DAY_ROLLOVER_HOUR)).weekday()
        samples.append(
            {
                "minutes": _logical_minutes(local_started),
                "weekday": weekday,
                "session_type": session_type,
            }
        )
    return samples


def _resolved_from_samples(
    samples: list[dict[str, Any]],
    *,
    source: str,
    training_day: str,
    timezone_name: str,
) -> ResolvedTrainingTime | None:
    if not samples:
        return None
    minute_samples = [float(row["minutes"]) for row in samples]
    centre = float(median(minute_samples))
    dispersion = float(median(abs(value - centre) for value in minute_samples))
    clock = _clock_from_logical_minutes(centre)
    if len(samples) >= MIN_HISTORY_SAMPLES and dispersion <= HIGH_CONFIDENCE_MAD_MINUTES:
        confidence = "high"
    elif len(samples) >= MIN_HISTORY_SAMPLES and dispersion <= MEDIUM_CONFIDENCE_MAD_MINUTES:
        confidence = "medium"
    else:
        confidence = "low"
    return ResolvedTrainingTime(
        resolved_training_time=_training_at(training_day, clock, timezone_name),
        timing_source=source,
        timing_confidence=confidence,
        sample_count=len(samples),
        median_absolute_deviation_minutes=dispersion,
    )


def resolve_training_time(
    store: AppStore,
    view: CommandView,
    preferences: NotificationPreferences,
    *,
    profile_id: str,
    timezone_name: str,
) -> ResolvedTrainingTime:
    """Resolve the best available time without mislabelling inference as fact."""

    explicit = _parse_clock(preferences.preferred_training_time)
    if explicit is not None:
        return ResolvedTrainingTime(
            _training_at(view.today.training_day, explicit, timezone_name),
            "preferred_training_time",
            "high",
        )

    scheduled = _session_clock(view, timezone_name)
    if scheduled is not None:
        return ResolvedTrainingTime(
            _training_at(view.today.training_day, scheduled, timezone_name),
            "session_schedule",
            "high",
        )

    samples = _history_samples(
        store,
        profile_id=profile_id,
        timezone_name=timezone_name,
    )
    try:
        target_weekday = date.fromisoformat(view.today.training_day).weekday()
    except ValueError:
        target_weekday = -1
    weekday_samples = [row for row in samples if row["weekday"] == target_weekday]
    resolved = _resolved_from_samples(
        weekday_samples,
        source="same_weekday_history",
        training_day=view.today.training_day,
        timezone_name=timezone_name,
    )
    if resolved is not None:
        return resolved

    current_type = str((view.today.next_session or {}).get("session_type") or "").strip().lower()
    type_samples = [row for row in samples if current_type and row["session_type"] == current_type]
    resolved = _resolved_from_samples(
        type_samples,
        source="same_session_type_history",
        training_day=view.today.training_day,
        timezone_name=timezone_name,
    )
    if resolved is not None:
        return resolved

    resolved = _resolved_from_samples(
        samples,
        source="athlete_recent_history",
        training_day=view.today.training_day,
        timezone_name=timezone_name,
    )
    if resolved is not None:
        return resolved

    fallback = _parse_clock(
        os.getenv("UNLXCK_NOTIFICATION_FALLBACK_TRAINING_TIME", DEFAULT_FALLBACK_TRAINING_TIME)
    ) or time(18, 0)
    return ResolvedTrainingTime(
        _training_at(view.today.training_day, fallback, timezone_name),
        "configurable_fallback",
        "low",
    )


__all__ = ["ResolvedTrainingTime", "resolve_training_time"]
