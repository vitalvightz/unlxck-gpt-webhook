import json
from pathlib import Path
from injury_subs import injury_subs

# Load exercise bank JSON
exercise_bank = json.loads(Path("exercise_bank.json").read_text())

def generate_strength_block(*, flags: dict, weaknesses=None):
    phase = flags.get("phase", "GPP")
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment_access = flags.get("equipment", [])
    style = flags.get("style", "")

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

    # Filter + score
    filtered = []
    for ex in exercise_bank:
        if phase not in ex["phases"]:
            continue
        if equipment_access and ex["equipment"] not in equipment_access:
            continue
        match_score = len(set(ex["tags"]).intersection(target_tags))
        if match_score:
            filtered.append((ex["name"], match_score))

    filtered.sort(key=lambda x: x[1], reverse=True)
    top_exercises = [ex[0] for ex in filtered[:6]]

    if not top_exercises:
        top_exercises = [ex["name"] for ex in exercise_bank if phase in ex["phases"]][:6]

    # Injury substitution
    def substitute_exercises(base_exercises, injuries_detected):
        modified = []
        for ex in base_exercises:
            replaced = False
            for area, subs in injury_subs.items():
                if area in injuries_detected:
                    for sub_ex in subs:
                        if any(k in ex.lower() for k in sub_ex.lower().split()):
                            modified.append(sub_ex)
                            replaced = True
                            break
                    if replaced:
                        break
            if not replaced:
                modified.append(ex)
        return modified

    final_exercises = substitute_exercises(top_exercises, injuries)

    phase_prescriptions = {
        "GPP": ("3x8-12 @ 60–75% 1RM, tempo 3-1-1", "Build hypertrophy base, tendon durability, and general strength."),
        "SPP": ("3–5x3-5 @ 85–90% 1RM, contrast methods", "Max strength + explosive power. Contrast and triphasic methods."),
        "TAPER": ("2–3x3-5 @ 80–85%, cluster sets", "Maintain intensity, cut volume. Preserve CNS freshness.")
    }
    prescription, focus = phase_prescriptions.get(phase, ("2x10 bodyweight basics", "Fallback default"))

    fatigue_note = ""
    if fatigue == "high":
        fatigue_note = "\n⚠️ High fatigue → drop 30% volume, skip final set each lift."
    elif fatigue == "moderate":
        fatigue_note = "\n⚠️ Moderate fatigue → reduce 1 set per lift if needed."

    strength_output = [
        "\n🏋️‍♂️ **Strength & Power Module**",
        f"**Phase:** {phase}",
        f"**Primary Focus:** {focus}",
        "**Top Exercises:**"
    ]
    strength_output += [f"- {ex}" for ex in final_exercises]
    strength_output.append(f"**Prescription:** {prescription}")
    if fatigue_note:
        strength_output.append(fatigue_note)

    return "\n".join(strength_output)