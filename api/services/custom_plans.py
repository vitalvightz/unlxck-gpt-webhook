"""Catalogue-backed storage only; no planner, readiness or completion writes."""
from fastapi import HTTPException

from api.contracts.custom_plans import CustomExerciseSnapshot, CustomPlanInput
from api.services.exercise_media import load_media_index
from api.services.training_library import cache, preview


def plan_fields(store, body: CustomPlanInput, previous: dict | None = None) -> dict:
    fields = body.model_dump(mode="json")
    old = {exercise["catalogue_id"]: exercise["snapshot"]
           for session in (previous or {}).get("sessions", []) for exercise in session["exercises"]}
    exercises = [exercise for session in fields["sessions"] for exercise in session["exercises"]]
    try:
        index = cache.get() if exercises else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, "Training library is temporarily unavailable.") from None
    media = load_media_index(store) if exercises else {}
    for exercise in exercises:
        identity = exercise["catalogue_id"]
        record = index.by_id.get(identity)
        if record is not None:
            if record["summary"]["category"] != "training":
                raise HTTPException(422, "Only Training exercises can be added to custom plans.")
            snapshot = preview(record)
            snapshot["media"] = media.get(record["entry"]["exercise_key"])
            exercise["snapshot"] = CustomExerciseSnapshot.model_validate(snapshot).model_dump(mode="json")
        elif identity in old:
            # A retired catalogue identity stays reviewable in its saved draft.
            exercise["snapshot"] = old[identity]
        else:
            raise HTTPException(422, "Exercise is no longer available. Choose another Training exercise.")
        dose = exercise["dose"]
        exercise["incomplete"] = not (dose["sets"] and dose["reps"]) if dose["mode"] == "reps" else not dose["duration_seconds"]
    fields["incomplete"] = not fields["sessions"] or any(not session["exercises"] for session in fields["sessions"]) or any(exercise["incomplete"] for exercise in exercises)
    return fields
