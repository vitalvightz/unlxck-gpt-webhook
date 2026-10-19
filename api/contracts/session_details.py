"""Small, read-only projection of one historical training occurrence."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.contracts.external_training import TrainingHistorySession
from api.contracts.rehab_exposure import ExposureDose, ExposureResponse
from api.models import ExerciseLogActual


class SessionDetailBlock(BaseModel):
    name: str
    kind: Literal["exercise", "rehab", "guidance"] = "exercise"
    prescribed: dict[str, Any] = Field(default_factory=dict)
    actual: ExerciseLogActual = Field(default_factory=ExerciseLogActual)
    status: Literal["as_prescribed", "modified", "skipped", "done_as_shown", "changed", "stopped"] | None = None
    reason: str | None = None
    notes: str | None = None
    completed_dose: ExposureDose | None = None
    responses: list[ExposureResponse] = Field(default_factory=list)


class SessionDetailSparring(BaseModel):
    intensity: str
    rounds_completed: int
    round_seconds: int | None = None
    head_contact: str | None = None
    rocked: bool | None = None
    notes: str | None = None


class SessionDetails(BaseModel):
    session: TrainingHistorySession
    blocks: list[SessionDetailBlock] = Field(default_factory=list)
    prescription_source: Literal["snapshot", "exercise_logs", "unavailable", "manual"]
    message: str | None = None
    sparring: SessionDetailSparring | None = None
