import json
from pathlib import Path
from training_context import allocate_sessions, normalize_equipment_list

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
    "plyometric", "rate_of_force", "contrast_pairing", "horizontal_power",
    "triple_extension", "overhead", "elastic", "compound", "mental_toughness",
    "work_capacity", "eccentric", "footwork",
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
    "injury_prevention": [
        "recovery", "balance", "eccentric", "zero_impact", "parasympathetic",
        "cns_freshness", "unilateral", "movement_quality", "stability", "neck"
    ],
    "mental_resilience": [
        "mental_toughness", "cognitive", "parasympathetic", "visual_processing",
        "focus", "environmental", "pressure_tolerance"
    ],
    "skill_refinement": [
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
style_conditioning_bank = json.loads(Path("style_conditioning_bank.json").read_text())
format_weights = json.loads(Path("format_energy_weights.json").read_text())

STYLE_CONDITIONING_RATIO = {
    "GPP": 0.15,
    "SPP": 0.55,
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

def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", [])
    technical = flags.get("style_technical", [])
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])
    days_available = flags.get("days_available", 3)
    equipment_access = normalize_equipment_list(flags.get("equipment", []))

    # Handle multiple technical styles
    if isinstance(technical, list):
        technical = technical[0].lower()
    else:
        technical = technical.lower()

    # preserve tactical style names for style drill filtering
    if isinstance(style, list):
        style_names = [s.lower().replace(" ", "_") for s in style]
    elif isinstance(style, str):
        style_names = [style.lower().replace(" ", "_")]
    else:
        style_names = []
    tech_style_tag = technical.lower().replace(" ", "_")

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
    style_system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
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
    target_style_tags = set(style_names + [tech_style_tag])
    for drill in style_conditioning_bank:
        tags = [t.lower() for t in drill.get("tags", [])]
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

        equip_bonus = 0.0
        for eq in drill.get("equipment", []):
            if eq.lower() in equipment_access:
                equip_bonus = 1.0
                break

        score = 0.0
        score += 3.0  # style tag match (already filtered)
        score += 1.5  # phase match
        score += 1.0  # energy system match
        score += equip_bonus
        score += 0.5  # unique name incentive

        style_system_drills[system].append((drill, score))

    for drills in system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)
    for drills in style_system_drills.values():
        drills.sort(key=lambda x: x[1], reverse=True)

    if days_available >= 6:
        num_conditioning_sessions = 3
    elif days_available >= 4:
        num_conditioning_sessions = 2
    elif days_available >= 2:
        num_conditioning_sessions = 1
    else:
        num_conditioning_sessions = 0

    drills_per_session = 3 if fatigue == "low" else 2
    total_drills = num_conditioning_sessions * drills_per_session

    system_quota = {
        k: max(1 if v > 0 else 0, round(total_drills * v))
        for k, v in PHASE_SYSTEM_RATIOS.get(phase.upper(), {}).items()
    }

    final_drills = []
    taper_selected = 0

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

    style_target = round(total_drills * STYLE_CONDITIONING_RATIO.get(phase.upper(), 0))
    style_remaining = min(style_target, sum(len(v) for v in style_system_drills.values()))
    general_remaining = total_drills - style_remaining

    def blended_pick(system: str):
        nonlocal style_remaining, general_remaining
        drill = None
        if style_remaining > 0:
            drill = pop_drill(style_system_drills, system)
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
        total_drills = min(total_drills, 3)
        style_list = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
        combined_focus = [w.lower() for w in weaknesses] + [g.lower() for g in goals]
        allow_aerobic = any(k in combined_focus for k in ["conditioning", "endurance"])
        allow_glycolytic = (
            fatigue == "low" and any(s in ["pressure fighter", "scrambler"] for s in style_list)
        )

        d = blended_pick("alactic")
        if d:
            final_drills.append(("alactic", [d]))
            taper_selected += 1

        if allow_aerobic and taper_selected < 2:
            d = blended_pick("aerobic")
            if d:
                final_drills.append(("aerobic", [d]))
                taper_selected += 1

        if allow_glycolytic and taper_selected < 2:
            d = blended_pick("glycolytic")
            if d:
                final_drills.append(("glycolytic", [d]))
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
                quota -= 1

        remaining_slots = total_drills - len(selected_drill_names)
        for system in preferred_order:
            if remaining_slots <= 0:
                break
            while remaining_slots > 0:
                d = blended_pick(system)
                if not d:
                    break
                final_drills.append((system, [d]))
                remaining_slots -= 1

    # --------- UNIVERSAL CONDITIONING INSERTION ---------
    if phase == "GPP":
        try:
            with open("universal_gpp_conditioning.json", "r") as f:
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

        injected = 0
        for drill in universal_conditioning:
            if injected >= 3:
                break
            if drill.get("name") in existing_cond_names:
                continue
            drill_tags = set(drill.get("tags", []))
            if drill.get("name") in high_priority_names or drill_tags & (goal_tags_set | weakness_tags_set):
                final_drills.append((drill.get("system", "misc"), [drill]))
                selected_drill_names.append(drill.get("name"))
                existing_cond_names.add(drill.get("name"))
                injected += 1

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