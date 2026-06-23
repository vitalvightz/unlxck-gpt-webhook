"""Live athlete daily flow: dashboard state, check-ins, session logs, injury
flags, and the admin review queue.

Weeks and sessions are derived from the persisted plan (the same weekly
schedule mapper the plan viewer uses); this module layers the athlete's logged
reality on top and records every rule decision as an ``adaptation_notes`` row.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.models import (
    AdaptationNoteRecord,
    AdminAthleteDailyStatus,
    AdminReviewRecord,
    AdminReviewResolveRequest,
    AthleteDashboardState,
    DailyCheckinRecord,
    DailyCheckinRequest,
    DailyCheckinResponse,
    DashboardCompletionStats,
    InjuryFlagCreateRequest,
    InjuryFlagRecord,
    InjuryFlagUpdateRequest,
    ProfileRecord,
    SessionLogRecord,
    SessionLogRequest,
    SessionLogResponse,
    WeeklyDayEntry,
    WeeklySchedule,
)
from api.plan_mappers import _map_plan_summary, _map_weekly_schedule, _visible_plans_for_athlete
from api.readiness import (
    AdaptationDecision,
    compute_readiness_summary,
    evaluate_checkin_adaptations,
    evaluate_session_log_adaptations,
)
from api.store import AppStore

RECENT_SESSION_LOG_WINDOW = 20
COMPLETION_WINDOW_DAYS = 7


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _parse_iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip()[:10])
    except (ValueError, AttributeError):
        return None


def _map_checkin(row: dict[str, Any]) -> DailyCheckinRecord:
    return DailyCheckinRecord(
        id=str(row["id"]),
        athlete_id=str(row["athlete_id"]),
        checkin_date=str(row.get("checkin_date") or ""),
        readiness=int(row.get("readiness") or 3),
        fatigue=int(row.get("fatigue") or 3),
        soreness=int(row.get("soreness") or 3),
        sleep_quality=int(row.get("sleep_quality") or 3),
        sleep_hours=float(row["sleep_hours"]) if row.get("sleep_hours") is not None else None,
        injury_note=str(row.get("injury_note") or ""),
        notes=str(row.get("notes") or ""),
        readiness_state=str(row.get("readiness_state") or "ready"),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _map_session_log(row: dict[str, Any]) -> SessionLogRecord:
    return SessionLogRecord(
        id=str(row["id"]),
        athlete_id=str(row["athlete_id"]),
        plan_id=str(row["plan_id"]) if row.get("plan_id") else None,
        session_date=str(row.get("session_date") or ""),
        session_type=str(row.get("session_type") or "training"),
        completed=bool(row.get("completed", True)),
        rpe=int(row["rpe"]) if row.get("rpe") is not None else None,
        duration_minutes=int(row["duration_minutes"]) if row.get("duration_minutes") is not None else None,
        notes=str(row.get("notes") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _map_injury_flag(row: dict[str, Any]) -> InjuryFlagRecord:
    return InjuryFlagRecord(
        id=str(row["id"]),
        athlete_id=str(row["athlete_id"]),
        plan_id=str(row["plan_id"]) if row.get("plan_id") else None,
        source=str(row.get("source") or "checkin"),
        body_area=str(row.get("body_area") or ""),
        description=str(row.get("description") or ""),
        severity=str(row.get("severity") or "moderate"),
        status=str(row.get("status") or "open"),
        resolved_at=str(row["resolved_at"]) if row.get("resolved_at") else None,
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _map_adaptation_note(row: dict[str, Any]) -> AdaptationNoteRecord:
    return AdaptationNoteRecord(
        id=str(row["id"]),
        athlete_id=str(row["athlete_id"]),
        plan_id=str(row["plan_id"]) if row.get("plan_id") else None,
        checkin_id=str(row["checkin_id"]) if row.get("checkin_id") else None,
        session_log_id=str(row["session_log_id"]) if row.get("session_log_id") else None,
        rule_code=str(row.get("rule_code") or ""),
        decision=str(row.get("decision") or "keep_plan"),
        summary=str(row.get("summary") or ""),
        details=row.get("details") if isinstance(row.get("details"), dict) else {},
        created_at=str(row.get("created_at") or ""),
    )


def _map_admin_review(row: dict[str, Any], *, athlete_email: str = "", athlete_name: str = "") -> AdminReviewRecord:
    return AdminReviewRecord(
        id=str(row["id"]),
        athlete_id=str(row["athlete_id"]),
        athlete_email=athlete_email,
        athlete_name=athlete_name,
        adaptation_note_id=str(row["adaptation_note_id"]) if row.get("adaptation_note_id") else None,
        injury_flag_id=str(row["injury_flag_id"]) if row.get("injury_flag_id") else None,
        reason=str(row.get("reason") or ""),
        status=str(row.get("status") or "pending"),
        resolution_notes=str(row.get("resolution_notes") or ""),
        resolved_by=str(row.get("resolved_by") or ""),
        resolved_at=str(row["resolved_at"]) if row.get("resolved_at") else None,
        created_at=str(row.get("created_at") or ""),
    )


def _latest_visible_plan_row(store: AppStore, athlete_id: str) -> dict[str, Any] | None:
    return next(iter(_visible_plans_for_athlete(store.list_user_plans(athlete_id))), None)


def _weekly_schedule_or_none(plan_row: dict[str, Any], *, week_index: int) -> WeeklySchedule | None:
    try:
        return _map_weekly_schedule(plan_row, week_index=week_index)
    except HTTPException:
        return None


def _resolve_current_week(plan_row: dict[str, Any], *, today: date) -> tuple[int | None, WeeklySchedule | None]:
    """Find the schedule week containing today.

    Prefers calendar dates (set when a fight date exists); falls back to weeks
    elapsed since the plan was created for open-ended camps.
    """
    first_week = _weekly_schedule_or_none(plan_row, week_index=0)
    if first_week is None:
        return None, None
    week_count = max(1, first_week.week_count)

    candidate = first_week
    for index in range(week_count):
        week = candidate if index == 0 else _weekly_schedule_or_none(plan_row, week_index=index)
        if week is None:
            break
        dated = [d for d in week.days if d.calendar_date]
        if dated:
            dates = [_parse_iso_date(d.calendar_date) for d in dated]
            dates = [d for d in dates if d is not None]
            if dates and min(dates) <= today <= max(dates):
                return index, week
        else:
            # No calendar dates anywhere — fall back to elapsed weeks.
            created = _parse_iso_date(plan_row.get("created_at"))
            elapsed_weeks = ((today - created).days // 7) if created else 0
            fallback_index = min(max(0, elapsed_weeks), week_count - 1)
            fallback_week = (
                week if fallback_index == index else _weekly_schedule_or_none(plan_row, week_index=fallback_index)
            )
            return (fallback_index, fallback_week) if fallback_week else (index, week)
    # Dated plan but today is outside every week (camp over or not started):
    # clamp to the nearest end.
    last_week = _weekly_schedule_or_none(plan_row, week_index=week_count - 1)
    if last_week is not None:
        last_dates = [_parse_iso_date(d.calendar_date) for d in last_week.days if d.calendar_date]
        last_dates = [d for d in last_dates if d is not None]
        if last_dates and today > max(last_dates):
            return week_count - 1, last_week
    return 0, first_week


_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _has_scheduled_day_content(entry: WeeklyDayEntry) -> bool:
    return str(entry.effective_load or "").strip().lower() not in {"", "none", "off", "rest"}


def _resolve_today_and_next(week: WeeklySchedule | None, *, today: date) -> tuple[WeeklyDayEntry | None, WeeklyDayEntry | None]:
    if week is None or not week.days:
        return None, None
    today_entry: WeeklyDayEntry | None = None
    today_index: int | None = None
    for index, entry in enumerate(week.days):
        entry_date = _parse_iso_date(entry.calendar_date) if entry.calendar_date else None
        if entry_date == today or (entry_date is None and entry.weekday == _WEEKDAY_NAMES[today.weekday()]):
            today_entry = entry
            today_index = index
            break
    next_entry: WeeklyDayEntry | None = None
    future_dated_entries: list[tuple[date, WeeklyDayEntry]] = []
    for entry in week.days:
        if not _has_scheduled_day_content(entry):
            continue
        entry_date = _parse_iso_date(entry.calendar_date) if entry.calendar_date else None
        if entry_date is not None and entry_date > today:
            future_dated_entries.append((entry_date, entry))
    if future_dated_entries:
        future_dated_entries.sort(key=lambda item: item[0])
        return today_entry, future_dated_entries[0][1]

    if today_index is not None:
        for entry in week.days[today_index + 1:]:
            if _has_scheduled_day_content(entry):
                next_entry = entry
                break
    return today_entry, next_entry


def _completion_stats(
    *, checkins: list[dict[str, Any]], session_logs: list[dict[str, Any]], today: date
) -> DashboardCompletionStats:
    cutoff = today - timedelta(days=COMPLETION_WINDOW_DAYS - 1)

    def _in_window(value: Any) -> bool:
        parsed = _parse_iso_date(value)
        return parsed is not None and cutoff <= parsed <= today

    window_logs = [log for log in session_logs if _in_window(log.get("session_date"))]
    return DashboardCompletionStats(
        logged_sessions_7d=len(window_logs),
        completed_sessions_7d=sum(1 for log in window_logs if log.get("completed", True)),
        missed_sessions_7d=sum(1 for log in window_logs if log.get("completed") is False),
        checkins_7d=sum(1 for c in checkins if _in_window(c.get("checkin_date"))),
    )


def _persist_decisions(
    store: AppStore,
    *,
    athlete_id: str,
    decisions: list[AdaptationDecision],
    plan_id: str | None = None,
    checkin_id: str | None = None,
    session_log_id: str | None = None,
    injury_flag_id: str | None = None,
) -> tuple[list[AdaptationNoteRecord], bool]:
    """Record every decision as an adaptation note; open one admin review when
    any decision requires it (deduped against an already-pending review)."""
    notes: list[AdaptationNoteRecord] = []
    review_reasons: list[str] = []
    first_review_note_id: str | None = None
    for decision in decisions:
        row = store.create_adaptation_note(
            athlete_id,
            {
                "plan_id": plan_id,
                "checkin_id": checkin_id,
                "session_log_id": session_log_id,
                "rule_code": decision.rule_code,
                "decision": decision.decision,
                "summary": decision.summary,
                "details": decision.details,
            },
        )
        notes.append(_map_adaptation_note(row))
        if decision.requires_admin_review:
            review_reasons.append(decision.summary)
            if first_review_note_id is None:
                first_review_note_id = str(row["id"])

    review_created = False
    if review_reasons and store.count_pending_admin_reviews_for_athlete(athlete_id) == 0:
        store.create_admin_review(
            athlete_id,
            {
                "adaptation_note_id": first_review_note_id,
                "injury_flag_id": injury_flag_id,
                "reason": "; ".join(review_reasons),
                "status": "pending",
            },
        )
        review_created = True
    return notes, review_created


def build_daily_router(*, require_profile, require_admin, get_store) -> APIRouter:
    router = APIRouter()

    # ------------------------------------------------------------------
    # Athlete endpoints
    # ------------------------------------------------------------------

    @router.get("/api/dashboard", response_model=AthleteDashboardState)
    def get_dashboard(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> AthleteDashboardState:
        today = _today_utc()
        plan_row = _latest_visible_plan_row(store, profile.athlete_id)
        week_index: int | None = None
        week: WeeklySchedule | None = None
        if plan_row is not None:
            week_index, week = _resolve_current_week(plan_row, today=today)
        today_entry, next_entry = _resolve_today_and_next(week, today=today)

        checkins = store.list_daily_checkins(profile.athlete_id, limit=14)
        session_logs = store.list_session_logs(profile.athlete_id, limit=RECENT_SESSION_LOG_WINDOW)
        open_flags = store.list_injury_flags(profile.athlete_id, statuses=("open", "monitoring"))
        latest_checkin = checkins[0] if checkins else None

        readiness = compute_readiness_summary(
            latest_checkin=latest_checkin,
            open_injury_flag_count=sum(1 for f in open_flags if f.get("status") == "open"),
            recent_session_logs=session_logs,
        )
        return AthleteDashboardState(
            plan=_map_plan_summary(plan_row) if plan_row else None,
            current_week_index=week_index,
            current_week=week,
            today=today_entry,
            next_session=next_entry,
            readiness=readiness,
            latest_checkin=_map_checkin(latest_checkin) if latest_checkin else None,
            checked_in_today=bool(latest_checkin and str(latest_checkin.get("checkin_date")) == today.isoformat()),
            open_injury_flags=[_map_injury_flag(row) for row in open_flags],
            recent_adaptation_notes=[
                _map_adaptation_note(row) for row in store.list_adaptation_notes(profile.athlete_id, limit=5)
            ],
            completion=_completion_stats(checkins=checkins, session_logs=session_logs, today=today),
        )

    @router.post("/api/checkins", response_model=DailyCheckinResponse, status_code=status.HTTP_201_CREATED)
    def submit_checkin(
        request_body: DailyCheckinRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> DailyCheckinResponse:
        checkin_date = request_body.checkin_date or _today_utc().isoformat()
        plan_row = _latest_visible_plan_row(store, profile.athlete_id)
        plan_id = str(plan_row["id"]) if plan_row else None

        open_flags = store.list_injury_flags(profile.athlete_id, statuses=("open",))
        fields = {
            "checkin_date": checkin_date,
            "readiness": request_body.readiness,
            "fatigue": request_body.fatigue,
            "soreness": request_body.soreness,
            "sleep_quality": request_body.sleep_quality,
            "sleep_hours": request_body.sleep_hours,
            "injury_note": request_body.injury_note,
            "notes": request_body.notes,
        }

        injury_flag_row: dict[str, Any] | None = None
        if request_body.injury_note:
            duplicate = any(
                str(flag.get("description") or "").strip() == request_body.injury_note for flag in open_flags
            )
            if not duplicate:
                injury_flag_row = store.create_injury_flag(
                    profile.athlete_id,
                    {
                        "plan_id": plan_id,
                        "source": "checkin",
                        "description": request_body.injury_note,
                        "severity": "moderate",
                        "status": "open",
                    },
                )
                open_flags = [injury_flag_row, *open_flags]

        readiness = compute_readiness_summary(
            latest_checkin=fields,
            open_injury_flag_count=len(open_flags),
            recent_session_logs=store.list_session_logs(profile.athlete_id, limit=RECENT_SESSION_LOG_WINDOW),
        )
        fields["readiness_state"] = readiness.state
        checkin_row = store.upsert_daily_checkin(profile.athlete_id, fields)

        decisions = evaluate_checkin_adaptations(
            checkin=fields,
            open_injury_flag_count=len(open_flags),
        )
        notes, review_created = _persist_decisions(
            store,
            athlete_id=profile.athlete_id,
            decisions=decisions,
            plan_id=plan_id,
            checkin_id=str(checkin_row["id"]),
            injury_flag_id=str(injury_flag_row["id"]) if injury_flag_row else None,
        )
        return DailyCheckinResponse(
            checkin=_map_checkin(checkin_row),
            readiness=readiness,
            adaptation_notes=notes,
            injury_flag=_map_injury_flag(injury_flag_row) if injury_flag_row else None,
            admin_review_created=review_created,
        )

    @router.get("/api/checkins", response_model=list[DailyCheckinRecord])
    def list_checkins(
        limit: int = Query(14, ge=1, le=90),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[DailyCheckinRecord]:
        return [_map_checkin(row) for row in store.list_daily_checkins(profile.athlete_id, limit=limit)]

    @router.post("/api/session-logs", response_model=SessionLogResponse, status_code=status.HTTP_201_CREATED)
    def submit_session_log(
        request_body: SessionLogRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> SessionLogResponse:
        plan_id: str | None = None
        if request_body.plan_id:
            try:
                uuid.UUID(request_body.plan_id)
            except (ValueError, AttributeError):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            plan_row = store.get_plan_for_athlete(request_body.plan_id, profile.athlete_id)
            if not plan_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            plan_id = request_body.plan_id
        else:
            latest = _latest_visible_plan_row(store, profile.athlete_id)
            plan_id = str(latest["id"]) if latest else None

        log_row = store.create_session_log(
            profile.athlete_id,
            {
                "plan_id": plan_id,
                "session_date": request_body.session_date or _today_utc().isoformat(),
                "session_type": request_body.session_type,
                "completed": request_body.completed,
                "rpe": request_body.rpe,
                "duration_minutes": request_body.duration_minutes,
                "notes": request_body.notes,
            },
        )
        recent_logs = store.list_session_logs(profile.athlete_id, limit=RECENT_SESSION_LOG_WINDOW)
        decisions = evaluate_session_log_adaptations(log=log_row, recent_session_logs=recent_logs)
        notes, review_created = _persist_decisions(
            store,
            athlete_id=profile.athlete_id,
            decisions=decisions,
            plan_id=plan_id,
            session_log_id=str(log_row["id"]),
        )
        return SessionLogResponse(
            log=_map_session_log(log_row),
            adaptation_notes=notes,
            admin_review_created=review_created,
        )

    @router.get("/api/session-logs", response_model=list[SessionLogRecord])
    def list_session_logs(
        limit: int = Query(20, ge=1, le=90),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[SessionLogRecord]:
        return [_map_session_log(row) for row in store.list_session_logs(profile.athlete_id, limit=limit)]

    @router.post("/api/injury-flags", response_model=InjuryFlagRecord, status_code=status.HTTP_201_CREATED)
    def report_injury(
        request_body: InjuryFlagCreateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> InjuryFlagRecord:
        plan_row = _latest_visible_plan_row(store, profile.athlete_id)
        flag_row = store.create_injury_flag(
            profile.athlete_id,
            {
                "plan_id": str(plan_row["id"]) if plan_row else None,
                "source": "manual",
                "body_area": request_body.body_area,
                "description": request_body.description,
                "severity": request_body.severity,
                "status": "open",
            },
        )
        decision = AdaptationDecision(
            rule_code="injury_reported",
            decision="flag_admin_review",
            summary=f"Athlete reported an injury ({request_body.severity}): needs coach review",
            details={"body_area": request_body.body_area, "severity": request_body.severity},
            requires_admin_review=True,
        )
        _persist_decisions(
            store,
            athlete_id=profile.athlete_id,
            decisions=[decision],
            plan_id=str(plan_row["id"]) if plan_row else None,
            injury_flag_id=str(flag_row["id"]),
        )
        return _map_injury_flag(flag_row)

    @router.get("/api/injury-flags", response_model=list[InjuryFlagRecord])
    def list_injury_flags(
        include_resolved: bool = Query(False),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[InjuryFlagRecord]:
        statuses = ("open", "monitoring", "resolved") if include_resolved else ("open", "monitoring")
        return [_map_injury_flag(row) for row in store.list_injury_flags(profile.athlete_id, statuses=statuses)]

    # ------------------------------------------------------------------
    # Admin endpoints
    # ------------------------------------------------------------------

    def _review_athletes_by_id(store: AppStore, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        athlete_ids = sorted({str(row.get("athlete_id") or "") for row in rows if row.get("athlete_id")})
        if not athlete_ids:
            return {}
        return {str(row["id"]): row for row in store.list_admin_athletes_by_ids(athlete_ids)}

    def _enriched_review(row: dict[str, Any], athletes_by_id: dict[str, dict[str, Any]]) -> AdminReviewRecord:
        athlete = athletes_by_id.get(str(row["athlete_id"])) or {}
        return _map_admin_review(
            row,
            athlete_email=str(athlete.get("email") or ""),
            athlete_name=str(athlete.get("full_name") or ""),
        )

    @router.get("/api/admin/reviews", response_model=list[AdminReviewRecord])
    def list_admin_reviews(
        review_status: str | None = Query("pending", alias="status"),
        limit: int = Query(50, ge=1, le=200),
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> list[AdminReviewRecord]:
        if review_status and review_status not in {"pending", "acknowledged", "resolved", "all"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid status filter")
        status_filter = None if review_status in (None, "all") else review_status
        rows = store.list_admin_reviews(status_filter=status_filter, limit=limit)
        athletes_by_id = _review_athletes_by_id(store, rows)
        return [_enriched_review(row, athletes_by_id) for row in rows]

    @router.post("/api/admin/reviews/{review_id}/resolve", response_model=AdminReviewRecord)
    def resolve_admin_review(
        review_id: str,
        request_body: AdminReviewResolveRequest,
        admin: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> AdminReviewRecord:
        try:
            uuid.UUID(review_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review not found")
        row = store.resolve_admin_review(
            review_id,
            {
                "status": request_body.status,
                "resolution_notes": request_body.resolution_notes,
                "resolved_by": admin.email,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        athletes_by_id = _review_athletes_by_id(store, [row])
        return _enriched_review(row, athletes_by_id)

    @router.patch("/api/admin/injury-flags/{flag_id}", response_model=InjuryFlagRecord)
    def update_injury_flag(
        flag_id: str,
        request_body: InjuryFlagUpdateRequest,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> InjuryFlagRecord:
        try:
            uuid.UUID(flag_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="injury flag not found")
        fields: dict[str, Any] = {"status": request_body.status}
        fields["resolved_at"] = (
            datetime.now(timezone.utc).isoformat() if request_body.status == "resolved" else None
        )
        return _map_injury_flag(store.update_injury_flag(flag_id, fields))

    @router.get("/api/admin/athletes/{athlete_id}/daily-status", response_model=AdminAthleteDailyStatus)
    def get_admin_athlete_daily_status(
        athlete_id: str,
        _: ProfileRecord = Depends(require_admin),
        store: AppStore = Depends(get_store),
    ) -> AdminAthleteDailyStatus:
        try:
            uuid.UUID(athlete_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        athlete = store.get_admin_athlete(athlete_id)
        if not athlete:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="athlete not found")
        checkins = store.list_daily_checkins(athlete_id, limit=14)
        session_logs = store.list_session_logs(athlete_id, limit=RECENT_SESSION_LOG_WINDOW)
        open_flags = store.list_injury_flags(athlete_id, statuses=("open", "monitoring"))
        latest_checkin = checkins[0] if checkins else None
        readiness = compute_readiness_summary(
            latest_checkin=latest_checkin,
            open_injury_flag_count=sum(1 for f in open_flags if f.get("status") == "open"),
            recent_session_logs=session_logs,
        )
        return AdminAthleteDailyStatus(
            athlete_id=athlete_id,
            readiness=readiness,
            latest_checkin=_map_checkin(latest_checkin) if latest_checkin else None,
            open_injury_flags=[_map_injury_flag(row) for row in open_flags],
            recent_session_logs=[_map_session_log(row) for row in session_logs[:10]],
            recent_adaptation_notes=[
                _map_adaptation_note(row) for row in store.list_adaptation_notes(athlete_id, limit=10)
            ],
            pending_review_count=store.count_pending_admin_reviews_for_athlete(athlete_id),
        )

    return router
