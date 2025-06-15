from pathlib import Path
import json
import ast
import random
from .training_context import (
    normalize_equipment_list,
    known_equipment,
    allocate_sessions,
    calculate_exercise_numbers,
)

# Optional equipment boosts by training phase
phase_equipment_boost = {
    "GPP": {"barbell", "trap_bar", "sled", "pullup_bar"},
    "SPP": {"landmine", "cable", "medicine_ball", "bands"},
    "TAPER": {"medicine_ball", "bodyweight", "band", "partner"}
}

# Load style specific exercises (file lacks closing brackets so we patch)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_style_text = (DATA_DIR / "style_specific_exercises").read_text()
_start = _style_text.find("[")
_end = _style_text.rfind("}")
_snippet = _style_text[_start:_end + 1] + "]" if _start != -1 and _end != -1 else "[]"
try:
    STYLE_EXERCISES = ast.literal_eval(_snippet)
except Exception:
    STYLE_EXERCISES = []

STYLE_MANDATORY = {
    "brawler": ["Sledgehammer Slam", "Medicine Ball Slam"],
    "pressure fighter": ["Weighted Sled Push", "Jumping Lunge"],
    "clinch fighter": ["Farmer’s Carry", "Weighted Pull-Up"],
    "distance striker": ["Overhead Med Ball Slam", "Pallof Press"],
    "counter striker": ["Barbell Landmine Twist", "Pallof Press"],
    "submission hunter": ["Weighted Pull-Up", "Kettlebell Swing"],
    "kicker": ["Bulgarian Split Squat", "Walking Lunges"],
    "scrambler": ["Barbell Thruster", "Turkish Get-Up"],
}

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


def score_exercise(
    exercise_tags,
    weakness_tags,
    goal_tags,
    style_tags,
    phase_tags,
    current_phase,
    fatigue_level,
    available_equipment,
    required_equipment,
    is_rehab,
):
    """Return a weighted score for a candidate exercise."""
    score = 0.0

    weakness_matches = len(set(exercise_tags) & set(weakness_tags))
    score += weakness_matches * 0.6

    goal_matches = len(set(exercise_tags) & set(goal_tags))
    score += goal_matches * 0.5

    matched_style_tags = list(set(exercise_tags) & set(style_tags))
    score += len(matched_style_tags) * 0.3

    if len(matched_style_tags) == 2:
        score += 0.2
    elif len(matched_style_tags) >= 3:
        score += 0.1

    total_matches = len(
        set(exercise_tags) & set(weakness_tags + goal_tags + style_tags)
    )
    if total_matches >= 3:
        score += 0.2

    phase_matches = len(set(exercise_tags) & set(phase_tags))
    score += phase_matches * 0.4

    if fatigue_level == "high":
        score -= 0.75
    elif fatigue_level == "moderate":
        score -= 0.35

    if not set(required_equipment).issubset(set(available_equipment)):
        return -999

    if is_rehab:
        phase_penalties = {"GPP": -0.7, "SPP": -1.0, "TAPER": -0.75}
        score += phase_penalties.get(current_phase, -0.75)

    score += random.uniform(-0.15, 0.15)

    return round(score, 4)

def is_banned_exercise(name: str, tags: list[str], fight_format: str) -> bool:
    """Return True if the exercise should be removed for the given sport."""
    name = name.lower()
    tags = [t.lower() for t in tags]

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
            if term in name or term in tags:
                return True

    if fight_format == "boxing":
        for term in ["kick", "knee", "clinch knee strike"]:
            if term in name or term in tags:
                return True

    return False

exercise_bank = json.loads((DATA_DIR / "exercise_bank.json").read_text())

def generate_strength_block(*, flags: dict, weaknesses=None, mindset_cue=None):
    phase = flags.get("phase", "GPP").upper()
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment_access = normalize_equipment_list(flags.get("equipment", []))
    fight_format = flags.get("fight_format", "mma")
    style_input = flags.get("style_tactical", [])
    if isinstance(style_input, str):
        style_list = [style_input.lower()]
    elif isinstance(style_input, list):
        style_list = [s.lower() for s in style_input]
    else:
        style_list = []
    goals = flags.get("key_goals", [])
    training_days = flags.get("training_days", [])
    training_frequency = flags.get(
        "training_frequency", flags.get("days_available", len(training_days))
    )
    num_strength_sessions = allocate_sessions(training_frequency, phase).get("strength", 2)
    exercise_counts = calculate_exercise_numbers(training_frequency, phase)
    target_exercises = exercise_counts.get("strength", 0)
    prev_exercises = flags.get("prev_exercises", [])

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

    style_tags = [t for s in style_list for t in style_tag_map.get(s, [])]
    goal_tags = [tag for g in goals for tag in goal_tag_map.get(g, [])]

    phase_tag_boost = {
        "GPP": {"triphasic": 1, "tempo": 1, "eccentric": 1},
        "SPP": {"contrast": 1.5, "explosive": 1.5},
        "TAPER": {"neural_primer": 2, "cluster": 2, "speed": 2},
    }


    weighted_exercises = []
    taper_allowed = {"neural_primer", "speed", "cluster", "explosive", "low_impact", "reactive", "rehab_friendly"}
    taper_banned = {
        "eccentric",
        "lunge_pattern",
        "compound",
        "horizontal_power",
        "triple_extension",
        "overhead",
        "contrast_pairing",
        "rate_of_force",
        "plyometric",
        "elastic",
        "mental_toughness",
        "posterior_chain",
        "high_volume",
        "barbell",
        "trap_bar",
    }

    for ex in exercise_bank:
        tags = ex.get("tags", [])
        if is_banned_exercise(ex.get("name", ""), tags, fight_format):
            continue
        ex_equipment = [e.strip().lower() for e in ex.get("equipment", "").replace("/", ",").split(",") if e.strip()]
        if phase == "TAPER":
            if any(t in taper_banned for t in tags) or any(eq in {"barbell", "trap_bar"} for eq in ex_equipment):
                continue
            if not any(t in taper_allowed for t in tags):
                continue
        if phase not in ex["phases"]:
            continue

        phase_dict = phase_tag_boost.get(phase, {})
        phase_tags = list(phase_dict.keys()) if isinstance(phase_dict, dict) else []
        method = ex.get("method", "").lower()

        score = score_exercise(
            exercise_tags=tags,
            weakness_tags=weaknesses or [],
            goal_tags=goal_tags,
            style_tags=style_tags,
            phase_tags=phase_tags,
            current_phase=phase,
            fatigue_level=fatigue,
            available_equipment=equipment_access,
            required_equipment=ex_equipment,
            is_rehab=method == "rehab",
        )
        if score == -999:
            continue

        # Phase-based novelty enforcement
        if ex.get("name") in prev_exercises and not (
            phase == "TAPER" and any(t in {"neural_primer", "speed"} for t in tags)
        ):
            continue

        # No additional fatigue or equipment adjustments; handled in score_exercise

        if score >= 0:
            weighted_exercises.append((ex, score))

    weighted_exercises.sort(key=lambda x: x[1], reverse=True)
    days_count = len(training_days) if isinstance(training_days, list) else training_days
    if not isinstance(days_count, int):
        days_count = 3
    # Target exercise count determined by phase multipliers

    if len(weighted_exercises) < target_exercises:
        fallback_exercises = []
        for ex in exercise_bank:
            if ex in [we[0] for we in weighted_exercises]:
                continue
            if phase not in ex["phases"]:
                continue
            ex_equipment = [e.strip().lower() for e in ex.get("equipment", "").replace("/", ",").split(",") if e.strip()]
            if not set(ex_equipment).issubset(set(equipment_access)):
                continue
            tags = ex.get("tags", [])
            if is_banned_exercise(ex.get("name", ""), tags, fight_format):
                continue
            if ex.get("name") in prev_exercises and not (
                phase == "TAPER" and any(t in {"neural_primer", "speed"} for t in tags)
            ):
                continue
            if phase == "TAPER":
                if any(t in taper_banned for t in tags) or any(eq in {"barbell", "trap_bar"} for eq in ex_equipment):
                    continue
                if not any(t in taper_allowed for t in tags):
                    continue
            fallback_exercises.append(ex)
            if len(fallback_exercises) >= target_exercises - len(weighted_exercises):
                break
        weighted_exercises += [(ex, 0) for ex in fallback_exercises]

    # Keep score pairs for later lookups
    top_pairs = weighted_exercises[:target_exercises]
    top_exercises = [ex for ex, _ in top_pairs]
    # Remove any duplicate exercise names that slipped through scoring
    seen_exercises: set[str] = set()
    unique_top: list[dict] = []
    for ex in top_exercises:
        name = ex.get("name")
        if name not in seen_exercises:
            seen_exercises.add(name)
            unique_top.append(ex)
    top_exercises = unique_top

    # --------- UNIVERSAL STRENGTH INSERTION ---------
    if phase == "GPP":
        try:
            with open(DATA_DIR / "universal_gpp_strength.json", "r") as f:
                universal_strength = json.load(f)
        except Exception:
            universal_strength = []

        existing_names = {e["name"] for e in top_exercises}
        existing_tags = {tag for e in top_exercises for tag in e.get("tags", [])}
        priority_strength_tags = [
            ("pull", "upper_body"),
            ("anti_rotation", "core"),
            ("unilateral",),
            ("neck", "traps"),
        ]

        inserted = 0
        for drill in universal_strength:
            if inserted >= 4:
                break
            if drill.get("name") in existing_names:
                continue
            for group in priority_strength_tags:
                if any(tag in drill.get("tags", []) for tag in group) and not any(
                    tag in existing_tags for tag in group
                ):
                    top_exercises.append(drill)
                    inserted += 1
                    break

    # Inject mandatory exercises for each tactical style
    mandatory = []
    for st in style_list:
        mandatory.extend(STYLE_MANDATORY.get(st, [])[:2])
    # remove duplicates while preserving order
    seen: set[str] = set()
    unique_mandatory: list[str] = []
    for m in mandatory:
        if m not in seen:
            seen.add(m)
            unique_mandatory.append(m)
    mandatory = unique_mandatory
    for name in mandatory:
        ex_obj = next((e for e in STYLE_EXERCISES if e.get("name") == name), None)
        if not ex_obj:
            continue
        if phase not in ex_obj.get("phases", []):
            continue
        if all(e.get("name") != name for e in top_exercises):
            top_exercises.append(ex_obj)
    if len(top_exercises) > target_exercises:
        top_exercises = top_exercises[:target_exercises]

    # --------- ISOMETRIC GUARANTEE ---------
    if phase in {"GPP", "SPP"}:
        if not any("isometric" in ex.get("tags", []) for ex in top_exercises):
            score_lookup = {ex["name"]: score for ex, score in weighted_exercises}
            iso_candidates = [
                (ex, score)
                for ex, score in weighted_exercises
                if "isometric" in ex.get("tags", []) and ex not in top_exercises
            ]
            if iso_candidates:
                best_iso, _ = max(iso_candidates, key=lambda x: x[1])
                worst_index = 0
                worst_score = float("inf")
                for idx, ex in enumerate(top_exercises):
                    sc = score_lookup.get(ex.get("name"), 0)
                    if sc < worst_score:
                        worst_score = sc
                        worst_index = idx
                top_exercises[worst_index] = best_iso

    base_exercises = top_exercises
    # Final safety deduplication in case database contained repeats
    seen_names: set[str] = set()
    unique_base: list[dict] = []
    for ex in base_exercises:
        name = ex.get("name")
        if name not in seen_names:
            seen_names.add(name)
            unique_base.append(ex)
    base_exercises = unique_base
    used_days = training_days[:num_strength_sessions]

    phase_loads = {
        "GPP": ("3x8-12 @ 60–75% 1RM with slow eccentrics, tempo 3-1-1",
                "Build hypertrophy base, tendon durability, and general strength."),
        "SPP": ("3–5x3-5 @ 85–90% 1RM with contrast training (pair with explosive move)",
                "Max strength + explosive power. Contrast and triphasic methods emphasized."),
        "TAPER": ("2–3x3-5 @ 80–85%, cluster sets, minimal eccentric load",
                  "Maintain intensity, cut volume, CNS freshness. High bar speed focus."),
    }
    base_block, focus = phase_loads.get(phase, ("Default fallback block", "Ensure phase logic handled upstream."))

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
    ] + [f"- {ex['name']}" for ex in base_exercises] + [
        f"**Prescription:** {base_block}",
        f"**Total Exercises:** {target_exercises}",
    ]
    
    if fatigue_note:
        strength_output.append(f"**Adjustment:** {fatigue_note}")

    all_tags = []
    for ex in base_exercises:
        all_tags.extend(ex.get("tags", []))

    return {
        "block": "\n".join(strength_output),
        "num_sessions": len(used_days),
        "preferred_tags": list(set(all_tags)),
        "exercises": base_exercises,
    }
    