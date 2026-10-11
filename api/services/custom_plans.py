"""Owner-scoped custom draft storage only; no planner, readiness or completion writes."""

import re

from fastapi import HTTPException

from api.contracts.custom_plans import (
    CustomDose,
    CustomDoseSuggestion,
    CustomExerciseSnapshot,
    CustomPlanInput,
)
from api.services.exercise_media import load_media_index
from api.services.training_library import cache, preview


def plan_fields(store, body: CustomPlanInput, previous: dict | None = None) -> dict:
    fields = body.model_dump(mode="json")
    old = {
        exercise["catalogue_id"]: exercise["snapshot"]
        for session in (previous or {}).get("sessions", [])
        for exercise in session["exercises"]
        if "catalogue_id" in exercise
    }
    exercises = [
        exercise for session in fields["sessions"] for exercise in session["exercises"]
    ]
    try:
        index = (
            cache.get() if any(e["origin"] == "catalogue" for e in exercises) else None
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(
            503, "Training library is temporarily unavailable."
        ) from None
    media = (
        load_media_index(store)
        if any(e["origin"] == "catalogue" for e in exercises)
        else {}
    )
    previous_ids = {
        e["id"]: e for s in (previous or {}).get("sessions", []) for e in s["exercises"]
    }
    for exercise in exercises:
        prior = previous_ids.get(exercise["id"])
        if prior and (
            prior.get("origin", "catalogue") != exercise["origin"]
            or prior.get("catalogue_id") != exercise.get("catalogue_id")
        ):
            raise HTTPException(
                422,
                "An exercise occurrence cannot change origin or catalogue identity.",
            )
        exercise["incomplete"] = dose_incomplete(exercise["dose"])
        if exercise["origin"] == "manual":
            continue
        identity = exercise["catalogue_id"]
        record = index.by_id.get(identity)
        if record is not None:
            if record["summary"]["category"] != "training":
                raise HTTPException(
                    422, "Only Training exercises can be added to custom plans."
                )
            snapshot = preview(record)
            snapshot["media"] = media.get(record["entry"]["exercise_key"])
            exercise["snapshot"] = CustomExerciseSnapshot.model_validate(
                snapshot
            ).model_dump(mode="json")
        elif identity in old:
            # A retired catalogue identity stays reviewable in its saved draft.
            exercise["snapshot"] = old[identity]
        else:
            raise HTTPException(
                422,
                "Exercise is no longer available. Choose another Training exercise.",
            )
    fields["incomplete"] = (
        not fields["sessions"]
        or any(not session["exercises"] for session in fields["sessions"])
        or any(exercise["incomplete"] for exercise in exercises)
    )
    return fields


def dose_incomplete(dose):
    mode = dose["mode"]
    if mode == "reps":
        return not (dose.get("sets") and dose.get("reps"))
    if mode == "duration":
        return not dose.get("duration_seconds") or bool(dose.get("distance")) != bool(
            dose.get("distance_unit")
        )
    if mode == "intervals":
        return (
            not (dose.get("rounds") and dose.get("work_seconds"))
            or dose.get("rest_seconds") is None
        )
    return not (dose.get("prescription") or "").strip()


def source_suggestion(catalogue_id: str):
    """Read current bank evidence only; ambiguous formats remain editable text."""
    try:
        record = cache.get().by_id.get(catalogue_id)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(
            503, "Training library is temporarily unavailable."
        ) from None
    if not record or record["summary"]["category"] != "training":
        raise HTTPException(404, "Training exercise not found.")
    snapshot = preview(record)
    raw = record["entry"]["raw"]
    original = str(raw.get("duration") or raw.get("prescription") or "")
    evidence = {
        key: raw[key]
        for key in (
            "rounds",
            "work_sec",
            "rest_sec",
            "total_minutes",
            "rpe",
            "sets",
            "reps",
        )
        if raw.get(key) is not None
    }
    if evidence:
        original = " · ".join(
            filter(
                None, [original, ", ".join(f"{k}: {v}" for k, v in evidence.items())]
            )
        )
    dose = None
    try:

        def number(key):
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return value

        rounds, work, rest, total = (
            number(k) for k in ("rounds", "work_sec", "rest_sec", "total_minutes")
        )
        duration = str(raw.get("duration") or raw.get("prescription") or "").strip()
        intervals = re.fullmatch(
            r"(\d+)\s*[x×]\s*(\d+)\s*min\s*(?:rounds?)?,?\s*(\d+)\s*s\s*rest", duration, re.I
        )
        continuous = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(min|minutes?|s|sec|seconds?)(?:\s+continuous)?",
            duration,
            re.I,
        )
        if rounds is not None and work is not None and rest is not None:
            agrees = not duration or (
                intervals
                and (int(intervals[1]), int(intervals[2]) * 60, int(intervals[3]))
                == (rounds, work, rest)
            )
            totals = (
                (rounds * work + (rounds - 1) * rest) / 60,
                (rounds * work + rounds * rest) / 60,
            )
            if agrees and (total is None or total in totals):
                dose = CustomDose(
                    mode="intervals",
                    rounds=rounds,
                    work_seconds=work,
                    rest_seconds=rest,
                )
        elif (
            rounds is None
            and rest is None
            and total is not None
            and (not duration or continuous)
        ):
            seconds = float(total) * 60
            parsed = (
                float(continuous[1])
                * (60 if continuous[2].lower().startswith("min") else 1)
                if continuous
                else seconds
            )
            if parsed == seconds and (work is None or work == seconds):
                dose = (
                    CustomDose(mode="duration", duration_seconds=int(seconds))
                    if seconds.is_integer()
                    else None
                )
        elif set(evidence) <= {"rpe"} and continuous:
            seconds = float(continuous[1]) * (
                60 if continuous[2].lower().startswith("min") else 1
            )
            if seconds.is_integer():
                dose = CustomDose(mode="duration", duration_seconds=int(seconds))
        elif (
            not duration
            and set(evidence) <= {"sets", "reps", "rest_sec", "rpe"}
            and number("sets") is not None
            and number("reps") is not None
        ):
            dose = CustomDose(
                mode="reps", sets=number("sets"), reps=number("reps"), rest_seconds=rest
            )
        allowed = {
            "intervals": {"rounds", "work_sec", "rest_sec", "total_minutes", "rpe"},
            "duration": {"work_sec", "total_minutes", "rpe"},
            "reps": {"sets", "reps", "rest_sec", "rpe"},
        }
        if dose and (
            not set(evidence) <= allowed[dose.mode]
            or any(number(key) is None for key in evidence)
        ):
            dose = None
        if dose and number("rpe") is not None:
            dose = CustomDose.model_validate(
                {**dose.model_dump(), "rpe": number("rpe")}
            )
    except (ValueError, TypeError):
        dose = None
    if dose is None and original:
        dose = CustomDose(mode="text", prescription=original[:500])
    return CustomDoseSuggestion(
        dose=dose,
        original=original,
        source=snapshot["source"],
        source_revision=snapshot["source_revision"],
        row_revision=snapshot["row_revision"],
    )
