from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, status

from api.generation_job_helpers import _job_response
from api.models import GenerationJobResponse, ProfileRecord
from api.store import AppStore, is_effective_admin_profile

Planner = Callable[[dict[str, Any]], dict[str, Any]]

_FAKE_STORE_JOB_ID_PATTERN = re.compile(r"^job_[0-9a-f]{10}$")


def _validate_generation_job_id(job_id: str) -> None:
    try:
        uuid.UUID(job_id)
        return
    except (ValueError, TypeError, AttributeError):
        if _FAKE_STORE_JOB_ID_PATTERN.fullmatch(str(job_id or "")):
            return
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")


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
        viewer_role = "admin" if is_effective_admin_profile(profile, store) else profile.role
        return _job_response(job, store=store, viewer_role=viewer_role)

    @router.get("/api/generation-jobs/latest", response_model=GenerationJobResponse | None)
    async def get_latest_generation_job(
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> GenerationJobResponse | None:
        job = await asyncio.to_thread(store.get_latest_generation_job_for_athlete, profile.athlete_id)
        if not job:
            return None
        is_admin = is_effective_admin_profile(profile, store)
        if not is_admin and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        return _job_response(job, store=store, viewer_role="admin" if is_admin else profile.role)

    @router.get("/api/generation-jobs/{job_id}", response_model=GenerationJobResponse)
    async def get_generation_job(
        job_id: str,
        profile: ProfileRecord = Depends(require_profile),
        store: AppStore = Depends(get_store),
    ) -> GenerationJobResponse:
        _validate_generation_job_id(job_id)
        job = await asyncio.to_thread(store.get_generation_job, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        is_admin = is_effective_admin_profile(profile, store)
        if not is_admin and str(job["athlete_id"]) != profile.athlete_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not allowed")
        return _job_response(job, store=store, viewer_role="admin" if is_admin else (profile.role or "athlete"))

    return router
