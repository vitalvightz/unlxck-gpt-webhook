from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status

from api.generation_job_helpers import _job_response
from api.models import GenerationJobResponse, ProfileRecord
from api.store import AppStore

Planner = Callable[[dict[str, Any]], dict[str, Any]]


def build_generation_jobs_router(
    *,
    require_profile,
    get_store,
    get_planner,
    get_stage2_automator,
    get_active_generation_tasks,
    get_enable_in_process_generation,
    schedule_generation_job_if_needed,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/generation-jobs/active", response_model=GenerationJobResponse | None)
    async def get_active_generation_job(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> GenerationJobResponse | None:
        job = await asyncio.to_thread(store.get_visible_active_generation_job_for_athlete, profile.athlete_id)
        if not job:
            return None
        return _job_response(job, store=store, viewer_role=profile.role)

    @router.get("/api/generation-jobs/latest", response_model=GenerationJobResponse | None)
    async def get_latest_generation_job(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> GenerationJobResponse | None:
        job = await asyncio.to_thread(store.get_latest_generation_job_for_athlete, profile.athlete_id)
        if not job:
            return None
        if profile.role != "admin" and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        return _job_response(job, store=store, viewer_role=profile.role)

    @router.get("/api/generation-jobs/{job_id}", response_model=GenerationJobResponse)
    async def get_generation_job(
        job_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> GenerationJobResponse:
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        if profile.role != "admin" and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        return _job_response(job, store=store, viewer_role=profile.role)

    return router
