from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
from typing import Callable, Iterable
from collections import defaultdict
from .training_context import (
    allocate_sessions,
    normalize_equipment_list,
    calculate_exercise_numbers,
)
from .bank_schema import KNOWN_SYSTEMS, SYSTEM_ALIASES, validate_training_item
from .injury_filtering import injury_match_details, _log_exclusion, _log_replacement
from .injury_guard import Decision, choose_injury_replacement, injury_decision, make_guarded_decision_factory
from .restriction_filtering import evaluate_restriction_impact
from .diagnostics import format_missing_system_block
from .tagging import normalize_item_tags, normalize_tags
from .tag_maps import GOAL_TAG_MAP, STYLE_TAG_MAP, WEAKNESS_TAG_MAP
from .config import (
    PHASE_SYSTEM_RATIOS,
    STYLE_CONDITIONING_RATIO,
    DATA_DIR,
    INJURY_GUARD_SHORTLIST,
    trim_to_injury_guard_shortlist,
)

TAPER_AVOID_TAGS = {
    "contrast_pairing",
    "triple_extension",
    "overhead",
    "compound",
    "mental_toughness",
    "work_capacity",
    "eccentric",
}

_MIXED_SYSTEM_LOGGED: set[tuple[str, str]] = set()
_UNKNOWN_SYSTEM_LOGGED: set[tuple[str, str]] = set()
_UNKNOWN_SYSTEM_DRILL_LOGGED: set[tuple[str, str, str]] = set()

logger = logging.getLogger(__name__)

ALACTIC_MAX_WORK_SEC = 12
ALACTIC_MIN_REST_SEC = 60
SPORT_LANGUAGE_BLACKLIST = {
    "boxing": {
        "dirty td",
        "td setup",
        "takedown",
        "double-leg",
        "double leg",
        "single-leg",
        "single leg",
        "sprawl",
        "thai clinch",
        "clinch knee",
        "cage clinch",
        "elbow",
        "cage",
        "octagon",
        "ground and pound",
        "grappling",
    },
}
_TIME_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:-|-)?\s*(\d+(?:\.\d+)?)?\s*"
    r"(s|sec|secs|second|seconds|min|mins|minute|minutes)\b",
    re.IGNORECASE,
)


def _time_token_to_seconds(value: float, unit: str) -> float:
    if unit.lower().startswith("m"):
        return value * 60.0
    return value


def _extract_time_values(text: str) -> list[float]:
    values: list[float] = []
    for match in _TIME_TOKEN.finditer(text or ""):
        start_val = float(match.group(1))
        end_val = float(match.group(2)) if match.group(2) else None
        unit = match.group(3)
        value = max(start_val, end_val) if end_val is not None else start_val
        values.append(_time_token_to_seconds(value, unit))
    return values


def _alactic_structure_ok(drill: dict) -> bool:
    timing = drill.get("timing") or ""
    duration = drill.get("duration") or ""
    rest = drill.get("rest") or ""
    duration_text = " ".join(filter(None, [timing, duration]))
    work_candidates: list[float] = []
    rest_candidates: list[float] = []

    for clause in re.split(r"[;,/]", duration_text):
        clause_lower = clause.lower()
        is_rest_clause = any(
            key in clause_lower
            for key in ("rest", "off", "recovery", "recover", "between")
        )
        targets = rest_candidates if is_rest_clause else work_candidates
        targets.extend(_extract_time_values(clause))

    if rest:
        rest_candidates.extend(_extract_time_values(rest))

    if not work_candidates:
        return False
    if not rest_candidates:
        return False

    work_seconds = max(work_candidates)
    rest_seconds = max(rest_candidates)
    return work_seconds <= ALACTIC_MAX_WORK_SEC and rest_seconds >= ALACTIC_MIN_REST_SEC


def normalize_system(raw_system: str | None, *, source: str) -> str:
    """Return a normalized system name and log unknown values once."""
    system = (raw_system or "").strip().lower()
    if not system:
        normalized = "misc"
    else:
        normalized = SYSTEM_ALIASES.get(system, system)

    if any(sep in system for sep in ("+", "→", "/", "&")) or "->" in system:
        parts = [
            part.strip()
            for part in re.split(r"\s*(?:\+|/|→|->|&)\s*", system)
            if part.strip()
        ]
        mapped_parts = [SYSTEM_ALIASES.get(part, part) for part in parts]
        known_parts = [part for part in mapped_parts if part in KNOWN_SYSTEMS]
        if known_parts:
            if "glycolytic" in known_parts:
                normalized = "glycolytic"
            else:
                normalized = known_parts[0]
            log_key = (source, system)
            if log_key not in _MIXED_SYSTEM_LOGGED and len(known_parts) > 1:
                _MIXED_SYSTEM_LOGGED.add(log_key)
                logger.warning(
                    "[conditioning] Mixed energy system '%s' normalized='%s' source=%s",
                    system,
                    normalized,
                    source,
                )
        else:
            normalized = SYSTEM_ALIASES.get(system, system or "misc")
    if normalized not in KNOWN_SYSTEMS:
        log_key = (source, normalized)
        if log_key not in _UNKNOWN_SYSTEM_LOGGED:
            _UNKNOWN_SYSTEM_LOGGED.add(log_key)
            logger.warning(
                "[conditioning] Unknown energy system '%s' normalized='%s' source=%s",
                system or "unknown",
                normalized,
                source,
            )
    return normalized


def _sanitize_conditioning_bank(bank, *, source: str):
    def normalize_items(items: list[dict]) -> list[dict]:
        cleaned: list[dict] = []
        for item in items:
            placement = item.get("placement", "conditioning").lower()
            validate_training_item(
                item,
                source=source,
                require_phases=True,
                require_system=placement == "conditioning",
            )
            normalize_item_tags(item)
            if placement != "conditioning":
                cleaned.append(item)
                continue
            normalized = normalize_system(item.get("system"), source=source)
            if normalized not in KNOWN_SYSTEMS:
                name = item.get("name", "Unnamed Drill")
                logger.warning(
                    "[conditioning] Removing drill with invalid system bank=%s name='%s' system='%s'",
                    source,
                    name,
                    item.get("system"),
                )
                continue
            if item.get("system") != normalized:
                item["system"] = normalized
            cleaned.append(item)
        return cleaned

    if isinstance(bank, list):
        return normalize_items(bank)
    cleaned_bank = {}
    for key, items in bank.items():
        if isinstance(items, list):
            cleaned_bank[key] = normalize_items(items)
        else:
            cleaned_bank[key] = items
    return cleaned_bank


def _load_bank(path: Path, *, source: str, enforce_conditioning_systems: bool = False):
    bank = json.loads(path.read_text(encoding="utf-8"))
    if enforce_conditioning_systems:
        return _sanitize_conditioning_bank(bank, source=source)
    if isinstance(bank, list):
        for item in bank:
            validate_training_item(item, source=source, require_phases=True)
            normalize_item_tags(item)
        return bank
    for items in bank.values():
        if isinstance(items, list):
            for item in items:
                validate_training_item(item, source=source, require_phases=True)
                normalize_item_tags(item)
    return bank


_conditioning_bank_cache = None
_style_conditioning_bank_cache = None
_format_weights_cache = None
_coordination_bank_cache = None
coordination_bank = None


def get_conditioning_bank():
    global _conditioning_bank_cache
    if _conditioning_bank_cache is None:
        _conditioning_bank_cache = _load_bank(
            DATA_DIR / "conditioning_bank.json",
            source="conditioning_bank.json",
            enforce_conditioning_systems=True,
        )
    return _conditioning_bank_cache


def get_style_conditioning_bank():
    global _style_conditioning_bank_cache
    if _style_conditioning_bank_cache is None:
        _style_conditioning_bank_cache = _load_bank(
            DATA_DIR / "style_conditioning_bank.json",
            source="style_conditioning_bank.json",
            enforce_conditioning_systems=True,
        )
    return _style_conditioning_bank_cache


def get_format_weights():
    global _format_weights_cache
    if _format_weights_cache is None:
        _format_weights_cache = json.loads(
            (DATA_DIR / "format_energy_weights.json").read_text(encoding="utf-8")
        )
    return _format_weights_cache


def get_coordination_bank():
    global _coordination_bank_cache, coordination_bank
    if coordination_bank is not None:
        return coordination_bank
    if _coordination_bank_cache is not None:
        coordination_bank = _coordination_bank_cache
        return _coordination_bank_cache
    try:
        coord_data = _load_bank(DATA_DIR / "coordination_bank.json", source="coordination_bank.json")
    except FileNotFoundError:
        logger.warning("[bank-load] optional coordination bank missing")
        coord_data = []
    except (json.JSONDecodeError, ValueError):
        logger.exception("[bank-load-failed] bank=coordination_bank.json")
        coord_data = []
    loaded_coordination_bank: list[dict] = []
    if isinstance(coord_data, list):
        loaded_coordination_bank.extend(coord_data)
    elif isinstance(coord_data, dict):
        for val in coord_data.values():
            if isinstance(val, list):
                loaded_coordination_bank.extend(val)
    _coordination_bank_cache = loaded_coordination_bank
    coordination_bank = loaded_coordination_bank
    return _coordination_bank_cache

def prime_conditioning_banks() -> None:
    get_conditioning_bank()
    get_style_conditioning_bank()
    get_format_weights()
    get_coordination_bank()

def get_system_or_warn(drill: dict, *, source: str) -> str | None:
    system = normalize_system(drill.get("system"), source=source)
    if system in KNOWN_SYSTEMS:
        return system
    name = drill.get("name", "Unnamed Drill")
    log_key = (source, system, name)
    if log_key not in _UNKNOWN_SYSTEM_DRILL_LOGGED:
        _UNKNOWN_SYSTEM_DRILL_LOGGED.add(log_key)
        logger.warning(
            "[conditioning] Dropping drill with unknown system bank=%s name='%s' system='%s'",
            source,
            name,
            system,
        )
    return None


def _drill_text_injury_reasons(drill: dict, injuries: list[str]) -> list[dict]:
    return injury_match_details(drill, injuries, fields=("name", "notes"))


def _is_drill_text_safe(
    drill: dict,
    injuries: list[str],
    *,
    label: str,
    phase: str = "GPP",
    fatigue: str = "moderate",
) -> bool:
    decision = injury_decision(drill, injuries, phase, fatigue)
    if decision.action != "exclude":
        return True
    return False

# Relative emphasis of each energy system by training phase
def expand_tags(input_list, tag_map):
    expanded = []
    for item in input_list:
        tags = tag_map.get(item.lower(), [])
        expanded.extend(tags)
    return normalize_tags(expanded)

def is_banned_drill(
    name: str,
    tags: list[str],
    fight_format: str,
    details: str = "",
    tactical_styles: list[str] | None = None,
    technical_styles: list[str] | None = None,
) -> bool:
    """Return True if the drill should be removed for the given sport."""
    name = name.lower()
    tags = normalize_tags(tags)
    details = details.lower()

    tactical_styles = [s.lower().replace(" ", "_") for s in tactical_styles or []]
    technical_styles = [s.lower().replace(" ", "_") for s in technical_styles or []]

    grappling_terms = {
        "wrestling",
        "wrestle",
        "wrestler",
        "bjj",
        "grappling",
        "grapple",
        "grappler",
        "sprawl",
        "thai clinch",
        "clinch knee",
        "cage clinch",
        "sprawling",
        "takedown",
        "takedowns",
    }

    joined_tags = " ".join(tags)

    if fight_format in {"boxing", "kickboxing"}:
        for term in grappling_terms:
            if term in name or term in joined_tags or term in details:
                return True

    if fight_format == "boxing":
        boxing_terms = {
            "grappling",
            "wrestling",
            "muay_thai",
            "thai clinch",
            "clinch knee",
            "kick",
            "teep",
            "elbow",
        }
        for term in boxing_terms:
            if term in name or term in joined_tags or term in details:
                return True

    kick_terms = ["kick", "knee", "clinch knee strike", "teep"]

    if fight_format not in {"kickboxing", "muay_thai"}:
        if (
            "kicker" not in tactical_styles
            and not any(s in {"kickboxing", "muay_thai"} for s in technical_styles)
        ):
            for term in kick_terms:
                if term in name or term in tags or term in details:
                    return True

    return False


def _sanitize_sport_language(text: str, *, fight_format: str) -> str:
    """Swap blacklisted sport language with sport-safe alternatives."""
    if not text:
        return text
    sanitized = text
    if fight_format == "boxing":
        replacements = {
            r"\bdirty\s*td\s*setups?\b": "inside-angle entries",
            r"\btd\s*setups?\b": "entry setups",
            r"\btakedowns?\b": "entries",
            r"\bdouble\s*-?\s*legs?\b": "level-change entries",
            r"\bsingle\s*-?\s*legs?\b": "angle entries",
            r"\bsprawls?\b": "quick exits",
            r"\belbows?\b": "short hooks",
            r"\bthai\s+clinch\b": "inside tie-up",
            r"\bclinch\s+knees?\b": "inside body-shot entries",
            r"\bcage\s+clinch\b": "rope tie-up",
            r"\bcage\b": "ropes",
            r"\boctagon\b": "ring",
            r"\bground\s+and\s+pound\b": "close-range punch volume",
            r"\bgrappling\b": "hand-fighting",
        }
        for pattern, replacement in replacements.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def _violates_sport_language_blacklist(drill: dict, *, fight_format: str) -> bool:
    terms = SPORT_LANGUAGE_BLACKLIST.get(fight_format, set())
    if not terms:
        return False
    haystack = " ".join(
        str(drill.get(field, ""))
        for field in ("name", "modality", "notes", "purpose", "description", "duration", "timing")
    ).lower()
    return any(term in haystack for term in terms)


def _alactic_maintenance_fallback(phase: str) -> dict:
    phase = phase.upper()
    rounds = "6–8" if phase == "SPP" else "4–6"
    return {
        "system": "ALACTIC",
        "name": "Explosive Boxing Burst Intervals",
        "load": "RPE 8–9, keep quality high and stop before speed drop-off",
        "rest": "75-120 sec complete rest between reps",
        "timing": f"{rounds} x 6–10 sec fast punch bursts",
        "purpose": "Minimal-dose ATP-PCr maintenance for striking speed and neural sharpness.",
        "red_flags": "Terminate set if punch speed/position quality drops.",
    }


def _suppress_alactic_maintenance(*, fatigue: str, injuries: list[str]) -> bool:
    if (fatigue or "").lower() == "high":
        return True
    risk_terms = {
        "concussion",
        "dizzy",
        "vertigo",
        "hamstring tear",
        "achilles",
        "calf tear",
    }
    joined = " ".join(i.lower() for i in injuries)
    return any(term in joined for term in risk_terms)


def select_coordination_drill(flags, existing_names: set[str], injuries: list[str]):
    """Return a coordination drill matching the current phase if needed."""
    goals = [g.lower() for g in flags.get("key_goals", [])]
    weaknesses = [w.lower() for w in flags.get("weaknesses", [])]
    coord_terms = {"coordination", "coordination/proprioception", "coordination / proprioception"}
    if not any(g in coord_terms for g in goals) and not any(w in coord_terms for w in weaknesses):
        return None

    phase = flags.get("phase", "GPP").upper()
    equipment_access = set(normalize_equipment_list(flags.get("equipment", [])))
    candidates = []
    for drill in get_coordination_bank():
        if phase not in [p.upper() for p in drill.get("phases", [])]:
            continue
        if drill.get("placement", "conditioning").lower() != "conditioning":
            continue
        if drill.get("name") in existing_names:
            continue
        equipment = normalize_equipment_list(drill.get("equipment", []))
        if equipment and not set(equipment).issubset(equipment_access):
            continue
        candidates.append(drill)

    candidates = sorted(candidates, key=lambda d: d.get("name") or "")
    for drill in candidates[:INJURY_GUARD_SHORTLIST]:
        decision = injury_decision(drill, injuries, phase, flags.get("fatigue", "low"))
        if decision.action != "exclude":
            return drill
    return None


def format_drill_block(drill: dict, *, phase_color: str = "#000") -> str:
    """Return a formatted Markdown block for a single drill."""

    # Use HTML line breaks so bullets display vertically when converted to HTML
    br = "<br>"
    bullet = "•"
    load_line = f"  {bullet} Load: {drill['load']}"
    if drill.get("equipment_note"):
        load_line += f" ({drill['equipment_note']})"
    load_line += br
    parts = [
        f"- **Drill: {drill['name']}**",
        load_line,
        f"  {bullet} Rest: {drill['rest']}{br}",
        f"  {bullet} Timing: {drill['timing']}{br}",
        f"  {bullet} Purpose: {drill['purpose']}{br}",
        f"  ⚠️ Red Flags: {drill['red_flags']}",
    ]
    return "".join(parts) + "\n"


def _normalize_fight_format(fight_format: str) -> str:
    if fight_format == "muay_thai":
        return "kickboxing"
    return fight_format


def _glycolytic_fallback(phase: str) -> dict:
    phase = phase.upper()
    intensity = "RPE 7–8" if phase == "SPP" else "RPE 6–7"
    return {
        "system": "GLYCOLYTIC",
        "name": "Fight-Pace Rounds: 6-10 x (2-3 min on / 1 min off)",
        "load": f"{intensity} fight-pace",
        "rest": "1 min between rounds",
        "timing": "2-3 min work / 1 min rest",
        "purpose": "Maintain glycolytic conditioning with clear work:rest structure.",
        "red_flags": "None",
    }


def render_conditioning_block(
    grouped_drills: dict[str, list[dict]],
    *,
    phase: str,
    phase_color: str,
    missing_systems: Iterable[str] | None = None,
    num_sessions: int = 1,
    diagnostic_context: dict | None = None,
    sport: str | None = None,
) -> str:
    phase = phase.upper()
    phase_titles = {
        "GPP": "Aerobic Base & Durability",
        "SPP": "Fight-Specific Conditioning",
        "TAPER": "Neural Sharpness & Rhythm",
    }
    phase_intent = {
        "GPP": "Build aerobic base, improve repeatability, low damage.",
        "SPP": "Match fight demands with intervals and skill-relevant density.",
        "TAPER": "Speed + alactic sharpness, neural freshness, low damage.",
    }
    dosage_template = {
        "GPP": "3–5 rounds of 3–5 min @ RPE 6–7, work:rest 1:1–1:0.5 (cap 20–30 min). Template applies unless a drill lists its own structure.",
        "SPP": "4–6 rounds of 2–5 min @ RPE 7–8, work:rest 1:1–1:0.5 (cap 18–25 min). Template applies unless a drill lists its own structure.",
        "TAPER": "6–10 rounds of 6–12 sec @ RPE 8–9, rest 60–120 sec (cap 8–12 min). Template applies unless a drill lists its own structure.",
    }
    weekly_progression = {
        "GPP": "Add 1 round or ~5–10% volume weekly; deload final week by ~20%.",
        "SPP": "Increase density or intensity weekly; keep volume flat; deload final week by ~20%.",
        "TAPER": "Reduce volume 40–60%; keep speed sharp; last 3–5 days very light.",
    }
    time_short = {
        "GPP": "Keep 2 aerobic rounds + 1 alactic pop.",
        "SPP": "Keep 2 fight-pace rounds (system priority).",
        "TAPER": "Keep 4–6 alactic bursts + shadowboxing rhythm.",
    }
    fatigue_note = {
        "GPP": "If fatigue high: drop 1–2 rounds, keep intensity easy.",
        "SPP": "If fatigue high: drop volume, keep rest longer.",
        "TAPER": "If fatigue high: keep only 4–6 low-impact bursts.",
    }

    output_lines = []
    missing_systems = set(missing_systems or [])
    diagnostic_context = diagnostic_context or {}
    if missing_systems:
        diagnostic_blocks = [
            format_missing_system_block(
                system_name,
                phase=phase,
                sport=sport or "",
                context=diagnostic_context,
            )
            for system_name in ["aerobic", "glycolytic", "alactic"]
            if system_name in missing_systems
        ]
        if diagnostic_blocks:
            output_lines.append("\n\n".join(diagnostic_blocks))

    ordered_keys = ["aerobic", "glycolytic", "alactic"]
    ordered_keys += [k for k in grouped_drills.keys() if k not in ordered_keys]

    session_count = max(1, num_sessions or 1)
    total_drills = sum(len(drills or []) for drills in grouped_drills.values())
    if total_drills:
        session_count = min(session_count, total_drills)
    sessions = [{"drills": {}, "systems": set()} for _ in range(session_count)]
    drill_index = 0
    for system in ordered_keys:
        drills = grouped_drills.get(system, [])
        for d in drills:
            target = sessions[drill_index % session_count]
            target["drills"].setdefault(system, []).append(d)
            target["systems"].add(system)
            drill_index += 1

    system_labels = {
        "alactic": "Alactic Speed",
        "glycolytic": "Glycolytic Power",
        "aerobic": "Aerobic Base",
    }
    phase_suffix = {
        "GPP": " + Repeatability",
        "SPP": " + Fight-Pace Density",
        "TAPER": " + Skill Rhythm",
    }

    for idx, session in enumerate(sessions, start=1):
        if not session["drills"]:
            continue
        systems = session["systems"]
        title_bits = [system_labels[s] for s in ordered_keys if s in systems]
        title = " + ".join(title_bits) if title_bits else phase_titles.get(phase, "Conditioning")
        title += phase_suffix.get(phase, "")
        output_lines.append(f"\n#### Conditioning Block {phase} — {title}")
        output_lines.append(f"**Intent:** {phase_intent.get(phase, 'Match phase intent.')}")
        output_lines.append(f"**Dosage Template:** {dosage_template.get(phase, 'Match system goals.')}")
        output_lines.append(f"**Weekly Progression:** {weekly_progression.get(phase, 'Progress weekly.')}")
        output_lines.append(f"**If Time Short:** {time_short.get(phase, 'Keep top 2 drills.')}")
        output_lines.append(f"**If Fatigue High:** {fatigue_note.get(phase, 'Reduce volume.')}")

        for system in ordered_keys:
            drills = session["drills"].get(system)
            if not drills:
                continue
            output_lines.append(
                f"\n📌 **System: {system.upper()}** (scaled by format emphasis)"
            )
            for d in drills:
                name = d.get("name", "Unnamed Drill")
                equipment = normalize_equipment_list(d.get("equipment", []))
                extra_eq = [e for e in equipment if e not in name.lower()]
                if extra_eq:
                    name = f"{name} ({', '.join(extra_eq)})"

                timing = d.get("timing") or d.get("duration") or "—"
                load = d.get("load") or d.get("intensity") or "—"
                equip_note = d.get("equipment_note") or d.get("equipment_notes")

                purpose = (
                    d.get("purpose")
                    or d.get("notes")
                    or d.get("description")
                    or "—"
                )
                rest = d.get("rest", "—")

                name = _sanitize_sport_language(name, fight_format=(sport or "").lower())
                timing = _sanitize_sport_language(timing, fight_format=(sport or "").lower())
                load = _sanitize_sport_language(load, fight_format=(sport or "").lower())
                rest = _sanitize_sport_language(rest, fight_format=(sport or "").lower())
                purpose = _sanitize_sport_language(purpose, fight_format=(sport or "").lower())

                drill_block = {
                    "system": system.upper(),
                    "name": name,
                    "load": load,
                    "equipment_note": equip_note,
                    "rest": rest,
                    "timing": timing,
                    "purpose": purpose,
                    "red_flags": d.get("red_flags", "None"),
                }
                output_lines.append(format_drill_block(drill_block, phase_color=phase_color))

    return "\n".join(output_lines)

def _conditioning_explanation(reasons: dict) -> str:
    parts = []
    if reasons.get("goal_hits"):
        parts.append(f"{reasons['goal_hits']} goal match")
    if reasons.get("weakness_hits"):
        parts.append(f"{reasons['weakness_hits']} weakness tag")
    if reasons.get("style_hits"):
        parts.append(f"{reasons['style_hits']} style tag")
    if reasons.get("phase_hits"):
        parts.append(f"{reasons['phase_hits']} phase tag")
    if reasons.get("equipment_boost"):
        parts.append("equipment boost")
    if reasons.get("load_adjustments"):
        parts.append("system emphasis")
    return ", ".join(parts) if parts else "balanced selection"


def _build_conditioning_candidate_reservoir(
    system_drills: dict[str, list[tuple[dict, float, dict]]],
    style_system_drills: dict[str, list[tuple[dict, float, dict]]],
    grouped_drills: dict[str, list[dict]],
    reason_lookup: dict[str, dict],
    *,
    limit_per_system: int = 5,
) -> dict[str, list[dict]]:
    reservoirs: dict[str, list[dict]] = defaultdict(list)
    seen_by_system: dict[str, set[str]] = defaultdict(set)

    def _append(system: str, drill: dict, score: float, reasons: dict) -> None:
        name = drill.get("name")
        if not name:
            return
        if name in seen_by_system[system]:
            return
        if len(reservoirs[system]) >= limit_per_system:
            return
        reservoirs[system].append(
            {
                "drill": drill.copy(),
                "score": score,
                "reasons": (reasons or {}).copy(),
                "explanation": _conditioning_explanation(reasons or {}),
            }
        )
        seen_by_system[system].add(name)

    for system, drills in grouped_drills.items():
        for drill in drills:
            reasons = reason_lookup.get(drill.get("name"), {}).copy()
            reasons.setdefault("final_score", 0)
            _append(system, drill, float(reasons.get("final_score", 0) or 0), reasons)

    for source in (system_drills, style_system_drills):
        for system, candidates in source.items():
            for drill, score, reasons in candidates:
                _append(system, drill, score, reasons)

    return dict(reservoirs)


def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    phase_color = {"GPP": "#4CAF50", "SPP": "#FF9800", "TAPER": "#F44336"}.get(phase.upper(), "#000")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", [])
    technical = flags.get("style_technical", [])
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])
    injuries = flags.get("injuries", [])
    restrictions = flags.get("restrictions")
    ignore_restrictions = bool(flags.get("ignore_restrictions", False))
    injury_trace = os.environ.get("INJURY_TRACE", "0") == "1"
    training_frequency = flags.get("training_frequency", flags.get("days_available", 3))
    equipment_access = normalize_equipment_list(flags.get("equipment", []))
    equipment_access_set = set(equipment_access)
    days_until_fight = flags.get("days_until_fight")
    # Normalize technical style(s)
    if isinstance(technical, str):
        tech_styles = [t.strip().lower() for t in technical.split(',') if t.strip()]
    elif isinstance(technical, list):
        tech_styles = [t.strip().lower() for t in technical if t]
    else:
        tech_styles = []
    # First style in list determines fight format
    primary_tech = tech_styles[0] if tech_styles else ""

    # preserve tactical style names for style drill filtering
    if isinstance(style, list):
        style_names = [s.lower().replace(" ", "_") for s in style]
    elif isinstance(style, str) and style:
        style_names = [style.lower().replace(" ", "_")]
    else:
        style_names = []
    tech_style_tags = [t.replace(" ", "_") for t in tech_styles]
    if not style_names:
        style_names = tech_style_tags

    style_tags = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
    style_tags = normalize_tags([t for s in style_tags for t in STYLE_TAG_MAP.get(s, [])])

    goal_tags = expand_tags(goals, GOAL_TAG_MAP)
    goal_list = [g.lower() for g in goals]
    weak_tags = expand_tags(weaknesses, WEAKNESS_TAG_MAP)
    shoulder_focus = any('shoulder' in g.lower() for g in goals) or any(
        'shoulder' in w.lower() for w in weaknesses
    )

    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "boxing": "boxing",
        "kickboxer": "kickboxing",
        "kickboxing": "kickboxing",
        "muay thai": "muay_thai",
        "muaythai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "wrestling": "wrestler",
        "grappler": "mma",
        "grappling": "grappler",
        "karate": "kickboxing",
    }
    fight_format = style_map.get(primary_tech, "mma")
    selection_format = _normalize_fight_format(fight_format)
    energy_weights = get_format_weights().get(selection_format, {})

    rename_map = {}
    if selection_format == "boxing":
        rename_map = {
            "Clinch Frame Throws": "Frame-and-Pop Chest Throw",
            "Thai Clinch EMOM": "Inside Hand-Fight EMOM",
        }

    format_tag_map = {
        "mma": ["mma", "bjj", "wrestler"],
        "boxing": ["boxing"],
        "kickboxing": ["kickboxing", "muay_thai"],
        "muay_thai": ["muay_thai"]
    }
    fight_format_tags = flags.get("fight_format_tags") or format_tag_map.get(selection_format, [])

    phase_priority = {
        "GPP": ["aerobic", "glycolytic", "alactic"],
        "SPP": ["glycolytic", "alactic", "aerobic"],
        "TAPER": ["alactic", "aerobic", "glycolytic"]
    }
    preferred_order = phase_priority.get(phase.upper(), ["aerobic", "glycolytic", "alactic"])
    system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    style_system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    # Track drills per individual style for even distribution
    style_drills_by_style = {
        s: {"aerobic": [], "glycolytic": [], "alactic": []} for s in style_names
    }
    selected_drill_names = []
    reason_lookup: dict[str, dict] = {}
    excluded_by_injury: list[dict] = []
    restriction_candidates = 0
    restriction_blocked = 0
    restriction_reason_counts: dict[str, int] = defaultdict(int)
    restriction_warning_counts: dict[str, int] = defaultdict(int)
    restriction_blocked_items: list[dict] = []

    for drill in get_conditioning_bank():
        d = drill.copy()
        if d.get("placement", "conditioning").lower() != "conditioning":
            continue
        if selection_format == "boxing":
            d["name"] = rename_map.get(d.get("name"), d.get("name"))
            d["tags"] = [
                "boxing" if t.lower() == "muay_thai" else t
                for t in d.get("tags", [])
            ]
        if phase.upper() not in d.get("phases", []):
            continue

        system = get_system_or_warn(d, source="conditioning_bank.json")
        if system is None:
            continue
        if system == "alactic" and not _alactic_structure_ok(d):
            continue

        tags = normalize_tags(d.get("tags", []))
        details = " ".join(
            [
                d.get("duration", ""),
                d.get("notes", ""),
                d.get("modality", ""),
                d.get("equipment_note", ""),
            ]
        )
        restriction_text = " ".join(
            [
                d.get("name", ""),
                d.get("modality", ""),
                d.get("notes", ""),
                d.get("equipment_note", ""),
            ]
        )
        if is_banned_drill(
            d.get("name", ""),
            tags,
            selection_format,
            details,
            style_names,
            tech_style_tags,
        ):
            continue
        if _violates_sport_language_blacklist(d, fight_format=selection_format):
            continue

        if (
            selection_format == "boxing"
            and phase.upper() == "TAPER"
            and {"overhead", "rotational", "heavy_load"}.issubset(tags)
            and not (shoulder_focus and fatigue == "low")
        ):
            continue

        drill_equipment = normalize_equipment_list(d.get("equipment", []))
        if drill_equipment and not set(drill_equipment).issubset(equipment_access_set):
            continue

        # Suppress high CNS drills in TAPER unless criteria met
        if (
            phase.upper() == "TAPER"
            and "high_cns" in tags
            and not (
                fatigue == "low"
                and system == "alactic"
                and any(t in weak_tags or t in goal_tags for t in tags)
            )
        ):
            continue

        # Additional tag suppression in TAPER for moderate/high fatigue
        if (
            phase.upper() == "TAPER"
            and fatigue != "low"
            and any(t in TAPER_AVOID_TAGS for t in tags)
            and not any(t in goal_tags or t in weak_tags for t in tags)
        ):
            continue

        restriction_candidates += 1
        restriction_result = evaluate_restriction_impact(
            restrictions,
            text=restriction_text,
            tags=tags,
            limit_penalty=-0.75,
        )
        restriction_penalty = restriction_result.get("penalty", 0.0)
        matched_restrictions = restriction_result.get("matched", [])
        if not ignore_restrictions and not restriction_result.get("allowed", True):
            restriction_blocked += 1
            for match in matched_restrictions:
                restriction_reason_counts[match.get("restriction", "generic_constraint")] += 1
            if matched_restrictions:
                top_match = max(matched_restrictions, key=lambda m: m.get("confidence", 0))
                restriction_blocked_items.append(
                    {
                        "name": d.get("name", "<unnamed>"),
                        "match": top_match,
                        "risk": restriction_result.get("risk", 0.0),
                    }
                )
            if injury_trace:
                print(
                    "[guard-block] conditioning:%s name=%s matched=%s risk=%.2f"
                    % (
                        phase.upper(),
                        d.get("name", "<unnamed>"),
                        matched_restrictions,
                        restriction_result.get("risk", 0.0),
                    )
                )
            continue
        if restriction_result.get("no_match_hints"):
            for hint in restriction_result.get("no_match_hints", []):
                restriction_warning_counts[hint] += 1

        num_weak = sum(1 for t in tags if t in weak_tags)
        num_goals = sum(1 for t in tags if t in goal_tags)
        num_style = sum(1 for t in tags if t in style_tags)
        num_format = sum(1 for t in tags if t in fight_format_tags)

        base_score = 2.5 * min(num_weak, 2)
        base_score += 2.0 * min(num_goals, 2)
        base_score += 1.0 * min(num_style, 2)
        base_score += 1.0 * min(num_format, 1)

        energy_multiplier = energy_weights.get(system, 1.0)
        system_score = round(energy_multiplier * 1.0, 2)
        total_score = base_score + system_score

        penalty = 0.0
        if fatigue == "high" and "high_cns" in tags:
            total_score -= 2.0
            penalty = -2.0
        elif fatigue == "moderate" and "high_cns" in tags:
            total_score -= 1.0
            penalty = -1.0
        if not ignore_restrictions and restriction_penalty:
            total_score += restriction_penalty
            penalty += restriction_penalty

        reasons = {
            "weakness_hits": num_weak,
            "goal_hits": num_goals,
            "style_hits": num_style,
            "phase_hits": 1,
            "load_adjustments": system_score,
            "equipment_boost": 0.0,
            "penalties": penalty,
            "restriction_hits": len(matched_restrictions),
            "final_score": round(total_score, 4),
        }

        system_drills[system].append((d, total_score, reasons))

    # ---- Style specific conditioning ----
    target_style_tags = set(style_names + tech_style_tags)
    for drill in get_style_conditioning_bank():
        d = drill.copy()
        if d.get("placement", "conditioning").lower() != "conditioning":
            continue
        if selection_format == "boxing":
            d["name"] = rename_map.get(d.get("name"), d.get("name"))
            d["tags"] = [
                "boxing" if t.lower() == "muay_thai" else t
                for t in d.get("tags", [])
            ]
        tags = normalize_tags(d.get("tags", []))
        details = " ".join(
            [
                d.get("duration", ""),
                d.get("notes", ""),
                d.get("modality", ""),
                d.get("equipment_note", ""),
            ]
        )
        restriction_text = " ".join(
            [
                d.get("name", ""),
                d.get("modality", ""),
                d.get("notes", ""),
                d.get("equipment_note", ""),
            ]
        )
        if is_banned_drill(
            d.get("name", ""),
            tags,
            selection_format,
            details,
            style_names,
            tech_style_tags,
        ):
            continue
        if _violates_sport_language_blacklist(d, fight_format=selection_format):
            continue
        if not target_style_tags.intersection(tags):
            continue
        if phase.upper() not in d.get("phases", []):
            continue

        if (
            selection_format == "boxing"
            and phase.upper() == "TAPER"
            and {"overhead", "rotational", "heavy_load"}.issubset(tags)
            and not (shoulder_focus and fatigue == "low")
        ):
            continue

        system = get_system_or_warn(d, source="style_conditioning_bank.json")
        if system is None:
            continue
        if system == "alactic" and not _alactic_structure_ok(d):
            continue

        # Apply same fatigue/CNS suppression rules
        if (
            phase.upper() == "TAPER"
            and "high_cns" in tags
            and not (
                fatigue == "low"
                and system == "alactic"
                and any(t in weak_tags or t in goal_tags for t in tags)
            )
        ):
            continue
        if (
            phase.upper() == "TAPER"
            and fatigue != "low"
            and any(t in TAPER_AVOID_TAGS for t in tags)
            and not any(t in goal_tags or t in weak_tags for t in tags)
        ):
            continue
        drill_equipment = normalize_equipment_list(d.get("equipment", []))
        if drill_equipment and not set(drill_equipment).issubset(equipment_access_set):
            continue
        equip_bonus = 0.5 if drill_equipment else 0.0

        restriction_candidates += 1
        restriction_result = evaluate_restriction_impact(
            restrictions,
            text=restriction_text,
            tags=tags,
            limit_penalty=-0.75,
        )
        restriction_penalty = restriction_result.get("penalty", 0.0)
        matched_restrictions = restriction_result.get("matched", [])
        if not ignore_restrictions and not restriction_result.get("allowed", True):
            restriction_blocked += 1
            for match in matched_restrictions:
                restriction_reason_counts[match.get("restriction", "generic_constraint")] += 1
            if matched_restrictions:
                top_match = max(matched_restrictions, key=lambda m: m.get("confidence", 0))
                restriction_blocked_items.append(
                    {
                        "name": d.get("name", "<unnamed>"),
                        "match": top_match,
                        "risk": restriction_result.get("risk", 0.0),
                    }
                )
            if injury_trace:
                print(
                    "[guard-block] conditioning:%s name=%s matched=%s risk=%.2f"
                    % (
                        phase.upper(),
                        d.get("name", "<unnamed>"),
                        matched_restrictions,
                        restriction_result.get("risk", 0.0),
                    )
                )
            continue
        if restriction_result.get("no_match_hints"):
            for hint in restriction_result.get("no_match_hints", []):
                restriction_warning_counts[hint] += 1

        score = 0.0
        score += 1.5  # style match already guaranteed by filter
        score += 1.0  # phase match
        top_system = preferred_order[0]
        if system == top_system:
            score += 0.75
        score += equip_bonus
        weak_matches = sum(1 for t in tags if t in weak_tags)
        goal_matches = sum(1 for t in tags if t in goal_tags)
        score += 0.6 * min(weak_matches, 1)
        score += 0.5 * min(goal_matches, 1)
        penalty = 0.0
        if "high_cns" in tags:
            if fatigue == "high":
                score -= 1.0
                penalty = -1.0
            elif fatigue == "moderate":
                score -= 0.5
                penalty = -0.5
        if not ignore_restrictions and restriction_penalty:
            score += restriction_penalty
            penalty += restriction_penalty
        reasons = {
            "weakness_hits": weak_matches,
            "goal_hits": goal_matches,
            "style_hits": 1,
            "phase_hits": 1,
            "load_adjustments": 0.75 if system == top_system else 0.0,
            "equipment_boost": equip_bonus,
            "penalties": penalty,
            "restriction_hits": len(matched_restrictions),
            "final_score": round(score, 4),
        }

        style_system_drills[system].append((d, score, reasons))
        for st in style_names:
            if st in tags:
                style_drills_by_style[st][system].append((d, score, reasons))

    for drills in system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for drills in style_system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for style_lists in style_drills_by_style.values():
        for drills in style_lists.values():
            drills.sort(key=lambda x: x[1], reverse=True)

    if injury_trace and restrictions:
        active_restrictions = sorted({r.get("restriction", "generic_constraint") for r in restrictions})
        top_blocks = sorted(
            restriction_blocked_items,
            key=lambda item: item.get("risk", 0.0),
            reverse=True,
        )[:5]
        formatted_blocks = [
            {
                "name": item.get("name"),
                "rule": item.get("match", {}).get("restriction"),
                "method": item.get("match", {}).get("method"),
                "confidence": item.get("match", {}).get("confidence"),
                "risk": item.get("risk"),
            }
            for item in top_blocks
        ]
        logger.info(
            "[guard-report] conditioning:%s restrictions=%s candidates=%d blocked=%d reasons=%s",
            phase.upper(),
            active_restrictions,
            restriction_candidates,
            restriction_blocked,
            dict(restriction_reason_counts),
        )
        logger.info(
            "[guard-report] conditioning:%s top_blocks=%s",
            phase.upper(),
            formatted_blocks,
        )
        logger.info(
            "[guard-report] conditioning:%s warnings=%s",
            phase.upper(),
            dict(restriction_warning_counts),
        )

    # Refactored: Use utility function instead of local duplicate implementation
    system_drills = {system: trim_to_injury_guard_shortlist(drills) for system, drills in system_drills.items()}
    style_system_drills = {system: trim_to_injury_guard_shortlist(drills) for system, drills in style_system_drills.items()}
    style_drills_by_style = {
        style: {system: trim_to_injury_guard_shortlist(drills) for system, drills in systems.items()}
        for style, systems in style_drills_by_style.items()
    }

    injury_guard_names: set[str] = {
        d.get("name")
        for drills in system_drills.values()
        for d, _, _ in drills
        if d.get("name")
    }
    injury_guard_names |= {
        d.get("name")
        for drills in style_system_drills.values()
        for d, _, _ in drills
        if d.get("name")
    }

    # Refactored: Use factory function instead of local duplicate implementation
    _guarded_injury_decision = make_guarded_decision_factory(
        injuries,
        phase,
        fatigue,
        injury_guard_names,
        restrictions=restrictions,
        ignore_restrictions=ignore_restrictions,
    )

    all_candidates_by_system = {
        system: [drill for drill, _, _ in system_drills.get(system, [])]
        + [drill for drill, _, _ in style_system_drills.get(system, [])]
        for system in system_drills
    }
    score_lookup: dict[str, float] = {}
    for drills in (system_drills, style_system_drills):
        for drill_list in drills.values():
            for drill, score, _ in drill_list:
                name = drill.get("name")
                if not name:
                    continue
                score_lookup[name] = max(score_lookup.get(name, float("-inf")), score)

    num_conditioning_sessions = allocate_sessions(training_frequency, phase).get(
        "conditioning", 0
    )
    exercise_counts = calculate_exercise_numbers(training_frequency, phase)

    # Use recommended drill count based on phase multipliers
    total_drills = exercise_counts.get("conditioning", 0)

    system_quota = {
        k: max(1 if v > 0 else 0, round(total_drills * v))
        for k, v in PHASE_SYSTEM_RATIOS.get(phase.upper(), {}).items()
    }

    final_drills = []
    taper_selected = 0
    selected_counts = {"aerobic": 0, "glycolytic": 0, "alactic": 0}

    style_counts = {s: 0 for s in style_names}

    def pop_drill(source: dict, system: str):
        drills = source.get(system, [])
        for idx, (drill, _, reasons) in enumerate(drills):
            name = drill.get("name")
            tags = normalize_tags(drill.get("tags", []))
            allow_repeat = (
                phase.upper() == "TAPER"
                and system == "alactic"
                and any(t in weak_tags for t in tags)
            )
            if name in selected_drill_names and not allow_repeat:
                continue
            selected_drill_names.append(name)
            del drills[idx]
            source[system] = drills
            return drill, reasons
        return None, None

    def pop_style_drill(system: str):
        for style in sorted(style_counts, key=style_counts.get):
            drills = style_drills_by_style.get(style, {}).get(system, [])
            for idx, (drill, _, reasons) in enumerate(drills):
                name = drill.get("name")
                tags = normalize_tags(drill.get("tags", []))
                allow_repeat = (
                    phase.upper() == "TAPER"
                    and system == "alactic"
                    and any(t in weak_tags for t in tags)
                )
                if name in selected_drill_names and not allow_repeat:
                    continue
                selected_drill_names.append(name)
                del drills[idx]
                style_drills_by_style[style][system] = drills
                style_counts[style] += 1
                return drill, reasons
        return None, None

    style_target = round(total_drills * STYLE_CONDITIONING_RATIO.get(phase.upper(), 0))
    style_remaining = min(style_target, sum(len(v) for v in style_system_drills.values()))
    general_remaining = total_drills - style_remaining

    allow_glycolytic = False
    if phase.upper() == "TAPER":
        lactic_goal_tags = {"glycolytic", "anaerobic_lactic", "lactic"}
        has_conditioning_goal = any(g in {"conditioning", "endurance"} for g in goal_list)
        has_lactic_goal = bool(set(goal_tags) & lactic_goal_tags)
        allow_glycolytic = (
            fatigue == "low"
            and (has_conditioning_goal or has_lactic_goal)
            and isinstance(days_until_fight, int)
            and days_until_fight > 7
        )

    def _allow_system_insert(system: str) -> bool:
        if phase.upper() != "TAPER" or system != "glycolytic":
            return True
        return allow_glycolytic and selected_counts["glycolytic"] < 1

    def _append_drill(system: str, drill: dict, reasons: dict | None) -> None:
        if not _allow_system_insert(system):
            return
        final_drills.append((system, [drill]))
        selected_drill_names.append(drill.get("name"))
        if system in selected_counts:
            selected_counts[system] += 1
        if reasons is not None:
            reason_lookup[drill.get("name")] = reasons

    def blended_pick(system: str):
        nonlocal style_remaining, general_remaining
        drill = None
        reasons = None
        if style_remaining > 0:
            drill, reasons = pop_style_drill(system)
            if drill:
                style_remaining -= 1
                return drill, reasons
        if general_remaining > 0:
            drill, reasons = pop_drill(system_drills, system)
            if drill:
                general_remaining -= 1
                return drill, reasons
        return None, None

    if phase.upper() == "TAPER":
        combined_focus = [w.lower() for w in weaknesses] + goal_list
        allow_aerobic = any(k in combined_focus for k in ["conditioning", "endurance"])

        d, r = blended_pick("alactic")
        if d:
            final_drills.append(("alactic", [d]))
            reason_lookup[d.get("name")] = r
            selected_counts["alactic"] += 1
            taper_selected += 1

        if allow_aerobic and taper_selected < 2:
            d, r = blended_pick("aerobic")
            if d:
                final_drills.append(("aerobic", [d]))
                reason_lookup[d.get("name")] = r
                selected_counts["aerobic"] += 1
                taper_selected += 1

        if allow_glycolytic and taper_selected < 2 and _allow_system_insert("glycolytic"):
            d, r = blended_pick("glycolytic")
            if d:
                final_drills.append(("glycolytic", [d]))
                reason_lookup[d.get("name")] = r
                selected_counts["glycolytic"] += 1
                taper_selected += 1
    else:
        for system in preferred_order:
            quota = system_quota.get(system, 0)
            if quota <= 0:
                continue
            while quota > 0:
                d, r = blended_pick(system)
                if not d:
                    break
                final_drills.append((system, [d]))
                reason_lookup[d.get("name")] = r
                selected_counts[system] += 1
                quota -= 1

        remaining_slots = total_drills - len(selected_drill_names)
        deficits = {
            s: max(0, system_quota.get(s, 0) - selected_counts.get(s, 0))
            for s in system_quota
        }
        while remaining_slots > 0 and any(deficits.values()):
            system = max(deficits, key=deficits.get)
            if deficits[system] <= 0:
                break
            d, r = blended_pick(system)
            if not d:
                deficits[system] = 0
                continue
            final_drills.append((system, [d]))
            reason_lookup[d.get("name")] = r
            selected_counts[system] += 1
            deficits[system] = max(0, deficits[system] - 1)
            remaining_slots -= 1

    # --------- UNIVERSAL CONDITIONING INSERTION ---------
    if phase == "GPP":
        try:
            universal_conditioning = _load_bank(
                DATA_DIR / "universal_gpp_conditioning.json",
                source="universal_gpp_conditioning.json",
                enforce_conditioning_systems=True,
            )
        except Exception:
            universal_conditioning = []

        existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
        goal_tags_set = set(goal_tags or [])
        weakness_tags_set = set(weaknesses or [])

        high_priority_names = {
            "Jump Rope Endurance (Footwork Conditioning)",
            "Steady-State Cardio (Run / Bike / Row)",
            "Explosive Medicine Ball Throws",
        }

        injected_target = 2
        injected = 0
        universal_candidates = []
        for drill in universal_conditioning:
            if injected >= injected_target or len(selected_drill_names) >= total_drills:
                break
            if drill.get("name") in existing_cond_names:
                continue
            if drill.get("placement", "conditioning").lower() != "conditioning":
                continue
            drill_eq = normalize_equipment_list(drill.get("equipment", []))
            if drill_eq and not set(drill_eq).issubset(equipment_access_set):
                continue
            system = get_system_or_warn(drill, source="universal_gpp_conditioning.json")
            if system is None:
                continue
            universal_candidates.append((system, drill))

        for system, drill in sorted(
            universal_candidates, key=lambda pair: pair[1].get("name") or ""
        )[:INJURY_GUARD_SHORTLIST]:
            if injected >= injected_target or len(selected_drill_names) >= total_drills:
                break
            decision = _guarded_injury_decision(drill)
            if decision.action == "exclude":
                # Log exclusion using new helper
                _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                continue
            drill_tags = set(normalize_tags(drill.get("tags", [])))
            if drill.get("name") in high_priority_names or drill_tags & (goal_tags_set | weakness_tags_set):
                final_drills.append((system, [drill]))
                selected_drill_names.append(drill.get("name"))
                reason_lookup[drill.get("name")] = {
                    "goal_hits": 0,
                    "weakness_hits": 0,
                    "style_hits": 0,
                    "phase_hits": 1,
                    "load_adjustments": 0,
                    "equipment_boost": 0,
                    "penalties": 0,
                    "final_score": 0,
                }
                existing_cond_names.add(drill.get("name"))
                injected += 1

    # --------- STYLE TAPER DRILL INSERTION ---------
    if phase == "TAPER":
        try:
            style_taper_bank = _load_bank(
                DATA_DIR / "style_taper_conditioning.json",
                source="style_taper_conditioning.json",
                enforce_conditioning_systems=True,
            )
        except Exception:
            style_taper_bank = []

        existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
        style_set = set(style_names)
        taper_candidates = []
        for d in style_taper_bank:
            if d.get("placement", "conditioning").lower() != "conditioning":
                continue
            if not style_set.intersection(set(normalize_tags(d.get("tags", [])))):
                continue
            eq = normalize_equipment_list(d.get("equipment", []))
            if eq and not set(eq).issubset(equipment_access_set):
                continue
            taper_candidates.append(d)
        if not taper_candidates:
            taper_candidates = [
                d
                for d in style_taper_bank
                if d.get("placement", "conditioning").lower() == "conditioning"
                and (
                    not normalize_equipment_list(d.get("equipment", []))
                    or set(normalize_equipment_list(d.get("equipment", []))).issubset(
                        equipment_access_set
                    )
                )
            ]

        if taper_candidates and len(selected_drill_names) < total_drills:
            for drill in sorted(
                taper_candidates, key=lambda d: d.get("name") or ""
            )[:INJURY_GUARD_SHORTLIST]:
                if drill.get("name") in existing_cond_names:
                    continue
                decision = _guarded_injury_decision(drill)
                if decision.action == "exclude":
                    # Log exclusion using new helper
                    _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                    continue
                system = get_system_or_warn(drill, source="style_taper_conditioning.json")
                if system is not None:
                    _append_drill(system, drill, {
                        "goal_hits": 0,
                        "weakness_hits": 0,
                        "style_hits": 0,
                        "phase_hits": 1,
                        "load_adjustments": 0,
                        "equipment_boost": 0,
                        "penalties": 0,
                        "final_score": 0,
                    })
                    break

        # --------- TAPER PLYOMETRIC GUARANTEE ---------
        taper_plyos = [
            d for d in get_conditioning_bank()
            if "TAPER" in [p.upper() for p in d.get("phases", [])]
            and d.get("placement", "conditioning").lower() == "conditioning"
            and "plyometric" in set(normalize_tags(d.get("tags", [])))
            and (
                not normalize_equipment_list(d.get("equipment", []))
                or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access_set)
            )
        ]
        if taper_plyos and len(selected_drill_names) < total_drills:
            existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
            for drill in sorted(
                taper_plyos, key=lambda d: d.get("name") or ""
            )[:INJURY_GUARD_SHORTLIST]:
                if drill.get("name") in existing_cond_names:
                    continue
                decision = _guarded_injury_decision(drill)
                if decision.action == "exclude":
                    # Log exclusion using new helper
                    _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                    continue
                system = get_system_or_warn(drill, source="conditioning_taper_plyo")
                if system is not None:
                    _append_drill(system, drill, {
                        "goal_hits": 0,
                        "weakness_hits": 0,
                        "style_hits": 0,
                        "phase_hits": 1,
                        "load_adjustments": 0,
                        "equipment_boost": 0,
                        "penalties": 0,
                        "final_score": 0,
                    })
                    break

    # --------- SKILL REFINEMENT DRILL GUARANTEE ---------
    goal_set = {g.lower() for g in goals}
    if "skill_refinement" in goal_set and len(selected_drill_names) < total_drills:
        existing_names = {d.get("name") for _, drills in final_drills for d in drills}
        skill_drills = [
            d for d in get_style_conditioning_bank()
            if "skill_refinement" in set(normalize_tags(d.get("tags", [])))
            and d.get("placement", "conditioning").lower() == "conditioning"
            and phase.upper() in d.get("phases", [])
            and (
                not normalize_equipment_list(d.get("equipment", []))
                or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access_set)
            )
        ]
        skill_drills = sorted(skill_drills, key=lambda d: d.get("name") or "")
        for drill in skill_drills[:INJURY_GUARD_SHORTLIST]:
            if drill.get("name") in existing_names:
                continue
            decision = _guarded_injury_decision(drill)
            if decision.action == "exclude":
                # Log exclusion using new helper
                _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                continue
            system = get_system_or_warn(drill, source="skill_refinement")
            if system is None:
                continue
            _append_drill(system, drill, None)
            break

    # --------- OPTIONAL COORDINATION DRILL INSERTION ---------
    existing_names = {d.get("name") for _, drills in final_drills for d in drills}
    coord_drill = select_coordination_drill(
        {**flags, "equipment": equipment_access}, existing_names, injuries
    )
    if coord_drill and len(selected_drill_names) < total_drills:
        system = get_system_or_warn(coord_drill, source="coordination")
        if system is not None:
            _append_drill(system, coord_drill, {
                "goal_hits": 0,
                "weakness_hits": 0,
                "style_hits": 0,
                "phase_hits": 1,
                "load_adjustments": 0,
                "equipment_boost": 0,
                "penalties": 0,
                "final_score": 0,
            })

    # --------- PRO NECK DRILL GUARANTEE ---------
    status = flags.get("status", "").strip().lower()
    if status in {"professional", "pro"}:
        has_neck = any(
            "neck" in set(normalize_tags(d.get("tags", [])))
            for _, drills in final_drills
            for d in drills
        )
        if not has_neck:
            neck_candidates = [
                d
                for d in get_conditioning_bank()
                if "neck" in set(normalize_tags(d.get("tags", [])))
                and phase.upper() in d.get("phases", [])
                and (
                    not normalize_equipment_list(d.get("equipment", []))
                    or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access_set)
                )
            ]
            if neck_candidates and len(selected_drill_names) < total_drills:
                for drill in sorted(
                    neck_candidates, key=lambda d: d.get("name") or ""
                )[:INJURY_GUARD_SHORTLIST]:
                    decision = _guarded_injury_decision(drill)
                    if decision.action == "exclude":
                        # Log exclusion using new helper
                        _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)
                        continue
                    system = get_system_or_warn(drill, source="pro_neck")
                    if system is not None:
                        _append_drill(system, drill, {
                            "goal_hits": 0,
                            "weakness_hits": 0,
                            "style_hits": 0,
                            "phase_hits": 1,
                            "load_adjustments": 0,
                            "equipment_boost": 0,
                            "penalties": 0,
                            "final_score": 0,
                        })
                        break

    # Trim any extras beyond the recommended count
    if len(selected_drill_names) > total_drills:
        extra = len(selected_drill_names) - total_drills
        final_drills = final_drills[:-extra]
        selected_drill_names = selected_drill_names[:-extra]

    # Group drills by energy system so each system only prints once
    grouped_drills: dict[str, list[dict]] = {}
    for system, drills in final_drills:
        grouped_drills.setdefault(system, []).extend(drills)

    def _record_injury_exclusion(drill: dict, decision: Decision) -> None:
        reason = decision.reason if isinstance(decision.reason, dict) else {}
        excluded_by_injury.append({
            "name": drill.get("name", "<unnamed>"),
            "score": float(score_lookup.get(drill.get("name"), 0.0)),
            "region": reason.get("region"),
            "severity": reason.get("severity"),
            "bucket": reason.get("bucket"),
            "matched_tags": list(decision.matched_tags or []),
        })

    def _finalize_injury_safe_drills(
        grouped: dict[str, list[dict]],
        injuries: list[dict],
        all_candidates_by_system: dict[str, list[dict]],
        selected_drill_names: list[str],
        reason_lookup: dict,
        score_fn: Callable[[dict], float] | None = None,
    ) -> None:
        def _name(x: dict) -> str | None:
            n = x.get("name")
            return n.strip() if isinstance(n, str) and n.strip() else None

        used_names = {n for drills in grouped.values() for d in drills if (n := _name(d))}
        cache: dict[str, tuple[str, Decision]] = {}

        def _decision(d: dict) -> Decision:
            n = _name(d) or f"__unnamed__:{id(d)}"
            if n in cache:
                return cache[n][1]
            decision = _guarded_injury_decision(d)
            cache[n] = (n, decision)
            return decision

        for system, drills in list(grouped.items()):
            idx = 0
            candidates = all_candidates_by_system.get(system, [])

            while idx < len(drills):
                drill = drills[idx]
                decision = _decision(drill)

                if decision.action != "exclude":
                    idx += 1
                    continue
                _record_injury_exclusion(drill, decision)
                # Log exclusion using new helper
                _log_exclusion(f"conditioning:{phase.upper()}", drill, decision)

                safe_pool: list[dict] = []
                for cand in candidates:
                    cand_name = _name(cand)
                    if not cand_name or cand_name in used_names:
                        continue
                    cand_decision = _decision(cand)
                    if cand_decision.action == "exclude":
                        continue
                    safe_pool.append(cand)

                replacement = None
                if safe_pool:
                    replacement = choose_injury_replacement(
                        excluded_item=drill,
                        candidates=safe_pool,
                        injuries=injuries,
                        phase=phase,
                        fatigue=fatigue,
                        score_fn=score_fn,
                    )

                if replacement:
                    rep_name = _name(replacement) or "(unnamed)"

                    old_name = _name(drill)
                    if old_name:
                        used_names.discard(old_name)
                    used_names.add(rep_name)

                    drills[idx] = replacement
                    
                    # Log replacement when INJURY_DEBUG is enabled
                    _log_replacement(f"conditioning:{phase.upper()}", old_name or "<unnamed>", rep_name)

                    reason_lookup.setdefault(rep_name, {
                        "goal_hits": 0,
                        "weakness_hits": 0,
                        "style_hits": 0,
                        "phase_hits": 1,
                        "load_adjustments": 0,
                        "equipment_boost": 0,
                        "penalties": 0,
                        "final_score": 0,
                    })

                    if old_name and old_name in selected_drill_names:
                        selected_drill_names[selected_drill_names.index(old_name)] = rep_name

                    idx += 1
                else:
                    old_name = _name(drill)
                    if old_name:
                        used_names.discard(old_name)
                        if old_name in selected_drill_names:
                            selected_drill_names.remove(old_name)

                    drills.pop(idx)

            grouped[system] = drills

    _finalize_injury_safe_drills(
        grouped_drills,
        injuries,
        all_candidates_by_system,
        selected_drill_names,
        reason_lookup,
    )

    if phase.upper() in {"SPP", "TAPER"} and not grouped_drills.get("glycolytic"):
        fallback = _glycolytic_fallback(phase)
        grouped_drills["glycolytic"] = [fallback]
        selected_drill_names.append(fallback["name"])

    if (
        selection_format in {"boxing", "kickboxing"}
        and phase.upper() in {"SPP", "TAPER"}
        and not grouped_drills.get("alactic")
        and not _suppress_alactic_maintenance(fatigue=fatigue, injuries=injuries)
    ):
        fallback = _alactic_maintenance_fallback(phase)
        grouped_drills["alactic"] = [fallback]
        selected_drill_names.append(fallback["name"])

    missing_systems = [
        system_name
        for system_name in ["aerobic", "glycolytic", "alactic"]
        if not grouped_drills.get(system_name)
    ]
    diagnostic_context = {
        "phase": phase,
        "sport": flags.get("sport"),
        "time_to_fight_days": flags.get("time_to_fight_days"),
        "days_until_fight": days_until_fight,
        "weeks_out": flags.get("weeks_out"),
        "fatigue_level": fatigue,
        "injuries": injuries,
        "fight_format": fight_format,
    }
    output_lines = render_conditioning_block(
        grouped_drills,
        phase=phase,
        phase_color=phase_color,
        missing_systems=missing_systems,
        num_sessions=num_conditioning_sessions,
        diagnostic_context=diagnostic_context,
        sport=flags.get("sport"),
    )

    why_log = []
    for system, drills in grouped_drills.items():
        for d in drills:
            nm = d.get("name")
            reasons = reason_lookup.get(nm, {}).copy()
            reasons.setdefault("final_score", 0)
            explanation = _conditioning_explanation(reasons)
            why_log.append({"name": nm, "system": system, "reasons": reasons, "explanation": explanation})

    candidate_reservoir = _build_conditioning_candidate_reservoir(
        system_drills,
        style_system_drills,
        grouped_drills,
        reason_lookup,
    )

    return output_lines, selected_drill_names, why_log, grouped_drills, missing_systems, candidate_reservoir
# Map for tactical styles




