"""Pydantic models for the persisted runtime records.

These validate the envelopes written at two store seams: the generation job
record and the persisted plan record. They check the record structure
(required identifiers, valid status, field types) and treat the embedded
pipeline payloads (stage1_result, final_result, stage2_payload, planning_brief)
as opaque blobs -- those are validated at the Stage 1 seam, not re-validated
here. ``extra="allow"`` covers DB-added columns (id, created_at, updated_at).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .state_machine import GenerationJobStatus


class GenerationJobState(BaseModel):
    """The generation_jobs record created in create_or_get_generation_job."""

    model_config = ConfigDict(extra="allow")

    athlete_id: str
    client_request_id: str
    source: str
    status: GenerationJobStatus
    request_payload: dict[str, Any] = Field(default_factory=dict)
    attempt_count: int = 0
    heartbeat_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    intake_id: str | None = None
    stage1_result: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    plan_id: str | None = None


class PersistedPlanRuntime(BaseModel):
    """The plans record created in create_plan."""

    model_config = ConfigDict(extra="allow")

    athlete_id: str
    intake_id: str
    full_name: str
    status: str
    fight_date: str | None = None
    technical_style: list[str] = Field(default_factory=list)
    plan_name: str = ""
    plan_text: str = ""
    draft_plan_text: str = ""
    final_plan_text: str = ""
    coach_notes: str = ""
    pdf_url: str | None = None
    why_log: dict[str, Any] = Field(default_factory=dict)
    planning_brief: Any = None
    stage2_payload: dict[str, Any] | None = None
    stage2_handoff_text: str = ""
    stage2_retry_text: str = ""
    stage2_validator_report: dict[str, Any] = Field(default_factory=dict)
    stage2_status: str = ""
    stage2_attempt_count: int = 0
    parsing_metadata: dict[str, Any] | None = None
