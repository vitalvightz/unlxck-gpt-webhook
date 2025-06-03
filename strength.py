from pathlib import Path
import json
from injury_subs import injury_subs

exercise_bank = json.loads(Path("exercise_bank.json").read_text())

goal_tag_map = {
    "power": ["explosive", "rate_of_force", "triple_extension", "horizontal_power", "plyometric", "elastic", "lateral_power", "deadlift"],
    "strength": ["posterior_chain", "quad_dominant", "upper_body", "core", "pull", "hamstring", "hip_dominant", "eccentric", "deadlift"],
    "endurance": ["aerobic", "glycolytic", "work_capacity", "mental_toughness", "conditioning", "improvised"],
    "speed": ["speed", "agility", "footwork", "reactive", "acceleration", "ATP-PCr", "anaerobic_alactic"],
    "mobility": ["mobility", "hip_dominant", "balance", "eccentric", "unilateral", "adductors"],
    "grappling": ["wrestling", "bjj", "grip", "rotational", "core", "unilateral"],
    "striking": ["striking", "boxing", "muay_thai", "shoulders", "rate_of_force", "coordination", "visual_processing"],
    "injury prevention": ["recovery", "balance", "eccentric", "zero_impact", "parasympathetic", "cns_freshness", "unilateral"],
    "mental resilience": ["mental_toughness", "cognitive", "parasympathetic", "visual_processing", "environmental"],
    "skill refinement": ["coordination", "skill", "footwork", "cognitive"]
}

style_tag_map = {
    "brawler": ["compound", "posterior_chain", "power", "rate_of_force", "grip", "core"],
    "pressure fighter": ["conditioning", "core", "rate_of_force", "endurance", "mental_toughness", "anaerobic_alactic"],
    "clinch fighter": ["grip", "core", "unilateral", "shoulders", "rotational", "balance"],
    "distance striker": ["explosive", "reactive", "balance", "footwork", "coordination", "visual_processing"],
    "counter striker": ["reactive", "core", "anti_rotation", "cognitive", "visual_processing", "balance"],
    "submission hunter": ["grip", "mobility", "core", "stability", "anti_rotation", "rotational"],
    "kicker": ["hinge", "posterior_chain", "balance", "mobility", "unilateral", "hip_dominant"],
    "scrambler": ["core", "rotational", "balance", "endurance", "agility", "reactive"],
    "boxer": ["speed", "footwork", "reactive", "core", "shoulders", "rate_of_force"],
    "wrestler": ["grip", "posterior_chain", "core", "unilateral", "rotational", "endurance"],
    "muay thai": ["balance", "mobility", "core", "explosive", "shoulders", "hip_dominant"],
    "bjj": ["grip", "core", "mobility", "stability", "anti_rotation", "endurance"]
}

def generate_strength_block(*, flags: dict, weaknesses=None):
    phase = flags.get("phase", "GPP")
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment_access = flags.get("equipment", [])
    style = flags.get("style", "")
    goals = flags.get("goals", [])
    training_days = flags.get("training_days", [])

    style_tags = style_tag_map.get(style.lower(), [])
    goal_tags = []
    for goal in goals:
        goal_tags.extend(goal_tag_map.get(goal.lower(), []))

    target_tags = set((weaknesses or []) + style_tags + goal_tags)

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

    filtered = [
        ex for ex in exercise_bank
        if phase in ex["phases"]
        and (not equipment_access or ex["equipment"] in equipment_access)
        and target_tags.intersection(set(ex["tags"]))
    ]

    if not filtered:
        filtered = [ex for ex in exercise_bank if phase in ex["phases"]][:6]

    selected = substitute_exercises(filtered[:6], injuries)

    used_days = training_days[:min(len(training_days), len(selected))]
    tags_by_day = {day: ex.get("tags", []) for day, ex in zip(used_days, selected)}

    phase_loads = {
        "GPP": ("3x8-12 @ 60–75% 1RM with slow eccentrics, tempo 3-1-1", "Build hypertrophy base, tendon durability, and general strength."),
        "SPP": ("3–5x3-5 @ 85–90% 1RM with contrast training (pair with explosive move)", "Max strength + explosive power. Contrast and triphasic methods emphasized."),
        "TAPER": ("2–3x3-5 @ 80–85%, cluster sets, minimal eccentric load", "Maintain intensity, cut volume, CNS freshness. High bar speed focus.")
    }

    base_block, focus = phase_loads.get(phase, ("Default fallback", "Ensure phase logic."))

    fatigue_note = {
        "high": "⚠️ High fatigue → reduce volume by 30–40%, drop last set per lift.",
        "moderate": "⚠️ Moderate fatigue → reduce 1 set if performance drops."
    }.get(fatigue, "")

    output = [
        "\n🏋️‍♂️ **Strength & Power Module**",
        f"**Phase:** {phase}",
        f"**Primary Focus:** {focus}",
        "**Top Exercises:**"
    ] + [f"- {ex['name']}" for ex in selected] + [
        f"**Prescription:** {base_block}"
    ]
    if fatigue_note:
        output.append(f"**Adjustment:** {fatigue_note}")

    return {
        "block": "\n".join(output),
        "num_sessions": len(used_days),
        "preferred_tags": list(set(tag for ex in selected for tag in ex.get("tags", [])))
    }