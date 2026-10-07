"""The in-memory notification ledger decides claims the way production does.

Tests throughout the suite approve notification behaviour against
tests/support.InMemoryNotificationLedger, so it must reject everything the
production RPC (claim_notification_delivery_v2) rejects. These cases pin the
rules one by one, and pin the shared constants to the migration text so a
change on either side fails here.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.services.notification_foundation import (
    NOTIFICATION_MAX_ATTEMPTS,
    NOTIFICATION_STALE_CLAIM_AFTER,
    NotificationCandidate,
    attempt_notification_delivery_claim,
    finalize_notification_delivery,
    simulate_notification_delivery_decision,
)
from support import InMemoryNotificationLedger

NOW = datetime(2026, 8, 2, 7, 30, tzinfo=timezone.utc)
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20260813072104_redesign_fight_camp_notifications.sql"
)


class Ledger(InMemoryNotificationLedger):
    pass


def _candidate(**overrides) -> NotificationCandidate:
    fields = dict(
        profile_id="p1",
        notification_type="checkin",
        intent="morning_checkin",
        category="checkin_reminders",
        priority=10,
        title="Check in",
        body="Two minutes.",
        url="/today",
        tag="checkin",
        dedupe_key="d1",
        expires_at=NOW + timedelta(hours=4),
        timezone_name="Europe/London",
    )
    fields.update(overrides)
    return NotificationCandidate(**fields)


def _claim(store, candidate=None, *, at=NOW):
    return attempt_notification_delivery_claim(store, candidate or _candidate(), now_utc=at)


def test_retry_limits_match_the_migration():
    sql = MIGRATION.read_text(encoding="utf-8")
    function = sql[sql.index("function public.claim_notification_delivery_v2") :]
    assert f"v_existing.attempt_count < {NOTIFICATION_MAX_ATTEMPTS} and (" in function
    minutes = int(NOTIFICATION_STALE_CLAIM_AFTER.total_seconds() // 60)
    assert re.search(rf"claimed_at <= v_now - interval '{minutes} minutes'", function)


def test_stale_pending_claim_is_not_reclaimed_after_the_attempt_limit():
    store = Ledger()
    at = NOW
    for _ in range(NOTIFICATION_MAX_ATTEMPTS):
        assert _claim(store, at=at).decision == "claimed"
        at += NOTIFICATION_STALE_CLAIM_AFTER  # leave it pending until stale

    assert _claim(store, at=at).decision == "duplicate_dedupe_key"


def test_failed_claim_is_not_retried_after_the_attempt_limit():
    store = Ledger()
    for _ in range(NOTIFICATION_MAX_ATTEMPTS):
        attempt = _claim(store)
        assert attempt.decision == "claimed"
        finalize_notification_delivery(store, attempt.claim, status="failed", delivered_count=0)

    assert _claim(store).decision == "duplicate_dedupe_key"


def test_fresh_pending_and_sent_claims_are_never_reclaimed():
    store = Ledger()
    attempt = _claim(store)
    assert _claim(store, at=NOW + timedelta(minutes=5)).decision == "duplicate_dedupe_key"

    finalize_notification_delivery(store, attempt.claim, status="sent", delivered_count=1)
    assert _claim(store, at=NOW + timedelta(hours=2)).decision == "duplicate_dedupe_key"


def test_a_reclaim_resets_the_previous_attempts_outcome():
    store = Ledger()
    attempt = _claim(store)
    finalize_notification_delivery(
        store, attempt.claim, status="failed", delivered_count=0, error_code="push_gone"
    )

    retry = _claim(store)

    assert retry.decision == "claimed"
    assert retry.claim.attempt_count == 2
    (row,) = store.list_notification_deliveries("p1")
    assert row["error_code"] is None and row["delivered_count"] == 0 and row["sent_at"] is None


def test_an_expired_candidate_is_outside_the_due_window():
    assert _claim(Ledger(), _candidate(expires_at=NOW)).decision == "outside_due_window"


def test_the_daily_cap_always_allows_one_delivery():
    # Candidates reject a zero cap, but the RPC floors it (greatest(1, cap)) for
    # any caller, so the ledger method does too.
    params = {
        "profile_id": "p1",
        "notification_type": "checkin",
        "intent": "morning_checkin",
        "dedupe_key": "d1",
        "expires_at": (NOW + timedelta(hours=4)).isoformat(),
        "training_day": "2026-08-02",
        "action_key": "",
        "variant_id": "",
        "notification_class": "routine",
        "daily_cap": 0,
        "min_spacing_minutes": 0,
    }
    assert Ledger().claim_notification_delivery(params, now_utc=NOW)["decision"] == "claimed"


def test_simulation_reads_only_what_production_queries():
    store = Ledger()
    # Another profile's delivery and an unrelated old day must not count.
    other = _candidate(profile_id="p2", dedupe_key="other")
    _claim(store, other)
    _claim(store, _candidate(dedupe_key="old", training_day="2026-07-01", expires_at=NOW + timedelta(hours=1)))

    state = store.get_notification_simulation_state(
        "p1",
        dedupe_keys=["d1"],
        training_days=["2026-08-02"],
        notification_classes=["routine"],
        action_keys=[],
    )

    assert state == {"deliveries": [], "evaluations": [], "action_rows": []}
    # With nothing in scope the candidate would be claimed.
    assert simulate_notification_delivery_decision(store, [_candidate()], now_utc=NOW) is not None
