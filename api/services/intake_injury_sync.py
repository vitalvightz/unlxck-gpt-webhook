"""Synchronize active intake injuries into the live daily injury tracker.

Guided intake's ``cleared`` field answers "Have you been medically cleared?".
It does not mean the injury has healed. The explicit ``timeframe=old_cleared``
choice is the history-only signal.

Each generated-plan injury receives a stable ``source_key``. The store writes
it atomically (production: one database RPC), adopting a matching legacy row or
inserting a new one. This preserves old resolved states and prevents concurrent
duplicates.

A guided injury also carries a plan-independent ``intake_identity`` (body zone
plus injury type). When a new plan lists an injury whose identity matches an
open or monitoring intake injury from another plan, the store carries that row
onto the new plan instead of inserting a duplicate (see
supabase/migrations/20261008001000_intake_injury_identity_across_plans.sql).
The athlete's training-impact choice and notes are settings on the injury, so
changing them in camp setup updates the injury rather than creating another.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from api.contracts.training_day import resolve_training_day_str
from api.store import AppStore

from .active_plan import ActivePlanResolution, resolve_active_plan
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


def _normalized_token(value: object) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def _normalized_description(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _source_key(*, plan_id: str, candidate: Mapping[str, Any]) -> str:
    identity = (
        f"{_normalized_token(candidate.get('body_area'))}\n"
        f"{_normalized_description(candidate.get('description'))}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"intake:{plan_id}:{digest}"


def _guided_identity(injury: Mapping[str, Any], candidate: Mapping[str, Any]) -> str | None:
    """What the injury is, independent of plan, notes and training impact.

    The body zone (which carries the side, e.g. ``l_ankle``) and the injury type
    tell two injuries apart: an ankle sprain and an ankle blister differ in
    type. Without a type, nothing structured identifies the injury, so none is
    given and the store falls back to area + description.
    """
    injury_type = _normalized_token(injury.get("injury_type"))
    if not injury_type:
        return None
    place = _normalized_token(injury.get("zone")) or _normalized_token(candidate.get("body_area"))
    if not place:
        return None
    return f"guided:{place}:{injury_type}"


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
    candidate = _guided_intake_injury_candidate(bootstrap_injury, plan_id=plan_id)
    if candidate is not None:
        candidate["intake_identity"] = _guided_identity(injury, candidate)
    return candidate


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
    try:
        return True, [
            dict(flag)
            for flag in (store.list_injury_flags(athlete_id, statuses=statuses, limit=500) or [])
        ]
    except Exception:
        logger.exception(
            "[intake_injury_sync] injury flag read failed athlete_id=%s statuses=%s",
            athlete_id,
            statuses,
        )
        return False, []


def _atomic_adopt_or_create(
    store: AppStore,
    *,
    athlete_id: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Adopt a legacy row or insert once by ``(athlete_id, source_key)``.

    The store runs the whole read/adopt/dedupe/insert sequence atomically; in
    production that is one transaction-scoped database RPC.
    """
    source_key = str(candidate.get("source_key") or "").strip()
    plan_id = str(candidate.get("plan_id") or "").strip()
    if not source_key or not plan_id:
        return None

    try:
        return store.adopt_or_create_intake_injury_flag(
            {
                "athlete_id": athlete_id,
                "plan_id": plan_id,
                "source_key": source_key,
                "body_area": str(candidate.get("body_area") or ""),
                "description": str(candidate.get("description") or ""),
                "severity": str(candidate.get("severity") or "moderate"),
                "status": str(candidate.get("status") or "open"),
                "resolved_at": candidate.get("resolved_at"),
                "skin_integrity": candidate.get("skin_integrity"),
                "bleeding_status": candidate.get("bleeding_status"),
                "infection_signs": candidate.get("infection_signs") or [],
                "coverable": candidate.get("coverable"),
                "drainage": candidate.get("drainage"),
                "intake_identity": candidate.get("intake_identity"),
            }
        )
    except Exception:
        logger.exception(
            "[intake_injury_sync] atomic adopt/create failed "
            "athlete_id=%s source_key=%s",
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
    Legacy rows are atomically adopted before insertion, preserving resolved
    status. A resolved injury from another plan cannot suppress this plan because
    the stable identity includes ``plan_id``.
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

    dedupe_readable, _all_flags = _list_flags(
        store,
        athlete_id,
        statuses=_DEDUPE_STATUSES,
    )
    if not dedupe_readable:
        return open_flags

    for raw_candidate in _intake_injury_candidates(intake_payload, plan_id=plan_id):
        candidate = {
            **raw_candidate,
            "source_key": _source_key(plan_id=plan_id, candidate=raw_candidate),
        }
        _atomic_adopt_or_create(
            store,
            athlete_id=athlete_id,
            candidate=candidate,
        )

    # Adoption may preserve a resolved row or collapse formerly-open duplicates.
    # Return a fresh authoritative snapshot instead of the pre-write list.
    final_readable, final_flags = _list_flags(
        store,
        athlete_id,
        statuses=_ACTIVE_STATUSES,
    )
    return final_flags if final_readable else []


def sync_active_plan_intake_injuries(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
    active_plan: ActivePlanResolution | None = None,
) -> list[dict[str, Any]]:
    """Synchronize the server-resolved active plan before Today is assembled.

    ``active_plan`` is the caller's resolution for the same training day; the
    Today build passes the one it will use itself, so the plan is read once.
    """
    if active_plan is not None:
        plan_row = active_plan.plan
    else:
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

    # resolve_active_plan reads the pointed-to plan with get_plan_for_athlete,
    # so plan_row is already the full owner-scoped row.
    return sync_intake_injuries_for_plan(
        store,
        athlete_id=athlete_id,
        plan_row=plan_row,
    )
