"""Choose editable dose fields from a drill's own instructions, not its bank."""
from __future__ import annotations

import re
from typing import Any, Mapping

from fastapi import HTTPException

from api.services.custom_plans import source_suggestion

_TIME = r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|min)\b"
_DISTANCE = r"(\d+(?:\.\d+)?)\s*(kilometers?|kilometres?|km|meters?|metres?|m|miles?|mi|yards?|yds?)\b"


def _seconds(match: re.Match) -> int:
    return round(float(match[1]) * (60 if match[2].lower().startswith("m") else 1))


def dose_guidance(record: Mapping[str, Any]) -> tuple[str, dict | None, dict]:
    """Mode, trustworthy complete dose, and editable source hints.

    Format evidence can be useful even when the bank's numbers conflict or are
    incomplete. Those hints require athlete confirmation; they never become an
    automatic prescription. The existing strict source parser owns full doses.
    """
    entry = record["entry"]
    raw = entry["raw"]
    text = str(raw.get("duration") or raw.get("prescription") or "").strip()
    name = entry["name"].lower()
    try:
        source = source_suggestion(entry["catalogue_id"]).dose
    except HTTPException:
        source = None
    if source and source.mode != "text":
        dose = source.model_dump(mode="json", exclude_none=True)
        return source.mode, dose, dose

    # Distance comes before time: 6 x 15 yards must never mean 15 seconds.
    distance = re.search(_DISTANCE, text, re.I)
    if distance:
        unit = distance[2].lower()
        unit = "km" if unit.startswith("k") else "mi" if unit.startswith("mi") else "yd" if unit.startswith(("y", "yd")) else "m"
        suggested: dict = {"mode": "distance", "distance": float(distance[1]), "distance_unit": unit}
        repeats = re.search(r"(\d+)\s*[x×]", text, re.I)
        if repeats:
            suggested["sets"] = int(repeats[1])
        return "distance", None, suggested

    timed = re.search(_TIME, text, re.I)
    repeated = re.search(r"(?:[x×]\s*(\d+)\s*(?:reps|rounds|sets)?\b|\b(\d+)\s*[x×])", text, re.I)
    reps = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\s*reps?\b", text, re.I)
    if reps and not timed:
        return "reps", None, {"mode": "reps", "sets": int(reps[1]), "reps": int(reps[2])}
    if timed and (repeated or raw.get("rounds") or re.search(r"interval|\bon\b|\bwork\b|\brest\b", text, re.I)):
        suggested = {"mode": "intervals", "work_seconds": _seconds(timed)}
        if repeated:
            suggested["rounds"] = int(repeated[1] or repeated[2])
        elif isinstance(raw.get("rounds"), int) and not isinstance(raw["rounds"], bool):
            suggested["rounds"] = raw["rounds"]
        rest = re.search(_TIME + r"\s*(?:rest|off|reset)\b", text, re.I)
        if rest:
            suggested["rest_seconds"] = _seconds(rest)
        elif isinstance(raw.get("rest_sec"), int) and not isinstance(raw["rest_sec"], bool):
            suggested["rest_seconds"] = raw["rest_sec"]
        return "intervals", None, suggested

    movement = str(raw.get("movement") or "").lower()
    if movement in {"isometric", "isometric_hold"} or re.search(r"\b(?:isometric|plank|hold|hang)\b", name):
        return "duration", None, {"mode": "duration"}
    if timed and not re.search(r"[x×]|circuit|emom|amrap|\+", text, re.I):
        # Ranges identify a format but do not silently select the upper limit.
        suggested = {"mode": "duration"}
        if not re.search(r"\d\s*[-–]\s*\d", text):
            suggested["duration_seconds"] = _seconds(timed)
        return "duration", None, suggested
    if re.search(r"\b(?:carry|carries|sled push|sled drag|sprint)\b", name):
        return "distance", None, {"mode": "distance", "distance_unit": "m"}
    if raw.get("work_sec") or raw.get("rounds") or re.search(r"interval|rounds?|bursts?|hill runs|rope", name):
        suggested = {"mode": "intervals"}
        for source_field, field in (("rounds", "rounds"), ("work_sec", "work_seconds"), ("rest_sec", "rest_seconds")):
            value = raw.get(source_field)
            if isinstance(value, int) and not isinstance(value, bool):
                suggested[field] = value
        return "intervals", None, suggested
    if raw.get("total_minutes") or entry.get("content_class") == "technical_coordination":
        return "duration", None, {"mode": "duration"}
    if entry["source"] == "exercise_bank.json":
        return "reps", None, {"mode": "reps"}
    # Complex circuits keep their actual instruction instead of fake rep work.
    return "text", None, {"mode": "text", "prescription": text[:500]}
