"""Completed external work, independent of plan/prescription identities."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from api.contracts.training_disciplines import SessionType, Sport, discipline_error

Activity = Literal["sparring", "boxing", "roadwork", "strength", "conditioning", "other"]
Effort = Literal["easy", "moderate", "hard"]


class ExternalTrainingFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: Activity
    # Same upper bound as the existing session_logs duration contract.
    duration_minutes: StrictInt = Field(ge=1, le=600)
    effort: Effort
    # Optional detail on what was trained. Absent on older records and never
    # inferred for them; ``activity`` must be the kind the pair maps to.
    sport: Sport | None = None
    session_type: SessionType | None = None

    @model_validator(mode="after")
    def check_discipline(self):
        if error := discipline_error(self.activity, self.sport, self.session_type):
            raise ValueError(error)
        return self


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
    sport: Sport | None = None
    session_type: SessionType | None = None
    duration_minutes: int | None = None
    effort: Effort | None = None
    plan_id: str | None = None
    session_rpe: int | None = None
    pain_after: int | None = None
    modification_reason: str | None = None
    notes: str | None = None
    # A manual session's short note on what was learned; never workload.
    takeaway: str = ""


class TrainingHistoryResponse(BaseModel):
    sessions: list[TrainingHistorySession]
    # Pass as ``before_day`` for the next, older page; None when there is none.
    next_before_day: str | None = None


TAKEAWAY_MAX_CHARS = 280


class ExternalTrainingTakeaway(BaseModel):
    model_config = ConfigDict(extra="forbid")
    takeaway: str = Field(default="", max_length=TAKEAWAY_MAX_CHARS)

    @field_validator("takeaway", mode="before")
    @classmethod
    def clean_takeaway(cls, value):
        return value.strip() if isinstance(value, str) else value
