import json
from pathlib import Path

conditioning_bank = json.loads(Path("conditioning_bank.json").read_text())
format_weights = json.loads(Path("format_energy_weights.json").read_text())

def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", "").lower()
    technical = flags.get("style_technical", "").lower()
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])

    # Map technical style to fight format
    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "kickboxer": "kickboxing",
        "muay thai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "grappler": "mma",
        "karate": "kickboxing"
    }
    fight_format = style_map.get(technical, "mma")
    energy_weights = format_weights.get(fight_format, {})

    style_tags = [style] if style else []
    goal_tags = [g.lower() for g in goals]
    weak_tags = [w.lower() for w in weaknesses]

    # Phase bias system
    phase_priority = {
        "GPP": ["aerobic", "glycolytic", "alactic"],
        "SPP": ["glycolytic", "alactic", "aerobic"],
        "TAPER": ["aerobic", "alactic"]
    }
    preferred_order = phase_priority.get(phase.upper(), ["aerobic", "glycolytic", "alactic"])

    # Group by system
    system_drills = {"aerobic": [], "glycolytic": [], "alactic": []}
    for drill in conditioning_bank:
        if phase.upper() not in drill.get("phases", []):
            continue

        system = drill.get("system", "").lower()
        if system not in system_drills:
            continue

        tags = [t.lower() for t in drill.get("tags", [])]
        base_score = 0
        base_score += sum(2.5 for t in tags if t in weak_tags)
        base_score += sum(2 for t in tags if t in goal_tags)
        base_score += sum(1 for t in tags if t in style_tags)

        # Apply energy system weighting
        system_weight = energy_weights.get(system, 0)
        system_score = system_weight * 5  # ⬅️ multiplier is tunable
        total_score = base_score + system_score

        system_drills[system].append((drill, total_score))

    # Select drills per system
    final_drills = []
    for system in preferred_order:
        drills = sorted(system_drills.get(system, []), key=lambda x: x[1], reverse=True)
        top = drills[:3] if fatigue == "low" else drills[:2]
        if not top:
            continue
        final_drills.append((system, [d[0] for d in top]))

    # Format Output
    output_lines = [f"\n🏃‍♂️ **Conditioning Block – {phase.upper()}**"]
    for system, drills in final_drills:
        output_lines.append(f"\n📌 **System: {system.upper()}**")
        for d in drills:
            name = d.get("name", "Unnamed Drill")
            load = d.get("load", "—")
            rest = d.get("rest", "—")
            timing = d.get("timing", "—")
            purpose = d.get("purpose", "—")
            red_flags = d.get("red_flags", "None")
            output_lines.append(f"- **Drill:** {name}")
            output_lines.append(f"  • Load: {load}")
            output_lines.append(f"  • Rest: {rest}")
            output_lines.append(f"  • Timing: {timing}")
            output_lines.append(f"  • Purpose: {purpose}")
            output_lines.append(f"  • ⚠️ Red Flags: {red_flags}")

    if fatigue == "high":
        output_lines.append("\n⚠️ High fatigue detected – conditioning volume reduced.")
    elif fatigue == "moderate":
        output_lines.append("\n⚠️ Moderate fatigue – monitor recovery and hydration closely.")

    return {
        "block": "\n".join(output_lines),
        "num_sessions": len(final_drills)
    }
