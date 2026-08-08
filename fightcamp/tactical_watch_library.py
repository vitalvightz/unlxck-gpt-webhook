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
    "distance_fighter": "distance_striker",
    "outside_fighter": "distance_striker",
    "out_boxer": "distance_striker",
    "outboxer": "distance_striker",
    "outfighter": "distance_striker",
    "range_fighter": "distance_striker",
    "range_striker": "distance_striker",
    "long_range_striker": "distance_striker",
    "brawler": "brawler",
    "pressure": "brawler",
    "pressure_fighter": "brawler",
    "inside_fighter": "brawler",
    "in_fighter": "brawler",
    "infighter": "brawler",
    "swarmer": "brawler",
    "volume_pressure": "brawler",
    "counter": "counter_striker",
    "counter_striker": "counter_striker",
    "counter_puncher": "counter_striker",
    "counterpuncher": "counter_striker",
    "counter_fighter": "counter_striker",
    "reactive_counter": "counter_striker",
    "reactive_counter_fighter": "counter_striker",
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


def _token(value: Any) -> str:
    text = str(value or "").strip().lower()
    for separator in (" ", "-", "/", ".", "+"):
        text = text.replace(separator, "_")
    return "_".join(part for part in text.split("_") if part)


def normalize_tactical_style(value: Any) -> str:
    token = _token(value)
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
            style = normalize_tactical_style(value)
            if style != "generic":
                return style
    return "generic"


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
        instructions = tuple(str(value).strip() for value in entry.get("instructions") or [] if str(value).strip())

        if not key or key in seen:
            raise ValueError(f"duplicate or blank Tactical Watch key: {key!r}")
        if not name or len(phases) != 1 or phases[0] not in PHASES:
            raise ValueError(f"invalid Tactical Watch identity: {key!r}")
        if "tactical_watch" not in tags:
            raise ValueError(f"Tactical Watch {key!r} is missing tactical_watch tag")
        style_tags = tags & set(STYLE_FAMILIES)
        if len(style_tags) != 1:
            raise ValueError(f"Tactical Watch {key!r} needs one style tag")
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
            style=next(iter(style_tags)),
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
    phase_key = str(phase or "GPP").strip().upper()
    if phase_key not in PHASES:
        phase_key = "GPP"
    specific = [watch for watch in all_watches() if watch.style == family and watch.phase == phase_key]
    if family == "generic":
        return tuple(specific)
    generic = [watch for watch in all_watches() if watch.style == "generic" and watch.phase == phase_key]
    return tuple(specific + generic)


def select_tactical_watch(
    style: Any,
    phase: Any,
    used_keys: Iterable[str] | None = None,
) -> TacticalWatch:
    used = {str(key) for key in (used_keys or ())}
    for watch in ordered_phase_bank(style, phase):
        if watch.key not in used:
            return watch
    raise TacticalWatchBankExhausted(
        f"no unused Tactical Watch for style={style!r} phase={phase!r}"
    )


def watch_metadata(watch: TacticalWatch) -> dict[str, Any]:
    mindset = {
        "intent": watch.intent,
        "focus": watch.focus,
        "reset": watch.reset,
        "anchor": watch.anchor,
        "context": watch.context,
    }
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
            "mindset": mindset,
            "instructions": list(watch.instructions),
            "progress": watch.progress,
        },
        "preferred_exercise_names": [watch.name],
        "preferred_tags": ["tactical_watch", watch.style, watch.phase.lower()],
        "governance": {
            "selected_drill_locked": True,
            "selected_drill_name": watch.name,
            "render_selected_drill_exactly": True,
            "do_not_reselect_or_generalize": True,
        },
    }


def build_watch_display_text(watch: TacticalWatch) -> str:
    """Render the selected watch in the shared athlete-facing session-body shape.

    Every other session in the plan reads the same way: an unbulleted ``Why:``
    objective, one bulleted activity heading (``- Name: dose``), then indented
    labelled lines that belong to that activity. The watch used to emit a layout
    of its own — a bare title line, a ``Mindset:`` / ``Prescription:`` header
    stack, and one bullet per instruction — and both renderers read those
    peer-level lines as *separate exercises*: the drill name, duration and the
    bare ``Prescription:`` header landed in the session objective, every
    instruction became its own load-less block, and the mindset lines piled onto
    whichever block happened to be last. Emitting the shared contract keeps the
    whole watch as one card with its own name, dose and coaching detail.

    The bank's wording is passed through untouched; only the line shape and the
    labels that introduce each line are chosen here.
    """
    lines = [
        f"Why: {watch.why}",
        f"- {watch.name}: {watch.duration_minutes} minutes, tactical review only. No physical load.",
        *(
            f"  Step {index}: {instruction}"
            for index, instruction in enumerate(watch.instructions, start=1)
        ),
        f"  Intent: {watch.intent}",
        f"  Focus: {watch.focus}",
        f"  Reset: {watch.reset}",
        f"  Anchor: {watch.anchor}",
        f"  Purpose: {watch.context}",
        f"  Progress: {watch.progress}",
    ]
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
        watch.instructions,
        watch.progress,
    )
