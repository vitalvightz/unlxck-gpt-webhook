from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re
from typing import Callable, Iterable
from .training_context import (
    allocate_sessions,
    normalize_equipment_list,
    calculate_exercise_numbers,
)
from .bank_schema import KNOWN_SYSTEMS, SYSTEM_ALIASES
from .injury_filtering import (
    injury_match_details,
    injury_violation_reasons,
    is_injury_safe,
    log_injury_debug,
)
from .tagging import normalize_item_tags, normalize_tags

# Map for tactical styles
style_tag_map = {
    "brawler": ["compound", "posterior_chain", "power", "rate_of_force", "grip", "core"],
    "pressure fighter": ["conditioning", "core", "rate_of_force", "endurance", "mental_toughness", "anaerobic_alactic"],
    "clinch fighter": ["grip", "core", "unilateral", "shoulders", "rotational", "balance"],
    "distance striker": ["explosive", "reactive", "balance", "footwork", "coordination", "visual_processing"],
    "counter striker": ["reactive", "core", "anti_rotation", "cognitive", "visual_processing", "balance"],
    "submission hunter": ["grip", "mobility", "core", "stability", "anti_rotation", "rotational"],
    "kicker": ["hinge", "posterior_chain", "balance", "mobility", "unilateral", "hip_dominant"],
    "scrambler": ["core", "rotational", "balance", "endurance", "agility", "reactive"]
}

# Extra explosive or high-load tags to avoid during TAPER when fatigue isn't low
TAPER_AVOID_TAGS = {
    "contrast_pairing",
    "triple_extension",
    "overhead",
    "compound",
    "mental_toughness",
    "work_capacity",
    "eccentric",
    
}

# Goal tags
goal_tag_map = {
    "power": [
        "explosive", "rate_of_force", "triple_extension", "horizontal_power",
        "plyometric", "elastic", "lateral_power", "deadlift",
        "ATP-PCr", "anaerobic_alactic", "speed_strength"
    ],
    "strength": [
        "posterior_chain", "quad_dominant", "upper_body", "core", "pull", "hamstring",
        "hip_dominant", "eccentric", "deadlift", "compound", "manual_resistance", "isometric"
    ],
    "endurance": [
        "aerobic", "glycolytic", "anaerobic_lactic", "work_capacity", "mental_toughness",
        "conditioning", "improvised", "volume_tolerance"
    ],
    "speed": [
        "speed", "agility", "footwork", "reactive", "acceleration", "ATP-PCr", "anaerobic_alactic",
        "visual_processing", "reactive_decision"
    ],
    "mobility": [
        "mobility", "hip_dominant", "balance", "eccentric", "unilateral", "adductors",
        "stability", "movement_quality", "range", "rehab_friendly"
    ],
    "grappler": [
        "wrestler", "bjj", "grip", "rotational", "core", "unilateral", "tactical",
        "manual_resistance", "positioning"
    ],
    "striking": [
        "striking", "boxing", "muay_thai", "shoulders", "rate_of_force",
        "coordination", "visual_processing", "rhythm", "timing"
    ],
    "injury_prevention": [
        "recovery", "balance", "eccentric", "zero_impact", "parasympathetic",
        "cns_freshness", "unilateral", "movement_quality", "stability", "neck"
    ],
    "mental_resilience": [
        "mental_toughness", "cognitive", "parasympathetic", "visual_processing",
        "focus", "environmental", "pressure_tolerance"
    ],
    "skill_refinement": [
        "coordination", "skill", "footwork", "cognitive", "focus", "reactive", "decision_speed", "skill_refinement"
    ],
    "coordination": ["coordination"]
}


# Weakness tags (based directly on the form's checkbox labels)
weakness_tag_map = {
    "core stability": ["core", "anti_rotation"],
    "cns fatigue": ["cns_freshness", "parasympathetic"],
    "speed / reaction": ["speed", "reaction", "reactive", "coordination"],
    "lateral movement": ["lateral_power", "agility", "balance"],
    "conditioning": ["aerobic", "glycolytic", "work_capacity"],
    "rotation": ["rotational", "anti_rotation"],
    "balance": ["balance", "stability", "unilateral"],
    "explosiveness": ["explosive", "rate_of_force", "plyometric"],
    "shoulders": ["shoulders", "upper_body"],
    "shoulder": ["shoulders", "upper_body"],
    "hip mobility": ["hip_dominant", "mobility"],
    "grip strength": ["grip", "pull"],
    "posterior chain": ["posterior_chain", "hip_dominant"],
    "knees": ["quad_dominant", "eccentric"],
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"]
}

_MIXED_SYSTEM_LOGGED: set[tuple[str, str]] = set()
_UNKNOWN_SYSTEM_LOGGED: set[tuple[str, str]] = set()
_UNKNOWN_SYSTEM_DRILL_LOGGED: set[tuple[str, str, str]] = set()

_INJURY_GUARD_LOGGED: set[tuple] = set()


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
                print(
                    f"[conditioning] Mixed energy system '{system}' "
                    f"normalized='{normalized}' source={source}"
                )
        else:
            normalized = SYSTEM_ALIASES.get(system, system or "misc")
    if normalized not in KNOWN_SYSTEMS:
        log_key = (source, normalized)
        if log_key not in _UNKNOWN_SYSTEM_LOGGED:
            _UNKNOWN_SYSTEM_LOGGED.add(log_key)
            print(
                f"[conditioning] Unknown energy system '{system or 'unknown'}' "
                f"normalized='{normalized}' source={source}"
            )
    return normalized


def _sanitize_conditioning_bank(bank, *, source: str):
    def normalize_items(items: list[dict]) -> list[dict]:
        cleaned: list[dict] = []
        for item in items:
            normalize_item_tags(item)
            placement = item.get("placement", "conditioning").lower()
            if placement != "conditioning":
                cleaned.append(item)
                continue
            normalized = normalize_system(item.get("system"), source=source)
            if normalized not in KNOWN_SYSTEMS:
                name = item.get("name", "Unnamed Drill")
                print(
                    f"[conditioning] Removing drill with invalid system "
                    f"bank={source} name='{name}' system='{item.get('system')}'"
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
    bank = json.loads(path.read_text())
    if enforce_conditioning_systems:
        return _sanitize_conditioning_bank(bank, source=source)
    if isinstance(bank, list):
        for item in bank:
            normalize_item_tags(item)
        return bank
    for items in bank.values():
        if isinstance(items, list):
            for item in items:
                normalize_item_tags(item)
    return bank


# Load banks
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
conditioning_bank = _load_bank(
    DATA_DIR / "conditioning_bank.json",
    source="conditioning_bank.json",
    enforce_conditioning_systems=True,
)
style_conditioning_bank = _load_bank(
    DATA_DIR / "style_conditioning_bank.json",
    source="style_conditioning_bank.json",
    enforce_conditioning_systems=True,
)
format_weights = json.loads((DATA_DIR / "format_energy_weights.json").read_text())

# Load coordination bank and flatten drills
try:
    _coord_data = _load_bank(DATA_DIR / "coordination_bank.json", source="coordination_bank.json")
except Exception:
    _coord_data = []

coordination_bank = []
if isinstance(_coord_data, list):
    coordination_bank.extend(_coord_data)
elif isinstance(_coord_data, dict):
    for val in _coord_data.values():
        if isinstance(val, list):
            coordination_bank.extend(val)

STYLE_CONDITIONING_RATIO = {
    "GPP": 0.20,
    "SPP": 0.60,
    "TAPER": 0.05,
}


def get_system_or_warn(drill: dict, *, source: str) -> str | None:
    system = normalize_system(drill.get("system"), source=source)
    if system in KNOWN_SYSTEMS:
        return system
    name = drill.get("name", "Unnamed Drill")
    log_key = (source, system, name)
    if log_key not in _UNKNOWN_SYSTEM_DRILL_LOGGED:
        _UNKNOWN_SYSTEM_DRILL_LOGGED.add(log_key)
        print(
            f"[conditioning] Dropping drill with unknown system "
            f"bank={source} name='{name}' system='{system}'"
        )
    return None


def _drill_text_injury_reasons(drill: dict, injuries: list[str]) -> list[dict]:
    return injury_match_details(drill, injuries, fields=("name", "notes"))


def _is_drill_text_safe(drill: dict, injuries: list[str], *, label: str) -> bool:
    reasons = _drill_text_injury_reasons(drill, injuries)
    if not reasons:
        return True
    for reason in reasons:
        region = reason["region"]
        fields = ", ".join(reason["fields"])
        patterns = ", ".join(reason["patterns"])
        tags = ", ".join(reason["tags"])
        log_key = (
            label,
            drill.get("name"),
            region,
            tuple(reason["fields"]),
            tuple(reason["patterns"]),
            tuple(reason["tags"]),
        )
        if log_key in _INJURY_GUARD_LOGGED:
            continue
        _INJURY_GUARD_LOGGED.add(log_key)
        print(
            f"[injury-guard] {label} excluded '{drill.get('name')}' "
            f"region={region} fields=[{fields}] patterns=[{patterns}] tags=[{tags}]"
        )
    return False

# Relative emphasis of each energy system by training phase
PHASE_SYSTEM_RATIOS = {
    "GPP": {"aerobic": 0.5, "glycolytic": 0.3, "alactic": 0.2},
    "SPP": {"glycolytic": 0.5, "alactic": 0.3, "aerobic": 0.2},
    "TAPER": {"alactic": 0.6, "aerobic": 0.4, "glycolytic": 0.0},
}

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
        "sprawling",
        "takedown",
        "takedowns",
    }

    if fight_format in {"boxing", "kickboxing"}:
        for term in grappling_terms:
            if term in name or term in tags or term in details:
                return True

    if fight_format == "boxing":
        boxing_terms = {
            "grappling",
            "wrestling",
            "muay_thai",
            "clinch",
            "knee",
            "kick",
            "teep",
            "elbow",
        }
        for term in boxing_terms:
            if term in name or term in tags:
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


def select_coordination_drill(flags, existing_names: set[str], injuries: list[str]):
    """Return a coordination drill matching the current phase if needed."""
    goals = [g.lower() for g in flags.get("key_goals", [])]
    weaknesses = [w.lower() for w in flags.get("weaknesses", [])]
    coord_terms = {"coordination", "coordination/proprioception", "coordination / proprioception"}
    if not any(g in coord_terms for g in goals) and not any(w in coord_terms for w in weaknesses):
        return None

    phase = flags.get("phase", "GPP").upper()
    equipment_access = set(normalize_equipment_list(flags.get("equipment", [])))
    candidates = [
        d
        for d in coordination_bank
        if phase in [p.upper() for p in d.get("phases", [])]
        and d.get("placement", "conditioning").lower() == "conditioning"
        and d.get("name") not in existing_names
        and _is_drill_text_safe(d, injuries, label="conditioning")
        and is_injury_safe(d, injuries)
        and (
            not normalize_equipment_list(d.get("equipment", []))
            or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access)
        )
    ]

    return random.choice(candidates) if candidates else None


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


def render_conditioning_block(
    grouped_drills: dict[str, list[dict]],
    *,
    phase: str,
    phase_color: str,
    missing_systems: Iterable[str] | None = None,
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
        "GPP": "3–5 rounds of 3–5 min @ RPE 6–7, work:rest 1:1–1:0.5 (cap 20–30 min).",
        "SPP": "4–6 rounds of 2–5 min @ RPE 7–8, work:rest 1:1–1:0.5 (cap 18–25 min).",
        "TAPER": "6–10 rounds of 6–12 sec @ RPE 8–9, rest 60–120 sec (cap 8–12 min).",
    }
    weekly_progression = {
        "GPP": "Add 1 round or ~5–10% volume weekly; deload final week by ~20%.",
        "SPP": "Increase density or intensity weekly; keep volume flat; deload final week by ~20%.",
        "TAPER": "Reduce volume 40–60%; keep speed sharp; last 3–5 days very light.",
    }
    time_short = {
        "GPP": "If time short: keep 2 aerobic rounds + 1 alactic pop.",
        "SPP": "If time short: keep 2 fight-pace rounds (system priority).",
        "TAPER": "If time short: keep 4–6 alactic bursts + shadowboxing rhythm.",
    }
    fatigue_note = {
        "GPP": "If fatigue high: drop 1–2 rounds, keep intensity easy.",
        "SPP": "If fatigue high: drop volume, keep rest longer.",
        "TAPER": "If fatigue high: keep only 4–6 low-impact bursts.",
    }

    output_lines = [f"\n🏃‍♂️ **Conditioning Block – {phase}**"]
    output_lines.append(f"**Session Title:** {phase_titles.get(phase, 'Conditioning')}")
    output_lines.append(f"**Intent:** {phase_intent.get(phase, 'Match phase intent.')}")
    output_lines.append(f"**Dosage Template:** {dosage_template.get(phase, 'Match system goals.')}")
    output_lines.append(f"**Weekly Progression:** {weekly_progression.get(phase, 'Progress weekly.')}")
    output_lines.append(f"**If Time Short:** {time_short.get(phase, 'Keep top 2 drills.')}")
    output_lines.append(f"**If Fatigue High:** {fatigue_note.get(phase, 'Reduce volume.')}")
    missing_systems = set(missing_systems or [])
    for system_name in ["aerobic", "glycolytic", "alactic"]:
        if system_name in missing_systems:
            output_lines.append(f"\n⚠️ No {system_name.upper()} drills available for this phase.")

    ordered_keys = ["aerobic", "glycolytic", "alactic"]
    ordered_keys += [k for k in grouped_drills.keys() if k not in ordered_keys]

    for system in ordered_keys:
        drills = grouped_drills.get(system)
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

def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    phase_color = {"GPP": "#4CAF50", "SPP": "#FF9800", "TAPER": "#F44336"}.get(phase.upper(), "#000")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", [])
    technical = flags.get("style_technical", [])
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])
    injuries = flags.get("injuries", [])
    training_frequency = flags.get("training_frequency", flags.get("days_available", 3))
    equipment_access = normalize_equipment_list(flags.get("equipment", []))
    equipment_access_set = set(equipment_access)

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
    style_tags = normalize_tags([t for s in style_tags for t in style_tag_map.get(s, [])])

    goal_tags = expand_tags(goals, goal_tag_map)
    weak_tags = expand_tags(weaknesses, weakness_tag_map)
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
    energy_weights = format_weights.get(fight_format, {})

    rename_map = {}
    if fight_format == "boxing":
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
    fight_format_tags = flags.get("fight_format_tags") or format_tag_map.get(fight_format, [])

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

    for drill in conditioning_bank:
        d = drill.copy()
        if d.get("placement", "conditioning").lower() != "conditioning":
            continue
        if fight_format == "boxing":
            d["name"] = rename_map.get(d.get("name"), d.get("name"))
            d["tags"] = [
                "boxing" if t.lower() == "muay_thai" else t
                for t in d.get("tags", [])
            ]
        if not _is_drill_text_safe(d, injuries, label="conditioning"):
            continue
        if not is_injury_safe(d, injuries):
            continue
        if phase.upper() not in d.get("phases", []):
            continue

        system = get_system_or_warn(d, source="conditioning_bank.json")
        if system is None:
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
        if is_banned_drill(
            d.get("name", ""),
            tags,
            fight_format,
            details,
            style_names,
            tech_style_tags,
        ):
            continue

        if (
            fight_format == "boxing"
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

        reasons = {
            "weakness_hits": num_weak,
            "goal_hits": num_goals,
            "style_hits": num_style,
            "phase_hits": 1,
            "load_adjustments": system_score,
            "equipment_boost": 0.0,
            "penalties": penalty,
            "final_score": round(total_score, 4),
        }

        system_drills[system].append((d, total_score, reasons))

    # ---- Style specific conditioning ----
    target_style_tags = set(style_names + tech_style_tags)
    for drill in style_conditioning_bank:
        d = drill.copy()
        if d.get("placement", "conditioning").lower() != "conditioning":
            continue
        if fight_format == "boxing":
            d["name"] = rename_map.get(d.get("name"), d.get("name"))
            d["tags"] = [
                "boxing" if t.lower() == "muay_thai" else t
                for t in d.get("tags", [])
            ]
        if not _is_drill_text_safe(d, injuries, label="conditioning"):
            continue
        if not is_injury_safe(d, injuries):
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
        if is_banned_drill(
            d.get("name", ""),
            tags,
            fight_format,
            details,
            style_names,
            tech_style_tags,
        ):
            continue
        if not target_style_tags.intersection(tags):
            continue
        if phase.upper() not in d.get("phases", []):
            continue

        if (
            fight_format == "boxing"
            and phase.upper() == "TAPER"
            and {"overhead", "rotational", "heavy_load"}.issubset(tags)
            and not (shoulder_focus and fatigue == "low")
        ):
            continue

        system = get_system_or_warn(d, source="style_conditioning_bank.json")
        if system is None:
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
        noise = random.uniform(-0.2, 0.2)
        score += noise

        reasons = {
            "weakness_hits": weak_matches,
            "goal_hits": goal_matches,
            "style_hits": 1,
            "phase_hits": 1,
            "load_adjustments": 0.75 if system == top_system else 0.0,
            "equipment_boost": equip_bonus,
            "penalties": penalty,
            "randomness": round(noise, 4),
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

    all_candidates_by_system = {
        system: [drill for drill, _, _ in system_drills.get(system, [])]
        + [drill for drill, _, _ in style_system_drills.get(system, [])]
        for system in system_drills
    }

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
        style_list = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
        combined_focus = [w.lower() for w in weaknesses] + [g.lower() for g in goals]
        allow_aerobic = any(k in combined_focus for k in ["conditioning", "endurance"])
        explicit_lactic_goal = any(g in ["conditioning", "endurance"] for g in combined_focus)
        allow_glycolytic = (
            fatigue == "low"
            and explicit_lactic_goal
            and any(s in ["pressure fighter", "scrambler"] for s in style_list)
        )

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

        if allow_glycolytic and taper_selected < 2:
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
        for drill in universal_conditioning:
            if injected >= injected_target or len(selected_drill_names) >= total_drills:
                break
            if drill.get("name") in existing_cond_names:
                continue
            if drill.get("placement", "conditioning").lower() != "conditioning":
                continue
            if not _is_drill_text_safe(drill, injuries, label="conditioning"):
                continue
            if not is_injury_safe(drill, injuries):
                continue
            drill_eq = normalize_equipment_list(drill.get("equipment", []))
            if drill_eq and not set(drill_eq).issubset(equipment_access_set):
                continue
            system = get_system_or_warn(drill, source="universal_gpp_conditioning.json")
            if system is None:
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
            if not _is_drill_text_safe(d, injuries, label="conditioning"):
                continue
            if not is_injury_safe(d, injuries):
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
                and _is_drill_text_safe(d, injuries, label="conditioning")
                and is_injury_safe(d, injuries)
                and (
                    not normalize_equipment_list(d.get("equipment", []))
                    or set(normalize_equipment_list(d.get("equipment", []))).issubset(
                        equipment_access_set
                    )
                )
            ]

        if taper_candidates and len(selected_drill_names) < total_drills:
            drill = random.choice(taper_candidates)
            if drill.get("name") not in existing_cond_names:
                system = get_system_or_warn(drill, source="style_taper_conditioning.json")
                if system is not None:
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

        # --------- TAPER PLYOMETRIC GUARANTEE ---------
        taper_plyos = [
            d for d in conditioning_bank
            if "TAPER" in [p.upper() for p in d.get("phases", [])]
            and d.get("placement", "conditioning").lower() == "conditioning"
            and "plyometric" in set(normalize_tags(d.get("tags", [])))
            and _is_drill_text_safe(d, injuries, label="conditioning")
            and is_injury_safe(d, injuries)
            and (
                not normalize_equipment_list(d.get("equipment", []))
                or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access_set)
            )
        ]
        if taper_plyos and len(selected_drill_names) < total_drills:
            existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
            drill = random.choice(taper_plyos)
            if drill.get("name") not in existing_cond_names:
                system = get_system_or_warn(drill, source="conditioning_taper_plyo")
                if system is not None:
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

    # --------- SKILL REFINEMENT DRILL GUARANTEE ---------
    goal_set = {g.lower() for g in goals}
    if "skill_refinement" in goal_set and len(selected_drill_names) < total_drills:
        existing_names = {d.get("name") for _, drills in final_drills for d in drills}
        skill_drills = [
            d for d in style_conditioning_bank
            if "skill_refinement" in set(normalize_tags(d.get("tags", [])))
            and d.get("placement", "conditioning").lower() == "conditioning"
            and phase.upper() in d.get("phases", [])
            and _is_drill_text_safe(d, injuries, label="conditioning")
            and is_injury_safe(d, injuries)
            and (
                not normalize_equipment_list(d.get("equipment", []))
                or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access_set)
            )
        ]
        random.shuffle(skill_drills)
        for drill in skill_drills:
            if drill.get("name") not in existing_names:
                system = get_system_or_warn(drill, source="skill_refinement")
                if system is None:
                    continue
                final_drills.append((system, [drill]))
                selected_drill_names.append(drill.get("name"))
                break

    # --------- OPTIONAL COORDINATION DRILL INSERTION ---------
    existing_names = {d.get("name") for _, drills in final_drills for d in drills}
    coord_drill = select_coordination_drill(
        {**flags, "equipment": equipment_access}, existing_names, injuries
    )
    if coord_drill and len(selected_drill_names) < total_drills:
        system = get_system_or_warn(coord_drill, source="coordination")
        if system is not None:
            final_drills.append((system, [coord_drill]))
            selected_drill_names.append(coord_drill.get("name"))
            reason_lookup[coord_drill.get("name")] = {
                "goal_hits": 0,
                "weakness_hits": 0,
                "style_hits": 0,
                "phase_hits": 1,
                "load_adjustments": 0,
                "equipment_boost": 0,
                "penalties": 0,
                "final_score": 0,
            }

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
                for d in conditioning_bank
                if "neck" in set(normalize_tags(d.get("tags", [])))
                and is_injury_safe(d, injuries)
                and _is_drill_text_safe(d, injuries, label="conditioning")
                and phase.upper() in d.get("phases", [])
                and (
                    not normalize_equipment_list(d.get("equipment", []))
                    or set(normalize_equipment_list(d.get("equipment", []))).issubset(equipment_access_set)
                )
            ]
            if neck_candidates and len(selected_drill_names) < total_drills:
                drill = random.choice(neck_candidates)
                system = get_system_or_warn(drill, source="pro_neck")
                if system is not None:
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

    # Trim any extras beyond the recommended count
    if len(selected_drill_names) > total_drills:
        extra = len(selected_drill_names) - total_drills
        final_drills = final_drills[:-extra]
        selected_drill_names = selected_drill_names[:-extra]

    # Group drills by energy system so each system only prints once
    grouped_drills: dict[str, list[dict]] = {}
    for system, drills in final_drills:
        grouped_drills.setdefault(system, []).extend(drills)

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
        cache: dict[str, tuple[bool, list]] = {}

        def _violations(d: dict) -> list:
            n = _name(d) or f"__unnamed__:{id(d)}"
            if n in cache:
                ok, reasons = cache[n]
                return [] if ok else reasons

            reasons = injury_match_details(
                d,
                injuries,
                fields=("name", "notes"),
                risk_levels=("exclude",),
            )

            ok = len(reasons) == 0
            cache[n] = (ok, reasons)
            return [] if ok else reasons

        for system, drills in list(grouped.items()):
            idx = 0
            candidates = all_candidates_by_system.get(system, [])

            while idx < len(drills):
                drill = drills[idx]
                drill_name = _name(drill) or "(unnamed)"
                reasons = _violations(drill)

                if not reasons:
                    idx += 1
                    continue

                safe_pool: list[dict] = []
                for cand in candidates:
                    cand_name = _name(cand)
                    if not cand_name or cand_name in used_names:
                        continue
                    if _violations(cand):
                        continue
                    safe_pool.append(cand)

                replacement = None
                if safe_pool:
                    if score_fn is None:
                        replacement = safe_pool[0]
                    else:
                        replacement = max(safe_pool, key=score_fn)

                if replacement:
                    rep_name = _name(replacement) or "(unnamed)"
                    print(
                        "[injury-guard] conditioning replacing "
                        f"'{drill_name}' -> '{rep_name}' reasons={reasons}"
                    )

                    old_name = _name(drill)
                    if old_name:
                        used_names.discard(old_name)
                    used_names.add(rep_name)

                    drills[idx] = replacement

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
                    print(
                        "[injury-guard] conditioning removing "
                        f"'{drill_name}' reasons={reasons}"
                    )

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

    if os.getenv("INJURY_DEBUG") == "1":
        all_selected = [d for drills in grouped_drills.values() for d in drills]
        log_injury_debug(all_selected, injuries, label=f"conditioning:{phase.upper()}")

    missing_systems = [
        system_name
        for system_name in ["aerobic", "glycolytic", "alactic"]
        if not system_drills[system_name]
    ]
    output_lines = render_conditioning_block(
        grouped_drills,
        phase=phase,
        phase_color=phase_color,
        missing_systems=missing_systems,
    )

    why_log = []
    for system, drills in grouped_drills.items():
        for d in drills:
            nm = d.get("name")
            reasons = reason_lookup.get(nm, {}).copy()
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
            explanation = ", ".join(parts) if parts else "balanced selection"
            reasons.setdefault("final_score", 0)
            why_log.append({"name": nm, "system": system, "reasons": reasons, "explanation": explanation})

    return output_lines, selected_drill_names, why_log, grouped_drills, missing_systems
