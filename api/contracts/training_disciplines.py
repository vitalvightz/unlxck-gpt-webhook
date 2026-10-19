"""Optional sport and session type for manual training (shared/training-disciplines.json).

They describe what was trained. ``activity`` stays the stored high-level kind:
each sport/session-type pair maps to exactly one activity, so the sparring
follow-up and older readers keep working. Neither field is workload, contact
exposure or clearance evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

_PATH = Path(__file__).resolve().parents[2] / "shared" / "training-disciplines.json"
_ACTIVITIES = {"sparring", "boxing", "roadwork", "strength", "conditioning", "other"}


def _load() -> dict[str, dict[str, Any]]:
    try:
        sports = json.loads(_PATH.read_text(encoding="utf-8"))["sports"]
    except FileNotFoundError as exc:
        raise RuntimeError(f"Training disciplines are missing at {_PATH}. "
                           "Ensure shared/training-disciplines.json is packaged.") from exc
    loaded = {}
    for sport in sports:
        types = {item["id"]: item for item in sport["session_types"]}
        if sport["id"] in loaded or len(types) != len(sport["session_types"]):
            raise RuntimeError("Training discipline ids must be unique")
        if {sport["activity"], *(item.get("activity", sport["activity"]) for item in types.values())} - _ACTIVITIES:
            raise RuntimeError("Training disciplines must map to an existing activity")
        loaded[sport["id"]] = {**sport, "session_types": types}
    return loaded


SPORTS = _load()
Sport = Literal[tuple(SPORTS)]  # type: ignore[valid-type]
SessionType = Literal[tuple(sorted({key for sport in SPORTS.values() for key in sport["session_types"]}))]  # type: ignore[valid-type]


def discipline_error(activity: str, sport: str | None, session_type: str | None) -> str | None:
    """Why this combination cannot be stored, or None. No sport keeps any activity."""
    if sport is None:
        return "Choose a sport for this session type." if session_type is not None else None
    entry = SPORTS[sport]
    kind = entry["session_types"].get(session_type) if session_type is not None else None
    if session_type is not None and kind is None:
        return f"{session_type} is not a {entry['label']} session type."
    if activity != (kind or entry).get("activity", entry["activity"]):
        return "Activity does not match the sport and session type."
    return None


def training_title(row: dict) -> str:
    """"Muay Thai · Clinch" when a sport is known; otherwise the activity, as before."""
    entry = SPORTS.get(row.get("sport") or "")
    if not entry:
        return str(row["activity"]).title()
    kind = entry["session_types"].get(row.get("session_type") or "")
    return f"{entry['label']} · {kind['label']}" if kind else entry["label"]
