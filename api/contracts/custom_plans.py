"""Saved self-directed drafts. These contracts never authorise execution."""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from api.contracts.training_library import LibraryEntry

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Weekday = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomDose(DraftModel):
    mode: Literal["reps", "duration"] = "reps"
    sets: int | None = Field(None, strict=True, ge=1, le=100)
    reps: int | None = Field(None, strict=True, ge=1, le=1000)
    duration_seconds: int | None = Field(None, strict=True, ge=1, le=36000)
    rest_seconds: int | None = Field(None, strict=True, ge=0, le=3600)
    load_or_intensity: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def matching_mode(self):
        if (self.mode == "reps" and self.duration_seconds is not None) or (self.mode == "duration" and self.reps is not None):
            raise ValueError("Use reps or duration for the selected dose mode.")
        return self


class CustomExerciseInput(DraftModel):
    id: UUID
    catalogue_id: str = Field(min_length=1, max_length=250)
    dose: CustomDose = Field(default_factory=CustomDose)


class CustomSessionInput(DraftModel):
    id: UUID
    name: Name
    weekday: Weekday | None = None
    exercises: list[CustomExerciseInput] = Field(default_factory=list, max_length=100)


class CustomPlanInput(DraftModel):
    name: Name
    sessions: list[CustomSessionInput] = Field(default_factory=list, max_length=28)

    @model_validator(mode="after")
    def unique_occurrences(self):
        ids = [session.id for session in self.sessions]
        ids += [exercise.id for session in self.sessions for exercise in session.exercises]
        if len(ids) != len(set(ids)):
            raise ValueError("Session and exercise IDs must be unique within a plan.")
        return self


class CustomExerciseSnapshot(LibraryEntry):
    category: Literal["training"] = "training"
    source: str
    source_revision: str
    row_revision: str


class CustomExercise(CustomExerciseInput):
    snapshot: CustomExerciseSnapshot
    incomplete: bool


class CustomSession(CustomSessionInput):
    exercises: list[CustomExercise] = Field(default_factory=list)


class CustomPlan(BaseModel):
    id: UUID
    name: str
    kind: Literal["self_directed"] = "self_directed"
    sessions: list[CustomSession]
    incomplete: bool
    created_at: datetime
    updated_at: datetime
