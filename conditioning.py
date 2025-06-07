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
    "power": ["explosive", "rate_of_force", "triple_extension", "horizontal_power", "plyometric", "elastic", "lateral_power", "deadlift"],
    "strength": ["posterior_chain", "quad_dominant", "upper_body", "core", "pull", "hamstring", "hip_dominant", "eccentric", "deadlift"],
    "endurance": ["aerobic", "glycolytic", "work_capacity", "mental_toughness", "conditioning", "improvised"],
    "speed": ["speed", "agility", "footwork", "reactive", "acceleration", "ATP-PCr", "anaerobic_alactic"],
    "mobility": ["mobility", "hip_dominant", "balance", "eccentric", "unilateral", "adductors", "stability"],
    "grappling": ["wrestling", "bjj", "grip", "rotational", "core", "unilateral"],
    "striking": ["striking", "boxing", "muay_thai", "shoulders", "rate_of_force", "coordination", "visual_processing"],
    "injury prevention": ["recovery", "balance", "eccentric", "zero_impact", "parasympathetic", "cns_freshness", "unilateral"],
    "mental resilience": ["mental_toughness", "cognitive", "parasympathetic", "visual_processing", "focus", "environmental"],
    "skill refinement": ["coordination", "skill", "footwork", "cognitive"]
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
        "TAPER": ["aerobic", "alactic"]
    }
    preferred_order = phase_priority.get(phase.upper(), ["aerobic", "glycolytic", "alactic"])
    system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}

    for drill in conditioning_bank:
        if phase.upper() not in drill.get("phases", []):
            continue

        raw_system = drill.get("system", "").lower()
        system = SYSTEM_ALIASES.get(raw_system, raw_system)
        if system not in system_drills:
            continue

        tags = [t.lower() for t in drill.get("tags", [])]

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
    enforced = set()
    for system in preferred_order:
        candidates = system_drills.get(system, [])
        if candidates:
            final_drills.append((system, [candidates[0][0]]))
            enforced.add(system)

    remaining_slots = total_drills - len(final_drills)
    for system in preferred_order:
        if remaining_slots <= 0:
            break
        available = [d for d in system_drills[system] if d[0] not in [dr[0] for _, drills in final_drills for dr in drills]]
        if not available:
            continue
        count = min(remaining_slots, len(available))
        final_drills.append((system, [d[0] for d in available[:count]]))
        remaining_slots -= count

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

    return {
        "block": "\n".join(output_lines),
        "num_sessions": len(final_drills)
    }