"""Read-only personal movement summaries and historical exercise-block results."""
from typing import Literal

from pydantic import BaseModel, Field

from api.contracts.session_details import SessionDetailBlock
from api.models import ExerciseLogActual


class RecordedExerciseLoad(BaseModel):
    value: float
    unit: Literal["kg", "lb"]
    training_day: str
    basis: Literal["reported", "confirmed_prescription"]


class PersonalExercise(BaseModel):
    id: str
    name: str
    identity_kind: Literal["canonical", "legacy"]
    latest_day: str
    latest_values: ExerciseLogActual
    latest_confirmed_as_prescribed: bool
    best_loads: list[RecordedExerciseLoad] = Field(default_factory=list)


class ExerciseLibraryResponse(BaseModel):
    exercises: list[PersonalExercise]
    as_of: str
    coverage: Literal["retained_logs"] = "retained_logs"


class ExercisePerformance(BaseModel):
    id: str
    training_day: str
    block: SessionDetailBlock
    # Same eligibility and frozen-prescription resolution as the library index.
    # Null means the record cannot supply chart evidence.
    performed_values: ExerciseLogActual | None = None


class ExercisePerformancesResponse(BaseModel):
    performances: list[ExercisePerformance]
    next_cursor: str | None = None
