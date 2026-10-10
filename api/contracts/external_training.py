"""Completed external work, independent of plan/prescription identities."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

Activity = Literal["sparring", "boxing", "roadwork", "strength", "conditioning", "other"]
Effort = Literal["easy", "moderate", "hard"]


class ExternalTrainingFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: Activity
    # Same upper bound as the existing session_logs duration contract.
    duration_minutes: StrictInt = Field(ge=1, le=600)
    effort: Effort


class ExternalTrainingCreate(ExternalTrainingFields):
    client_request_id: UUID


class TrainingHistorySession(BaseModel):
    id: str
    source: Literal["unlxck", "external"]
    training_day: str
    status: Literal["done", "modified", "skipped"]
    title: str
    activity: Activity | None = None
    duration_minutes: int | None = None
    effort: Effort | None = None
    plan_id: str | None = None
    session_rpe: int | None = None
    pain_after: int | None = None
    modification_reason: str | None = None
    notes: str | None = None


class TrainingHistoryResponse(BaseModel):
    sessions: list[TrainingHistorySession]
