from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from typing import Iterable

from .config import athlete_round_seconds
from .sports import normalize_sport
from .training_context import allocate_sessions

from .style_taper_governance import (
    D13_TO_D8,
    D7,
    D6_TO_D5,
    D4_TO_D2,
    D1,
    RPE_MAX_BY_WINDOW,
    SPORT_TAGS,
    STYLE_TAGS,
    assert_style_taper_entry,
    style_taper_window_for_days,
)


_STYLE_TAPER_CONTEXT: ContextVar[tuple[str, frozenset[str]]] = ContextVar(
    "style_taper_context",
    default=("", frozenset()),
)


def _format_cap(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _values(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


def _canonical_sport(value: object) -> str:
    sport = normalize_sport(value)
    return sport if sport in SPORT_TAGS else ""


def _style_taper_context_from_flags(flags: dict, style_tag_map: dict) -> tuple[str, frozenset[str]]:
    technical = _values(flags.get("style_technical"))
    sport_candidates = [
        *(technical[:1]),
        flags.get("sport"),
        flags.get("fight_format"),
    ]
    sport = next((resolved for value in sport_candidates if (resolved := _canonical_sport(value))), "")

    style_tokens: set[str] = set()
    for raw_style in _values(flags.get("style_tactical")):
        token = _token(raw_style)
        if token:
            style_tokens.add(token)
        spaced = token.replace("_", " ")
        for lookup in (raw_style, token, spaced):
            for mapped in style_tag_map.get(str(lookup).lower(), []) or []:
                mapped_token = _token(mapped)
                if mapped_token:
                    style_tokens.add(mapped_token)

    return sport, frozenset(style_tokens & STYLE_TAGS)


def _filter_style_taper_bank_for_context(
    bank: object,
    *,
    sport: str,
    styles: frozenset[str] | set[str] = frozenset(),
):
    """Validate Style Taper entries and fail closed across incompatible sports.

    Tactical style is ranked after role/window eligibility by the selector. This
    boundary therefore filters only by sport; deleting non-style matches here
    can leave a later role with no usable candidate.
    When no canonical sport can be resolved, the Style Taper guarantee is
    withheld rather than risking a cross-sport prescription.
    """
    if not isinstance(bank, list):
        return bank

    validated: list[dict] = []
    for entry in bank:
        assert_style_taper_entry(entry)
        validated.append(entry)

    resolved_sport = _canonical_sport(sport)
    if not resolved_sport:
        return []

    sport_safe = [
        entry
        for entry in validated
        if resolved_sport in {_token(tag) for tag in entry.get("tags", [])}
    ]
    if not sport_safe:
        return []

    return sport_safe


def late_fight_dosage_caps(days_until_fight: int) -> str:
    """Return athlete-facing D13-D1 dosage that cannot exceed Style Taper governance."""
    window = style_taper_window_for_days(days_until_fight)
    if window is None:
        return (
            "Late-fight caps: no conditioning development; keep only low-volume rhythm, "
            "sharpness, or recovery work."
        )

    cap = _format_cap(RPE_MAX_BY_WINDOW[window])
    prefix = f"D-{int(days_until_fight)} late-fight caps: "

    if window == D13_TO_D8:
        return (
            f"{prefix}no conditioning development; 3-4 crisp alactic bursts max "
            f"(5-6 sec @ RPE ≤{cap}, rest 90-120 sec); technical touch 1-2 short rounds max "
            f"(≤2 min @ RPE ≤{cap}); no generic conditioning rounds; cap 6-8 min active. "
            "These caps override any drill default structure."
        )
    if window == D7:
        return (
            f"{prefix}no conditioning development; 3-4 crisp alactic bursts max "
            f"(5-6 sec @ RPE ≤{cap}, rest 90-120 sec); technical touch 1-2 short rounds max "
            f"(≤2 min @ RPE ≤{cap}); no generic conditioning rounds; cap 5-7 min active. "
            "These caps override any drill default structure."
        )
    if window == D6_TO_D5:
        return (
            f"{prefix}optional alactic sharpness only; 2-3 bursts max "
            f"(5-6 sec @ RPE ≤{cap}, rest 120 sec); technical touch 1-2 short rounds max "
            f"(≤2 min @ RPE ≤{cap}); no generic conditioning rounds; cap 5-7 min active. "
            "These caps override any drill default structure."
        )
    if window == D4_TO_D2:
        return (
            f"{prefix}0-2 optional crisp bursts only "
            f"(4-6 sec @ RPE ≤{cap}, full rest); technical walk-through only "
            f"(≤90 sec @ RPE ≤{cap}); no conditioning development; cap 3-5 min active. "
            "These caps override any drill default structure."
        )
    if window == D1:
        return (
            f"{prefix}no conditioning work; optional zero-contact rhythm touch only "
            f"(1-2 x 3-4 sec @ RPE ≤{cap}, full rest); easy shadow rehearsal, breathing "
            "and visualization only; cap 2-4 min active. "
            "These caps override any drill default structure."
        )

    raise AssertionError(f"Unhandled style taper window: {window}")


def _replace_dosage_template(rendered: str, replacement: str) -> str:
    marker = "**Dosage Template:**"
    lines = rendered.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(marker):
            lines[index] = f"{marker} {replacement}"
            return "\n".join(lines)
    return rendered


def _is_style_taper_drill(drill: object) -> bool:
    return isinstance(drill, dict) and str(
        drill.get("_schema_source") or ""
    ).endswith("style_taper_conditioning.json")


def _style_taper_candidate_rank(entry: dict) -> tuple[float, float, float, int]:
    reasons = entry.get("reasons") if isinstance(entry.get("reasons"), dict) else {}
    drill = entry.get("drill") if isinstance(entry.get("drill"), dict) else {}
    try:
        score = float(entry.get("score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0
    try:
        bank_order = int(drill.get("bank_order"))
    except (TypeError, ValueError):
        bank_order = 10_000
    return (
        -float(reasons.get("style_hits", 0) or 0),
        -float(reasons.get("goal_hits", 0) or 0)
        - float(reasons.get("weakness_hits", 0) or 0),
        -score,
        bank_order,
    )


def _repair_taper_phase_winner_for_current_window(
    result,
    *,
    flags: dict,
    conditioning_module,
):
    """Keep the phase winner current-window legal without shrinking the reservoir.

    The Stage-1 reservoir intentionally contains every phase-authorised, safe
    Style Taper candidate so later D-days can choose independently. The visible
    TAPER phase winner is different: when generation itself is already inside a
    governed D13-D1 window, that winner must also be legal for the current window.
    """
    if not isinstance(result, tuple) or len(result) != 6:
        return result

    phase = str(flags.get("phase") or "").strip().upper()
    if phase != "TAPER":
        return result

    days_until_fight = flags.get("days_until_fight")
    if days_until_fight is None:
        days_until_fight = flags.get("time_to_fight_days")
    try:
        days_until_fight = int(days_until_fight)
    except (TypeError, ValueError):
        return result

    window = style_taper_window_for_days(days_until_fight)
    if window is None:
        return result

    output, _names, why_log, grouped_drills, missing_systems, reservoir = result
    if not isinstance(grouped_drills, dict) or not isinstance(reservoir, dict):
        return result

    grouped = {
        system: [dict(drill) for drill in drills if isinstance(drill, dict)]
        for system, drills in grouped_drills.items()
        if isinstance(drills, list)
    }
    used_names = {
        str(drill.get("name") or "")
        for drills in grouped.values()
        for drill in drills
        if drill.get("name")
    }
    changed = False

    legal_by_system: dict[str, list[dict]] = {}
    for system in ("alactic", "aerobic"):
        entries = reservoir.get(system)
        if not isinstance(entries, list):
            continue
        legal = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            drill = entry.get("drill")
            if not _is_style_taper_drill(drill):
                continue
            if phase not in (drill.get("phases") or []):
                continue
            if window not in (drill.get("late_windows") or []):
                continue
            legal.append(entry)
        legal_by_system[system] = sorted(legal, key=_style_taper_candidate_rank)

    for system, drills in list(grouped.items()):
        repaired: list[dict] = []
        for drill in drills:
            if not _is_style_taper_drill(drill) or window in (drill.get("late_windows") or []):
                repaired.append(drill)
                continue

            changed = True
            old_name = str(drill.get("name") or "")
            used_names.discard(old_name)
            replacement = next(
                (
                    entry
                    for entry in legal_by_system.get(system, [])
                    if str((entry.get("drill") or {}).get("name") or "") not in used_names
                ),
                None,
            )
            if replacement is None:
                # Fail closed: do not keep a Style Taper phase winner that is
                # illegal for the athlete's current late window.
                continue

            replacement_drill = dict(replacement["drill"])
            repaired.append(replacement_drill)
            replacement_name = str(replacement_drill.get("name") or "")
            if replacement_name:
                used_names.add(replacement_name)

        grouped[system] = repaired

    if not changed:
        return result

    selected_names = [
        str(drill.get("name") or "")
        for drills in grouped.values()
        for drill in drills
        if drill.get("name")
    ]

    candidate_by_name: dict[str, dict] = {}
    for entries in reservoir.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            drill = entry.get("drill")
            if not isinstance(drill, dict) or not drill.get("name"):
                continue
            candidate_by_name[str(drill["name"])] = entry

    old_why = {
        str(item.get("name") or ""): item
        for item in why_log or []
        if isinstance(item, dict) and item.get("name")
    }
    rebuilt_why = []
    for system, drills in grouped.items():
        for drill in drills:
            name = str(drill.get("name") or "")
            candidate = candidate_by_name.get(name)
            if candidate:
                rebuilt_why.append(
                    {
                        "name": name,
                        "system": system,
                        "reasons": dict(candidate.get("reasons") or {}),
                        "explanation": str(candidate.get("explanation") or ""),
                    }
                )
            elif name in old_why:
                rebuilt_why.append(dict(old_why[name]))

    training_frequency = flags.get("training_frequency", flags.get("days_available", 4))
    try:
        training_frequency = int(training_frequency)
    except (TypeError, ValueError):
        training_frequency = 4

    missing = list(missing_systems or [])
    for system in ("alactic", "aerobic"):
        if system in grouped and not grouped[system] and system not in missing:
            missing.append(system)

    diagnostic_context = {
        "phase": phase,
        "sport": flags.get("sport"),
        "time_to_fight_days": flags.get("time_to_fight_days"),
        "days_until_fight": days_until_fight,
        "weeks_out": flags.get("weeks_out"),
        "fatigue_level": flags.get("fatigue_level", flags.get("fatigue")),
        "injuries": flags.get("injuries"),
        "fight_format": flags.get("fight_format"),
    }
    output = conditioning_module.render_conditioning_block(
        grouped,
        phase=phase,
        phase_color="#F44336",
        missing_systems=missing,
        num_sessions=allocate_sessions(training_frequency, phase).get("conditioning", 0),
        diagnostic_context=diagnostic_context,
        round_seconds=athlete_round_seconds(flags.get("rounds_format")),
        sport=flags.get("sport"),
        stance=flags.get("stance"),
    )
    return output, selected_names, rebuilt_why, grouped, missing, reservoir


def install() -> None:
    """Install canonical D13-D1 taper dosage and Style Taper runtime governance."""
    from . import conditioning as conditioning_module

    if getattr(conditioning_module, "_STYLE_TAPER_DOSAGE_POLICY_INSTALLED", False):
        return

    original_render = conditioning_module.render_conditioning_block
    original_load_bank = conditioning_module._load_bank
    original_generate = conditioning_module.generate_conditioning_block

    @wraps(original_render)
    def render_conditioning_block(
        grouped_drills: dict[str, list[dict]],
        *,
        phase: str,
        phase_color: str,
        missing_systems: Iterable[str] | None = None,
        num_sessions: int = 1,
        diagnostic_context: dict | None = None,
        sport: str | None = None,
        stance: str | None = None,
        resolved_sessions: list[dict] | None = None,
        round_seconds: float | None = None,
    ) -> str:
        context = dict(diagnostic_context or {})
        days_until_fight = context.get("days_until_fight")
        if days_until_fight is None:
            days_until_fight = context.get("time_to_fight_days")

        window = style_taper_window_for_days(days_until_fight)
        if str(phase or "").upper() == "TAPER" and window is not None:
            # The legacy renderer can add a separate generic RPE 7-8 speed-dose line.
            # In D13-D1, the canonical Style Taper dosage already owns that exposure.
            context["speed_dose_allowed"] = False

        rendered = original_render(
            grouped_drills,
            phase=phase,
            phase_color=phase_color,
            missing_systems=missing_systems,
            num_sessions=num_sessions,
            diagnostic_context=context,
            sport=sport,
            stance=stance,
            resolved_sessions=resolved_sessions,
            round_seconds=round_seconds,
        )

        if str(phase or "").upper() == "TAPER" and window is not None:
            rendered = _replace_dosage_template(
                rendered,
                late_fight_dosage_caps(int(days_until_fight)),
            )
        return rendered

    @wraps(original_load_bank)
    def _load_bank(path, *, source: str, enforce_conditioning_systems: bool = False):
        bank = original_load_bank(
            path,
            source=source,
            enforce_conditioning_systems=enforce_conditioning_systems,
        )
        path_name = getattr(path, "name", str(path).rsplit("/", 1)[-1])
        if path_name != "style_taper_conditioning.json":
            return bank

        sport, styles = _STYLE_TAPER_CONTEXT.get()
        # Always run dedicated governance on the production file. Contextless
        # loads (bank validation, tooling) validate all entries but do not filter.
        if not sport and not styles:
            if isinstance(bank, list):
                for entry in bank:
                    assert_style_taper_entry(entry)
            return bank
        return _filter_style_taper_bank_for_context(bank, sport=sport, styles=styles)

    @wraps(original_generate)
    def generate_conditioning_block(flags):
        sport, styles = _style_taper_context_from_flags(
            flags or {},
            conditioning_module.STYLE_TAG_MAP,
        )
        token = _STYLE_TAPER_CONTEXT.set((sport, styles))
        try:
            result = original_generate(flags)
            return _repair_taper_phase_winner_for_current_window(
                result,
                flags=flags or {},
                conditioning_module=conditioning_module,
            )
        finally:
            _STYLE_TAPER_CONTEXT.reset(token)

    conditioning_module._late_fight_dosage_caps = late_fight_dosage_caps
    conditioning_module._filter_style_taper_bank_for_context = _filter_style_taper_bank_for_context
    conditioning_module._load_bank = _load_bank
    conditioning_module.generate_conditioning_block = generate_conditioning_block
    conditioning_module.render_conditioning_block = render_conditioning_block
    conditioning_module._STYLE_TAPER_DOSAGE_POLICY_INSTALLED = True
