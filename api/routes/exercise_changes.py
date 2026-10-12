"""Swap, add and remove exercises on an app-generated plan (owner-scoped)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from api.contracts.exercise_changes import (
    ExerciseChangeRequest, ExerciseChangeResult, ExerciseOptionsResponse, ExerciseUndoRequest,
)
from api.services import exercise_customisation as customisation


def build_exercise_changes_router(*, require_profile, get_store):
    router = APIRouter(prefix="/api/plans/{plan_id}/exercise-changes", tags=["exercise changes"])

    @router.get("/alternatives", response_model=ExerciseOptionsResponse)
    def alternatives(
        plan_id: str, date: str = Query(..., min_length=10, max_length=10),
        session_id: str = Query(..., min_length=1, max_length=200),
        block_id: str = Query(..., min_length=1, max_length=200), all: bool = False,
        profile=Depends(require_profile), store=Depends(get_store),
    ):
        return customisation.exercise_options(
            store, athlete_id=profile.athlete_id, athlete_timezone=profile.athlete_timezone, plan_id=plan_id,
            day=date, session_id=session_id, block_id=block_id, show_all=all,
        )

    @router.get("/additions", response_model=ExerciseOptionsResponse)
    def additions(
        plan_id: str, date: str = Query(..., min_length=10, max_length=10),
        session_id: str = Query(..., min_length=1, max_length=200), all: bool = False,
        q: str = Query("", max_length=100),
        profile=Depends(require_profile), store=Depends(get_store),
    ):
        return customisation.addition_options(
            store, athlete_id=profile.athlete_id, athlete_timezone=profile.athlete_timezone, plan_id=plan_id,
            day=date, session_id=session_id, show_all=all, query=q,
        )

    @router.post("", response_model=ExerciseChangeResult)
    def apply(plan_id: str, body: ExerciseChangeRequest, profile=Depends(require_profile), store=Depends(get_store)):
        if body.action in {"swap", "remove", "edit"} and not body.block_id:
            raise HTTPException(422, "Choose the exercise to change.")
        if body.action in {"swap", "add"} and not body.catalogue_id:
            raise HTTPException(422, "Choose an exercise.")
        payload = body.model_dump(mode="json")
        return customisation.apply_change(
            store, athlete_id=profile.athlete_id, athlete_timezone=profile.athlete_timezone,
            plan_id=plan_id, payload=payload,
        )

    @router.post("/{change_id}/undo", response_model=ExerciseChangeResult)
    def undo(plan_id: str, change_id: str, body: ExerciseUndoRequest | None = None,
             profile=Depends(require_profile), store=Depends(get_store)):
        return customisation.undo_change(
            store, athlete_id=profile.athlete_id, athlete_timezone=profile.athlete_timezone,
            plan_id=plan_id, change_id=change_id, from_day=body.date if body else None,
        )

    return router
