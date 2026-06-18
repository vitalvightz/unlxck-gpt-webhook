"""Block 4 Today/Overview orchestration: connect the pure contracts in
``api/contracts`` to persistence (``api/store.py``).

Everything here is server-authoritative:

* the **training day** is computed from the athlete's timezone (04:00 rollover),
  never supplied by the client;
* the **recommendation** is computed by ``evaluate_checkin`` and persisted on the
  check-in row — the client never calculates or supplies it;
* the **command view** and **landing** state are derived from persisted rows.

No saved plan is ever mutated here, and no readiness text is invented: reasons
come straight from the deterministic evaluator.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import HTTPException, status
from pydantic import ValidationError

from api.contracts.checkin_decision import CheckinInputs, evaluate_checkin
from api.contracts.command_view import CommandView, build_command_view, make_risk
from api.contracts.completion import (
    SessionCompletionRecord,
    completion_landing_state,
    completion_status_of,
)
from api.contracts.landing import LandingDecision, resolve_landing
from api.contracts.training_day import resolve_training_day_str
from api.store import AppStore
from api.services.active_plan import resolve_active_plan


def _plan_schedule_helpers():
    """Lazily borrow the dashboard's weekly-schedule helpers.

    Imported lazily (not at module top) to avoid a circular import: the route
    package's ``__init__`` imports the Today router, which imports this service.
    By the time these helpers are needed at call time, ``api.routes.daily`` is
    fully loaded. Reusing them keeps "today's session" a single derivation from
    the persisted plan rather than a second implementation.
    """
    from api.routes.daily import (
        _latest_visible_plan_row,
        _parse_iso_date,
        _resolve_current_week,
        _resolve_today_and_next,
    )

    return (
        _latest_visible_plan_row,
        _parse_iso_date,
        _resolve_current_week,
        _resolve_today_and_next,
    )

_CHECKIN_INPUT_FIELDS = (
    "sleep",
    "body",
    "pain",
    "phase",
    "active_injury",
    "previous_session",
    "sharp_pain",
    "instability",
    "swelling",
    "neurological_symptoms",
    "illness_symptoms",
    "cannot_warm_into_movement",
    "worse_next_day_pain",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_valid_plan_id(plan_id: str) -> None:
    """422 on a malformed plan_id so it never reaches the DB as a uuid syntax error."""
    try:
        uuid.UUID(plan_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="plan_id must be a valid UUID",
        ) from exc


def resolve_training_day(athlete_timezone: str | None, *, now: datetime | None = None) -> str:
    """Athlete-local training day (``YYYY-MM-DD``) — the canonical key."""
    return resolve_training_day_str(
        now or datetime.now(timezone.utc),
        athlete_timezone=athlete_timezone,
    )


def _checkin_inputs_from(payload: Mapping[str, Any]) -> CheckinInputs:
    return CheckinInputs(**{field: payload[field] for field in _CHECKIN_INPUT_FIELDS})


def submit_today_checkin(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist a Today check-in and its server-evaluated recommendation.

    ``payload`` carries ``plan_id`` plus the categorical inputs/safety flags.
    Any client-supplied recommendation field is ignored — the recommendation is
    always recomputed here. Returns the persisted row (recommendation included).
    """
    plan_id = str(payload.get("plan_id") or "").strip()
    if not plan_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="plan_id is required")
    _require_valid_plan_id(plan_id)

    # Writes are service-role (RLS does not gate them here), so the backend must
    # prove the plan belongs to the caller before persisting anything.
    if store.get_plan_for_athlete(plan_id, athlete_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

    training_day = resolve_training_day(athlete_timezone, now=now)
    decision = evaluate_checkin(_checkin_inputs_from(payload))

    fields: dict[str, Any] = {
        "plan_id": plan_id,
        "training_day": training_day,
        "athlete_timezone": athlete_timezone or "",
        # Server-computed recommendation — never trust a client-supplied value.
        "recommendation_state": decision.decision,
        "recommendation_reason": decision.reason,
        "recommendation_triggers": list(decision.triggers),
    }
    for field in _CHECKIN_INPUT_FIELDS:
        fields[field] = payload[field]

    return store.upsert_today_checkin(athlete_id, fields)


def _recommendation_mapping(checkin: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Adapt a persisted check-in row to the recommendation contract shape."""
    if not checkin:
        return None
    return {
        "training_day": checkin.get("training_day"),
        "decision": checkin.get("recommendation_state"),
        "reason": checkin.get("recommendation_reason"),
    }


def upsert_session_completion(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate (via the completion contract) and upsert a session completion.

    The server computes ``training_day`` and stamps ``started_at`` /
    ``completed_at`` from the status transition; the contract's field rules are
    enforced before anything is written.
    """
    plan_id = str(payload.get("plan_id") or "").strip()
    session_id = str(payload.get("session_id") or "").strip()
    if not plan_id or not session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="plan_id and session_id are required",
        )
    _require_valid_plan_id(plan_id)

    # Service-role write: enforce plan ownership at the backend (RLS won't here).
    if store.get_plan_for_athlete(plan_id, athlete_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

    training_day = resolve_training_day(athlete_timezone, now=now)
    now_iso = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    status_value = str(payload.get("status") or "not_started")

    existing = store.get_session_completion(athlete_id, session_id, training_day) or {}

    # Stamp timestamps from the transition. started/done/modified carry
    # started_at; done/modified carry completed_at. Both are preserved once set
    # (idempotent re-saves keep the original time) and cleared when the status
    # moves back to a state that should not have them.
    existing_started_at = existing.get("started_at")
    existing_completed_at = existing.get("completed_at")

    if status_value in {"started", "done", "modified"}:
        started_at = existing_started_at or now_iso
    else:
        started_at = None

    if status_value in {"done", "modified"}:
        completed_at = existing_completed_at or now_iso
    else:
        completed_at = None

    modification_reason = str(payload.get("modification_reason") or "")
    notes = str(payload.get("notes") or "")

    # Enforce the completion contract (started_at / completed_at / reason rules)
    # before writing — surface a 422 rather than persisting an invalid record.
    try:
        SessionCompletionRecord(
            user_id=athlete_id,
            plan_id=plan_id,
            session_id=session_id,
            training_day=training_day,
            status=status_value,  # type: ignore[arg-type]
            session_rpe=payload.get("session_rpe"),
            pain_after=payload.get("pain_after"),
            modification_reason=modification_reason,
            notes=notes,
            started_at=started_at,
            completed_at=completed_at,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid session completion: {exc.errors()[0]['msg']}",
        ) from exc

    fields = {
        "plan_id": plan_id,
        "session_id": session_id,
        "training_day": training_day,
        "status": status_value,
        "session_rpe": payload.get("session_rpe"),
        "pain_after": payload.get("pain_after"),
        "modification_reason": modification_reason,
        "notes": notes,
        "started_at": started_at,
        "completed_at": completed_at,
    }
    return store.upsert_session_completion(athlete_id, fields)


def _session_id_for_entry(entry: Any) -> str | None:
    """A stable session id for a derived weekly-schedule day entry.

    Prefers the calendar date; falls back to the weekday label. Returns ``None``
    when there is nothing to key on so completion lookup is simply skipped.
    """
    if entry is None:
        return None
    calendar_date = getattr(entry, "calendar_date", None)
    if calendar_date:
        return str(calendar_date)
    weekday = getattr(entry, "weekday", "")
    return str(weekday) or None


def _next_session_payload(entry: Any, session_id: str | None) -> dict[str, Any]:
    if entry is None:
        return {}
    data = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
    if session_id:
        data["session_id"] = session_id
    return data


def _risks_from_checkin(checkin: Mapping[str, Any] | None):
    """Minimal, prioritized risk-watch derived from the live check-in."""
    if not checkin:
        return []
    risks = []
    state = str(checkin.get("recommendation_state") or "")
    if state == "pull_back":
        risks.append(make_risk("stop_red_flag", text="Recommendation: pull back today."))
    if str(checkin.get("active_injury")) == "worse":
        risks.append(make_risk("active_injury_worse", text="Active injury reported as worse."))
    if str(checkin.get("pain")) == "high":
        risks.append(make_risk("high_pain", text="Pain reported as high."))
    if str(checkin.get("phase")) in {"TAPER"}:
        risks.append(make_risk("phase_taper", text="In taper — do not chase fatigue."))
    if str(checkin.get("sleep")) == "poor" or str(checkin.get("body")) == "flat":
        risks.append(make_risk("fatigue", text="Fatigue signals on today's check-in."))
    return risks


def _plan_with_resolved_phase(plan_row: Mapping[str, Any], week: Any) -> dict[str, Any]:
    """Use the current schedule week as the command-view phase authority."""
    plan = dict(plan_row)
    resolved_phase = str(getattr(week, "phase", "") or "").strip()
    if resolved_phase:
        plan["phase"] = resolved_phase
    return plan


def build_today_command_view(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    now: datetime | None = None,
) -> CommandView:
    """Assemble the normalized command view from persisted state.

    Degrades gracefully: no active plan → empty view with the Intake CTA; a
    missing/unparseable structured plan → empty ``next_session`` (no crash).
    """
    (
        _latest_visible_plan_row,
        _parse_iso_date,
        _resolve_current_week,
        _resolve_today_and_next,
    ) = _plan_schedule_helpers()

    training_day = resolve_training_day(athlete_timezone, now=now)
    plan_row = resolve_active_plan(store, athlete_id).plan

    if not plan_row:
        return build_command_view(current_training_day=training_day, plan=None)

    plan_id = str(plan_row.get("id") or "")
    # Fetch the check-in once and reuse it for both the recommendation and the
    # risk watch (avoids a redundant DB roundtrip).
    today_checkin = store.get_today_checkin(athlete_id, plan_id, training_day)
    recommendation = _recommendation_mapping(today_checkin)

    # Derive today's/next session from the persisted plan's weekly schedule.
    today_entry = next_entry = None
    week = None
    training_date = _parse_iso_date(training_day)
    if training_date is not None:
        try:
            _week_index, week = _resolve_current_week(plan_row, today=training_date)
            today_entry, next_entry = _resolve_today_and_next(week, today=training_date)
        except Exception:
            # Malformed plan data must never crash Overview.
            today_entry = next_entry = None

    target_entry = today_entry or next_entry
    session_id = _session_id_for_entry(target_entry)
    completion = (
        store.get_session_completion(athlete_id, session_id, training_day)
        if session_id
        else None
    )

    return build_command_view(
        current_training_day=training_day,
        plan=_plan_with_resolved_phase(plan_row, week),
        recommendation=recommendation,
        completion=completion,
        next_session=_next_session_payload(target_entry, session_id),
        risks=_risks_from_checkin(today_checkin),
    )


def resolve_today_landing(
    store: AppStore,
    *,
    athlete_id: str,
    athlete_timezone: str | None,
    has_interacted: bool,
    now: datetime | None = None,
) -> LandingDecision:
    """Resolve the landing decision from persisted state (see ``resolve_landing``)."""
    (
        _latest_visible_plan_row,
        _parse_iso_date,
        _resolve_current_week,
        _resolve_today_and_next,
    ) = _plan_schedule_helpers()

    training_day = resolve_training_day(athlete_timezone, now=now)
    plan_row = resolve_active_plan(store, athlete_id).plan
    has_active_plan = bool(plan_row)

    session_state = "none"
    checked_in_today = False
    if plan_row:
        plan_id = str(plan_row.get("id") or "")
        checkin = store.get_today_checkin(athlete_id, plan_id, training_day)
        checked_in_today = checkin is not None

        today_entry = next_entry = None
        training_date = _parse_iso_date(training_day)
        if training_date is not None:
            try:
                _week_index, week = _resolve_current_week(plan_row, today=training_date)
                today_entry, next_entry = _resolve_today_and_next(week, today=training_date)
            except Exception:
                today_entry = next_entry = None
        session_id = _session_id_for_entry(today_entry or next_entry)
        if session_id:
            completion = store.get_session_completion(athlete_id, session_id, training_day)
            session_state = completion_landing_state(completion_status_of(completion))

    return resolve_landing(
        has_active_plan=has_active_plan,
        has_interacted=has_interacted,
        session_state=session_state,
        checked_in_today=checked_in_today,
    )
