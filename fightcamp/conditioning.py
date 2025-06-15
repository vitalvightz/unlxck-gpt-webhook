import json
from pathlib import Path
import random
from .training_context import (
    allocate_sessions,
    normalize_equipment_list,
    calculate_exercise_numbers,
)

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
    "hip mobility": ["hip_dominant", "mobility"],
    "grip strength": ["grip", "pull"],
    "posterior chain": ["posterior_chain", "hip_dominant"],
    "knees": ["quad_dominant", "eccentric"],
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"]
}

# Load banks
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
conditioning_bank = json.loads((DATA_DIR / "conditioning_bank.json").read_text())
style_conditioning_bank = json.loads((DATA_DIR / "style_conditioning_bank.json").read_text())
format_weights = json.loads((DATA_DIR / "format_energy_weights.json").read_text())

# Load coordination bank and flatten drills
try:
    _coord_data = json.loads((DATA_DIR / "coordination_bank.json").read_text())
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

SYSTEM_ALIASES = {
    "atp-pcr": "alactic",
    "anaerobic_alactic": "alactic",
    "cognitive": "alactic"
}

# Relative emphasis of each energy system by training phase
PHASE_SYSTEM_RATIOS = {
    "GPP": {"aerobic": 0.5, "glycolytic": 0.3, "alactic": 0.2},
    "SPP": {"glycolytic": 0.5, "alactic": 0.3, "aerobic": 0.2},
    "TAPER": {"alactic": 0.5, "aerobic": 0.35, "glycolytic": 0.15},
}

def expand_tags(input_list, tag_map):
    expanded = []
    for item in input_list:
        tags = tag_map.get(item.lower(), [])
        expanded.extend(tags)
    return [t.lower() for t in expanded]

def is_banned_drill(name: str, tags: list[str], fight_format: str, details: str = "") -> bool:
    """Return True if the drill should be removed for the given sport."""
    name = name.lower()
    tags = [t.lower() for t in tags]
    details = details.lower()

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
    }

    if fight_format in {"boxing", "kickboxing"}:
        for term in grappling_terms:
            if term in name or term in tags or term in details:
                return True

    if fight_format == "boxing":
        for term in ["kick", "knee", "clinch knee strike"]:
            if term in name or term in tags or term in details:
                return True

    return False


def select_coordination_drill(flags, existing_names: set[str]):
    """Return a coordination drill matching the current phase if needed."""
    goals = [g.lower() for g in flags.get("key_goals", [])]
    weaknesses = [w.lower() for w in flags.get("weaknesses", [])]
    coord_terms = {"coordination", "coordination/proprioception", "coordination / proprioception"}
    if not any(g in coord_terms for g in goals) and not any(w in coord_terms for w in weaknesses):
        return None

    phase = flags.get("phase", "GPP").upper()
    candidates = [
        d
        for d in coordination_bank
        if phase in [p.upper() for p in d.get("phases", [])]
        and d.get("placement", "conditioning").lower() == "conditioning"
        and d.get("name") not in existing_names
    ]

    return random.choice(candidates) if candidates else None

def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", [])
    technical = flags.get("style_technical", [])
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])
    training_frequency = flags.get("training_frequency", flags.get("days_available", 3))
    equipment_access = normalize_equipment_list(flags.get("equipment", []))

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
    style_tags = [t for s in style_tags for t in style_tag_map.get(s, [])]

    goal_tags = expand_tags(goals, goal_tag_map)
    weak_tags = expand_tags(weaknesses, weakness_tag_map)

    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "kickboxer": "kickboxing",
        "muay thai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "wrestling": "wrestler",
        "grappler": "mma",
        "grappling": "grappler",
        "karate": "kickboxing",
    }
    fight_format = style_map.get(primary_tech, "mma")
    energy_weights = format_weights.get(fight_format, {})

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

    for drill in conditioning_bank:
        if phase.upper() not in drill.get("phases", []):
            continue

        raw_system = drill.get("system", "").lower()
        system = SYSTEM_ALIASES.get(raw_system, raw_system)
        if system not in system_drills:
            continue

        tags = [t.lower() for t in drill.get("tags", [])]
        details = " ".join(
            [
                drill.get("duration", ""),
                drill.get("notes", ""),
                drill.get("modality", ""),
                drill.get("equipment_note", ""),
            ]
        )
        if is_banned_drill(drill.get("name", ""), tags, fight_format, details):
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

        if fatigue == "high" and "high_cns" in tags:
            total_score -= 2.0
        elif fatigue == "moderate" and "high_cns" in tags:
            total_score -= 1.0

        system_drills[system].append((drill, total_score))

    # ---- Style specific conditioning ----
    target_style_tags = set(style_names + tech_style_tags)
    for drill in style_conditioning_bank:
        tags = [t.lower() for t in drill.get("tags", [])]
        details = " ".join(
            [
                drill.get("duration", ""),
                drill.get("notes", ""),
                drill.get("modality", ""),
                drill.get("equipment_note", ""),
            ]
        )
        if is_banned_drill(drill.get("name", ""), tags, fight_format, details):
            continue
        if not target_style_tags.intersection(tags):
            continue
        if phase.upper() not in drill.get("phases", []):
            continue

        raw_system = drill.get("system", "").lower()
        system = SYSTEM_ALIASES.get(raw_system, raw_system)
        if system not in style_system_drills:
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

        equip_bonus = 0.5 if any(
            eq.lower() in equipment_access for eq in drill.get("equipment", [])
        ) else 0.0

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
        if "high_cns" in tags:
            if fatigue == "high":
                score -= 1.0
            elif fatigue == "moderate":
                score -= 0.5
        score += random.uniform(-0.2, 0.2)

        style_system_drills[system].append((drill, score))
        for st in style_names:
            if st in tags:
                style_drills_by_style[st][system].append((drill, score))

    for drills in system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for drills in style_system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for style_lists in style_drills_by_style.values():
        for drills in style_lists.values():
            drills.sort(key=lambda x: x[1], reverse=True)

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
        for idx, (drill, _) in enumerate(drills):
            name = drill.get("name")
            tags = [t.lower() for t in drill.get("tags", [])]
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
            return drill
        return None

    def pop_style_drill(system: str):
        for style in sorted(style_counts, key=style_counts.get):
            drills = style_drills_by_style.get(style, {}).get(system, [])
            for idx, (drill, _) in enumerate(drills):
                name = drill.get("name")
                tags = [t.lower() for t in drill.get("tags", [])]
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
                return drill
        return None

    style_target = round(total_drills * STYLE_CONDITIONING_RATIO.get(phase.upper(), 0))
    style_remaining = min(style_target, sum(len(v) for v in style_system_drills.values()))
    general_remaining = total_drills - style_remaining

    def blended_pick(system: str):
        nonlocal style_remaining, general_remaining
        drill = None
        if style_remaining > 0:
            drill = pop_style_drill(system)
            if drill:
                style_remaining -= 1
                return drill
        if general_remaining > 0:
            drill = pop_drill(system_drills, system)
            if drill:
                general_remaining -= 1
                return drill
        return None

    if phase.upper() == "TAPER":
        style_list = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
        combined_focus = [w.lower() for w in weaknesses] + [g.lower() for g in goals]
        allow_aerobic = any(k in combined_focus for k in ["conditioning", "endurance"])
        allow_glycolytic = (
            fatigue == "low" and any(s in ["pressure fighter", "scrambler"] for s in style_list)
        )

        d = blended_pick("alactic")
        if d:
            final_drills.append(("alactic", [d]))
            selected_counts["alactic"] += 1
            taper_selected += 1

        if allow_aerobic and taper_selected < 2:
            d = blended_pick("aerobic")
            if d:
                final_drills.append(("aerobic", [d]))
                selected_counts["aerobic"] += 1
                taper_selected += 1

        if allow_glycolytic and taper_selected < 2:
            d = blended_pick("glycolytic")
            if d:
                final_drills.append(("glycolytic", [d]))
                selected_counts["glycolytic"] += 1
                taper_selected += 1
    else:
        for system in preferred_order:
            quota = system_quota.get(system, 0)
            if quota <= 0:
                continue
            while quota > 0:
                d = blended_pick(system)
                if not d:
                    break
                final_drills.append((system, [d]))
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
            d = blended_pick(system)
            if not d:
                deficits[system] = 0
                continue
            final_drills.append((system, [d]))
            selected_counts[system] += 1
            deficits[system] = max(0, deficits[system] - 1)
            remaining_slots -= 1

    # --------- UNIVERSAL CONDITIONING INSERTION ---------
    if phase == "GPP":
        try:
            with open(DATA_DIR / "universal_gpp_conditioning.json", "r") as f:
                universal_conditioning = json.load(f)
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
            if injected >= injected_target:
                break
            if drill.get("name") in existing_cond_names:
                continue
            system = SYSTEM_ALIASES.get(drill.get("system", "").lower(), drill.get("system", "misc"))
            drill_tags = set(drill.get("tags", []))
            if drill.get("name") in high_priority_names or drill_tags & (goal_tags_set | weakness_tags_set):
                final_drills.append((system, [drill]))
                selected_drill_names.append(drill.get("name"))
                existing_cond_names.add(drill.get("name"))
                injected += 1

    # --------- STYLE TAPER DRILL INSERTION ---------
    if phase == "TAPER":
        try:
            with open(DATA_DIR / "style_taper_conditioning.json", "r") as f:
                style_taper_bank = json.load(f)
        except Exception:
            style_taper_bank = []

        existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
        style_set = set(style_names)
        taper_candidates = [
            d for d in style_taper_bank
            if style_set.intersection({t.lower() for t in d.get("tags", [])})
        ]
        if not taper_candidates:
            taper_candidates = style_taper_bank

        if taper_candidates:
            drill = random.choice(taper_candidates)
            if drill.get("name") not in existing_cond_names:
                system = SYSTEM_ALIASES.get(drill.get("system", "").lower(), drill.get("system", "misc"))
                final_drills.append((system, [drill]))
                selected_drill_names.append(drill.get("name"))

        # --------- TAPER PLYOMETRIC GUARANTEE ---------
        taper_plyos = [
            d for d in conditioning_bank
            if "TAPER" in [p.upper() for p in d.get("phases", [])]
            and "plyometric" in {t.lower() for t in d.get("tags", [])}
        ]
        if taper_plyos:
            existing_cond_names = {d.get("name") for _, drills in final_drills for d in drills}
            drill = random.choice(taper_plyos)
            if drill.get("name") not in existing_cond_names:
                system = SYSTEM_ALIASES.get(
                    drill.get("system", "").lower(), drill.get("system", "misc")
                )
                final_drills.append((system, [drill]))
                selected_drill_names.append(drill.get("name"))

    # --------- SKILL REFINEMENT DRILL GUARANTEE ---------
    goal_set = {g.lower() for g in goals}
    if "skill_refinement" in goal_set:
        existing_names = {d.get("name") for _, drills in final_drills for d in drills}
        skill_drills = [
            d for d in style_conditioning_bank
            if "skill_refinement" in {t.lower() for t in d.get("tags", [])}
            and phase.upper() in d.get("phases", [])
        ]
        random.shuffle(skill_drills)
        for drill in skill_drills:
            if drill.get("name") not in existing_names:
                system = SYSTEM_ALIASES.get(
                    drill.get("system", "").lower(), drill.get("system", "misc")
                )
                final_drills.append((system, [drill]))
                selected_drill_names.append(drill.get("name"))
                break

    # --------- OPTIONAL COORDINATION DRILL INSERTION ---------
    existing_names = {d.get("name") for _, drills in final_drills for d in drills}
    coord_drill = select_coordination_drill(flags, existing_names)
    if coord_drill:
        system = SYSTEM_ALIASES.get(coord_drill.get("system", "").lower(), coord_drill.get("system", "misc"))
        final_drills.append((system, [coord_drill]))
        selected_drill_names.append(coord_drill.get("name"))

    output_lines = [f"\n🏃‍♂️ **Conditioning Block – {phase.upper()}**"]
    for system_name in ["aerobic", "glycolytic", "alactic"]:
        if not system_drills[system_name]:
            output_lines.append(f"\n⚠️ No {system_name.upper()} drills available for this phase.")

    for system, drills in final_drills:
        output_lines.append(
            f"\n📌 **System: {system.upper()}** (scaled by format emphasis)"
        )
        for d in drills:
            name = d.get("name", "Unnamed Drill")
            equipment = d.get("equipment", [])
            if isinstance(equipment, str):
                equipment = [equipment]
            extra_eq = [e for e in equipment if e.lower() not in name.lower()]
            if extra_eq:
                name = f"{name} ({', '.join(extra_eq)})"

            timing = d.get("timing") or d.get("duration") or "—"
            load = d.get("load") or d.get("intensity") or "—"
            equip_note = d.get("equipment_note") or d.get("equipment_notes")
            if equip_note:
                load = f"{load} ({equip_note})" if load != "—" else equip_note

            purpose = (
                d.get("purpose")
                or d.get("notes")
                or d.get("description")
                or "—"
            )
            rest = d.get("rest", "—")

            output_lines.append(f"- **Drill:** {name}")
            output_lines.append(f"  • Load: {load}")
            output_lines.append(f"  • Rest: {rest}")
            output_lines.append(f"  • Timing: {timing}")
            output_lines.append(f"  • Purpose: {purpose}")
            output_lines.append(f"  • ⚠️ Red Flags: {d.get('red_flags', 'None')}")


    return "\n".join(output_lines), selected_drill_names
