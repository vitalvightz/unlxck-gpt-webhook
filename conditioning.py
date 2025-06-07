import json
from pathlib import Path
from training_context import allocate_sessions

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
    "grappling": [
        "wrestling", "bjj", "grip", "rotational", "core", "unilateral", "tactical",
        "manual_resistance", "positioning"
    ],
    "striking": [
        "striking", "boxing", "muay_thai", "shoulders", "rate_of_force",
        "coordination", "visual_processing", "rhythm", "timing"
    ],
    "injury prevention": [
        "recovery", "balance", "eccentric", "zero_impact", "parasympathetic",
        "cns_freshness", "unilateral", "movement_quality", "stability", "neck"
    ],
    "mental resilience": [
        "mental_toughness", "cognitive", "parasympathetic", "visual_processing",
        "focus", "environmental", "pressure_tolerance"
    ],
    "skill refinement": [
        "coordination", "skill", "footwork", "cognitive", "focus", "reactive", "decision_speed"
    ]
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
    "knees": ["quad_dominant", "eccentric"]
}

# Load banks
conditioning_bank = json.loads(Path("conditioning_bank.json").read_text())
format_weights = json.loads(Path("format_energy_weights.json").read_text())

SYSTEM_ALIASES = {
    "atp-pcr": "alactic",
    "anaerobic_alactic": "alactic",
    "cognitive": "alactic"
}

def expand_tags(input_list, tag_map):
    expanded = []
    for item in input_list:
        tags = tag_map.get(item.lower(), [])
        expanded.extend(tags)
    return [t.lower() for t in expanded]

def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", [])
    technical = flags.get("style_technical", [])
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])
    days_available = flags.get("days_available", 3)

    # Handle multiple technical styles
    if isinstance(technical, list):
        technical = technical[0].lower()
    else:
        technical = technical.lower()

    style_tags = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
    style_tags = [t for s in style_tags for t in style_tag_map.get(s, [])]

    goal_tags = expand_tags(goals, goal_tag_map)
    weak_tags = expand_tags(weaknesses, weakness_tag_map)

    style_map = {
        "mma": "mma", "boxer": "boxing", "kickboxer": "kickboxing",
        "muay thai": "muay_thai", "bjj": "mma", "wrestler": "mma",
        "grappler": "mma", "karate": "kickboxing"
    }
    fight_format = style_map.get(technical, "mma")
    energy_weights = format_weights.get(fight_format, {})

    format_tag_map = {
        "mma": ["mma", "bjj", "wrestling"],
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
    selected_drill_names = []

    for drill in conditioning_bank:
        if phase.upper() not in drill.get("phases", []):
            continue

        raw_system = drill.get("system", "").lower()
        system = SYSTEM_ALIASES.get(raw_system, raw_system)
        if system not in system_drills:
            continue

        tags = [t.lower() for t in drill.get("tags", [])]

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
        extra_skip_tags = {
            "plyometric",
            "rate_of_force",
            "contrast_pairing",
            "horizontal_power",
            "triple_extension",
            "overhead",
            "elastic",
            "compound",
            "mental_toughness",
            "work_capacity",
            "eccentric",
            "footwork",
        }
        if (
            phase.upper() == "TAPER"
            and fatigue != "low"
            and any(t in extra_skip_tags for t in tags)
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
        system_score = round(energy_multiplier * 2.0, 2)
        total_score = base_score + system_score

        if fatigue == "high" and "high_cns" in tags:
            total_score -= 1.5
        elif fatigue == "moderate" and "high_cns" in tags:
            total_score -= 0.75

        system_drills[system].append((drill, total_score))

    for drills in system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)

    session_allocation = allocate_sessions(days_available)
    num_conditioning_sessions = session_allocation.get("conditioning", 1)
    drills_per_session = 2 if fatigue == "low" else 1
    total_drills = num_conditioning_sessions * drills_per_session

    final_drills = []
    taper_selected = 0

    def pick_drill(system: str):
        for drill, _ in system_drills.get(system, []):
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
            return drill
        return None

    if phase.upper() == "TAPER":
        total_drills = min(total_drills, 3)
        style_list = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
        combined_focus = [w.lower() for w in weaknesses] + [g.lower() for g in goals]
        allow_aerobic = any(k in combined_focus for k in ["conditioning", "endurance"])
        allow_glycolytic = (
            fatigue == "low" and any(s in ["pressure fighter", "scrambler"] for s in style_list)
        )

        if system_drills["alactic"]:
            d = pick_drill("alactic")
            if d:
                final_drills.append(("alactic", [d]))
                taper_selected += 1

        if allow_aerobic and taper_selected < 2 and system_drills["aerobic"]:
            d = pick_drill("aerobic")
            if d:
                final_drills.append(("aerobic", [d]))
                taper_selected += 1

        if allow_glycolytic and taper_selected < 2 and system_drills["glycolytic"]:
            d = pick_drill("glycolytic")
            if d:
                final_drills.append(("glycolytic", [d]))
                taper_selected += 1
    else:
        enforced = set()
        for system in preferred_order:
            candidates = system_drills.get(system, [])
            for drill, _ in candidates:
                name = drill.get("name")
                tags = [t.lower() for t in drill.get("tags", [])]
                allow_repeat = (
                    phase.upper() == "TAPER"
                    and system == "alactic"
                    and any(t in weak_tags for t in tags)
                )
                if name in selected_drill_names and not allow_repeat:
                    continue
                final_drills.append((system, [drill]))
                selected_drill_names.append(name)
                enforced.add(system)
                break

        remaining_slots = total_drills - len(selected_drill_names)
        for system in preferred_order:
            if remaining_slots <= 0:
                break
            for drill, _ in system_drills.get(system, []):
                name = drill.get("name")
                tags = [t.lower() for t in drill.get("tags", [])]
                allow_repeat = (
                    phase.upper() == "TAPER"
                    and system == "alactic"
                    and any(t in weak_tags for t in tags)
                )
                if name in selected_drill_names and not allow_repeat:
                    continue
                final_drills.append((system, [drill]))
                selected_drill_names.append(name)
                remaining_slots -= 1
                if remaining_slots <= 0:
                    break

    taper_drill_count = sum(len(drills) for _, drills in final_drills) if phase.upper() == "TAPER" else 0

    output_lines = [f"\n🏃‍♂️ **Conditioning Block – {phase.upper()}**"]
    for system_name in ["aerobic", "glycolytic", "alactic"]:
        if not system_drills[system_name]:
            output_lines.append(f"\n⚠️ No {system_name.upper()} drills available for this phase.")

    for system, drills in final_drills:
        output_lines.append(f"\n📌 **System: {system.upper()}** (scaled by format emphasis)")
        for d in drills:
            output_lines.append(f"- **Drill:** {d.get('name', 'Unnamed Drill')}")
            output_lines.append(f"  • Load: {d.get('load', '—')}")
            output_lines.append(f"  • Rest: {d.get('rest', '—')}")
            output_lines.append(f"  • Timing: {d.get('timing', '—')}")
            output_lines.append(f"  • Purpose: {d.get('purpose', '—')}")
            output_lines.append(f"  • ⚠️ Red Flags: {d.get('red_flags', 'None')}")

    if fatigue == "high":
        output_lines.append("\n⚠️ High fatigue detected – conditioning volume reduced.")
    elif fatigue == "moderate":
        output_lines.append("\n⚠️ Moderate fatigue – monitor recovery and hydration closely.")

    return "\n".join(output_lines), selected_drill_names
