from pathlib import Path
import json
from injury_subs import injury_subs

# Load JSON-based exercise bank
exercise_bank = json.loads(Path("exercise_bank.json").read_text())

def generate_strength_block(*, flags: dict, weaknesses=None):
    phase = flags.get("phase", "GPP")
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment_access = flags.get("equipment", [])
    style = flags.get("style", "")
    training_days = flags.get("training_days", [])

    style_tag_map = {
        "brawler": ["compound", "posterior_chain", "power"],
        "pressure fighter": ["conditioning", "core", "rate_of_force"],
        "clinch fighter": ["grip", "core", "unilateral", "shoulders"],
        "distance striker": ["explosive", "reactive", "balance"],
        "counter striker": ["reactive", "core", "anti_rotation"],
        "submission hunter": ["grip", "mobility", "core", "stability"],
        "kicker": ["hinge", "posterior_chain", "balance", "mobility"],
        "scrambler": ["core", "rotational", "balance", "endurance"]
    }
    style_tags = style_tag_map.get(style.lower(), [])
    target_tags = set((weaknesses or []) + style_tags)

    filtered = []
    for ex in exercise_bank:
        if phase not in ex["phases"]:
            continue
        if equipment_access and ex["equipment"] not in equipment_access:
            continue
        if not target_tags.intersection(set(ex["tags"])):
            continue
        filtered.append(ex)

    if not filtered:
        filtered = [ex for ex in exercise_bank if phase in ex["phases"]][:6]

    def substitute_exercises(exercises, injuries_detected):
        modified = []
        for ex in exercises:
            name = ex["name"]
            replaced = False
            for area, subs_list in injury_subs.items():
                if area in injuries_detected:
                    for sub_ex in subs_list:
                        if any(keyword in name.lower() for keyword in sub_ex.lower().split()):
                            modified.append({"name": sub_ex, "tags": ex["tags"]})
                            replaced = True
                            break
                if replaced:
                    break
            if not replaced:
                modified.append(ex)
        return modified

    base_exercises = substitute_exercises(filtered[:6], injuries)

    used_days = training_days[:min(len(training_days), 3)]
    tags_by_day = {day: list(set(ex["tags"])) for day, ex in zip(used_days, base_exercises)}

    phase_loads = {
        "GPP": ("3x8-12 @ 60–75% 1RM with slow eccentrics, tempo 3-1-1", "Build hypertrophy base, tendon durability, and general strength."),
        "SPP": ("3–5x3-5 @ 85–90% 1RM with contrast training (pair with explosive move)", "Max strength + explosive power. Contrast and triphasic methods emphasized."),
        "TAPER": ("2–3x3-5 @ 80–85%, cluster sets, minimal eccentric load", "Maintain intensity, cut volume, CNS freshness. High bar speed focus.")
    }
    base_block, focus = phase_loads.get(phase, ("Default fallback block", "Default phase. Ensure proper phase detection upstream."))

    fatigue_note = ""
    if fatigue == "high":
        fatigue_note = "⚠️ High fatigue → reduce volume by 30–40%, drop last set per lift."
    elif fatigue == "moderate":
        fatigue_note = "⚠️ Moderate fatigue → reduce 1 set if performance drops."

    strength_output = [
        "\n🏋️‍♂️ **Strength & Power Module**",
        f"**Phase:** {phase}",
        f"**Primary Focus:** {focus}",
        "**Top Exercises:**"
    ]
    for ex in base_exercises:
        strength_output.append(f"- {ex['name']}")
    strength_output.append(f"**Prescription:** {base_block}")
    if fatigue_note:
        strength_output.append(f"**Adjustment:** {fatigue_note}")

    all_tags = []
    for ex in base_exercises:
        all_tags.extend(ex.get("tags", []))

    return {
        "block": "\n".join(strength_output),
        "num_sessions": len(used_days),
        "preferred_tags": list(set(all_tags))
    }
    