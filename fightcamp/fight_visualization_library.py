"""Bank-driven Fight Visualisation selection for the mandatory taper countdown.

This mirrors ``tactical_watch_library`` deliberately: one JSON bank is the sole
source of athlete-facing text, one selector resolves it, and one metadata helper
stamps the governed role. It does **not** re-declare taxonomy -- sport identity
comes from :mod:`fightcamp.sports` and tactical-style identity comes from
``tactical_watch_library`` (including the boxing ``pressure_fighter`` ->
``brawler`` programming alias), so an athlete resolves to the same style family
here as everywhere else in the planner.

Content is selected by ``sport -> tactical style -> countdown day``. D-7/D-5/D-3
carry the strongest style ownership; D-1/D-0 are sport-scoped on purpose, because
the psychological job (familiarity, then trusted automaticity) is the same for
every style in a sport and fabricating style variants there would only duplicate
copy.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

from .config import DATA_DIR
from .sports import normalize_sport, planning_format
from .tactical_watch_library import (
    STYLE_FAMILIES,
    TacticalStyleSelection,
    extract_tactical_style,
    normalize_tactical_style,
)

# The mandatory countdown interventions. These are protocol, not gap filler:
# they stay in the plan whatever else the day carries and whatever the athlete's
# physical load is.
FIGHT_VISUALIZATION_COUNTDOWN_DAYS = (7, 5, 3, 1, 0)

ROLE_KEY = "fight_visualization"
ATHLETE_FACING_LABEL = "Fight Visualisation"

BANK_SPORTS = ("boxing", "kickboxing", "mma", "cross_sport")
_BANK_STYLES = frozenset(STYLE_FAMILIES)

# Planning-family reuse only. ``planning_format`` already resolves muay thai,
# wrestling, BJJ, grappling and karate onto an existing family; the one extra
# hop here is muay_thai, which has no bank of its own and shares kickboxing's
# striking situations.
_PLANNING_FAMILY_TO_BANK = {"muay_thai": "kickboxing"}


class FightVisualizationBankError(ValueError):
    pass


@dataclass(frozen=True)
class FightVisualization:
    key: str
    name: str
    countdown_day: int
    sports: tuple[str, ...]
    styles: tuple[str, ...]
    duration_min: tuple[int, int]
    why: str
    instructions: tuple[str, ...]
    cue: str
    pre_bout: str = ""
    # Deterministic selection provenance. Empty string means an exact
    # sport + style + countdown-day match was available.
    fallback_reason: str = ""
    requested_sport: str = ""
    requested_style: str = ""


@lru_cache(maxsize=1)
def all_visualizations() -> tuple[FightVisualization, ...]:
    raw = json.loads(
        (DATA_DIR / "fight_visualization_bank.json").read_text(encoding="utf-8")
    )
    if not isinstance(raw, list) or not raw:
        raise FightVisualizationBankError(
            "fight_visualization_bank.json must contain a non-empty list"
        )

    entries: list[FightVisualization] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise FightVisualizationBankError("bank entries must be objects")
        key = str(entry.get("key") or "").strip()
        if not key or key in seen:
            raise FightVisualizationBankError(f"duplicate or blank key: {key!r}")
        seen.add(key)

        name = str(entry.get("name") or "").strip()
        if not name:
            raise FightVisualizationBankError(f"{key!r} has no name")

        countdown_day = entry.get("countdown_day")
        if countdown_day not in FIGHT_VISUALIZATION_COUNTDOWN_DAYS:
            raise FightVisualizationBankError(
                f"{key!r} countdown_day must be one of "
                f"{list(FIGHT_VISUALIZATION_COUNTDOWN_DAYS)}"
            )

        sports = tuple(normalize_sport(value) for value in entry.get("sports") or [])
        if not sports or set(sports) - set(BANK_SPORTS):
            raise FightVisualizationBankError(f"{key!r} has unsupported sport ownership")

        styles = tuple(
            str(value or "").strip().lower() for value in entry.get("styles") or []
        )
        if not styles or set(styles) - _BANK_STYLES:
            raise FightVisualizationBankError(f"{key!r} has unsupported style ownership")

        duration = entry.get("duration_min") or []
        if (
            not isinstance(duration, list)
            or len(duration) != 2
            or not all(isinstance(value, int) and value > 0 for value in duration)
            or duration[0] > duration[1]
        ):
            raise FightVisualizationBankError(f"{key!r} duration_min must be [min, max]")

        why = str(entry.get("why") or "").strip()
        cue = str(entry.get("cue") or "").strip()
        instructions = tuple(
            str(value).strip()
            for value in entry.get("instructions") or []
            if str(value).strip()
        )
        if not why or not cue:
            raise FightVisualizationBankError(f"{key!r} has incomplete visible content")
        # Concise-by-contract: a bank record is a card the athlete reads in one
        # pass, not a script. These bounds are asserted at load so the bank
        # cannot silently drift back into long-form prose.
        if not 3 <= len(instructions) <= 6:
            raise FightVisualizationBankError(
                f"{key!r} must carry 3-6 coaching instructions, got {len(instructions)}"
            )
        word_count = len(" ".join((why, *instructions, cue)).split())
        if word_count > 120:
            raise FightVisualizationBankError(
                f"{key!r} is {word_count} words; bank records stay concise"
            )

        entries.append(
            FightVisualization(
                key=key,
                name=name,
                countdown_day=int(countdown_day),
                sports=sports,
                styles=styles,
                duration_min=(int(duration[0]), int(duration[1])),
                why=why,
                instructions=instructions,
                cue=cue,
                pre_bout=str(entry.get("pre_bout") or "").strip(),
            )
        )

    missing = set(FIGHT_VISUALIZATION_COUNTDOWN_DAYS) - {
        entry.countdown_day for entry in entries
    }
    if missing:
        raise FightVisualizationBankError(
            f"bank is missing mandatory countdown days: {sorted(missing)!r}"
        )

    # The last rung of the selection ladder. Every athlete, whatever their sport
    # or style, must land on exactly one universal entry per countdown day --
    # otherwise a future bank edit could delete the safety net (leaving
    # select_fight_visualization returning None for a mandatory day) or add a
    # second one (making the fallback depend on file order) while the JSON still
    # validated cleanly.
    for countdown_day in FIGHT_VISUALIZATION_COUNTDOWN_DAYS:
        universal = [
            entry.key
            for entry in entries
            if entry.countdown_day == countdown_day
            and "cross_sport" in entry.sports
            and "generic" in entry.styles
        ]
        if len(universal) != 1:
            raise FightVisualizationBankError(
                f"D-{countdown_day} needs exactly one cross_sport generic "
                f"fallback, found {len(universal)}: {sorted(universal)!r}"
            )
    return tuple(entries)


def bank_sport(value: Any) -> str:
    """Resolve any athlete sport onto the bank's owning sport, or ''."""
    sport = normalize_sport(value)
    if sport in BANK_SPORTS:
        return sport
    family = planning_format(sport, fallback=None)
    if family is None:
        return ""
    family = _PLANNING_FAMILY_TO_BANK.get(family, family)
    return family if family in BANK_SPORTS else ""


def _style_family(sport: Any, tactical_style: Any) -> str:
    """Normalise a style through the existing taxonomy, sport alias included."""
    family = normalize_tactical_style(tactical_style)
    sport_key = normalize_sport(sport)
    raw = str(tactical_style or "").strip().lower().replace(" ", "_")
    if sport_key in {"", "boxing"} and family == "pressure_fighter":
        # Boxing keeps its historical pressure-family programming key.
        family = "brawler"
    elif sport_key not in {"", "boxing"} and family == "brawler" and raw != "brawler":
        family = "pressure_fighter"
    return family


def select_fight_visualization(
    sport: Any,
    tactical_style: Any,
    days_to_fight: Any,
) -> FightVisualization | None:
    """Return the governed prescription for this athlete on this countdown day.

    Returns ``None`` when ``days_to_fight`` is not one of the mandatory
    countdown days -- Fight Visualisation is a protocol, not a filler, so it has
    nothing to offer on any other day.

    Precedence, in order, with the reason recorded on the returned record:

    1. exact sport + exact style + D-x
    2. compatible sport family (muay thai -> kickboxing, wrestling/BJJ -> MMA)
       + exact style + D-x
    3. that sport's generic entry + D-x
    4. the explicit cross-sport entry + D-x

    An unrelated fighting style is never substituted: a style with no bank entry
    for its sport falls to that sport's *generic* content, flagged as such.
    """
    try:
        countdown_day = int(days_to_fight)
    except (TypeError, ValueError):
        return None
    if countdown_day not in FIGHT_VISUALIZATION_COUNTDOWN_DAYS:
        return None

    requested_sport = normalize_sport(sport)
    exact_sport = requested_sport if requested_sport in BANK_SPORTS else ""
    family_sport = bank_sport(requested_sport)
    style = _style_family(requested_sport, tactical_style)

    day_bank = [
        entry for entry in all_visualizations() if entry.countdown_day == countdown_day
    ]

    def first(sport_key: str, style_key: str) -> FightVisualization | None:
        return next(
            (
                entry
                for entry in day_bank
                if sport_key in entry.sports and style_key in entry.styles
            ),
            None,
        )

    candidates: list[tuple[FightVisualization | None, str]] = []
    if exact_sport and style != "generic":
        candidates.append((first(exact_sport, style), ""))
    if family_sport and family_sport != exact_sport and style != "generic":
        candidates.append((first(family_sport, style), "compatible_sport_fallback"))
    if exact_sport:
        candidates.append(
            (
                first(exact_sport, "generic"),
                "" if style == "generic" else "sport_generic_fallback",
            )
        )
    if family_sport and family_sport != exact_sport:
        candidates.append((first(family_sport, "generic"), "compatible_sport_fallback"))
    candidates.append(
        (
            first("cross_sport", "generic"),
            "cross_sport_fallback" if requested_sport else "unknown_sport_fallback",
        )
    )

    for entry, reason in candidates:
        if entry is None:
            continue
        # A style that has no bank entry for a sport it does not belong to
        # (a boxing grappler, say) is reported precisely rather than being
        # quietly served another style's content.
        if reason == "sport_generic_fallback" and style not in _styles_owned_by(
            exact_sport
        ):
            # The style has no home in this sport at all (a boxing grappler),
            # as opposed to D-1/D-0 where every style deliberately shares the
            # sport's content. Report the difference rather than hiding it.
            reason = "sport_incompatible_tactical_style"
        return replace(
            entry,
            fallback_reason=reason,
            requested_sport=requested_sport,
            requested_style=style,
        )
    return None


@lru_cache(maxsize=None)
def _styles_owned_by(sport_key: str) -> frozenset[str]:
    """Every style this sport owns anywhere in the bank, across countdown days."""
    return frozenset(
        style
        for entry in all_visualizations()
        if sport_key in entry.sports
        for style in entry.styles
    )


def select_for_athlete(
    athlete_model: Any, days_to_fight: Any
) -> FightVisualization | None:
    """Convenience wrapper resolving sport/style from the athlete model."""
    model = athlete_model if isinstance(athlete_model, dict) else {}
    style: TacticalStyleSelection = extract_tactical_style(model)
    sport = model.get("sport") or model.get("fight_format") or ""
    return select_fight_visualization(sport, style, days_to_fight)


def build_visualization_display_text(
    entry: FightVisualization, *, prescribed_duration_min: int | None = None
) -> str:
    """Render the prescription in the shared athlete-facing session-body shape.

    Same contract as ``build_watch_display_text``: an unbulleted ``Why:``, one
    bulleted activity heading, then indented labelled lines that belong to it.
    Both renderers read peer-level lines as separate exercises, so the whole
    prescription must stay inside one bulleted activity.
    """
    dose = prescribed_duration_min or entry.duration_min[1]
    lines = [
        f"Why: {entry.why}",
        f"- {entry.name}: {dose} minutes, mental rehearsal only. No physical load.",
        *(
            f"  Step {index}: {instruction}"
            for index, instruction in enumerate(entry.instructions, start=1)
        ),
        f"  Cue: {entry.cue}",
    ]
    if entry.pre_bout:
        lines.append(f"  Pre-bout: {entry.pre_bout}")
    return "\n".join(lines)


def visualization_metadata(
    entry: FightVisualization, *, prescribed_duration_min: int | None = None
) -> dict[str, Any]:
    """Stamp the governed role fields, mirroring ``watch_metadata``."""
    low, high = entry.duration_min
    selected = prescribed_duration_min or high
    return {
        "fight_visualization_key": entry.key,
        "fight_visualization_name": entry.name,
        "fight_visualization_countdown_day": entry.countdown_day,
        "fight_visualization_style": entry.requested_style or None,
        "fight_visualization_sports": list(entry.sports),
        "fight_visualization_fallback_reason": entry.fallback_reason or None,
        "fight_visualization": {
            "key": entry.key,
            "name": entry.name,
            "countdown_day": entry.countdown_day,
            "sports": list(entry.sports),
            "styles": list(entry.styles),
            "requested_sport": entry.requested_sport or None,
            "requested_style": entry.requested_style or None,
            "fallback_reason": entry.fallback_reason or None,
            "duration_min": [low, high],
            "prescribed_duration_min": selected,
            "why": entry.why,
            "instructions": list(entry.instructions),
            "cue": entry.cue,
            "pre_bout": entry.pre_bout or None,
        },
        "preferred_exercise_names": [entry.name],
        "preferred_tags": [
            "fight_visualization",
            "mental",
            f"d{entry.countdown_day}",
        ],
        "governance": {
            "authority": "fight_visualization_library",
            "mandatory": True,
            "selected_drill_locked": True,
            "selected_drill_name": entry.name,
            "render_selected_drill_exactly": True,
            "do_not_reselect_or_generalize": True,
            "meaningful_stress": False,
        },
    }
