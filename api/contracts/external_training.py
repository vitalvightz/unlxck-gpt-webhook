"""Completed external work, independent of plan/prescription identities."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

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
    training_day: date | None = None

    @field_validator("training_day", mode="before")
    @classmethod
    def validate_training_day(cls, value):
        if value is None:
            return None
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("Use a training date in YYYY-MM-DD format.")
        return date.fromisoformat(value)


class TrainingHistorySession(BaseModel):
    completion_origin: Literal["reported", "day_credit"] | None = None
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
