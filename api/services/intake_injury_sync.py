"""Synchronize active intake injuries into the live daily injury tracker.

Guided intake's ``cleared`` field answers "Have you been medically cleared?".
It does not mean the injury has healed. The explicit ``timeframe=old_cleared``
choice is the history-only signal.

Each generated-plan injury receives a stable ``source_key``. Production writes
use a database upsert protected by a unique constraint, so concurrent Today,
Plan, notification and XP reads cannot create duplicate rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Mapping

from api.contracts.training_day import resolve_training_day_str
from api.store import AppStore

from .active_plan import resolve_active_plan
from .today_service import (
    _guided_injury_has_content,
    _guided_intake_injury_candidate,
    _intake_payload_from_row,
    _intake_row_for_plan,
    _legacy_intake_injury_candidate,
)

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("open", "monitoring")
_DEDUPE_STATUSES = ("open", "monitoring", "resolved")
_HISTORICAL_CLEARED_TIMEFRAME = "old_cleared"
_FALLBACK_LOCK = threading.RLock()


def _normalized_token(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def _source_key(*, plan_id: str, candidate: Mapping[str, Any]) -> str:
    identity = {
        "body_area": _normalized_token(candidate.get("body_area")),
        "description": " ".join(str(candidate.get("description") or "").lower().split()),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    return f"intake:{plan_id}:{digest}"


def _guided_candidate(
    injury: Mapping[str, Any],
    *,
    plan_id: str,
) -> dict[str, object] | None:
    if _normalized_token(injury.get("timeframe")) == _HISTORICAL_CLEARED_TIMEFRAME:
        return None

    # Medical clearance permits training around an injury; it is not resolution.
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
) -> tuple[bool, list[dict[str, Any]]]:
    lister = getattr(store, "list_injury_flags", None)
    if not callable(lister):
        return False, []
    try:
        return True, [
            dict(flag)
            for flag in (lister(athlete_id, statuses=statuses, limit=500) or [])
        ]
    except Exception:
        logger.exception(
            "[intake_injury_sync] injury flag read failed athlete_id=%s statuses=%s",
            athlete_id,
            statuses,
        )
        return False, []


def _atomic_create_once(
    store: AppStore,
    *,
    athlete_id: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Insert once by ``(athlete_id, source_key)``.

    Supabase/PostgREST uses the database uniqueness constraint. In-memory and
    minimal test stores use one process lock plus a second read inside the lock.
    """
    payload = {"athlete_id": athlete_id, **dict(candidate)}
    client = getattr(store, "client", None)
    if client is not None:
        try:
            response = (
                client.table("injury_flags")
                .upsert(
                    payload,
                    on_conflict="athlete_id,source_key",
                    ignore_duplicates=True,
                )
                .execute()
            )
            rows = response.data or []
            if rows:
                return dict(rows[0])
            lookup = (
                client.table("injury_flags")
                .select("*")
                .eq("athlete_id", athlete_id)
                .eq("source_key", str(candidate.get("source_key") or ""))
                .limit(1)
                .execute()
            )
            return dict(lookup.data[0]) if lookup.data else None
        except Exception:
            logger.exception(
                "[intake_injury_sync] atomic upsert failed athlete_id=%s source_key=%s",
                athlete_id,
                candidate.get("source_key"),
            )
            return None

    create_flag = getattr(store, "create_injury_flag", None)
    if not callable(create_flag):
        return None
    with _FALLBACK_LOCK:
        readable, flags = _list_flags(store, athlete_id, statuses=_DEDUPE_STATUSES)
        if not readable:
            return None
        source_key = str(candidate.get("source_key") or "")
        existing = next(
            (flag for flag in flags if str(flag.get("source_key") or "") == source_key),
            None,
        )
        if existing:
            return existing
        try:
            return dict(create_flag(athlete_id, dict(candidate)))
        except Exception:
            logger.exception(
                "[intake_injury_sync] injury flag create failed athlete_id=%s source_key=%s",
                athlete_id,
                source_key,
            )
            return None


def sync_intake_injuries_for_plan(
    store: AppStore,
    *,
    athlete_id: str,
    plan_row: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Seed active-plan intake injuries and return current open/monitoring flags.

    No insert is attempted unless the existing flag set was read successfully.
    Resolved rows suppress recreation only through the same stable source key;
    an old plan's resolved ankle cannot block a new plan's ankle injury.
    """
    active_readable, open_flags = _list_flags(store, athlete_id, statuses=_ACTIVE_STATUSES)
    if not active_readable:
        return []

    plan_id = str(plan_row.get("id") or "").strip()
    if not plan_id:
        return open_flags

    try:
        intake_payload = _intake_payload_from_row(
            _intake_row_for_plan(store, athlete_id=athlete_id, plan_row=plan_row)
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

    dedupe_readable, all_flags = _list_flags(store, athlete_id, statuses=_DEDUPE_STATUSES)
    if not dedupe_readable:
        return open_flags
    existing_keys = {
        str(flag.get("source_key") or "")
        for flag in all_flags
        if str(flag.get("source_key") or "")
    }

    seeded = list(open_flags)
    for raw_candidate in _intake_injury_candidates(intake_payload, plan_id=plan_id):
        candidate = {
            **raw_candidate,
            "source_key": _source_key(plan_id=plan_id, candidate=raw_candidate),
        }
        source_key = str(candidate["source_key"])
        if source_key in existing_keys:
            continue
        created = _atomic_create_once(
            store,
            athlete_id=athlete_id,
            candidate=candidate,
        )
        if created is None:
            continue
        existing_keys.add(source_key)
        if str(created.get("status") or "") in _ACTIVE_STATUSES:
            seeded.insert(0, created)
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
        return []
    if not plan_row:
        readable, flags = _list_flags(store, athlete_id, statuses=_ACTIVE_STATUSES)
        return flags if readable else []

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
            return []

    return sync_intake_injuries_for_plan(
        store,
        athlete_id=athlete_id,
        plan_row=plan_row,
    )
