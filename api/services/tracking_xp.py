"""Database-validated training milestones and one approved contribution reward.

No client chooses an amount, beneficiary, milestone or notification. These
best-effort hooks run after the authoritative product save; retries reconcile.
"""
import logging
from datetime import datetime, timedelta, timezone

from api.services.notification_foundation import NotificationCandidate
from api.services.progress_notifications import build_level_up_candidate, merge_progress_candidates
from api.services.push_notifications import dispatch_push_candidate
from api.services.xp_awards import ensure_xp_abuse_hardening

logger = logging.getLogger(__name__)

MILESTONE_TITLES = {
    "first_session_logged": "First session. UNLXCKED.",
    "first_exercise_logged": "Your first result. UNLXCKED.",
    "training_days_10": "10 training days. UNLXCKED.",
    "training_days_25": "25 training days. UNLXCKED.",
    "training_days_50": "50 training days. UNLXCKED.",
    "training_days_100": "100 training days. UNLXCKED.",
    "exercise_contribution_approved": "Your contribution is UNLXCKED.",
}


def notify_tracking_awards(store, athlete_id: str, results: list, athlete_timezone: str = "UTC") -> None:
    """At most one progress push per save, through existing preferences/caps."""
    awarded = [row for row in results if isinstance(row, dict) and row.get("awarded") and isinstance(row.get("award"), dict)]
    if not awarded:
        return
    now = datetime.now(timezone.utc)
    milestone = max((row for row in awarded if row["award"].get("action") in MILESTONE_TITLES),
                    key=lambda row: int(row["award"]["amount"]), default=None)
    candidates = []
    if milestone:
        award = milestone["award"]
        contribution = award["action"] == "exercise_contribution_approved"
        candidates.append(NotificationCandidate(
            profile_id=athlete_id, notification_type="exercise_contribution_approved" if contribution else "training_record_milestone",
            category="progress_milestones", priority=55, title=MILESTONE_TITLES[award["action"]],
            body="Your YouTube demo is approved for the community library. +100 XP." if contribution else f"Progress recorded. +{sum(int(row['award']['amount']) for row in awarded)} XP banked.",
            url="/progress", tag="training-progress", dedupe_key=f"tracking-xp:{award['id']}",
            expires_at=now + timedelta(days=3), timezone_name=athlete_timezone or "UTC",
            respect_quiet_hours=True, notification_class="event", min_spacing_minutes=30,
            action_key="review-progress", source_event_metadata={"award_id": award["id"], "action": award["action"]},
        ))
    level = build_level_up_candidate(
        athlete_id=athlete_id, previous_total_xp=awarded[0]["previous_total_xp"],
        total_xp=awarded[-1]["state"]["total_xp"], source_key=str(awarded[-1]["award"]["id"]),
        timezone_name=athlete_timezone or "UTC", now_utc=now,
    )
    if level:
        candidates.append(level)
    selected = merge_progress_candidates(candidates, now_utc=now)
    if selected:
        dispatch_push_candidate(store, selected, now_utc=now)


def reconcile_training_xp(store, athlete_id: str, *, manual_session_id: str | None = None, athlete_timezone: str | None = "UTC") -> list:
    try:
        ensure_xp_abuse_hardening(store)
        results = store.reconcile_training_engagement_xp(athlete_id, manual_session_id=manual_session_id)
        results = results if isinstance(results, list) else []
    except Exception:  # noqa: BLE001 - never turn a successful training save into an error
        logger.exception("[xp] tracking reconciliation failed athlete_id=%s", athlete_id)
        return []
    try:
        notify_tracking_awards(store, athlete_id, results, athlete_timezone or "UTC")
    except Exception:  # noqa: BLE001 - notification failure must not affect XP
        logger.exception("[notification] tracking milestone delivery failed athlete_id=%s", athlete_id)
    return results


def reconcile_contribution_xp(store, revision_id: str) -> None:
    try:
        ensure_xp_abuse_hardening(store)
        result = store.reconcile_approved_contribution_xp(revision_id)
        if isinstance(result, dict) and result.get("athlete_id"):
            notify_tracking_awards(store, result["athlete_id"], result.get("results") or [], result.get("timezone") or "UTC")
    except Exception:  # noqa: BLE001 - approval and publication have already succeeded
        logger.exception("[xp] approved contribution reconciliation failed revision_id=%s", revision_id)
