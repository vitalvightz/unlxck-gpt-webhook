"""Synchronize active intake injuries into the live daily injury tracker.

Guided intake's ``cleared`` field answers "Have you been medically cleared?".
It does not mean the injury has healed. The explicit ``timeframe=old_cleared``
choice is the history-only signal.

Each generated-plan injury receives a stable ``source_key``. Production writes
use one database RPC that atomically adopts matching legacy rows or inserts a
new row. This preserves old resolved states and prevents concurrent duplicates.
"""

from __future__ import annotations

import hashlib
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


def _normalized_description(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _source_key(*, plan_id: str, candidate: Mapping[str, Any]) -> str:
    identity = (
        f"{_normalized_token(candidate.get('body_area'))}\n"
        f"{_normalized_description(candidate.get('description'))}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
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


def _is_legacy_match(
    flag: Mapping[str, Any],
    *,
    plan_id: str,
    candidate: Mapping[str, Any],
) -> bool:
    return (
        str(flag.get("source") or "").strip().lower() == "intake"
        and str(flag.get("plan_id") or "").strip() == plan_id
        and not str(flag.get("source_key") or "").strip()
        and _normalized_token(flag.get("body_area"))
        == _normalized_token(candidate.get("body_area"))
        and _normalized_description(flag.get("description"))
        == _normalized_description(candidate.get("description"))
    )


def _canonical_legacy_match(flags: list[dict[str, Any]]) -> dict[str, Any]:
    status_rank = {"resolved": 0, "monitoring": 1, "open": 2}
    return min(
        flags,
        key=lambda flag: (
            status_rank.get(str(flag.get("status") or "").strip().lower(), 3),
            str(flag.get("created_at") or ""),
            str(flag.get("id") or ""),
        ),
    )


def _rpc_result_row(data: object) -> dict[str, Any] | None:
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        return dict(data[0])
    return None


def _atomic_adopt_or_create(
    store: AppStore,
    *,
    athlete_id: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Adopt a legacy row or insert once by ``(athlete_id, source_key)``.

    Production delegates the whole read/adopt/dedupe/insert sequence to one
    transaction-scoped database RPC. In-memory stores use one process lock and
    re-read inside it, mirroring the same decision for regression tests.
    """
    source_key = str(candidate.get("source_key") or "").strip()
    plan_id = str(candidate.get("plan_id") or "").strip()
    if not source_key or not plan_id:
        return None

    client = getattr(store, "client", None)
    if client is not None:
        try:
            response = client.rpc(
                "adopt_or_create_intake_injury_flag",
                {
                    "p_athlete_id": athlete_id,
                    "p_plan_id": plan_id,
                    "p_source_key": source_key,
                    "p_body_area": str(candidate.get("body_area") or ""),
                    "p_description": str(candidate.get("description") or ""),
                    "p_severity": str(candidate.get("severity") or "moderate"),
                    "p_status": str(candidate.get("status") or "open"),
                    "p_resolved_at": candidate.get("resolved_at"),
                },
            ).execute()
            return _rpc_result_row(response.data)
        except Exception:
            logger.exception(
                "[intake_injury_sync] atomic adopt/create failed "
                "athlete_id=%s source_key=%s",
                athlete_id,
                source_key,
            )
            return None

    create_flag = getattr(store, "create_injury_flag", None)
    update_flag = getattr(store, "update_injury_flag", None)
    if not callable(create_flag):
        return None

    with _FALLBACK_LOCK:
        readable, flags = _list_flags(store, athlete_id, statuses=_DEDUPE_STATUSES)
        if not readable:
            return None

        existing = next(
            (
                flag
                for flag in flags
                if str(flag.get("source_key") or "").strip() == source_key
            ),
            None,
        )
        legacy_matches = [
            flag
            for flag in flags
            if _is_legacy_match(flag, plan_id=plan_id, candidate=candidate)
        ]

        if existing:
            # Clean up any leftover unkeyed duplicates without touching the
            # already-adopted row's status or resolved timestamp.
            if legacy_matches and callable(update_flag):
                now_iso = datetime.now(timezone.utc).isoformat()
                for duplicate in legacy_matches:
                    duplicate_id = str(duplicate.get("id") or "")
                    if not duplicate_id:
                        continue
                    update_flag(
                        duplicate_id,
                        {
                            "source_key": f"{source_key}:legacy-duplicate:{duplicate_id}",
                            "status": "resolved",
                            "resolved_at": duplicate.get("resolved_at") or now_iso,
                        },
                    )
            return existing

        if legacy_matches:
            # If we cannot update the legacy row, fail closed rather than create
            # a second injury beside it.
            if not callable(update_flag):
                return None
            canonical = _canonical_legacy_match(legacy_matches)
            canonical_id = str(canonical.get("id") or "")
            if not canonical_id:
                return None

            now_iso = datetime.now(timezone.utc).isoformat()
            for duplicate in legacy_matches:
                duplicate_id = str(duplicate.get("id") or "")
                if not duplicate_id or duplicate_id == canonical_id:
                    continue
                update_flag(
                    duplicate_id,
                    {
                        "source_key": f"{source_key}:legacy-duplicate:{duplicate_id}",
                        "status": "resolved",
                        "resolved_at": duplicate.get("resolved_at") or now_iso,
                    },
                )

            # Only attach identity to the canonical row. Its existing status and
            # resolved_at are deliberately left unchanged.
            return dict(update_flag(canonical_id, {"source_key": source_key}))

        try:
            return dict(create_flag(athlete_id, dict(candidate)))
        except Exception:
            logger.exception(
                "[intake_injury_sync] injury flag create failed "
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
