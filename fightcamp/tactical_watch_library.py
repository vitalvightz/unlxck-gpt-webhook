from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from .config import DATA_DIR


STYLE_FAMILIES = ("distance_striker", "brawler", "counter_striker", "generic")
PHASES = ("GPP", "SPP", "TAPER")


class TacticalWatchBankExhausted(RuntimeError):
    pass


_STYLE_ALIASES = {
    "distance_striker": "distance_striker",
    "distance": "distance_striker",
    "distance_fighter": "distance_striker",
    "outside_fighter": "distance_striker",
    "out_fighter": "distance_striker",
    "outfighter": "distance_striker",
    "out_boxer": "distance_striker",
    "outboxer": "distance_striker",
    "range_fighter": "distance_striker",
    "range_striker": "distance_striker",
    "long_range_striker": "distance_striker",
    "long_range": "distance_striker",
    "brawler": "brawler",
    "pressure_fighter": "brawler",
    "pressure": "brawler",
    "inside_fighter": "brawler",
    "infighter": "brawler",
    "in_fighter": "brawler",
    "swarmer": "brawler",
    "volume_pressure": "brawler",
    "counter_striker": "counter_striker",
    "counter_puncher": "counter_striker",
    "counterpuncher": "counter_striker",
    "counter_fighter": "counter_striker",
    "counter": "counter_striker",
    "reactive_counter_fighter": "counter_striker",
    "reactive_counter": "counter_striker",
}

_STYLE_FIELDS = (
    "tactical_style",
    "tactical_styles",
    "style_tactical",
    "technical_styles",
    "style_technical",
    "fighting_style",
    "fighting_styles",
    "style",
)

_PHASE_ALIASES = {
    "gpp": "GPP",
    "general_prep": "GPP",
    "general_preparation": "GPP",
    "early_camp": "GPP",
    "base": "GPP",
    "spp": "SPP",
    "specific_prep": "SPP",
    "specific_preparation": "SPP",
    "specific": "SPP",
    "taper": "TAPER",
    "fight_week": "TAPER",
    "fightweek": "TAPER",
    "peak": "TAPER",
}


def _token(value: Any) -> str:
    text = str(value or "").strip().lower()
    for separator in (" ", "-", "/", ".", "+"):
        text = text.replace(separator, "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def normalize_tactical_style(value: Any) -> str:
    token = _token(value)
    if token in STYLE_FAMILIES:
        return token
    if token in _STYLE_ALIASES:
        return _STYLE_ALIASES[token]
    for alias, family in _STYLE_ALIASES.items():
        if alias and alias in token:
            return family
    return "generic"


def extract_tactical_style(athlete_model: dict[str, Any] | None) -> str:
    if not isinstance(athlete_model, dict):
        return "generic"
    for field in _STYLE_FIELDS:
        raw = athlete_model.get(field)
        values = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for value in values:
            family = normalize_tactical_style(value)
            if family != "generic":
                return family
    return "generic"


def normalize_camp_phase(value: Any) -> str:
    token = _token(value)
    if token.upper() in PHASES:
        return token.upper()
    return _PHASE_ALIASES.get(token, "GPP")


@dataclass(frozen=True)
class TacticalWatch:
    key: str
    name: str
    style: str
    phase: str
    why: str
    intent: str
    focus: str
    reset: str
    anchor: str
    context: str
    duration_minutes: int
    instructions: tuple[str, ...]
    progress: str


@lru_cache(maxsize=1)
def all_watches() -> tuple[TacticalWatch, ...]:
    raw = json.loads((DATA_DIR / "tactical_watch_bank.json").read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("tactical_watch_bank.json must contain a list")

    watches: list[TacticalWatch] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Tactical Watch bank entries must be objects")
        key = str(entry.get("key") or "").strip()
        name = str(entry.get("name") or "").strip()
        phases = [str(value or "").strip().upper() for value in entry.get("phases") or []]
        tags = {_token(value) for value in entry.get("tags") or []}
        mindset = entry.get("mindset") or {}
        instructions = tuple(
            str(value).strip() for value in entry.get("instructions") or [] if str(value).strip()
        )
        if not key or key in seen:
            raise ValueError(f"duplicate or blank Tactical Watch key: {key!r}")
        if not name or len(phases) != 1 or phases[0] not in PHASES:
            raise ValueError(f"invalid Tactical Watch identity: {key!r}")
        if "tactical_watch" not in tags:
            raise ValueError(f"Tactical Watch {key!r} is missing tactical_watch tag")
        style = next((family for family in STYLE_FAMILIES if family in tags), "generic")
        if not isinstance(mindset, dict) or not all(
            str(mindset.get(field) or "").strip()
            for field in ("intent", "focus", "reset", "anchor", "context")
        ):
            raise ValueError(f"Tactical Watch {key!r} has incomplete mindset content")
        if not instructions:
            raise ValueError(f"Tactical Watch {key!r} has no instructions")

        watch = TacticalWatch(
            key=key,
            name=name,
            style=style,
            phase=phases[0],
            why=str(entry.get("why") or "").strip(),
            intent=str(mindset.get("intent") or "").strip(),
            focus=str(mindset.get("focus") or "").strip(),
            reset=str(mindset.get("reset") or "").strip(),
            anchor=str(mindset.get("anchor") or "").strip(),
            context=str(mindset.get("context") or "").strip(),
            duration_minutes=int(entry.get("duration_min") or 10),
            instructions=instructions,
            progress=str(entry.get("progress") or "").strip(),
        )
        if not watch.why or not watch.progress:
            raise ValueError(f"Tactical Watch {key!r} has incomplete visible content")
        watches.append(watch)
        seen.add(key)
    return tuple(watches)


def ordered_phase_bank(style: Any, phase: Any) -> tuple[TacticalWatch, ...]:
    family = normalize_tactical_style(style)
    phase_key = normalize_camp_phase(phase)
    specific = [watch for watch in all_watches() if watch.style == family and watch.phase == phase_key]
    if family == "generic":
        return tuple(specific)
    generic = [watch for watch in all_watches() if watch.style == "generic" and watch.phase == phase_key]
    return tuple([*specific, *generic])


def select_tactical_watch(
    style: Any,
    phase: Any,
    used_keys: Iterable[str] | None = None,
) -> TacticalWatch:
    used = {str(key) for key in (used_keys or ())}
    bank = ordered_phase_bank(style, phase)
    for watch in bank:
        if watch.key not in used:
            return watch
    raise TacticalWatchBankExhausted(
        f"no unused Tactical Watch for style={style!r} phase={phase!r}"
    )


def watch_metadata(watch: TacticalWatch) -> dict[str, Any]:
    return {
        "tactical_watch_key": watch.key,
        "tactical_watch_name": watch.name,
        "tactical_watch_style": watch.style,
        "tactical_watch_phase": watch.phase,
        "tactical_watch": {
            "key": watch.key,
            "name": watch.name,
            "style": watch.style,
            "phase": watch.phase,
            "why": watch.why,
            "duration_min": watch.duration_minutes,
            "mindset": {
                "intent": watch.intent,
                "focus": watch.focus,
                "reset": watch.reset,
                "anchor": watch.anchor,
                "context": watch.context,
            },
            "instructions": list(watch.instructions),
            "progress": watch.progress,
        },
        "preferred_exercise_names": [watch.name],
        "preferred_tags": ["tactical_watch", watch.style, watch.phase.lower()],
    }


def build_watch_display_text(watch: TacticalWatch, camp_focus: str = "") -> str:
    lines = [
        "Fight Tactical Watch",
        f"Why: {watch.why}",
        "Mindset:",
        f"Intent: {watch.intent}",
        f"Focus: {watch.focus}",
        f"Reset: {watch.reset}",
        f"Anchor: {watch.anchor}",
        f"Context: {watch.context}",
        "",
        watch.name,
        f"Duration: {watch.duration_minutes} minutes",
        "Prescription:",
    ]
    lines.extend(f"- {instruction}" for instruction in watch.instructions)
    lines.append(f"Progress: {watch.progress}")
    return "\n".join(lines)


def canonical_watch_signature(watch: TacticalWatch) -> tuple[Any, ...]:
    return (
        watch.name,
        watch.why,
        watch.intent,
        watch.focus,
        watch.reset,
        watch.anchor,
        watch.context,
        tuple(watch.instructions),
        watch.progress,
    )
