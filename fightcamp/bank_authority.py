"""Neutral lookup of original exercise-bank authority rows."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .config import DATA_DIR


_CANONICAL_PHASES = ("GPP", "SPP", "TAPER")


def _normalise_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _normalise_phase(value: object) -> str:
    phase = str(value or "").strip().upper()
    return phase if phase in _CANONICAL_PHASES else ""


def _normalise_phase_list(value: object) -> set[str]:
    values = [value] if isinstance(value, str) else list(value or [])
    return {
        phase
        for phase in (_normalise_phase(item) for item in values)
        if phase
    }


def _iter_training_items(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_training_items(item)
        return
    if not isinstance(value, dict):
        return

    if str(value.get("name") or "").strip() and value.get("phases") is not None:
        yield value
    for nested in value.values():
        if isinstance(nested, (dict, list)):
            yield from _iter_training_items(nested)


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


@lru_cache(maxsize=1)
def _bank_indexes() -> dict[str, dict[str, list[dict[str, Any]]]]:
    sources = {
        "strength_slots": [DATA_DIR / "exercise_bank.json"],
        "conditioning_slots": [
            DATA_DIR / "conditioning_bank.json",
            DATA_DIR / "style_conditioning_bank.json",
        ],
    }
    coordination_dir = DATA_DIR / "coordination"
    if coordination_dir.exists():
        sources["conditioning_slots"].extend(sorted(coordination_dir.rglob("*.json")))

    indexes = {slot_group: {} for slot_group in sources}
    for slot_group, paths in sources.items():
        for path in paths:
            for item in _iter_training_items(_load_json(path)):
                key = _normalise_name(item.get("name"))
                if key:
                    indexes[slot_group].setdefault(key, []).append(item)
    return indexes


def original_bank_entries(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve original rows, using source phase only as a provenance hint."""
    slot_group = str(assignment.get("slot_group") or "").strip()
    if slot_group not in _bank_indexes():
        return []

    entries = list(
        _bank_indexes()[slot_group].get(_normalise_name(assignment.get("name")), [])
    )
    source_phase = _normalise_phase(assignment.get("source_phase"))
    if not source_phase or not entries:
        return entries

    narrowed = [
        item
        for item in entries
        if source_phase in _normalise_phase_list(item.get("phases"))
    ]
    return narrowed or entries
