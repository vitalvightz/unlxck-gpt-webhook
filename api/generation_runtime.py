"""Backward-compatibility shim for the generation runtime.

The implementation now lives in the ``api.generation`` package; this module
re-exports the public surface so existing importers (``api.worker``, ``api.app``,
the test suite) keep working unchanged. New code should import from the
``api.generation.*`` modules directly.
"""
from __future__ import annotations

from .state_machine import job_status_for_plan_status
from .generation.time_utils import utc_now_iso as utc_now_iso
from .generation.timeouts import (
    _stage1_planner_timeout_seconds as _stage1_planner_timeout_seconds,
    _stage2_finalize_timeout_seconds as _stage2_finalize_timeout_seconds,
)
from .generation.stage2_runner import (
    _OPENAI_QUOTA_ADMIN_ERROR as _OPENAI_QUOTA_ADMIN_ERROR,
    _OPENAI_QUOTA_ATHLETE_ERROR as _OPENAI_QUOTA_ATHLETE_ERROR,
    is_openai_quota_error as is_openai_quota_error,
)
from .generation.triage import (
    _compact_generation_job_final_result as _compact_generation_job_final_result,
    should_skip_stage2 as should_skip_stage2,
)
from .generation.milestones import (
    _MAX_PERSISTED_MILESTONES as _MAX_PERSISTED_MILESTONES,
    build_progress_recorder as build_progress_recorder,
)
from .generation.heartbeat import is_stale_job as is_stale_job
from .generation.stage1_runner import (
    _invoke_planner as _invoke_planner,
    _stage1_mp_start_method as _stage1_mp_start_method,
    default_planner as default_planner,
    run_stage1_planner as run_stage1_planner,
)
from .generation.orchestrator import run_generation_job as run_generation_job
from .generation.scheduler import (
    is_in_process_generation_enabled as is_in_process_generation_enabled,
    schedule_generation_job_if_needed as schedule_generation_job_if_needed,
)

_TERMINAL_GENERATION_JOB_STATUSES = {"completed", "review_required", "failed"}


def generation_status_from_plan_status(plan_status: str) -> str:
    return job_status_for_plan_status(plan_status)
