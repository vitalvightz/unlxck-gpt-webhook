"""Block 4 Today/Overview API surface.

Thin HTTP wrappers over the fail-safe Today service boundary. The server owns the
training-day calculation and the recommendation; endpoints never trust a
client-supplied recommendation and never mutate the saved plan. This is the
non-UI backend integration — no Today UI is built here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from api.models import (
    InjuryFlagRecord,
    LandingResponse,
    ProfileRecord,
    SessionCompletionRecordResponse,
    SessionCompletionRequest,
    SessionCompletionResponse,
    TodayCheckinRecord,
    TodayCheckinRequest,
    TodayCheckinResponse,
    TodayInjuryCheckinRequest,
    TodayInjuryCheckinResponse,
)
from api.contracts.command_view import CommandView
from api.contracts.completion import completion_landing_state, completion_status_of
from api.services.readiness_fail_safe import (
    build_today_command_view,
    resolve_today_landing,
    submit_today_checkin,
    submit_today_injury_checkin,
    upsert_session_completion,
)
from api.store import AppStore


def _checkin_record(row: dict[str, Any]) -> TodayCheckinRecord:
    triggers = row.get("recommendation_triggers") or []
    if not isinstance(triggers, list):
        triggers = []
    return TodayCheckinRecord(**{**row, "recommendation_triggers": list(triggers)})


def build_today_router(*, require_profile, get_store) -> APIRouter:
    router = APIRouter(tags=["today"])

    @router.post(
        "/api/today/checkin",
        response_model=TodayCheckinResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def submit_checkin(
        request_body: TodayCheckinRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> TodayCheckinResponse:
        row = submit_today_checkin(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            payload=request_body.model_dump(),
        )
        record = _checkin_record(row)
        # Backend-owned typed safety signal (additive to the response). Defaults
        # keep the field set stable even if the signal is ever absent.
        signal = row.get("readiness_signal") or {}
        return TodayCheckinResponse(
            checkin=record,
            training_day=record.training_day,
            recommendation_state=record.recommendation_state,
            recommendation_reason=record.recommendation_reason,
            triggers=record.recommendation_triggers,
            warnings=[str(warning) for warning in row.get("warnings", [])],
            decision=str(signal.get("decision") or record.recommendation_state),
            decision_tier=str(signal.get("decision_tier") or ""),
            display_state=str(signal.get("display_state") or ""),
            reason_codes=[str(code) for code in signal.get("reason_codes", [])],
            title=str(signal.get("title") or ""),
            detail=str(signal.get("detail") or ""),
            action=str(signal.get("action") or ""),
            safety=str(signal.get("safety") or ""),
            blocks_training=bool(signal.get("blocks_training", False)),
        )

    @router.post(
        "/api/today/injury-checkin",
        response_model=TodayInjuryCheckinResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def submit_injury_checkin(
        request_body: TodayInjuryCheckinRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> TodayInjuryCheckinResponse:
        result = submit_today_injury_checkin(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            payload=request_body.model_dump(),
        )
        return TodayInjuryCheckinResponse(
            open_injuries=[InjuryFlagRecord(**row) for row in result.get("open_injuries", [])],
        )

    @router.get(
        "/api/today/session-completions",
        response_model=list[SessionCompletionRecordResponse],
    )
    def list_session_completion_history(
        limit: int = Query(default=30, ge=1, le=200),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[SessionCompletionRecordResponse]:
        # History is System B only (session_completions). The legacy
        # session_logs table has no web UI and stays out of this view.
        rows = store.list_session_completions(profile.athlete_id, limit=limit)
        return [SessionCompletionRecordResponse(**row) for row in rows]

    @router.get(
        "/api/today/checkins",
        response_model=list[TodayCheckinRecord],
    )
    def list_checkin_history(
        limit: int = Query(default=30, ge=1, le=200),
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> list[TodayCheckinRecord]:
        rows = store.list_today_checkins(profile.athlete_id, limit=limit)
        return [_checkin_record(row) for row in rows]

    @router.get("/api/today", response_model=CommandView)
    def get_today_state(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> CommandView:
        return build_today_command_view(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
        )

    @router.get("/api/today/landing", response_model=LandingResponse)
    def get_landing(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> LandingResponse:
        # A returning athlete has at least one persisted plan; cold users do not.
        # get_latest_plan is a limit(1) lookup — cheaper than fetching all plans.
        has_interacted = store.get_latest_plan(profile.athlete_id) is not None
        decision = resolve_today_landing(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            has_interacted=has_interacted,
        )
        return LandingResponse(
            target=decision.target,
            cta=decision.cta,
            row=decision.row,
            reason=decision.reason,
        )

    @router.post(
        "/api/today/session-completion",
        response_model=SessionCompletionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def update_session_completion(
        request_body: SessionCompletionRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> SessionCompletionResponse:
        row = upsert_session_completion(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            payload=request_body.model_dump(),
        )
        completion_status = completion_status_of(row)
        return SessionCompletionResponse(
            completion=row,
            completion_status=completion_status,
            landing_session_state=completion_landing_state(completion_status),
        )

    return router
