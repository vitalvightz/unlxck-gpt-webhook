"""Authoritative phase, first-plan and fight-camp milestone orchestration."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from api.services.notification_foundation import NotificationCandidate
from api.services.progress_notifications import (
    build_level_up_candidate,
    build_week_complete_candidate,
    merge_progress_candidates,
)
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


def _call_store_or_rpc(
    store: AppStore,
    *,
    method_name: str,
    rpc_name: str,
    method_args: tuple[Any, ...],
    method_kwargs: Mapping[str, Any],
    rpc_params: Mapping[str, Any],
) -> dict[str, Any] | None:
    method = getattr(store, method_name, None)
    if callable(method):
        result = method(*method_args, **dict(method_kwargs))
        return dict(result) if isinstance(result, Mapping) else None

    client = getattr(store, "client", None)
    if client is None:
        return None
    return _rpc_payload(client.rpc(rpc_name, dict(rpc_params)).execute())


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
    return _call_store_or_rpc(
        store,
        method_name="record_plan_milestone",
        rpc_name="record_plan_milestone",
        method_args=(athlete_id,),
        method_kwargs={
            "plan_id": plan_id,
            "milestone_type": milestone_type,
            "milestone_key": milestone_key,
            "phase_label": phase_label,
            "metadata": dict(metadata),
        },
        rpc_params={
            "p_athlete_id": athlete_id,
            "p_plan_id": plan_id,
            "p_milestone_type": milestone_type,
            "p_milestone_key": milestone_key,
            "p_phase_label": phase_label,
            "p_metadata": dict(metadata),
        },
    )


def _begin_week_reconciliation(
    store: AppStore,
    *,
    athlete_id: str,
    plan_id: str,
    week_id: str,
) -> dict[str, Any] | None:
    return _call_store_or_rpc(
        store,
        method_name="begin_week_lifecycle_reconciliation",
        rpc_name="begin_week_lifecycle_reconciliation",
        method_args=(athlete_id,),
        method_kwargs={"plan_id": plan_id, "week_id": week_id},
        rpc_params={
            "p_athlete_id": athlete_id,
            "p_plan_id": plan_id,
            "p_week_id": week_id,
        },
    )


def _complete_week_reconciliation(
    store: AppStore,
    *,
    athlete_id: str,
    plan_id: str,
    week_id: str,
) -> dict[str, Any] | None:
    return _call_store_or_rpc(
        store,
        method_name="complete_week_lifecycle_reconciliation",
        rpc_name="complete_week_lifecycle_reconciliation",
        method_args=(athlete_id,),
        method_kwargs={"plan_id": plan_id, "week_id": week_id},
        rpc_params={
            "p_athlete_id": athlete_id,
            "p_plan_id": plan_id,
            "p_week_id": week_id,
        },
    )


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
    plan_id: str,
    milestone_type: str,
    milestone_key: str,
    phase_label: str | None,
    first_plan_xp_awarded: bool,
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
        title = "First plan complete" if first_plan_xp_awarded else "Plan complete"
        body = (
            "You finished your first full plan. Review what moved you forward."
            if first_plan_xp_awarded
            else "You finished this plan. Review what moved you forward."
        )
        notification_type = (
            "first_plan_complete" if first_plan_xp_awarded else "plan_complete"
        )
        tag = "plan-complete"
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
        dedupe_key=f"{tag}:{plan_id}:{milestone_key}"[:160],
        expires_at=now_utc + timedelta(days=4),
        timezone_name=timezone_name or "UTC",
        respect_quiet_hours=True,
        training_day=now_utc.astimezone(timezone.utc).date().isoformat(),
        notification_class="event",
        min_spacing_minutes=30,
        action_key="review-progress",
        source_event_metadata={
            "plan_id": plan_id,
            "milestone_type": milestone_type,
            "milestone_key": milestone_key,
        },
    )


def _record_milestone_safely(
    store: AppStore,
    *,
    athlete_id: str,
    plan_id: str,
    milestone_type: str,
    milestone_key: str,
    phase_label: str | None,
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    try:
        return _record_milestone(
            store,
            athlete_id=athlete_id,
            plan_id=plan_id,
            milestone_type=milestone_type,
            milestone_key=milestone_key,
            phase_label=phase_label,
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001 - milestones must never break session logging
        logger.exception(
            "[xp] plan milestone failed athlete_id=%s plan_id=%s type=%s key=%s",
            athlete_id,
            plan_id,
            milestone_type,
            milestone_key,
        )
        return None


def _milestone_specs(
    *,
    plan: Mapping[str, Any],
    completed_week: Mapping[str, Any],
    completions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    weeks = _ordered_weeks(plan)
    current_week_id = _week_id(completed_week)
    if not weeks or not current_week_id:
        return []

    specs: list[dict[str, Any]] = []
    phase_weeks = _phase_segment(weeks, current_week_id=current_week_id)
    phase = _phase_label(completed_week)
    if phase_weeks and phase and _all_weeks_complete(phase_weeks, completions):
        phase_week_ids = [_week_id(week) for week in phase_weeks]
        specs.append(
            {
                "milestone_type": "phase_completed",
                "milestone_key": (
                    f"phase:{phase}:{phase_week_ids[0]}:{phase_week_ids[-1]}"
                ),
                "phase_label": phase,
                "metadata": {"week_ids": phase_week_ids, "phase_label": phase},
            }
        )

    plan_type = _plan_type(plan)
    if (
        not plan_type
        or plan_type in OPEN_ENDED_PLAN_TYPES
        or not _all_weeks_complete(weeks, completions)
    ):
        return specs

    week_ids = [_week_id(week) for week in weeks]
    specs.append(
        {
            "milestone_type": "plan_completed",
            "milestone_key": "plan-complete",
            "phase_label": None,
            "metadata": {"week_ids": week_ids, "plan_type": plan_type},
        }
    )
    if plan_type == "fight_camp":
        specs.append(
            {
                "milestone_type": "camp_completed",
                "milestone_key": "camp-complete",
                "phase_label": None,
                "metadata": {"week_ids": week_ids, "plan_type": plan_type},
            }
        )
    return specs


def _result_identity(result: Mapping[str, Any]) -> tuple[str, str] | None:
    milestone = result.get("milestone")
    if not isinstance(milestone, Mapping):
        return None
    milestone_type = str(milestone.get("milestone_type") or "").strip()
    milestone_key = str(milestone.get("milestone_key") or "").strip()
    if not milestone_type or not milestone_key:
        return None
    return milestone_type, milestone_key


def _dispatch_best_notification(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    plan_id: str,
    recorded: Sequence[tuple[str, str, str | None, Mapping[str, Any]]],
    week_award_result: Mapping[str, Any] | None = None,
    week_key: str | None = None,
    now_utc: datetime | None = None,
) -> int:
    reference = now_utc or datetime.now(timezone.utc)
    milestone_candidates: list[NotificationCandidate] = []
    level_candidates: list[tuple[int, NotificationCandidate]] = []

    for milestone_type, milestone_key, phase_label, result in recorded:
        award = _award_result(result)
        award_was_new = bool(award.get("awarded"))
        milestone_was_new = bool(result.get("milestone_inserted"))

        if milestone_was_new:
            candidate = _milestone_candidate(
                athlete_id=athlete_id,
                plan_id=plan_id,
                milestone_type=milestone_type,
                milestone_key=milestone_key,
                phase_label=phase_label,
                first_plan_xp_awarded=(
                    milestone_type == "plan_completed" and award_was_new
                ),
                timezone_name=athlete_timezone or "UTC",
                now_utc=reference,
            )
            if candidate is not None:
                milestone_candidates.append(candidate)

        if award_was_new:
            previous, total = _result_totals(award)
            level_candidate = build_level_up_candidate(
                athlete_id=athlete_id,
                previous_total_xp=previous,
                total_xp=total,
                source_key=f"{plan_id}:{milestone_key}",
                timezone_name=athlete_timezone or "UTC",
                now_utc=reference,
            )
            if level_candidate is not None:
                level_candidates.append((total, level_candidate))

    combined = list(milestone_candidates)
    if level_candidates:
        # Several milestone awards can cross levels in one reconciliation. The
        # athlete should see only the highest resulting level in the compound.
        combined.append(max(level_candidates, key=lambda item: item[0])[1])
    if week_key and bool((week_award_result or {}).get("awarded")):
        combined.append(
            build_week_complete_candidate(
                athlete_id=athlete_id,
                week_key=week_key,
                timezone_name=athlete_timezone or "UTC",
                now_utc=reference,
            )
        )
        previous, total = _result_totals(week_award_result or {})
        level_candidate = build_level_up_candidate(
            athlete_id=athlete_id,
            previous_total_xp=previous,
            total_xp=total,
            source_key=week_key,
            timezone_name=athlete_timezone or "UTC",
            now_utc=reference,
        )
        if level_candidate is not None:
            combined.append(level_candidate)
    selected = merge_progress_candidates(combined, now_utc=reference)
    if selected is None:
        return 0
    return dispatch_push_candidate(store, selected, now_utc=reference)


def record_plan_milestones_after_completed_week(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    plan: Mapping[str, Any],
    completed_week: Mapping[str, Any],
    completions: Sequence[Mapping[str, Any]],
    week_award_result: Mapping[str, Any] | None = None,
    week_key: str | None = None,
) -> list[dict[str, Any]]:
    """Idempotently record every lifecycle milestone now implied by the plan."""

    plan_id = str(plan.get("id") or "").strip()
    if not plan_id:
        return []

    specs = _milestone_specs(
        plan=plan,
        completed_week=completed_week,
        completions=completions,
    )
    recorded: list[tuple[str, str, str | None, Mapping[str, Any]]] = []
    results: list[dict[str, Any]] = []

    for spec in specs:
        milestone_type = str(spec["milestone_type"])
        milestone_key = str(spec["milestone_key"])
        phase_label = spec.get("phase_label")
        result = _record_milestone_safely(
            store,
            athlete_id=athlete_id,
            plan_id=plan_id,
            milestone_type=milestone_type,
            milestone_key=milestone_key,
            phase_label=str(phase_label) if phase_label is not None else None,
            metadata=spec["metadata"],
        )
        if result:
            normalized = dict(result)
            results.append(normalized)
            recorded.append(
                (
                    milestone_type,
                    milestone_key,
                    str(phase_label) if phase_label is not None else None,
                    normalized,
                )
            )

    try:
        _dispatch_best_notification(
            store,
            athlete_id=athlete_id,
            athlete_timezone=athlete_timezone,
            plan_id=plan_id,
            recorded=recorded,
            week_award_result=week_award_result,
            week_key=week_key,
        )
    except Exception:  # noqa: BLE001 - push must never break milestone persistence
        logger.exception(
            "[notification] plan milestone delivery failed athlete_id=%s plan_id=%s",
            athlete_id,
            plan_id,
        )
    return results


def reconcile_plan_milestones_after_completed_week(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str,
    plan: Mapping[str, Any],
    completed_week: Mapping[str, Any],
    completions: Sequence[Mapping[str, Any]],
    week_award_result: Mapping[str, Any] | None = None,
    week_key: str | None = None,
) -> dict[str, Any]:
    """Durably reconcile lifecycle milestones for an already-confirmed week.

    A pending checkpoint is written before milestone work starts. Repeated calls
    repair any missing phase, plan or camp rows idempotently. The checkpoint is
    marked completed only when every milestone currently implied by the
    authoritative plan/completion state has been observed.
    """

    plan_id = str(plan.get("id") or "").strip()
    week_id = _week_id(completed_week)
    if not plan_id or not week_id:
        return {"reconciled": False, "expected": [], "results": []}

    checkpoint: dict[str, Any] | None = None
    try:
        checkpoint = _begin_week_reconciliation(
            store,
            athlete_id=athlete_id,
            plan_id=plan_id,
            week_id=week_id,
        )
    except Exception:  # noqa: BLE001 - checkpoint failure must not break session logging
        logger.exception(
            "[xp] lifecycle checkpoint start failed athlete_id=%s plan_id=%s week_id=%s",
            athlete_id,
            plan_id,
            week_id,
        )

    if checkpoint and str(checkpoint.get("status") or "") == "completed":
        return {
            "reconciled": True,
            "expected": [],
            "results": [],
            "checkpoint": checkpoint,
        }

    specs = _milestone_specs(
        plan=plan,
        completed_week=completed_week,
        completions=completions,
    )
    expected = {
        (str(spec["milestone_type"]), str(spec["milestone_key"]))
        for spec in specs
    }
    results = record_plan_milestones_after_completed_week(
        store,
        athlete_id=athlete_id,
        athlete_timezone=athlete_timezone,
        plan=plan,
        completed_week=completed_week,
        completions=completions,
        week_award_result=week_award_result,
        week_key=week_key,
    )
    observed = {
        identity
        for result in results
        if (identity := _result_identity(result)) is not None
    }
    reconciled = expected.issubset(observed)

    if reconciled and checkpoint is not None:
        try:
            completed_checkpoint = _complete_week_reconciliation(
                store,
                athlete_id=athlete_id,
                plan_id=plan_id,
                week_id=week_id,
            )
            if completed_checkpoint is not None:
                checkpoint = completed_checkpoint
        except Exception:  # noqa: BLE001 - retry will safely repair this marker
            logger.exception(
                "[xp] lifecycle checkpoint completion failed athlete_id=%s plan_id=%s week_id=%s",
                athlete_id,
                plan_id,
                week_id,
            )
            reconciled = False

    return {
        "reconciled": reconciled,
        "expected": sorted(expected),
        "results": results,
        "checkpoint": checkpoint,
    }


__all__ = [
    "OPEN_ENDED_PLAN_TYPES",
    "record_plan_milestones_after_completed_week",
    "reconcile_plan_milestones_after_completed_week",
]
