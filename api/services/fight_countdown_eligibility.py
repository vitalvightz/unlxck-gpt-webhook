"""Last-mile eligibility for late fight-countdown notifications.

The fight-camp orchestrator derives countdown dates from the command view's
active plan. This module re-checks the same authority immediately before push
claiming so a queued/deferred D-3 or D-1 candidate cannot survive an active-plan
switch, a bout-date change, or a non-combat plan.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from api.services.active_plan import resolve_active_plan
from api.services.notification_foundation import NotificationCandidate
from api.store import AppStore

COMBAT_TECHNICAL_STYLES = frozenset(
    {
        "boxing",
        "kickboxing",
        "muay_thai",
        "mma",
        "wrestling",
        "bjj",
    }
)
LATE_FIGHT_COUNTDOWN_DAYS = {
    "fc-d03": 3,
    "fc-d01": 1,
}


def _styles(plan: Mapping[str, Any]) -> set[str]:
    raw = plan.get("technical_style") or []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set, frozenset)):
        values = raw
    else:
        values = []
    return {str(value or "").strip().lower() for value in values if str(value or "").strip()}


def _candidate_plan_id(candidate: NotificationCandidate) -> str:
    metadata_plan_id = str(candidate.source_event_metadata.get("plan_id") or "").strip()
    if metadata_plan_id:
        return metadata_plan_id

    prefix = "fight-countdown:"
    key = str(candidate.dedupe_key or "")
    if not key.startswith(prefix):
        return ""
    remainder = key[len(prefix) :]
    plan_id, separator, _label = remainder.rpartition(":")
    return plan_id.strip() if separator else ""


def late_fight_countdown_candidate_is_eligible(
    store: AppStore,
    candidate: NotificationCandidate,
) -> bool:
    """Fail closed for D-3/D-1 unless the candidate still matches the active combat camp."""

    intent = str(candidate.intent or candidate.notification_type or "").strip()
    expected_days = LATE_FIGHT_COUNTDOWN_DAYS.get(str(candidate.variant_id or "").strip())
    if intent != "fight_countdown" or expected_days is None:
        return True

    training_day_text = str(candidate.training_day or "").strip()
    try:
        training_day = date.fromisoformat(training_day_text)
    except ValueError:
        return False

    resolution = resolve_active_plan(
        store,
        candidate.profile_id,
        current_training_day=training_day,
    )
    plan = resolution.plan
    if not isinstance(plan, Mapping):
        return False

    active_plan_id = str(plan.get("id") or plan.get("plan_id") or "").strip()
    if not active_plan_id or _candidate_plan_id(candidate) != active_plan_id:
        return False

    if not (_styles(plan) & COMBAT_TECHNICAL_STYLES):
        return False

    fight_date_text = str(plan.get("fight_date") or "").strip()
    try:
        fight_date = date.fromisoformat(fight_date_text[:10])
    except ValueError:
        return False

    return (fight_date - training_day).days == expected_days


def filter_late_fight_countdown_candidates(
    store: AppStore,
    candidates: list[NotificationCandidate],
) -> list[NotificationCandidate]:
    """Drop stale/ineligible D-3/D-1 candidates while leaving all other intents untouched."""

    return [
        candidate
        for candidate in candidates
        if late_fight_countdown_candidate_is_eligible(store, candidate)
    ]
