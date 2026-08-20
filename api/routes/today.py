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

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.compliance_guards import require_health_feature_access
from api.compliance import evaluate_profile_compliance
from api.models import (
    InjuryFlagRecord,
    LandingResponse,
    ProfileRecord,
    RehabResponseRequest,
    RehabResponseResult,
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
from api.contracts.rehab_completion import COMPLETED_STATUSES
from api.services.progress_notifications import award_session_progress
from api.services.rehab_completion_service import (
    collect_rehab_response_prompts,
    prompts_as_payload,
    record_rehab_exposures,
)
from api.services.notification_foundation import invalidate_notification_action
from api.services.today_service import resolve_training_day
from api.services.week_progress import try_award_completed_week_for_completion
from api.services.streaks import reconcile_adherence_streak
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
        # A readiness check-in collects soreness, fatigue, sleep and pain: health
        # data under Art. 9. No consent, no new collection.
        require_health_feature_access(profile)
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
        require_health_feature_access(profile)
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
        # The refreshed response contains every open injury, including untouched
        # flags. Only invalidate follow-ups for flags this request changed.
        for updated_injury_id in result.get("updated_injury_ids", []):
            injury_id = str(updated_injury_id or "").strip()
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
        payload = request_body.model_dump()
        if not evaluate_profile_compliance(profile).health_consent_granted:
            # Completion is mixed-purpose: preserve the training log while
            # dropping the sole health field after consent withdrawal.
            payload["pain_after"] = None
        row = upsert_session_completion(
            store,
            athlete_id=profile.athlete_id,
            athlete_timezone=profile.athlete_timezone,
            payload=payload,
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
            try:
                reconcile_adherence_streak(
                    store,
                    athlete_id=profile.athlete_id,
                    athlete_timezone=profile.athlete_timezone,
                )
            except Exception:  # noqa: BLE001 - completion remains authoritative
                logger.exception(
                    "[streak] adherence reconciliation failed athlete_id=%s",
                    profile.athlete_id,
                )
        return SessionCompletionResponse(
            completion=row,
            completion_status=completion_status,
            landing_session_state=completion_landing_state(completion_status),
            rehab_response_prompts=_rehab_prompts_for_completion(
                store, profile=profile, completion=row
            ),
        )

    def _plan_row_for_completion(
        store: AppStore, *, profile: ProfileRecord, plan_id: str
    ) -> dict[str, Any] | None:
        reader = getattr(store, "get_plan_for_athlete", None)
        if not callable(reader) or not plan_id:
            return None
        return reader(plan_id, profile.athlete_id)

    def _rehab_prompts_for_completion(
        store: AppStore, *, profile: ProfileRecord, completion: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """The injury-specific prompts this completion raises, or none.

        Health-gated: an athlete who has not granted health consent is not asked
        about an injury, and a resolution failure must never take the completion
        down with it — the session is logged either way.
        """
        if completion_status_of(completion) not in COMPLETED_STATUSES:
            # Checked before the plan read: starting and skipping a session are
            # the common taps, and neither can produce an exposure.
            return []
        if not evaluate_profile_compliance(profile).health_consent_granted:
            return []
        try:
            plan_row = _plan_row_for_completion(
                store, profile=profile, plan_id=str(completion.get("plan_id") or "")
            )
            if not plan_row:
                return []
            prompts = collect_rehab_response_prompts(
                store,
                athlete_id=profile.athlete_id,
                plan_row=plan_row,
                training_day=str(completion.get("training_day") or ""),
                session_id=str(completion.get("session_id") or ""),
                completion=completion,
            )
        except Exception:  # noqa: BLE001 - the completion record is authoritative
            logger.exception(
                "[rehab] response prompt resolution failed athlete_id=%s",
                profile.athlete_id,
            )
            return []
        return prompts_as_payload(prompts)

    @router.post(
        "/api/today/rehab-responses",
        response_model=RehabResponseResult,
        status_code=status.HTTP_201_CREATED,
    )
    def submit_rehab_responses(
        request_body: RehabResponseRequest,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> RehabResponseResult:
        """Append the injury-specific evidence for one completed rehab session.

        The request returns the immutable injury episode context issued with each
        prompt. The current episode must still match. Drill, side and demand are
        re-resolved from the stored plan and injury record, so nothing the client
        asserts can become evidence.
        """
        require_health_feature_access(profile)
        plan_row = _plan_row_for_completion(
            store, profile=profile, plan_id=request_body.plan_id
        )
        if not plan_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

        training_day = request_body.training_day or resolve_training_day(
            profile.athlete_timezone
        )
        completion = store.get_session_completion(
            profile.athlete_id, request_body.session_id, training_day
        )
        if not completion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="no session completion to attach this response to",
            )
        if str(completion.get("plan_id") or "") != request_body.plan_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="session completion belongs to another plan",
            )

        events = record_rehab_exposures(
            store,
            athlete_id=profile.athlete_id,
            plan_row=plan_row,
            training_day=training_day,
            session_id=request_body.session_id,
            completion=completion,
            answers={
                answer.injury_id: {
                    "injury_episode_id": str(answer.injury_episode_id),
                    "during_response": answer.during_response,
                    "limit_response": answer.limit_response,
                }
                for answer in request_body.answers
            },
        )
        return RehabResponseResult(
            recorded_exposure_ids=[str(event.exposure_id) for event in events],
            recorded_injury_ids=[str(event.injury_id) for event in events],
        )

    return router
