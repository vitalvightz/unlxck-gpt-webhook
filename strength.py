from pathlib import Path
import json
from injury_subs import injury_subs
from training_context import normalize_equipment_list, known_equipment, allocate_sessions

def equipment_score_adjust(entry_equip, user_equipment, known_equipment):
    entry_equip_list = [e.strip().lower() for e in entry_equip.replace("/", ",").split(",") if e.strip()]
    user_equipment = [e.lower().strip() for e in user_equipment]
    known_equipment = [e.lower() for e in known_equipment]

    if not entry_equip_list or "bodyweight" in entry_equip_list:
        return 0

    for eq in entry_equip_list:
        if eq in known_equipment and eq not in user_equipment:
            return -999

    if any(eq not in known_equipment for eq in entry_equip_list):
        return -1

    return 0


exercise_bank = json.loads(Path("exercise_bank.json").read_text())


def generate_strength_block(*, flags: dict, weaknesses=None):
    phase = flags.get("phase", "GPP").upper()
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment_access = normalize_equipment_list(flags.get("equipment", []))
    style = flags.get("style_tactical", [])
    style_tags = [s.lower() for s in style] if isinstance(style, list) else [style.lower()]
    goals = flags.get("key_goals", [])
    training_days = flags.get("training_days", [])

    days_available = flags.get("days_available", len(training_days))
    num_strength_sessions = allocate_sessions(days_available).get("strength", 2)

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



    style_tags = style_tag_map.get(style.lower(), [])
    goal_tags = [tag for g in goals for tag in goal_tag_map.get(g, [])]

    weighted_exercises = []

    for ex in exercise_bank:
        if phase not in ex["phases"]:
            continue

        penalty = equipment_score_adjust(
            ex.get("equipment", ""), equipment_access, known_equipment
        )
        if penalty == -999:
            continue

        tags = ex.get("tags", [])
        method = ex.get("method", "").lower()

        rehab_penalty_by_phase = {
            "GPP": -1,
            "SPP": -3,
            "TAPER": -2
        }
        rehab_penalty = rehab_penalty_by_phase.get(phase.upper(), 0) if method == "rehab" else 0

        score = 0
        weakness_matches = sum(1 for tag in tags if tag in (weaknesses or []))
        goal_matches = sum(1 for tag in tags if tag in goal_tags)
        style_matches = sum(1 for tag in tags if tag in style_tags)

        score += weakness_matches * 1.5
        score += goal_matches * 1.25
        score += style_matches * 1.0

        if style_matches >= 2:
            score += 2  # Style bonus

        if (weakness_matches + goal_matches + style_matches) >= 3:
            score += 1  # Extra synergy bonus

        score += penalty
        score += rehab_penalty

        if score >= 0:
            weighted_exercises.append((ex, score))

    weighted_exercises.sort(key=lambda x: x[1], reverse=True)
    days_count = (
        len(training_days) if isinstance(training_days, list) else training_days
    )
    if not isinstance(days_count, int):
        days_count = 3  # Fallback

    target_exercises = 12

    if len(weighted_exercises) < target_exercises:
        print(
            f"⚠️ Only found {len(weighted_exercises)} scored exercises. Filling with low/no-score entries..."
        )

        fallback_exercises = [
            ex
            for ex in exercise_bank
            if phase in ex["phases"]
            and equipment_score_adjust(
                ex.get("equipment", ""), equipment_access, known_equipment
            )
            > -999
            and ex not in [we[0] for we in weighted_exercises]
        ][: target_exercises - len(weighted_exercises)]

        weighted_exercises += [(ex, 0) for ex in fallback_exercises]

    top_exercises = [ex for ex, _ in weighted_exercises[:target_exercises]]

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

    base_exercises = substitute_exercises(top_exercises, injuries)

    used_days = training_days[:num_strength_sessions]

    phase_loads = {
        "GPP": (
            "3x8-12 @ 60–75% 1RM with slow eccentrics, tempo 3-1-1",
            "Build hypertrophy base, tendon durability, and general strength.",
        ),
        "SPP": (
            "3–5x3-5 @ 85–90% 1RM with contrast training (pair with explosive move)",
            "Max strength + explosive power. Contrast and triphasic methods emphasized.",
        ),
        "TAPER": (
            "2–3x3-5 @ 80–85%, cluster sets, minimal eccentric load",
            "Maintain intensity, cut volume, CNS freshness. High bar speed focus.",
        ),
    }

    base_block, focus = phase_loads.get(
        phase, ("Default fallback block", "Ensure phase logic handled upstream.")
    )

    fatigue_note = ""
    if fatigue == "high":
        fatigue_note = "⚠️ High fatigue → reduce volume by 30–40%, drop last set per lift."
    elif fatigue == "moderate":
        fatigue_note = "⚠️ Moderate fatigue → reduce 1 set if performance drops."

    strength_output = [
        "\n🏋️‍♂️ **Strength & Power Module**",
        f"**Phase:** {phase}",
        f"**Primary Focus:** {focus}",
        "**Top Exercises:**",
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
        "preferred_tags": list(set(all_tags)),
    }
