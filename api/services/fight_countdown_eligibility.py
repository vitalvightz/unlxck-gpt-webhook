"""Last-mile eligibility for D-3 and D-1 fight-countdown notifications.

Late countdown pushes must come from the athlete's currently active combat plan,
not from a profile-level sport tag or a stale saved plan. Re-resolving the active
plan immediately before delivery also prevents a deferred notification surviving
an active-plan switch or a bout-date change.

The approved copy itself is owned by :mod:`api.services.notification_templates`,
which is also what the Supabase ``notification_templates`` v2 rows carry. This
module re-applies it at the last mile so the approved wording ships even if the
data migration has not run yet, but it never introduces a second wording.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any, Mapping

from fightcamp.sports import PLANNING_FAMILIES, normalize_sport

from api.services.active_plan import resolve_active_plan
from api.services.notification_foundation import NotificationCandidate
from api.services.notification_templates import LATE_FIGHT_COUNTDOWN_COPY
from api.store import AppStore

LATE_FIGHT_COUNTDOWN_DAYS = {
    "fc-d03": 3,
    "fc-d01": 1,
}

# Every canonical sport that runs a bout camp, not just the identities in
# ``SUPPORTED_SPORTS``. ``technical_style`` is free-form on the athlete model, so
# a persisted ``karate`` or ``grappling`` plan is reachable and must not be
# silently excluded from its own fight countdown.
LATE_FIGHT_COUNTDOWN_SPORTS = frozenset(PLANNING_FAMILIES)


def _styles(plan: Mapping[str, Any]) -> set[str]:
    raw = plan.get("technical_style") or []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set, frozenset)):
        values = raw
    else:
        values = []
    return {
        normalize_sport(value)
        for value in values
        if str(value or "").strip()
    }


def _candidate_intent(candidate: NotificationCandidate) -> str:
    """One resolved intent for both the gate and the copy enforcement."""

    return str(candidate.intent or candidate.notification_type or "").strip()


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
    """Fail closed for D-3/D-1 unless the source is still the active combat camp."""

    expected_days = LATE_FIGHT_COUNTDOWN_DAYS.get(str(candidate.variant_id or "").strip())
    if _candidate_intent(candidate) != "fight_countdown" or expected_days is None:
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

    if not (_styles(plan) & LATE_FIGHT_COUNTDOWN_SPORTS):
        return False

    fight_date_text = str(plan.get("fight_date") or "").strip()
    if not fight_date_text:
        return False
    try:
        fight_date = date.fromisoformat(fight_date_text[:10])
    except ValueError:
        return False

    return (fight_date - training_day).days == expected_days


def filter_late_fight_countdown_candidates(
    store: AppStore,
    candidates: list[NotificationCandidate],
) -> list[NotificationCandidate]:
    """Filter stale late-countdown events in-place and enforce approved copy.

    The in-place update is intentional and load-bearing: ``morning_push`` gates
    its streak and session-timing fallbacks on the orchestrator's reported
    candidate count, so a rejected D-3/D-1 event must shrink that count rather
    than silently suppressing every later notification path for the day.
    """

    filtered: list[NotificationCandidate] = []
    for candidate in candidates:
        if not late_fight_countdown_candidate_is_eligible(store, candidate):
            continue
        copy = LATE_FIGHT_COUNTDOWN_COPY.get(str(candidate.variant_id or "").strip())
        if copy is None or _candidate_intent(candidate) != "fight_countdown":
            filtered.append(candidate)
            continue
        # Record that delivery, not template selection, settled these bytes, so
        # the ledger's template_version stays honest about where copy came from.
        metadata = {
            **dict(candidate.source_event_metadata or {}),
            "late_countdown_copy_enforced": True,
        }
        filtered.append(
            replace(
                candidate,
                title=copy[0],
                body=copy[1],
                source_event_metadata=metadata,
            )
        )
    candidates[:] = filtered
    return candidates


__all__ = [
    "LATE_FIGHT_COUNTDOWN_COPY",
    "LATE_FIGHT_COUNTDOWN_DAYS",
    "LATE_FIGHT_COUNTDOWN_SPORTS",
    "filter_late_fight_countdown_candidates",
    "late_fight_countdown_candidate_is_eligible",
]
