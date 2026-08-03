"""Synchronize active intake injuries into the live daily injury tracker.

Guided intake's ``cleared`` field answers "Have you been medically cleared?".
It does not mean the injury has healed. Treating ``cleared=yes`` as resolution
made structural injuries disappear from ``injury_flags`` immediately after plan
generation, so their rehab blocks were labelled Prehab before the athlete had
actually cleared the injury in Today.

The explicit ``timeframe=old_cleared`` option is the history-only signal. Every
other guided injury is eligible for the live tracker, including an injury the
athlete is medically cleared to train around.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from api.contracts.training_day import resolve_training_day_str
from api.store import AppStore

from .active_plan import resolve_active_plan
from .today_service import (
    _guided_injury_has_content,
    _guided_intake_injury_candidate,
    _injury_dedupe_keys,
    _intake_payload_from_row,
    _intake_row_for_plan,
    _legacy_intake_injury_candidate,
)

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("open", "monitoring")
_DEDUPE_STATUSES = ("open", "monitoring", "resolved")
_HISTORICAL_CLEARED_TIMEFRAME = "old_cleared"


def _normalized_token(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def _guided_candidate(
    injury: Mapping[str, Any],
    *,
    plan_id: str,
) -> dict[str, object] | None:
    # "Old / cleared" is the explicit resolved-history choice. The separate
    # `cleared` answer is medical clearance to train and must not suppress an
    # otherwise active injury from daily tracking.
    if _normalized_token(injury.get("timeframe")) == _HISTORICAL_CLEARED_TIMEFRAME:
        return None

    bootstrap_injury = dict(injury)
    bootstrap_injury["cleared"] = ""
    return _guided_intake_injury_candidate(bootstrap_injury, plan_id=plan_id)


def _intake_injury_candidates(
    intake_payload: Mapping[str, Any],
    *,
    plan_id: str,
) -> list[dict[str, object]]:
    guided_injuries = intake_payload.get("guided_injuries")
    if isinstance(guided_injuries, list):
        guided_items = [
            injury
            for injury in guided_injuries
            if isinstance(injury, Mapping) and _guided_injury_has_content(injury)
        ]
        if guided_items:
            return [
                candidate
                for injury in guided_items
                if (candidate := _guided_candidate(injury, plan_id=plan_id)) is not None
            ]

    guided_injury = intake_payload.get("guided_injury")
    if isinstance(guided_injury, Mapping) and _guided_injury_has_content(guided_injury):
        candidate = _guided_candidate(guided_injury, plan_id=plan_id)
        return [candidate] if candidate else []

    legacy = _legacy_intake_injury_candidate(
        intake_payload.get("injuries"),
        plan_id=plan_id,
    )
    return [legacy] if legacy else []


def _list_flags(
    store: AppStore,
    athlete_id: str,
    *,
    statuses: tuple[str, ...],
) -> list[dict[str, Any]]:
    lister = getattr(store, "list_injury_flags", None)
    if not callable(lister):
        return []
    try:
        return [
            dict(flag)
            for flag in (lister(athlete_id, statuses=statuses, limit=500) or [])
        ]
    except Exception:
        logger.exception(
            "[intake_injury_sync] injury flag read failed athlete_id=%s statuses=%s",
            athlete_id,
            statuses,
        )
        return []


def sync_intake_injuries_for_plan(
    store: AppStore,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Seed active-plan intake injuries and return current open/monitoring flags.

    Reads resolved rows for deduplication so an injury cleared through Today never
    returns merely because the original intake remains unchanged. The write is
    best-effort: a tracker failure must not make the plan or Today endpoint fail.
    """
    open_flags = _list_flags(store, athlete_id, statuses=_ACTIVE_STATUSES)
    plan_id = str(plan_row.get("id") or "").strip()
    if not plan_id:
        return open_flags

    try:
        intake_payload = _intake_payload_from_row(
            _intake_row_for_plan(
                store,
                athlete_id=athlete_id,
                plan_row=plan_row,
            )
        )
    except Exception:
        logger.exception(
            "[intake_injury_sync] intake read failed athlete_id=%s plan_id=%s",
            athlete_id,
            plan_id,
        )
        return open_flags
    if not intake_payload:
        return open_flags

    create_flag = getattr(store, "create_injury_flag", None)
    if not callable(create_flag):
        return open_flags

    dedupe_flags = _list_flags(store, athlete_id, statuses=_DEDUPE_STATUSES)
    if not dedupe_flags:
        dedupe_flags = list(open_flags)
    seen_keys = {
        key
        for flag in dedupe_flags
        for key in _injury_dedupe_keys(flag)
    }

    seeded = list(open_flags)
    for candidate in _intake_injury_candidates(intake_payload, plan_id=plan_id):
        candidate_keys = _injury_dedupe_keys(candidate)
        if not candidate_keys or candidate_keys & seen_keys:
            continue
        try:
            created = dict(create_flag(athlete_id, candidate))
        except Exception:
            logger.exception(
                "[intake_injury_sync] injury flag create failed athlete_id=%s plan_id=%s",
                athlete_id,
                plan_id,
            )
            continue
        seeded.insert(0, created)
        seen_keys.update(candidate_keys)
    return seeded


def sync_active_plan_intake_injuries(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Synchronize the server-resolved active plan before Today is assembled."""
    training_day = resolve_training_day_str(
        now or datetime.now(timezone.utc),
        athlete_timezone=athlete_timezone,
    )
    try:
        plan_row = resolve_active_plan(
            store,
            athlete_id,
            current_training_day=training_day,
        ).plan
    except Exception:
        logger.exception(
            "[intake_injury_sync] active plan resolution failed athlete_id=%s",
            athlete_id,
        )
        return _list_flags(store, athlete_id, statuses=_ACTIVE_STATUSES)
    if not plan_row:
        return _list_flags(store, athlete_id, statuses=_ACTIVE_STATUSES)

    plan_id = str(plan_row.get("id") or "").strip()
    reader = getattr(store, "get_plan_for_athlete", None)
    if plan_id and callable(reader):
        try:
            full_plan = reader(plan_id, athlete_id)
            if full_plan:
                plan_row = full_plan
        except Exception:
            logger.exception(
                "[intake_injury_sync] full plan read failed athlete_id=%s plan_id=%s",
                athlete_id,
                plan_id,
            )

    return sync_intake_injuries_for_plan(
        store,
        athlete_id=athlete_id,
        plan_row=plan_row,
    )
