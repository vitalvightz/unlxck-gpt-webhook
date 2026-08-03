"""Authoritative phase, first-plan and fight-camp milestone orchestration."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from api.services.notification_foundation import NotificationCandidate
from api.services.progress_notifications import build_level_up_candidate
from api.services.push_notifications import dispatch_push_candidate
from api.services.week_progress import evaluate_week_completion
from api.store import AppStore

logger = logging.getLogger(__name__)

OPEN_ENDED_PLAN_TYPES = frozenset({"open_ongoing_system"})


def _mapping_rows(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _structured(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    value = plan.get("structured_plan")
    return value if isinstance(value, Mapping) else {}


def _ordered_weeks(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    weeks = _mapping_rows(_structured(plan).get("weeks"))
    indexed = list(enumerate(weeks))

    def sort_key(item: tuple[int, Mapping[str, Any]]) -> tuple[int, int]:
        position, week = item
        try:
            week_index = int(week.get("week_index"))
        except (TypeError, ValueError):
            week_index = 10_000 + position
        return week_index, position

    return [week for _, week in sorted(indexed, key=sort_key)]


def _plan_type(plan: Mapping[str, Any]) -> str:
    metadata = _structured(plan).get("plan_metadata")
    if not isinstance(metadata, Mapping):
        return ""
    return str(metadata.get("plan_type") or "").strip().lower()


def _week_id(week: Mapping[str, Any]) -> str:
    return str(week.get("week_id") or "").strip()


def _phase_label(week: Mapping[str, Any]) -> str:
    return str(week.get("phase_label") or "").strip().upper()


def _phase_segment(
    weeks: Sequence[Mapping[str, Any]],
    *,
    current_week_id: str,
) -> list[Mapping[str, Any]]:
    current_index = next(
        (index for index, week in enumerate(weeks) if _week_id(week) == current_week_id),
        None,
    )
    if current_index is None:
        return []
    label = _phase_label(weeks[current_index])
    if not label:
        return []

    start = current_index
    while start > 0 and _phase_label(weeks[start - 1]) == label:
        start -= 1
    end = current_index
    while end + 1 < len(weeks) and _phase_label(weeks[end + 1]) == label:
        end += 1
    return list(weeks[start : end + 1])


def _week_completions(
    week: Mapping[str, Any],
    completions: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    start_date = str(week.get("start_date") or "").strip()
    end_date = str(week.get("end_date") or "").strip()
    if not start_date or not end_date:
        return []
    return [
        row
        for row in completions
        if start_date <= str(row.get("training_day") or "") <= end_date
    ]


def _all_weeks_complete(
    weeks: Sequence[Mapping[str, Any]],
    completions: Sequence[Mapping[str, Any]],
) -> bool:
    if not weeks:
        return False
    return all(
        evaluate_week_completion(
            week=week,
            completions=_week_completions(week, completions),
        )["complete"]
        for week in weeks
    )


def _rpc_payload(response: object) -> dict[str, Any] | None:
    payload = getattr(response, "data", None)
    if isinstance(payload, list):
        payload = payload[0] if payload else None
    return dict(payload) if isinstance(payload, Mapping) else None


def _record_milestone(
    store: AppStore,
    *,
    athlete_id: str,
    plan_id: str,
    milestone_type: str,
    milestone_key: str,
    phase_label: str | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    recorder = getattr(store, "record_plan_milestone", None)
    if callable(recorder):
        result = recorder(
            athlete_id,
            plan_id=plan_id,
            milestone_type=milestone_type,
            milestone_key=milestone_key,
            phase_label=phase_label,
            metadata=dict(metadata),
        )
        return dict(result) if isinstance(result, Mapping) else None

    client = getattr(store, "client", None)
    if client is None:
        return None
    response = client.rpc(
        "record_plan_milestone",
        {
            "p_athlete_id": athlete_id,
            "p_plan_id": plan_id,
            "p_milestone_type": milestone_type,
            "p_milestone_key": milestone_key,
            "p_phase_label": phase_label,
            "p_metadata": dict(metadata),
        },
    ).execute()
    return _rpc_payload(response)


def _award_result(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("award_result")
    return value if isinstance(value, Mapping) else {}


def _result_totals(result: Mapping[str, Any]) -> tuple[int, int]:
    try:
        previous = max(0, int(result.get("previous_total_xp") or 0))
    except (TypeError, ValueError):
        previous = 0
    state = result.get("state") if isinstance(result.get("state"), Mapping) else {}
    try:
        total = max(0, int(state.get("total_xp") or previous))
    except (TypeError, ValueError):
        total = previous
    return previous, total


def _milestone_candidate(
    *,
    athlete_id: str,
    milestone_type: str,
    milestone_key: str,
    phase_label: str | None,
    timezone_name: str,
    now_utc: datetime,
) -> NotificationCandidate | None:
    if milestone_type == "phase_completed" and phase_label:
        title = f"{phase_label} complete"
        body = "That phase is banked. Review it before the next block."
        notification_type = "training_phase_complete"
        tag = "training-phase-complete"
        priority = 58
    elif milestone_type == "plan_completed":
        title = "First plan complete"
        body = "You finished the full plan. Review what moved you forward."
        notification_type = "first_plan_complete"
        tag = "first-plan-complete"
        priority = 56
    elif milestone_type == "camp_completed":
        title = "Camp complete"
        body = "The full camp is banked. Review the journey before the next one."
        notification_type = "fight_camp_complete"
        tag = "fight-camp-complete"
        priority = 54
    else:
        return None

    return NotificationCandidate(
        profile_id=athlete_id,
        notification_type=notification_type,
        category="progress_milestones",
        priority=priority,
        title=title,
        body=body,
        url="/history",
        tag=tag,
        dedupe_key=f"{tag}:{milestone_key}"[:160],
        expires_at=now_utc + timedelta(days=4),
        timezone_name=timezone_name or "UTC",
        respect_quiet_hours=True,
    )


def _dispatch_milestone_notification(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    milestone_type: str,
    milestone_key: str,
    phase_label: str | None,
    result: Mapping[str, Any],
    now_utc: datetime | None = None,
) -> int:
    award = _award_result(result)
    if not bool(award.get("awarded")):
        return 0
    reference = now_utc or datetime.now(timezone.utc)
    previous, total = _result_totals(award)
    candidates: list[NotificationCandidate] = []
    milestone_candidate = _milestone_candidate(
        athlete_id=athlete_id,
        milestone_type=milestone_type,
        milestone_key=milestone_key,
        phase_label=phase_label,
        timezone_name=athlete_timezone or "UTC",
        now_utc=reference,
    )
    if milestone_candidate is not None:
        candidates.append(milestone_candidate)
    level_candidate = build_level_up_candidate(
        athlete_id=athlete_id,
        previous_total_xp=previous,
        total_xp=total,
        source_key=milestone_key,
        timezone_name=athlete_timezone or "UTC",
        now_utc=reference,
    )
    if level_candidate is not None:
        candidates.append(level_candidate)
    if not candidates:
        return 0
    return dispatch_push_candidate(
        store,
        min(candidates, key=lambda candidate: candidate.priority),
        now_utc=reference,
    )


def _record_and_notify(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    plan_id: str,
    milestone_type: str,
    milestone_key: str,
    phase_label: str | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    try:
        result = _record_milestone(
            store,
            athlete_id=athlete_id,
            plan_id=plan_id,
            milestone_type=milestone_type,
            milestone_key=milestone_key,
            phase_label=phase_label,
            metadata=metadata,
        )
        if not isinstance(result, Mapping):
            return None
        normalized = dict(result)
        _dispatch_milestone_notification(
            store,
            athlete_id=athlete_id,
            athlete_timezone=athlete_timezone,
            milestone_type=milestone_type,
            milestone_key=milestone_key,
            phase_label=phase_label,
            result=normalized,
        )
        return normalized
    except Exception:  # noqa: BLE001 - milestones must never break session logging
        logger.exception(
            "[xp] plan milestone failed athlete_id=%s plan_id=%s type=%s key=%s",
            athlete_id,
            plan_id,
            milestone_type,
            milestone_key,
        )
        return None


def record_plan_milestones_after_completed_week(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    plan: Mapping[str, Any],
    completed_week: Mapping[str, Any],
    completions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    plan_id = str(plan.get("id") or "").strip()
    current_week_id = _week_id(completed_week)
    weeks = _ordered_weeks(plan)
    if not plan_id or not current_week_id or not weeks:
        return []

    results: list[dict[str, Any]] = []
    phase_weeks = _phase_segment(weeks, current_week_id=current_week_id)
    phase = _phase_label(completed_week)
    if phase_weeks and phase and _all_weeks_complete(phase_weeks, completions):
        phase_week_ids = [_week_id(week) for week in phase_weeks]
        phase_key = f"phase:{phase}:{phase_week_ids[0]}:{phase_week_ids[-1]}"
        result = _record_and_notify(
            store,
            athlete_id=athlete_id,
            athlete_timezone=athlete_timezone,
            plan_id=plan_id,
            milestone_type="phase_completed",
            milestone_key=phase_key,
            phase_label=phase,
            metadata={"week_ids": phase_week_ids, "phase_label": phase},
        )
        if result:
            results.append(result)

    plan_type = _plan_type(plan)
    if plan_type in OPEN_ENDED_PLAN_TYPES or not _all_weeks_complete(weeks, completions):
        return results

    week_ids = [_week_id(week) for week in weeks]
    plan_result = _record_and_notify(
        store,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        plan_id=plan_id,
        milestone_type="plan_completed",
        milestone_key="plan-complete",
        phase_label=None,
        metadata={"week_ids": week_ids, "plan_type": plan_type},
    )
    if plan_result:
        results.append(plan_result)

    if plan_type == "fight_camp":
        camp_result = _record_and_notify(
            store,
            athlete_id=athlete_id,
            athlete_timezone=athlete_timezone,
            plan_id=plan_id,
            milestone_type="camp_completed",
            milestone_key="camp-complete",
            phase_label=None,
            metadata={"week_ids": week_ids, "plan_type": plan_type},
        )
        if camp_result:
            results.append(camp_result)
    return results


__all__ = [
    "OPEN_ENDED_PLAN_TYPES",
    "record_plan_milestones_after_completed_week",
]
