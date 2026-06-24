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
from datetime import date, datetime, timezone
from typing import Any, Mapping

from fastapi import HTTPException, status
from pydantic import ValidationError

from api.contracts.checkin_decision import CheckinInputs, evaluate_checkin
from api.contracts.command_view import CommandView, RiskWatchItem, build_command_view, make_risk
from api.contracts.completion import (
    TERMINAL_COMPLETION_STATUSES,
    SessionCompletionRecord,
    completion_landing_state,
    completion_status_of,
)
from api.contracts.injury_checkin import (
    DeclaredInjury,
    open_injury_flag_risks,
    reconcile_injury_checkin,
)
from api.contracts.injury_signal import derive_injury_signal
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
        _weekly_schedule_or_none,
    )

    return (
        _latest_visible_plan_row,
        _parse_iso_date,
        _resolve_current_week,
        _resolve_today_and_next,
        _weekly_schedule_or_none,
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

OTHER_PLAN_CHECKIN_WARNING = (
    "You already submitted a check-in for another plan today. "
    "This check-in is saved to the selected active plan only."
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


def _same_day_other_plan_warnings(
    store: AppStore,
    *,
    athlete_id: str,
    plan_id: str,
    training_day: str,
) -> list[str]:
    lister = getattr(store, "list_today_checkins_for_day", None)
    if not callable(lister):
        return []
    rows = lister(athlete_id, training_day) or []
    has_other_plan_checkin = any(str(row.get("plan_id") or "") != plan_id for row in rows)
    return [OTHER_PLAN_CHECKIN_WARNING] if has_other_plan_checkin else []


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
    warnings = _same_day_other_plan_warnings(
        store,
        athlete_id=athlete_id,
        plan_id=plan_id,
        training_day=training_day,
    )
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

    row = dict(store.upsert_today_checkin(athlete_id, fields))
    row["warnings"] = warnings
    return row


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


def submit_today_injury_checkin(
    store: AppStore,
    *,
    athlete_id: str,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reconcile a day's declared injuries against the athlete's open flags.

    Validates each declaration via the ``DeclaredInjury`` contract, then applies
    the deterministic create/update plan: new injuries open a flag, easing ones
    move to ``monitoring``, resolved ones close (stamping ``resolved_at``), and a
    reopened flag clears its ``resolved_at``. Foreign/stale ``flag_id``s can't be
    updated — only ids in the athlete's own open set are honoured. Returns the
    refreshed open-injury list.
    """
    raw_injuries = payload.get("injuries") or []
    try:
        declared = [DeclaredInjury(**dict(item)) for item in raw_injuries]
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid injury check-in: {exc.errors()[0]['msg']}",
        ) from exc

    open_flags = list(store.list_injury_flags(athlete_id, statuses=("open", "monitoring")) or [])
    open_flag_ids = [str(flag.get("id")) for flag in open_flags if flag.get("id")]
    plan = reconcile_injury_checkin(declared=declared, open_flag_ids=open_flag_ids)

    now_iso = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    active_plan_row = resolve_active_plan(store, athlete_id).plan
    plan_id = str(active_plan_row.get("id")) if active_plan_row else None

    for fields in plan.creates:
        store.create_injury_flag(athlete_id, {**fields, "plan_id": plan_id})

    for update in plan.updates:
        fields = dict(update.fields)
        # Stamp resolution time on close; clear it when a flag is reopened so a
        # later "it came back" report doesn't keep a stale resolved_at.
        fields["resolved_at"] = now_iso if fields.get("status") == "resolved" else None
        store.update_injury_flag(update.flag_id, fields)

    open_after = list(store.list_injury_flags(athlete_id, statuses=("open", "monitoring")) or [])
    return {"open_injuries": open_after}


def _session_id_for_entry(entry: Any) -> str | None:
    """A stable session id for a derived weekly-schedule day entry.

    Prefers an explicit session id, then the calendar date, then the weekday
    label. Returns ``None`` when there is nothing to key on so completion lookup
    is simply skipped.
    """
    if entry is None:
        return None
    if isinstance(entry, Mapping):
        explicit_session_id = entry.get("session_id")
        calendar_date = entry.get("calendar_date")
        weekday = entry.get("weekday", "")
    else:
        explicit_session_id = getattr(entry, "session_id", None)
        calendar_date = getattr(entry, "calendar_date", None)
        weekday = getattr(entry, "weekday", "")
    if explicit_session_id:
        return str(explicit_session_id)
    if calendar_date:
        return str(calendar_date)
    return str(weekday) or None


def _has_scheduled_day_content(entry: Any) -> bool:
    if entry is None:
        return False
    if isinstance(entry, Mapping):
        status = entry.get("status")
        coach_note = entry.get("coach_note")
        effective_load = entry.get("effective_load")
    else:
        status = getattr(entry, "status", None)
        coach_note = getattr(entry, "coach_note", None)
        effective_load = getattr(entry, "effective_load", None)
    if isinstance(effective_load, str):
        effective_load = effective_load.strip().lower()
    if effective_load in {"none", "off", "rest"}:
        return False
    return bool(effective_load not in (None, "") or status or coach_note)


def _entry_has_training(entry: Any) -> bool:
    return _has_scheduled_day_content(entry)


def _iter_mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_structured_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(_clean_text(value)[:10])
    except ValueError:
        return None


def _structured_effective_load(day_type: Any) -> str:
    normalized = _clean_text(day_type).lower()
    if normalized in {"hard", "high"}:
        return "hard"
    if normalized in {"reduced", "low", "recovery"}:
        return "reduced"
    if normalized in {"rest", "off", "none"}:
        return "none"
    return "technical"


def _structured_plan_weeks(plan_row: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    structured_plan = plan_row.get("structured_plan")
    if not isinstance(structured_plan, Mapping):
        return []
    return _iter_mapping_items(structured_plan.get("weeks"))


def _normalized_structured_phase(value: Any) -> str:
    phase = _clean_text(value).upper().replace(" ", "_")
    if phase in {"GPP", "SPP", "TAPER", "REINTEGRATION"}:
        return phase
    for candidate in ("REINTEGRATION", "TAPER", "SPP", "GPP"):
        if candidate in phase:
            return candidate
    return ""


def _structured_phase_for_day(plan_row: Mapping[str, Any], training_day: str) -> str:
    for week in _structured_plan_weeks(plan_row):
        if not isinstance(week, Mapping):
            continue
        for day in _iter_mapping_items(week.get("days")):
            if not isinstance(day, Mapping):
                continue
            day_date = _clean_text(day.get("date"))[:10]
            if day_date == training_day:
                return _normalized_structured_phase(day.get("phase_label")) or _normalized_structured_phase(
                    week.get("phase_label")
                )
    return ""


def _structured_session_entry_for_day(
    day: Mapping[str, Any],
    *,
    week: Mapping[str, Any],
) -> dict[str, Any] | None:
    day_date = _clean_text(day.get("date"))[:10]
    if not day_date:
        return None
    sessions = _iter_mapping_items(day.get("sessions"))
    if not sessions:
        return None

    first_session = sessions[0]
    if not isinstance(first_session, Mapping):
        return None
    session = dict(first_session)
    today_card = day.get("today_card") if isinstance(day.get("today_card"), Mapping) else {}
    title = (
        _clean_text(session.get("title"))
        or _clean_text(today_card.get("headline"))
        or _clean_text(session.get("session_type"))
        or "Today's session"
    )
    objective = _clean_text(session.get("objective")) or _clean_text(today_card.get("headline"))
    session_id = _clean_text(session.get("session_id")) or day_date
    weekday = ""
    try:
        weekday = datetime.strptime(day_date, "%Y-%m-%d").strftime("%A")
    except ValueError:
        weekday = ""

    return {
        **session,
        "calendar_date": day_date,
        "weekday": weekday,
        "weekday_with_label": _clean_text(day.get("countdown_label")) or weekday,
        "day_label": _clean_text(day.get("countdown_label")),
        "title": title,
        "status": _clean_text(session.get("session_type")) or "scheduled_session",
        "coach_note": objective,
        "effective_load": _structured_effective_load(day.get("day_type")),
        "phase": _normalized_structured_phase(day.get("phase_label"))
        or _normalized_structured_phase(week.get("phase_label")),
        "session_id": session_id,
    }


def _structured_today_session_entry(plan_row: Mapping[str, Any], training_day: str) -> dict[str, Any] | None:
    for week in _structured_plan_weeks(plan_row):
        for day in _iter_mapping_items(week.get("days")):
            if _clean_text(day.get("date"))[:10] != training_day:
                continue
            return _structured_session_entry_for_day(day, week=week)
    return None


def _structured_next_session_entry(plan_row: Mapping[str, Any], training_day: str) -> dict[str, Any] | None:
    training_date = _parse_structured_date(training_day)
    if training_date is None:
        return None
    candidates: list[tuple[date, dict[str, Any]]] = []
    for week in _structured_plan_weeks(plan_row):
        for day in _iter_mapping_items(week.get("days")):
            day_date = _clean_text(day.get("date"))[:10]
            parsed_day_date = _parse_structured_date(day_date)
            if parsed_day_date is None or parsed_day_date <= training_date:
                continue
            entry = _structured_session_entry_for_day(day, week=week)
            if entry and _has_scheduled_day_content(entry):
                candidates.append((parsed_day_date, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _entry_calendar_date(entry: Any) -> date | None:
    if entry is None:
        return None
    calendar_date = (
        entry.get("calendar_date")
        if isinstance(entry, Mapping)
        else getattr(entry, "calendar_date", None)
    )
    return _parse_structured_date(calendar_date)


def _prefer_earlier_structured_next_entry(target_entry: Any, structured_next_entry: dict[str, Any] | None) -> Any:
    if structured_next_entry is None:
        return target_entry
    if target_entry is None:
        return structured_next_entry
    target_date = _entry_calendar_date(target_entry)
    structured_date = _entry_calendar_date(structured_next_entry)
    if structured_date is None:
        return target_entry
    if target_date is None or structured_date <= target_date:
        return structured_next_entry
    return target_entry


def _scan_forward_for_next_training(
    plan_row: Mapping[str, Any],
    *,
    week: Any,
    week_index: int,
    training_date: Any,
    weekly_schedule_or_none,
    parse_iso_date,
) -> Any:
    """Find the next training day in a later schedule week.

    The within-week resolver (``_resolve_today_and_next``) only looks at the
    remaining days of the *current* week. Taper and late-camp weeks frequently
    carry just one or two training days, so on every non-training day the rest of
    the week is empty and the genuine next session sits in a future week. Without
    crossing the week boundary the Overview "Next session" card reports
    "No session found" even though training is still scheduled. This scan walks
    subsequent weeks (in order) and returns the first day that carries training,
    so the card always reflects the next real session while one exists.
    """
    if week is None:
        return None
    week_count = int(getattr(week, "week_count", 0) or 0)
    for index in range(week_index + 1, week_count):
        later_week = weekly_schedule_or_none(plan_row, week_index=index)
        if later_week is None:
            continue
        dated_candidates = []
        undated_candidates = []
        for entry in getattr(later_week, "days", []) or []:
            if not _entry_has_training(entry):
                continue
            calendar_date = (
                entry.get("calendar_date")
                if isinstance(entry, Mapping)
                else getattr(entry, "calendar_date", None)
            )
            entry_date = parse_iso_date(calendar_date) if calendar_date else None
            # Dated plans: never surface a session on/before today. Undated plans
            # (weekday-only fallback) can't be compared, so any later-week
            # training day is the next session.
            if entry_date is not None and training_date is not None and entry_date <= training_date:
                continue
            if entry_date is not None:
                dated_candidates.append((entry_date, entry))
            else:
                undated_candidates.append(entry)
        if dated_candidates:
            dated_candidates.sort(key=lambda item: item[0])
            return dated_candidates[0][1]
        if undated_candidates:
            return undated_candidates[0]
    return None


def _next_session_payload(entry: Any, session_id: str | None, *, relation: str | None = None) -> dict[str, Any]:
    if entry is None:
        return {}
    data = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
    if session_id:
        data["session_id"] = session_id
    if relation:
        data["session_relation"] = relation
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


def _history_injury_risks(
    store: AppStore,
    *,
    athlete_id: str,
    training_day: str,
) -> list[RiskWatchItem]:
    """Derive an injury-risk item from logged pain/symptom history.

    Defensive about the store surface: the history readers are optional on
    minimal test doubles, and a transient read failure must never crash Overview
    — in either case the derived signal is simply skipped.
    """
    list_completions = getattr(store, "list_session_completions", None)
    list_checkins = getattr(store, "list_today_checkins", None)
    if not callable(list_completions) or not callable(list_checkins):
        return []
    try:
        completions = list_completions(athlete_id) or []
        checkins = list_checkins(athlete_id) or []
    except Exception:
        return []
    return derive_injury_signal(
        completions=completions,
        checkins=checkins,
        current_training_day=training_day,
    )


def _open_injury_flags(store: AppStore, athlete_id: str) -> list[dict[str, Any]]:
    """Open/monitoring injury flags for this athlete, defensively.

    Optional on minimal test doubles and resilient to a read failure — Overview
    must never crash because the injury list could not be loaded.
    """
    lister = getattr(store, "list_injury_flags", None)
    if not callable(lister):
        return []
    try:
        return [dict(flag) for flag in (lister(athlete_id, statuses=("open", "monitoring")) or [])]
    except Exception:
        return []


def _merge_risks(*risk_lists: list[RiskWatchItem]) -> list[RiskWatchItem]:
    """Concatenate risk lists, keeping the first item seen per category.

    Same-day check-in risks are passed first, so they win over a derived signal
    in the same category (the fresh self-report beats the logged-history echo).
    """
    seen: set[str] = set()
    merged: list[RiskWatchItem] = []
    for risk_list in risk_lists:
        for risk in risk_list:
            if risk.category in seen:
                continue
            seen.add(risk.category)
            merged.append(risk)
    return merged


def _plan_with_resolved_phase(
    plan_row: Mapping[str, Any],
    week: Any,
    *,
    structured_phase: str = "",
) -> dict[str, Any]:
    """Use the current schedule week as the command-view phase authority."""
    plan = dict(plan_row)
    resolved_phase = structured_phase or str(getattr(week, "phase", "") or "").strip()
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
        _weekly_schedule_or_none,
    ) = _plan_schedule_helpers()

    training_day = resolve_training_day(athlete_timezone, now=now)
    plan_row = resolve_active_plan(store, athlete_id).plan

    if not plan_row:
        return build_command_view(current_training_day=training_day, plan=None)

    plan_id = str(plan_row.get("id") or "")
    plan_reader = getattr(store, "get_plan_for_athlete", None)
    if plan_id and callable(plan_reader):
        full_plan_row = plan_reader(plan_id, athlete_id)
        if full_plan_row:
            plan_row = full_plan_row

    # Fetch the check-in once and reuse it for both the recommendation and the
    # risk watch (avoids a redundant DB roundtrip).
    today_checkin = store.get_today_checkin(athlete_id, plan_id, training_day)
    recommendation = _recommendation_mapping(today_checkin)
    warnings = _same_day_other_plan_warnings(
        store,
        athlete_id=athlete_id,
        plan_id=plan_id,
        training_day=training_day,
    )

    # Derive today's/next session from the persisted plan's weekly schedule.
    today_entry = next_entry = None
    week = None
    week_index = 0
    training_date = _parse_iso_date(training_day)
    if training_date is not None:
        try:
            week_index, week = _resolve_current_week(plan_row, today=training_date)
            today_entry, next_entry = _resolve_today_and_next(week, today=training_date)
        except Exception:
            # Malformed plan data must never crash Overview.
            today_entry = next_entry = None
            week = None

    structured_today_entry = _structured_today_session_entry(plan_row, training_day)
    today_session_entry = structured_today_entry or today_entry
    has_today_session = _has_scheduled_day_content(today_session_entry)
    today_session_id = _session_id_for_entry(today_session_entry) if has_today_session else None
    today_completion = (
        store.get_session_completion(athlete_id, today_session_id, training_day)
        if today_session_id
        else None
    )
    today_is_complete = completion_status_of(today_completion) in TERMINAL_COMPLETION_STATUSES
    target_entry = today_session_entry if has_today_session and not today_is_complete else next_entry
    if target_entry is None and week is not None:
        # No training left in the current week — look ahead so the "Next session"
        # card surfaces the upcoming session instead of "No session found".
        try:
            target_entry = _scan_forward_for_next_training(
                plan_row,
                week=week,
                week_index=week_index,
                training_date=training_date,
                weekly_schedule_or_none=_weekly_schedule_or_none,
                parse_iso_date=_parse_iso_date,
            )
        except Exception:
            target_entry = None
    if target_entry is not today_session_entry or today_session_entry is None:
        target_entry = _prefer_earlier_structured_next_entry(
            target_entry,
            _structured_next_session_entry(plan_row, training_day),
        )
    session_relation = (
        "today"
        if target_entry is not None and target_entry is today_session_entry
        else ("next" if target_entry is not None else None)
    )
    session_id = _session_id_for_entry(target_entry)

    open_injuries = _open_injury_flags(store, athlete_id)

    return build_command_view(
        current_training_day=training_day,
        plan=_plan_with_resolved_phase(
            plan_row,
            week,
            structured_phase=_structured_phase_for_day(plan_row, training_day),
        ),
        recommendation=recommendation,
        completion=today_completion,
        next_session=_next_session_payload(target_entry, session_id, relation=session_relation),
        session_scope=session_relation or "none",
        warnings=warnings,
        # Risk precedence per category, freshest signal first: today's check-in,
        # then tracked open injuries, then the derived post-session pain history.
        # Together they keep the badge live whether the athlete reported today,
        # is carrying an open injury, or just logged painful sessions.
        risks=_merge_risks(
            _risks_from_checkin(today_checkin),
            open_injury_flag_risks(open_injuries),
            _history_injury_risks(
                store,
                athlete_id=athlete_id,
                training_day=training_day,
            ),
        ),
        open_injuries=open_injuries,
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
        _weekly_schedule_or_none,
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
