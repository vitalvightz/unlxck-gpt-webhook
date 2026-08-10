from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
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
_DECLARED_STYLE_FIELDS = (
    "tactical_style",
    "tactical_styles",
    "style_tactical",
)
_CANONICAL_DISPLAY_LABELS = {
    "pressure_fighter": "Pressure Fighter",
    "counter_striker": "Counter Striker",
    "distance_striker": "Distance Striker",
    "clinch_fighter": "Clinch Fighter",
    "grappler": "Grappler",
    "hybrid": "Hybrid",
    # Legacy athlete-selectable wording is preserved rather than silently
    # relabelled to the current parent family.
    "brawler": "Brawler",
}


def _token(value: Any) -> str:
    text = str(value or "").strip().lower()
    for separator in (" ", "-", "/", ".", "+"):
        text = text.replace(separator, "_")
    return "_".join(part for part in text.split("_") if part)


def _display_label(value: Any) -> str:
    raw = str(value or "").strip()
    token = _token(raw)
    if not token:
        return ""
    canonical = _CANONICAL_DISPLAY_LABELS.get(token)
    if canonical:
        return canonical
    # Unknown/legacy selections keep their own wording instead of being renamed
    # to an internal family. This is display formatting only, not taxonomy.
    return " ".join(part.capitalize() for part in token.split("_") if part)


def declared_tactical_style_labels(athlete_model: dict[str, Any] | None) -> list[str]:
    """Return athlete-facing tactical identity labels without programming aliases.

    Runtime planning lowercases tactical selections and, for historical reasons,
    appends ``hybrid`` to ``style_tactical`` when the athlete's *stance* is Hybrid.
    That appended value is a programming signal, not a second tactical identity.
    Modern intake permits one tactical selection, so a trailing Hybrid alongside
    another tactical value is the stance-derived signal and must stay internal.
    """
    if not isinstance(athlete_model, dict):
        return []

    raw_values: list[Any] = []
    for field in _DECLARED_STYLE_FIELDS:
        raw = athlete_model.get(field)
        if raw is None:
            continue
        values = raw if isinstance(raw, (list, tuple, set)) else [raw]
        raw_values.extend(value for value in values if str(value or "").strip())
        if raw_values:
            break

    if len(raw_values) > 1 and _token(raw_values[-1]) == "hybrid":
        raw_values = raw_values[:-1]

    labels: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        token = _token(value)
        label = _display_label(value)
        if not token or not label or token in seen:
            continue
        seen.add(token)
        labels.append(label)
    return labels


class TacticalStyleSelection(str):
    """Internal style-family key carrying the athlete's separate display label.

    It remains a real ``str`` (e.g. ``selection == "brawler"``) so existing
    programming/scoring callers keep the same contract. ``select_tactical_watch``
    reads ``display_label`` only when producing the selected watch for rendering.
    """

    display_label: str

    def __new__(cls, family: str, display_label: str = "") -> "TacticalStyleSelection":
        instance = str.__new__(cls, family)
        instance.display_label = str(display_label or "").strip()
        return instance


def normalize_tactical_style(value: Any) -> str:
    token = _token(value)
    if token in _STYLE_ALIASES:
        return _STYLE_ALIASES[token]
    for alias, family in _STYLE_ALIASES.items():
        if alias and alias in token:
            return family
    return "generic"


def extract_tactical_style(athlete_model: dict[str, Any] | None) -> TacticalStyleSelection:
    if not isinstance(athlete_model, dict):
        return TacticalStyleSelection("generic")

    declared_labels = declared_tactical_style_labels(athlete_model)
    declared_label = declared_labels[0] if declared_labels else ""

    for field in _STYLE_FIELDS:
        raw = athlete_model.get(field)
        values = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for value in values:
            style = normalize_tactical_style(value)
            if style != "generic":
                display_label = declared_label if normalize_tactical_style(declared_label) == style else _display_label(value)
                return TacticalStyleSelection(style, display_label)
    return TacticalStyleSelection("generic")


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
    display_style: str = ""


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
    display_style = str(getattr(style, "display_label", "") or "").strip()
    for watch in ordered_phase_bank(style, phase):
        if watch.key not in used:
            if display_style and watch.style != "generic":
                return replace(watch, display_style=display_style)
            return watch
    raise TacticalWatchBankExhausted(
        f"no unused Tactical Watch for style={style!r} phase={phase!r}"
    )


def _athlete_visible_watch_text(watch: TacticalWatch, text: str) -> str:
    """Swap only the internal family noun for the athlete's declared label."""
    visible = str(text or "")
    display_style = str(watch.display_style or "").strip()
    if not visible or not display_style or watch.style == "generic":
        return visible
    family_phrase = watch.style.replace("_", " ")
    return re.sub(
        rf"\b{re.escape(family_phrase)}\b",
        display_style.lower(),
        visible,
        flags=re.IGNORECASE,
    )


def watch_metadata(watch: TacticalWatch) -> dict[str, Any]:
    mindset = {
        "intent": _athlete_visible_watch_text(watch, watch.intent),
        "focus": _athlete_visible_watch_text(watch, watch.focus),
        "reset": _athlete_visible_watch_text(watch, watch.reset),
        "anchor": _athlete_visible_watch_text(watch, watch.anchor),
        "context": _athlete_visible_watch_text(watch, watch.context),
    }
    visible_why = _athlete_visible_watch_text(watch, watch.why)
    visible_instructions = [
        _athlete_visible_watch_text(watch, instruction) for instruction in watch.instructions
    ]
    visible_progress = _athlete_visible_watch_text(watch, watch.progress)
    return {
        "tactical_watch_key": watch.key,
        "tactical_watch_name": watch.name,
        "tactical_watch_style": watch.style,
        "tactical_watch_display_style": watch.display_style or None,
        "tactical_watch_phase": watch.phase,
        "tactical_watch": {
            "key": watch.key,
            "name": watch.name,
            "style": watch.style,
            "display_style": watch.display_style or None,
            "phase": watch.phase,
            "why": visible_why,
            "duration_min": watch.duration_minutes,
            "mindset": mindset,
            "instructions": visible_instructions,
            "progress": visible_progress,
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

    Bank wording remains authoritative for the drill itself. When the selected
    bank family is an internal alias (for example ``brawler`` for an athlete who
    selected ``Pressure Fighter``), only that family noun is rewritten in visible
    prose; selection tags and programming metadata stay internal and unchanged.
    """
    lines = [
        f"Why: {_athlete_visible_watch_text(watch, watch.why)}",
        f"- {watch.name}: {watch.duration_minutes} minutes, tactical review only. No physical load.",
        *(
            f"  Step {index}: {_athlete_visible_watch_text(watch, instruction)}"
            for index, instruction in enumerate(watch.instructions, start=1)
        ),
        f"  Intent: {_athlete_visible_watch_text(watch, watch.intent)}",
        f"  Focus: {_athlete_visible_watch_text(watch, watch.focus)}",
        f"  Reset: {_athlete_visible_watch_text(watch, watch.reset)}",
        f"  Anchor: {_athlete_visible_watch_text(watch, watch.anchor)}",
        f"  Purpose: {_athlete_visible_watch_text(watch, watch.context)}",
        f"  Progress: {_athlete_visible_watch_text(watch, watch.progress)}",
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
