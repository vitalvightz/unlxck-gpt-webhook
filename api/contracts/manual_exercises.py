"""What an athlete chose to record for one movement in a manual session.

Never a prescription and never workload: the parent session already carries
activity, duration and effort. Every measurement is optional, and only values
the athlete entered are stored.
"""
import math
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from api.models import ExerciseLogActual

MeasurementFormat = Literal["strength", "bodyweight", "isometric", "intervals", "distance"]
MANUAL_EXERCISE_LIMIT = 30
NAME_MAX_CHARS = 100
NOTES_MAX_CHARS = 500
_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")

# The measurements each format records. Anything else in a request is refused
# rather than stored where no screen would show it.
FORMAT_FIELDS: dict[str, frozenset[str]] = {
    "strength": frozenset({"sets", "reps", "load", "rest", "effort"}),
    "bodyweight": frozenset({"sets", "reps", "load", "rest", "effort"}),
    "isometric": frozenset({"sets", "duration", "load", "rest", "effort"}),
    "intervals": frozenset({"rounds", "work", "rest", "distance", "effort"}),
    "distance": frozenset({"distance", "duration", "sets", "load", "rest", "effort"}),
}
# Realistic upper bounds in each accepted unit; nothing is converted.
_LIMITS = {
    "load": {"kg": 1000, "lb": 2200},
    "duration": {"seconds": 86400, "minutes": 1440},
    "work": {"seconds": 3600, "minutes": 60},
    "rest": {"seconds": 3600, "minutes": 60},
    "distance": {"meters": 200000, "km": 200, "miles": 125},
}


def name_key(name: str) -> str:
    """Case and whitespace only; never strips qualifiers that change the movement."""
    return " ".join(name.split()).casefold()


class PerformedExerciseChoice(BaseModel):
    """Exactly one way of naming the movement."""
    model_config = ConfigDict(extra="forbid")
    catalogue_id: str | None = Field(default=None, min_length=1, max_length=250)
    # A canonical movement the athlete has already recorded.
    exercise_key: str | None = Field(default=None, min_length=1, max_length=120)
    personal_exercise_id: UUID | None = None
    # A new private movement; the name alone is enough.
    name: str | None = Field(default=None, max_length=NAME_MAX_CHARS)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value

    @model_validator(mode="after")
    def exactly_one(self):
        given = [value for value in (self.catalogue_id, self.exercise_key, self.personal_exercise_id, self.name) if value]
        if len(given) != 1:
            raise ValueError("Choose one exercise.")
        if self.exercise_key is not None and not _KEY.fullmatch(self.exercise_key):
            raise ValueError("Invalid exercise.")
        return self


class PerformedExerciseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exercise: PerformedExerciseChoice
    format: MeasurementFormat
    actual: ExerciseLogActual = Field(default_factory=ExerciseLogActual)
    notes: str = Field(default="", max_length=NOTES_MAX_CHARS)
    # The entry revision this save is based on: 0 creates, n edits revision n.
    # Saves apply in order; a delayed retry of an older one is refused.
    revision: StrictInt = Field(default=0, ge=0, le=1_000_000)

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("actual", mode="before")
    @classmethod
    def numbers_only(cls, value):
        # "3" and true are not measurements; never coerce them into one.
        if isinstance(value, dict):
            for key, item in value.items():
                number = item.get("value") if isinstance(item, dict) else item
                if number is None:
                    continue
                if isinstance(number, bool) or not isinstance(number, (int, float)):
                    raise ValueError(f"{key} must be a number.")
                if key in {"sets", "reps", "rounds"} and not isinstance(number, int):
                    raise ValueError(f"{key} must be a whole number.")
        return value

    @model_validator(mode="after")
    def check_measurements(self):
        values = self.actual.model_dump(exclude_none=True)
        extra = sorted(set(values) - FORMAT_FIELDS[self.format])
        if extra:
            raise ValueError(f"{', '.join(extra)} cannot be recorded for this exercise format.")
        # Missing stays missing: a recorded count or measurement is a real one.
        for field in ("sets", "reps", "rounds"):
            if values.get(field) == 0:
                raise ValueError(f"{field} must be at least 1.")
        for field, limits in _LIMITS.items():
            measure = getattr(self.actual, field)
            if measure is None:
                continue
            if not math.isfinite(measure.value) or measure.value > limits[measure.unit]:
                raise ValueError(f"{field} must be at most {limits[measure.unit]} {measure.unit}.")
            if measure.value == 0 and field != "rest":
                raise ValueError(f"{field} must be more than 0.")
            if round(measure.value, 2) != measure.value:
                raise ValueError(f"{field} allows up to two decimal places.")
        if self.actual.effort is not None and self.actual.effort.value * 2 != int(self.actual.effort.value * 2):
            raise ValueError("RPE must be a whole or half number.")
        return self


class ManualExerciseEntry(BaseModel):
    id: str
    # The client's retry key; address the entry by it to edit or delete.
    entry_id: str
    external_session_id: str
    training_day: str
    # "key:<exercise_key>" or "custom:<personal_exercise_id>", as in the Exercise Library.
    exercise_id: str
    name: str
    format: MeasurementFormat
    actual: ExerciseLogActual = Field(default_factory=ExerciseLogActual)
    notes: str | None = None
    # Send back as ``revision`` to edit this entry.
    revision: int = 1


class ManualExerciseListResponse(BaseModel):
    entries: list[ManualExerciseEntry]
