"""Complete retained-log summaries; no current plans, guessed keys or evidence writes."""
import base64
from datetime import date, datetime, timezone
import json
import re
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from api.contracts.exercise_library import (
    ExerciseLibraryResponse, ExercisePerformance, ExercisePerformancesResponse,
    PersonalExercise, RecordedExerciseLoad,
)
from api.models import ExerciseLogActual
from api.services.session_details import _exercise, _map, _text

_BATCH_SIZE = 500
_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_EXCLUDED_TYPES = {"rehab", "mindset", "nutrition", "sparring"}
_UNIT_ALIASES = {"sec": "seconds", "s": "seconds", "second": "seconds", "min": "minutes", "minute": "minutes",
                 "m": "meters", "metres": "meters", "meter": "meters", "metre": "meters", "mi": "miles"}


def exercise_identity(row: dict) -> str:
    key = row.get("exercise_key")
    return f"key:{key}" if isinstance(key, str) and len(key) <= 120 and _KEY.fullmatch(key) else f"log:{row['id']}"


def _actual(row: dict) -> ExerciseLogActual | None:
    try:
        if not isinstance(row.get("actual"), dict):
            return None
        for value in row["actual"].values():
            number = value.get("value") if isinstance(value, dict) else value
            if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))):
                return None
        return ExerciseLogActual.model_validate(row["actual"])
    except ValidationError:
        return None


def _performed(row: dict, actual: ExerciseLogActual | None) -> bool:
    if actual is None or _map(row.get("prescribed")).get("block_type") in _EXCLUDED_TYPES:
        return False
    values = actual.model_dump(exclude_none=True)
    prescribed = _map(row.get("prescribed")) if row.get("status") == "as_prescribed" else {}
    if any(values.get(key, prescribed.get(key)) == 0 for key in ("sets", "reps", "rounds")):
        return False
    if any(_map(values.get(key, prescribed.get(key))).get("value") == 0 for key in ("duration", "work", "distance")):
        return False
    return row.get("status") == "as_prescribed" or (row.get("status") == "modified" and bool(values))


def performed_values(row: dict, actual: ExerciseLogActual) -> ExerciseLogActual:
    """Confirmed numeric prescription fields only; actuals always take priority."""
    values = actual.model_dump(exclude_none=True)
    if row.get("status") != "as_prescribed":
        return actual
    prescribed = _map(row.get("prescribed"))
    for key in ExerciseLogActual.model_fields:
        if key in values:
            continue
        value = prescribed.get(key)
        if key in {"sets", "reps", "rounds"}:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                continue
        elif key == "load":
            if _map(value).get("method") not in {None, "absolute"} or _map(value).get("unit") not in {"kg", "lb"}:
                continue
            if isinstance(value.get("value"), bool) or not isinstance(value.get("value"), (int, float)):
                continue
            value = {k: value[k] for k in ("value", "unit") if k in value}
        elif key == "effort":
            if _map(value).get("method") != "RPE":
                continue
            value = {k: value[k] for k in ("method", "value") if k in value}
        else:
            if not isinstance(value, dict):
                continue
            value = {"value": value.get("value"), "unit": _UNIT_ALIASES.get(value.get("unit"), value.get("unit"))}
        try:
            # Validate each fallback independently; never parse a display string.
            checked = ExerciseLogActual.model_validate({key: value}).model_dump(exclude_none=True)
        except ValidationError:
            continue
        values.update(checked)
    return ExerciseLogActual.model_validate(values)


def exercise_library(store, athlete_id: str, *, now: datetime | None = None) -> ExerciseLibraryResponse:
    as_of = (now or datetime.now(timezone.utc)).isoformat()
    summaries: dict[str, PersonalExercise] = {}
    latest: dict[str, tuple[str, str]] = {}
    after_id = None
    while True:
        rows = store.list_exercise_index_page(athlete_id, as_of=as_of, after_id=after_id, limit=_BATCH_SIZE)
        if not rows:
            break
        ids = [str(row.get("id") or "") for row in rows]
        if ids != sorted(set(ids)) or not all(ids) or (after_id and ids[0] <= after_id):
            raise HTTPException(503, "Exercise history is temporarily unavailable.")
        for row in rows:
            if row.get("athlete_id") != athlete_id:
                continue
            actual = _actual(row)
            if not _performed(row, actual):
                continue
            values = performed_values(row, actual)
            identity = exercise_identity(row)
            day = row["training_day"]
            order = (day, row["id"])
            if identity not in summaries:
                summaries[identity] = PersonalExercise(id=identity, name="Exercise", identity_kind="canonical" if identity.startswith("key:") else "legacy",
                    latest_day=day, latest_values=values, latest_confirmed_as_prescribed=False)
            summary = summaries[identity]
            if identity not in latest or order > latest[identity]:
                latest[identity] = order
                summary.name = _text(_map(row.get("prescribed")).get("display_name")) or (row.get("exercise_key") or "Legacy exercise record")
                summary.latest_day, summary.latest_values = day, values
                summary.latest_confirmed_as_prescribed = row["status"] == "as_prescribed"
            load = values.load
            if load is not None and load.value > 0:
                before = next((entry for entry in summary.best_loads if entry.unit == load.unit), None)
                if before is None or load.value > before.value:
                    summary.best_loads = [entry for entry in summary.best_loads if entry.unit != load.unit] + [RecordedExerciseLoad(
                        value=load.value, unit=load.unit, training_day=day,
                        basis="reported" if actual.load is not None else "confirmed_prescription")]
        after_id = ids[-1]
    for summary in summaries.values():
        summary.best_loads.sort(key=lambda entry: entry.unit)
    return ExerciseLibraryResponse(exercises=sorted(summaries.values(), key=lambda item: (item.name.casefold(), item.id)), as_of=as_of)


def _selector(identity: str) -> tuple[str | None, str | None]:
    if identity.startswith("key:") and len(identity) <= 124 and _KEY.fullmatch(identity[4:]):
        return identity[4:], None
    try:
        if identity.startswith("log:"):
            return None, str(UUID(identity[4:]))
    except ValueError:
        pass
    raise HTTPException(422, "Invalid exercise record.")


def _cutoff(value: str) -> str:
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None:
        raise ValueError("missing timezone")
    return instant.isoformat()


def exercise_performances(store, athlete_id: str, identity: str, *, as_of: str | None = None,
                          cursor: str | None = None, limit: int = 30, health_consent_granted: bool) -> ExercisePerformancesResponse:
    key, log_id = _selector(identity)
    before_day = before_id = None
    try:
        cutoff = _cutoff(as_of) if as_of else datetime.now(timezone.utc).isoformat()
        if cursor:
            data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if data["exercise"] != identity:
                raise ValueError("wrong exercise")
            cutoff = _cutoff(data["as_of"])
            before_day, before_id = date.fromisoformat(data["day"]).isoformat(), str(UUID(data["id"]))
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(422, "Invalid exercise history cursor.") from None
    rows = []
    # Do not mistake a lower server row cap or excluded legacy blocks for the
    # end of this movement's history. Stop at one valid sentinel or an empty read.
    while len(rows) <= limit:
        batch = store.list_exercise_performances(athlete_id, exercise_key=key, log_id=log_id,
            as_of=cutoff, before_day=before_day, before_id=before_id, limit=limit + 1 - len(rows))
        if not batch:
            break
        order = [(str(row.get("training_day") or ""), str(row.get("id") or "")) for row in batch]
        if (order != sorted(set(order), reverse=True) or not all(day and id for day, id in order)
                or (before_day and order[0] >= (before_day, before_id))):
            raise HTTPException(503, "Exercise history is temporarily unavailable.")
        rows.extend(row for row in batch if row.get("athlete_id") == athlete_id and exercise_identity(row) == identity
                    and _map(row.get("prescribed")).get("block_type") not in _EXCLUDED_TYPES)
        before_day, before_id = order[-1]
    if not rows and not cursor:
        raise HTTPException(404, "Exercise history not found.")
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps({"exercise": identity, "as_of": cutoff,
            "day": last["training_day"], "id": last["id"]}).encode()).decode().rstrip("=")
    return ExercisePerformancesResponse(performances=[ExercisePerformance(id=row["id"], training_day=row["training_day"],
        block=_exercise(_map(row.get("prescribed")), row, health_consent_granted)) for row in page], next_cursor=next_cursor)
