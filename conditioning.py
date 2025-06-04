import json
from pathlib import Path

conditioning_bank = json.loads(Path("conditioning_bank.json").read_text())

def generate_conditioning_block(flags):
    phase = flags.get("phase", "GPP")
    fatigue = flags.get("fatigue", "low")
    style = flags.get("style_tactical", "").lower()
    goals = flags.get("key_goals", [])
    weaknesses = flags.get("weaknesses", [])

    style_tags = [style] if style else []
    goal_tags = [g.lower() for g in goals]
    weak_tags = [w.lower() for w in weaknesses]

    # Phase bias system
    phase_priority = {
        "GPP": ["aerobic", "glycolytic", "ATP-PCr"],
        "SPP": ["glycolytic", "ATP-PCr", "aerobic"],
        "TAPER": ["aerobic", "ATP-PCr"]
    }

    preferred_order = phase_priority.get(phase.upper(), ["aerobic", "glycolytic", "ATP-PCr"])

    # Group by system
    system_drills = {"aerobic": [], "glycolytic": [], "ATP-PCr": []}
    for drill in conditioning_bank:
        if phase.upper() not in drill.get("phases", []):
            continue

        system = drill.get("system", "").lower()
        if system not in system_drills:
            continue

        tags = [t.lower() for t in drill.get("tags", [])]
        score = 0
        score += sum(2.5 for t in tags if t in weak_tags)
        score += sum(2 for t in tags if t in goal_tags)
        score += sum(1 for t in tags if t in style_tags)

        system_drills[system].append((drill, score))

    # Select drills per system
    final_drills = []
    for system in preferred_order:
        drills = sorted(system_drills.get(system, []), key=lambda x: x[1], reverse=True)
        top = drills[:3] if fatigue == "low" else drills[:2]  # reduce volume under fatigue
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

    # Fatigue note
    if fatigue == "high":
        output_lines.append("\n⚠️ High fatigue detected – conditioning volume reduced.")
    elif fatigue == "moderate":
        output_lines.append("\n⚠️ Moderate fatigue – monitor recovery and hydration closely.")

    return {
        "block": "\n".join(output_lines),
        "num_sessions": len(final_drills),
        "energy_systems": [s for s, _ in final_drills]
    }