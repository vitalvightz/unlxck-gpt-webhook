from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api.notification_models import NotificationPreferences
from api.services.notification_foundation import (
    NotificationCandidate,
    candidate_is_allowed,
    finalize_notification_delivery,
    get_notification_preferences,
    prepare_notification_delivery,
    select_notification_candidate,
    update_notification_preferences,
)


class MemoryStore:
    """No Supabase client: exercises the guarded in-memory dev/test adapter."""


def _candidate(
    *,
    notification_type: str = "checkin",
    category: str = "checkin_reminders",
    priority: int = 50,
    dedupe_key: str = "checkin:2026-08-02",
    timezone_name: str = "Europe/London",
    respect_quiet_hours: bool = True,
    now: datetime | None = None,
) -> NotificationCandidate:
    reference = now or datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    return NotificationCandidate(
        profile_id="athlete-1",
        notification_type=notification_type,
        category=category,  # type: ignore[arg-type]
        priority=priority,
        title="Check in before we train",
        body="Give me sleep, body and pain so I can set today's call.",
        url="/today#today-checkin",
        tag=notification_type,
        dedupe_key=dedupe_key,
        expires_at=reference + timedelta(hours=3),
        timezone_name=timezone_name,
        respect_quiet_hours=respect_quiet_hours,
    )


def test_candidate_enforces_notification_copy_limits():
    with pytest.raises(ValueError, match="title"):
        _candidate(notification_type="x" * 65)

    with pytest.raises(ValueError, match="title"):
        NotificationCandidate(
            profile_id="athlete-1",
            notification_type="test",
            category="checkin_reminders",
            priority=50,
            title="x" * 41,
            body="Valid body",
            url="/today",
            tag="test",
            dedupe_key="test:1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

    with pytest.raises(ValueError, match="body"):
        NotificationCandidate(
            profile_id="athlete-1",
            notification_type="test",
            category="checkin_reminders",
            priority=50,
            title="Valid title",
            body="x" * 91,
            url="/today",
            tag="test",
            dedupe_key="test:2",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )


def test_preferences_are_account_level_and_persist_in_adapter():
    store = MemoryStore()
    defaults = get_notification_preferences(store, "athlete-1")
    assert defaults.checkin_reminders is True
    assert defaults.quiet_hours_start == "22:00"

    updated = update_notification_preferences(
        store,
        "athlete-1",
        {"checkin_reminders": False, "quiet_hours_start": "23:30"},
    )
    assert updated.checkin_reminders is False
    assert updated.quiet_hours_start == "23:30"
    assert get_notification_preferences(store, "athlete-1") == updated


def test_priority_arbitration_returns_only_the_highest_allowed_candidate():
    now = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    preferences = NotificationPreferences(quiet_hours_enabled=False)
    lower = _candidate(notification_type="plan_update", category="plan_update_alerts", priority=60, now=now)
    higher = _candidate(notification_type="injury_recheck", category="injury_followups", priority=10, dedupe_key="injury:1", now=now)

    selected = select_notification_candidate([lower, higher], preferences, now_utc=now)
    assert selected == higher


def test_category_opt_out_and_quiet_hours_fail_closed():
    morning_utc = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    opted_out = NotificationPreferences(checkin_reminders=False, quiet_hours_enabled=False)
    assert candidate_is_allowed(_candidate(now=morning_utc), opted_out, now_utc=morning_utc) is False

    # 22:30 Europe/London in summer is 21:30 UTC, inside the default 22:00-07:00 window.
    quiet_utc = datetime(2026, 8, 2, 21, 30, tzinfo=timezone.utc)
    quiet_candidate = _candidate(now=quiet_utc)
    assert candidate_is_allowed(quiet_candidate, NotificationPreferences(), now_utc=quiet_utc) is False

    event_candidate = _candidate(now=quiet_utc, respect_quiet_hours=False)
    assert candidate_is_allowed(event_candidate, NotificationPreferences(), now_utc=quiet_utc) is True


def test_profile_delivery_claim_dedupes_and_caps_retries():
    store = MemoryStore()
    now = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    candidate = _candidate(now=now)

    first = prepare_notification_delivery(store, [candidate], now_utc=now)
    assert first is not None
    _, claim_1 = first
    finalize_notification_delivery(
        store,
        claim_1,
        status="failed",
        delivered_count=0,
        error_code="delivery_failed",
    )

    second = prepare_notification_delivery(store, [candidate], now_utc=now + timedelta(minutes=1))
    assert second is not None
    _, claim_2 = second
    assert claim_2.attempt_count == 2
    finalize_notification_delivery(store, claim_2, status="failed", delivered_count=0)

    third = prepare_notification_delivery(store, [candidate], now_utc=now + timedelta(minutes=2))
    assert third is not None
    _, claim_3 = third
    assert claim_3.attempt_count == 3
    finalize_notification_delivery(store, claim_3, status="failed", delivered_count=0)

    assert prepare_notification_delivery(
        store,
        [candidate],
        now_utc=now + timedelta(minutes=3),
    ) is None


def test_sent_delivery_never_reclaims_same_profile_dedupe_key():
    store = MemoryStore()
    now = datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc)
    candidate = _candidate(now=now)
    prepared = prepare_notification_delivery(store, [candidate], now_utc=now)
    assert prepared is not None
    _, claim = prepared
    finalize_notification_delivery(store, claim, status="sent", delivered_count=2)

    assert prepare_notification_delivery(
        store,
        [candidate],
        now_utc=now + timedelta(hours=1),
    ) is None
