from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from typing import Any, Iterable

from .config import DATA_DIR


class TacticalWatchBankExhausted(RuntimeError):
    pass


_STYLE_ALIASES = {
    "distance_striker": "distance_striker",
    "distance_fighter": "distance_striker",
    "outside_fighter": "distance_striker",
    "out_boxer": "distance_striker",
    "range_fighter": "distance_striker",
    "long_range_striker": "distance_striker",
    "brawler": "brawler",
    "pressure_fighter": "brawler",
    "inside_fighter": "brawler",
    "swarmer": "brawler",
    "volume_pressure": "brawler",
    "counter_striker": "counter_striker",
    "counter_puncher": "counter_striker",
    "counter_fighter": "counter_striker",
    "reactive_counter_fighter": "counter_striker",
}

_STYLE_FIELDS = (
    "tactical_styles",
    "style_tactical",
    "technical_styles",
    "style_technical",
    "style",
)

_VALID_PHASES = {"GPP", "SPP", "TAPER"}


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _token(value: Any) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
    )


def normalize_tactical_style(athlete_model: dict[str, Any] | None) -> str:
    athlete_model = athlete_model or {}
    for field in _STYLE_FIELDS:
        for raw in _values(athlete_model.get(field)):
            token = _token(raw)
            if token in _STYLE_ALIASES:
                return _STYLE_ALIASES[token]
    return "generic"


@lru_cache(maxsize=1)
def get_tactical_watch_bank() -> tuple[dict[str, Any], ...]:
    raw = json.loads((DATA_DIR / "tactical_watch_bank.json").read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("tactical_watch_bank.json must contain a list")

    seen: set[str] = set()
    bank: list[dict[str, Any]] = []
    required = {"key", "name", "phases", "tags", "duration_min", "why", "mindset", "instructions", "progress"}
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("tactical watch entries must be objects")
        missing = sorted(required - set(entry))
        if missing:
            raise ValueError(f"tactical watch {entry.get('key')!r} missing fields: {missing}")
        key = str(entry.get("key") or "").strip()
        if not key or key in seen:
            raise ValueError(f"duplicate or blank tactical watch key: {key!r}")
        phases = {str(phase or "").strip().upper() for phase in entry.get("phases") or []}
        if not phases or not phases <= _VALID_PHASES:
            raise ValueError(f"tactical watch {key!r} has invalid phases: {sorted(phases)}")
        tags = {_token(tag) for tag in entry.get("tags") or []}
        if "tactical_watch" not in tags:
            raise ValueError(f"tactical watch {key!r} must include tactical_watch tag")
        mindset = entry.get("mindset") or {}
        if not isinstance(mindset, dict) or not all(
            str(mindset.get(field) or "").strip()
            for field in ("intent", "focus", "reset", "anchor", "context")
        ):
            raise ValueError(f"tactical watch {key!r} has incomplete mindset")
        if not isinstance(entry.get("instructions"), list) or not entry.get("instructions"):
            raise ValueError(f"tactical watch {key!r} must include instructions")
        seen.add(key)
        bank.append(entry)
    return tuple(bank)


def _eligible(
    *,
    phase: str,
    style: str,
    used_keys: set[str],
) -> Iterable[dict[str, Any]]:
    for watch in get_tactical_watch_bank():
        key = str(watch["key"])
        if key in used_keys:
            continue
        phases = {str(value).strip().upper() for value in watch.get("phases") or []}
        tags = {_token(value) for value in watch.get("tags") or []}
        if phase in phases and style in tags:
            yield watch


def select_tactical_watch(
    athlete_model: dict[str, Any] | None,
    phase: str,
    *,
    used_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    resolved_phase = str(phase or "").strip().upper()
    if resolved_phase not in _VALID_PHASES:
        raise ValueError(f"unsupported tactical watch phase: {phase!r}")

    used = {str(key) for key in (used_keys or []) if str(key).strip()}
    style = normalize_tactical_style(athlete_model)

    if style != "generic":
        selected = next(_eligible(phase=resolved_phase, style=style, used_keys=used), None)
        if selected is not None:
            return deepcopy(selected)

    selected = next(_eligible(phase=resolved_phase, style="generic", used_keys=used), None)
    if selected is not None:
        return deepcopy(selected)

    raise TacticalWatchBankExhausted(
        f"No unused Tactical Watch remains for style={style} phase={resolved_phase}"
    )


def render_tactical_watch(watch: dict[str, Any]) -> str:
    mindset = watch.get("mindset") or {}
    duration = int(watch.get("duration_min") or 10)
    lines = [
        "Fight Tactical Watch",
        f"Why: {watch['why']}",
        "Mindset:",
        f"Intent: {mindset['intent']}",
        f"Focus: {mindset['focus']}",
        f"Reset: {mindset['reset']}",
        f"Anchor: {mindset['anchor']}",
        f"Context: {mindset['context']}",
        "",
        str(watch["name"]),
        f"Duration: {duration} minutes",
        "Prescription:",
    ]
    lines.extend(f"- {instruction}" for instruction in watch.get("instructions") or [])
    lines.append(f"Progress: {watch['progress']}")
    return "\n".join(lines)
