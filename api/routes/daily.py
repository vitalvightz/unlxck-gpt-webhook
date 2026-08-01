"""Athlete injury flags and the admin review queue.

Every rule decision is recorded as an ``adaptation_notes`` row, and one admin
review is opened per athlete while decisions requiring coach attention are
outstanding.

The dashboard / check-in / session-log endpoints that used to live here were
removed once the Today surface (``/api/today``, api/services/today_service.py)
became the only consumer path; it owns its own ``today_checkins`` and
``session_completions`` tables. The legacy ``daily_checkins`` and
``session_logs`` tables are intentionally left in place but no longer have an
HTTP surface.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.contracts.injury_checkin import MAX_INFECTION_SIGNS
from api.contracts.readiness_message import classify_injury_surface
from api.models import (
    AdaptationNoteRecord,
    AdminReviewRecord,
    AdminReviewResolveRequest,
    InjuryFlagCreateRequest,
    InjuryFlagRecord,
    InjuryFlagUpdateRequest,
    ProfileRecord,
)
from api.readiness import AdaptationDecision
from api.services.plan_schedule import latest_visible_plan_row
from api.store import AppStore
from fightcamp.injury_registry import (
    BLEEDING_STATUS_VALUES,
    COVERABLE_VALUES,
    DRAINAGE_VALUES,
    FRICTION_PROBLEM_VALUES,
    SKIN_INTEGRITY_VALUES,
)


_SURFACE_ENUM_VALUES: dict[str, frozenset[str]] = {
    "skin_integrity": SKIN_INTEGRITY_VALUES,
    "bleeding_status": BLEEDING_STATUS_VALUES,
    "drainage": DRAINAGE_VALUES,
    "coverable": COVERABLE_VALUES,
    "friction_or_contact_problem": FRICTION_PROBLEM_VALUES,
}


def _surface_enum(row: dict[str, Any], field: str) -> str | None:
    """One stored surface answer, or None when absent/unrecognised.

    A value the response model does not know is dropped rather than raised on:
    a legacy row must not be able to break the injury list.
    """
    value = str(row.get(field) or "").strip().lower()
    return value if value in _SURFACE_ENUM_VALUES[field] else None


def _surface_infection_signs(row: dict[str, Any]) -> list[str]:
    raw = row.get("infection_signs")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    signs = [str(item).strip()[:60] for item in raw if str(item or "").strip()]
    return signs[:MAX_INFECTION_SIGNS]


def _map_injury_flag(row: dict[str, Any]) -> InjuryFlagRecord:
    # The structured surface answers and the canonical classification are mapped
    # here too, not just on /api/today/injury-checkin. Dropping them left the
    # legacy and admin readers looking at an injury whose wound state was
    # blank — the same row that Today reports as needing review would read as
    # having no surface answers at all.
    surface_row = {
        **row,
        "infection_signs": _surface_infection_signs(row),
        **{field: _surface_enum(row, field) for field in _SURFACE_ENUM_VALUES},
    }
    try:
        surface_class = classify_injury_surface(surface_row)
    except Exception:
        # Response-only metadata: a classifier failure must not take the
        # injury list down with it.
        surface_class = None
    return InjuryFlagRecord(
        id=str(row["id"]),
        athlete_id=str(row["athlete_id"]),
        plan_id=str(row["plan_id"]) if row.get("plan_id") else None,
        source=str(row.get("source") or "checkin"),
        body_area=str(row.get("body_area") or ""),
        description=str(row.get("description") or ""),
        severity=str(row.get("severity") or "moderate"),
        # Provenance travels with the severity it describes. Without it a reader
        # cannot tell an athlete's "severe" from a wound floor the system
        # applied, which is the whole difference between a severity that may be
        # released automatically and one that may not.
        severity_source=str(row.get("severity_source") or "") or None,
        manual_severity=str(row.get("manual_severity") or "") or None,
        status=str(row.get("status") or "open"),
        latest_reported_status=str(row.get("latest_reported_status") or "ongoing"),
        skin_integrity=surface_row["skin_integrity"],
        bleeding_status=surface_row["bleeding_status"],
        drainage=surface_row["drainage"],
        infection_signs=surface_row["infection_signs"],
        coverable=surface_row["coverable"],
        friction_or_contact_problem=surface_row["friction_or_contact_problem"],
        surface_class=surface_class,
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

    @router.post("/api/injury-flags", response_model=InjuryFlagRecord, status_code=status.HTTP_201_CREATED)
    def report_injury(
        request_body: InjuryFlagCreateRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> InjuryFlagRecord:
        plan_row = latest_visible_plan_row(store, profile.athlete_id)
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

    return router
