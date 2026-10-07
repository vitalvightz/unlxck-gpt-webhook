"""Log what an athlete actually did for one prescribed block today.

A log never edits the plan. It records the block as prescribed (a frozen copy)
beside what was done, keyed on the block's server-owned ``block_id``.

Logging is only open for a session the athlete has started or completed today.
That is deliberate: every gate on training itself (rest day, safety hold,
severe injury, check-in, stale prescription) is enforced once, on the session
start, and a log can never record work the athlete was not cleared to begin.

Rehab blocks are not logged here. Their dose is recorded by the rehab
completion flow, which owns rehab evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from api.store import AppStore

from .today_service import (
    _TRAINING_COMPLETION_STATUSES,
    _iter_mapping_items,
    _require_valid_plan_id,
    _structured_day_for_training_day,
    resolve_training_day,
)

# The prescription fields a log freezes. Coaching copy (cues, purpose, stop
# rules) is left out: it is not what the athlete's numbers are compared against.
_PRESCRIBED_FIELDS: tuple[str, ...] = (
    "display_name",
    "block_type",
    "category",
    "sets",
    "reps",
    "rounds",
    "load",
    "duration",
    "work",
    "rest",
    "distance",
    "effort",
    "tempo",
    "intensity",
)

_NOT_STARTED_DETAIL = "Start today's session before logging an exercise."
_UNKNOWN_BLOCK_DETAIL = "That exercise is not in today's session. Refresh Today and try again."
_REHAB_DETAIL = "Rehab is logged when you complete the session."


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _prescribed_snapshot(block: Mapping[str, Any]) -> dict[str, Any]:
    return {key: block[key] for key in _PRESCRIBED_FIELDS if block.get(key) not in (None, "", [], {})}


def _active_completions(
    store: AppStore, *, athlete_id: str, plan_id: str, training_day: str
) -> list[dict[str, Any]]:
    """Today's started / completed session records for this plan."""
    rows = store.list_session_completions_from_day(athlete_id, training_day)
    return [
        row
        for row in rows
        if _clean(row.get("training_day"))[:10] == training_day
        and _clean(row.get("plan_id")) == plan_id
        and _clean(row.get("status")) in _TRAINING_COMPLETION_STATUSES
    ]


def _loggable_blocks(
    plan_row: Mapping[str, Any],
    *,
    training_day: str,
    completions: list[dict[str, Any]],
) -> list[tuple[str | None, Mapping[str, Any]]]:
    """``(session_id, block)`` for every block of today's started sessions.

    A session started under live injury guidance was frozen on its completion
    row; that frozen copy is what the athlete was shown, so it leads. The plan
    card's own sessions follow, and only the ones that were actually started.
    """
    plan_id = _clean(plan_row.get("id"))
    blocks: list[tuple[str | None, Mapping[str, Any]]] = []
    for completion in completions:
        snapshot = completion.get("prescription_snapshot")
        session = snapshot.get("session") if isinstance(snapshot, Mapping) else None
        if not isinstance(session, Mapping) or _clean(snapshot.get("plan_id")) != plan_id:
            continue
        session_id = _clean(session.get("session_id")) or _clean(completion.get("session_id")) or None
        blocks.extend((session_id, block) for block in _iter_mapping_items(session.get("blocks")))

    started_session_ids = {_clean(row.get("session_id")) for row in completions}
    matched = _structured_day_for_training_day(plan_row, training_day)
    if matched is not None:
        day, _week = matched
        for session in _iter_mapping_items(day.get("sessions")):
            session_id = _clean(session.get("session_id"))
            if session_id not in started_session_ids:
                continue
            blocks.extend((session_id, block) for block in _iter_mapping_items(session.get("blocks")))
    return blocks


def record_exercise_log(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    payload: Mapping[str, Any],
    health_consent_granted: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and upsert one exercise log for the server's training day."""
    plan_id = _clean(payload.get("plan_id"))
    block_id = _clean(payload.get("block_id"))
    _require_valid_plan_id(plan_id)
    # Service-role write: plan ownership is enforced here, not by RLS.
    plan_row = store.get_plan_for_athlete(plan_id, athlete_id)
    if plan_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

    training_day = resolve_training_day(athlete_timezone, now=now)
    completions = _active_completions(
        store, athlete_id=athlete_id, plan_id=plan_id, training_day=training_day
    )
    if not completions:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_NOT_STARTED_DETAIL)

    match = next(
        (
            (session_id, block)
            for session_id, block in _loggable_blocks(
                plan_row, training_day=training_day, completions=completions
            )
            if _clean(block.get("block_id")) == block_id
        ),
        None,
    )
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_UNKNOWN_BLOCK_DETAIL)
    session_id, block = match
    if _clean(block.get("block_type")) == "rehab":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_REHAB_DETAIL)

    reason = payload.get("reason")
    if reason == "pain" and not health_consent_granted:
        # Pain is health data. Without consent the training log is kept and the
        # health field is dropped, as session completion does with pain_after.
        reason = None
    actual = payload.get("actual")
    fields = {
        "plan_id": plan_id,
        "session_id": session_id,
        "block_id": block_id,
        "exercise_key": _clean(block.get("exercise_key")) or None,
        "training_day": training_day,
        "status": payload.get("status"),
        "reason": reason,
        "prescribed": _prescribed_snapshot(block),
        "actual": dict(actual) if isinstance(actual, Mapping) else {},
        "notes": _clean(payload.get("notes")),
    }
    return store.upsert_exercise_log(athlete_id, fields)


def list_exercise_logs_for_today(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    plan_id: str,
    now: datetime | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """``(training_day, logs)`` for one of the athlete's plans, today only."""
    _require_valid_plan_id(plan_id)
    if store.get_plan_for_athlete(plan_id, athlete_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
    training_day = resolve_training_day(athlete_timezone, now=now)
    rows = store.list_exercise_logs_for_day(athlete_id, plan_id=plan_id, training_day=training_day)
    return training_day, rows


__all__ = ["list_exercise_logs_for_today", "record_exercise_log"]
