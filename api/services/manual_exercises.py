"""Optional exercise results on a manual session. Never workload, XP or evidence.

The parent session (external_training_sessions) owns the occurrence: its day,
its workload and its lifecycle. Entries only add which movements were done and
whatever the athlete chose to record for each.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from api.contracts.manual_exercises import (
    MANUAL_EXERCISE_LIMIT, ManualExerciseEntry, PerformedExerciseInput, MeasurementFormat, name_key,
)
from api.models import ExerciseLogActual

_RUN = re.compile(r"\b(?:run|runs|running|jog|jogging|sprint|sprints|bike|cycle|cycling|row|rowing|swim|swimming|walk|ruck|ski)\b")
_HOLD = re.compile(r"\b(?:plank|hold|holds|hang|isometric|wall sit|l-sit|hollow)\b")
_formats: dict[tuple[str, str], MeasurementFormat | None] = {}


def entry_identity(row: dict) -> str:
    return f"key:{row['exercise_key']}" if row.get("exercise_key") else f"custom:{row['personal_exercise_id']}"


def entry_actual(row: dict) -> ExerciseLogActual | None:
    """A stored value that no longer validates is withheld, never coerced."""
    try:
        return ExerciseLogActual.model_validate(row.get("actual") if isinstance(row.get("actual"), dict) else {})
    except ValidationError:
        return None


def to_entry(row: dict, *, health_consent_granted: bool) -> ManualExerciseEntry:
    return ManualExerciseEntry(
        id=str(row["id"]), entry_id=str(row["client_entry_id"]), external_session_id=str(row["external_session_id"]),
        training_day=str(row["training_day"])[:10], exercise_id=entry_identity(row), name=row["display_name"],
        format=row["measurement_format"], actual=entry_actual(row) or ExerciseLogActual(),
        notes=(row.get("notes") or None) if health_consent_granted else None,
    )


def values_format(values: ExerciseLogActual) -> MeasurementFormat | None:
    """The layout that shows what a past record holds; None when it holds nothing."""
    if values.rounds is not None or values.work is not None:
        return "intervals"
    if values.distance is not None:
        return "distance"
    if values.duration is not None and values.reps is None:
        return "isometric"
    if values.reps is not None or values.sets is not None:
        return "strength" if values.load is not None else "bodyweight"
    if values.load is not None:
        return "strength"
    return None


def catalogue_format(record: dict) -> MeasurementFormat | None:
    """Suggest a layout from the catalogue's own dose evidence; None when ambiguous."""
    from api.services.exercise_dose import dose_guidance

    entry = record["entry"]
    cache_key = (str(entry.get("row_revision") or entry.get("source_revision") or ""), entry["catalogue_id"])
    if cache_key in _formats:
        return _formats[cache_key]
    name = str(entry.get("name") or "").casefold()
    try:
        mode = dose_guidance(record)[0]
    except (HTTPException, KeyError, TypeError, ValueError):
        mode = None
    equipment = set(record["summary"].get("equipment") or []) if record["summary"].get("equipment_state") == "known" else set()
    result: MeasurementFormat | None
    if mode == "reps":
        result = "bodyweight" if equipment and equipment <= {"none", "bodyweight", "no_equipment"} else "strength"
    elif mode == "intervals":
        result = "intervals"
    elif mode == "distance":
        result = "distance"
    elif mode == "duration":
        result = "isometric" if _HOLD.search(name) else "distance" if _RUN.search(name) else None
    else:
        result = None
    _formats[cache_key] = result
    return result


def _live_session(store, athlete_id: str, session_id: str) -> dict:
    session = store.get_external_training_session(athlete_id, session_id)
    if not session or session.get("athlete_id") != athlete_id or session.get("deleted_at"):
        raise HTTPException(404, "Training session not found.")
    return session


def _identity(store, athlete_id: str, body: PerformedExerciseInput) -> dict[str, Any]:
    choice = body.exercise
    if choice.catalogue_id:
        from api.services.training_library import cache

        try:
            record = cache.get().by_id.get(choice.catalogue_id)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(503, "Training library is temporarily unavailable.") from None
        key = record["entry"].get("exercise_key") if record and record["summary"]["category"] == "training" else None
        if not key:
            raise HTTPException(422, "That exercise can't be recorded. Enter it by name instead.")
        return {"exercise_key": key, "personal_exercise_id": None, "display_name": record["entry"]["name"][:120]}
    if choice.exercise_key:
        from api.services.training_library import cache

        try:
            known = next((r for r in cache.get().records if r["entry"].get("exercise_key") == choice.exercise_key), None)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            known = None
        if not known and not store.has_exercise_record(athlete_id, choice.exercise_key):
            raise HTTPException(422, "Exercise not found.")
        name = known["entry"]["name"] if known else _recorded_name(store, athlete_id, choice.exercise_key)
        return {"exercise_key": choice.exercise_key, "personal_exercise_id": None, "display_name": name[:120]}
    if choice.personal_exercise_id:
        row = store.get_personal_exercise(athlete_id, str(choice.personal_exercise_id))
        if not row or row.get("athlete_id") != athlete_id:
            raise HTTPException(422, "Exercise not found.")
        return {"exercise_key": None, "personal_exercise_id": str(row["id"]), "display_name": row["name"]}
    name = choice.name or ""
    if not name:
        raise HTTPException(422, "Enter an exercise name.")
    row = store.ensure_personal_exercise(athlete_id, name, name_key(name))
    if row.get("athlete_id") != athlete_id:
        raise HTTPException(500, "Failed to save exercise.")
    return {"exercise_key": None, "personal_exercise_id": str(row["id"]), "display_name": row["name"]}


def _recorded_name(store, athlete_id: str, key: str) -> str:
    from api.services.exercise_library import exercise_library

    library = exercise_library(store, athlete_id)
    return next((item.name for item in library.exercises if item.id == f"key:{key}"), key.replace("-", " ").capitalize())


def list_session_exercises(store, athlete_id: str, session_id: str, *, health_consent_granted: bool) -> list[ManualExerciseEntry]:
    _live_session(store, athlete_id, session_id)
    rows = [row for row in store.list_manual_exercises(athlete_id, session_id)
            if row.get("athlete_id") == athlete_id and row.get("external_session_id") == session_id and not row.get("deleted_at")]
    return [to_entry(row, health_consent_granted=health_consent_granted) for row in rows]


def save_session_exercise(store, athlete_id: str, session_id: str, entry_id: str, body: PerformedExerciseInput) -> ManualExerciseEntry:
    """Idempotent PUT: the same entry_id always names the same occurrence."""
    _live_session(store, athlete_id, session_id)
    existing = store.get_manual_exercise(athlete_id, entry_id)
    if existing and existing.get("athlete_id") != athlete_id:
        raise HTTPException(409, "This entry ID is already in use.")
    if existing and existing.get("deleted_at"):
        raise HTTPException(410, "This exercise was removed. Add it again as a new entry.")
    if existing and str(existing["external_session_id"]) != session_id:
        raise HTTPException(409, "This entry belongs to another session.")
    fields = {**_identity(store, athlete_id, body), "measurement_format": body.format,
              "actual": body.actual.model_dump(mode="json", exclude_none=True), "notes": body.notes}
    if not existing:
        if len(store.list_manual_exercises(athlete_id, session_id)) >= MANUAL_EXERCISE_LIMIT:
            raise HTTPException(422, f"Up to {MANUAL_EXERCISE_LIMIT} exercises per session.")
        existing = store.create_manual_exercise(athlete_id, {**fields, "external_session_id": session_id, "client_entry_id": entry_id})
        if existing.get("deleted_at"):
            raise HTTPException(410, "This exercise was removed. Add it again as a new entry.")
        if str(existing["external_session_id"]) != session_id:
            raise HTTPException(409, "This entry belongs to another session.")
    if any(existing.get(key) != value for key, value in fields.items()):
        existing = store.update_manual_exercise(athlete_id, entry_id, fields)
        if existing is None:
            raise HTTPException(410, "This exercise was removed. Add it again as a new entry.")
    return to_entry(existing, health_consent_granted=True)


def delete_session_exercise(store, athlete_id: str, session_id: str, entry_id: str) -> None:
    existing = store.get_manual_exercise(athlete_id, entry_id)
    if not existing or existing.get("athlete_id") != athlete_id or str(existing["external_session_id"]) != session_id:
        raise HTTPException(404, "Exercise not found.")
    # A tombstone answers a repeated delete, and blocks a late save retry.
    if not store.delete_manual_exercise(athlete_id, entry_id):
        raise HTTPException(404, "Exercise not found.")
