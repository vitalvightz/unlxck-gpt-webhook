"""Block 4 Today/Overview API surface.

Thin HTTP wrappers over the fail-safe Today service boundary. The server owns the
training-day calculation and the recommendation; endpoints never trust a
client-supplied recommendation and never mutate the saved plan. This is the
non-UI backend integration — no Today UI is built here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
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
from api.services.progress_notifications import award_session_progress
from api.services.notification_foundation import invalidate_notification_action
from api.services.today_service import resolve_training_day
from api.services.week_progress import try_award_completed_week_for_completion
from api.services.xp_awards import (
    award_checkin_xp,
    award_injury_update_xp,
    plan_completion_xp_eligible,
)
from api.services.today_readiness_boundary import (
    build_today_command_view,
    resolve_today_landing,
    submit_today_checkin,
    submit_today_injury_checkin,
    upsert_session_completion,
)
from api.store import AppStore

logger = logging.getLogger(__name__)


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
        award_checkin_xp(store, athlete_id=profile.athlete_id, checkin=row)
        record = _checkin_record(row)
        try:
            invalidate_notification_action(
                store,
                profile_id=profile.athlete_id,
                action_key=f"checkin:{record.training_day}",
                training_day=record.training_day,
                source_metadata={"checkin_id": str(row.get("id") or "")},
            )
        except Exception:  # noqa: BLE001 - notification state must not roll back check-in
            logger.exception(
                "[notification] check-in action invalidation failed profile_id=%s",
                profile.athlete_id,
            )
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
        # Pin the injury write and its calendar-scoped XP award to one instant so
        # a request crossing the 03:00 training-day rollover cannot split them
        # across two different athlete-local days.
        request_now = datetime.now(timezone.utc)
        result = submit_today_injury_checkin(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            payload=request_body.model_dump(),
            now=request_now,
        )
        # The injury service owns the write but returns only the refreshed injury
        # state. Resolve the same server-authoritative athlete-local day here
        # rather than expecting an undocumented result field that is never set.
        training_day = resolve_training_day(profile.athlete_timezone, now=request_now)
        # One successful declaration batch earns one daily reward. Returning all
        # open injury rows must never multiply XP, and an empty/no-op request
        # cannot farm the reward merely by re-reading existing injuries.
        award_injury_update_xp(
            store,
            athlete_id=profile.athlete_id,
            training_day=training_day,
            updated_injuries=request_body.injuries,
        )
        for injury in result.get("open_injuries", []):
            injury_id = str(injury.get("id") or "").strip()
            if not injury_id:
                continue
            try:
                invalidate_notification_action(
                    store,
                    profile_id=profile.athlete_id,
                    action_key=f"update-injury:{injury_id}",
                    training_day=training_day,
                    completed_at=request_now,
                    source_metadata={"injury_id": injury_id},
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[notification] injury action invalidation failed profile_id=%s injury_id=%s",
                    profile.athlete_id,
                    injury_id,
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
        if completion_status in {"done", "modified", "skipped"}:
            try:
                invalidate_notification_action(
                    store,
                    profile_id=profile.athlete_id,
                    action_key=f"complete-session:{row.get('session_id') or request_body.session_id}",
                    training_day=str(row.get("training_day") or request_body.training_day),
                    source_metadata={"completion_id": str(row.get("id") or "")},
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[notification] session action invalidation failed profile_id=%s",
                    profile.athlete_id,
                )
        # Preserve the completion record, but only the single server-resolved
        # active plan may drive XP. This closes the overlapping/inactive-plan
        # path without deleting legitimate history or retro logs.
        if plan_completion_xp_eligible(
            store,
            athlete_id=profile.athlete_id,
            completion=row,
        ):
            award_session_progress(
                store,
                athlete_id=profile.athlete_id,
                athlete_timezone=profile.athlete_timezone,
                completion=row,
            )
            try_award_completed_week_for_completion(
                store,
                athlete_id=profile.athlete_id,
                athlete_timezone=profile.athlete_timezone,
                completion=row,
            )
        return SessionCompletionResponse(
            completion=row,
            completion_status=completion_status,
            landing_session_state=completion_landing_state(completion_status),
        )

    return router
