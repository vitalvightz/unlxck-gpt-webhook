from pathlib import Path
import logging
import os
import json
import random
from .training_context import (
    normalize_equipment_list,
    known_equipment,
    allocate_sessions,
    calculate_exercise_numbers,
)
from .bank_schema import validate_training_item
from .tagging import normalize_item_tags, normalize_tags
from .tag_maps import GOAL_TAG_MAP, STYLE_TAG_MAP
from .config import PHASE_EQUIPMENT_BOOST, PHASE_TAG_BOOST
from .injury_filtering import (
    _load_style_specific_exercises,
    injury_match_details,
    is_injury_safe_with_fields,
    log_injury_debug,
)

# Load style specific exercises (JSON list)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STYLE_EXERCISES = _load_style_specific_exercises()


CANONICAL_STYLE_TAGS = {
    "brawler",
    "pressure_fighter",
    "clinch_fighter",
    "distance_striker",
    "counter_striker",
    "submission_hunter",
    "kicker",
    "scrambler",
    "grappler",
    "wrestler",
}


def normalize_style_tags(tags):
    """Return canonical tactical style tags without ``style_`` prefixes."""
    normalized = set()
    for tag in tags:
        t = tag.lower().replace(" ", "_")
        if t.startswith("style_"):
            t = t[6:]
        if t in CANONICAL_STYLE_TAGS:
            normalized.add(t)
    return normalized

def equipment_score_adjust(entry_equip, user_equipment, known_equipment):
    entry_equip_list = normalize_equipment_list(entry_equip)
    user_equipment = normalize_equipment_list(user_equipment)
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
    must_have_tags,
    phase_tags,
    current_phase,
    fatigue_level,
    available_equipment,
    required_equipment,
    is_rehab,
):
    """Return a weighted score and breakdown for a candidate exercise."""
    exercise_tags = normalize_tags(exercise_tags or [])
    weakness_tags = normalize_tags(weakness_tags or [])
    goal_tags = normalize_tags(goal_tags or [])
    style_tags = normalize_tags(style_tags or [])
    must_have_tags = normalize_tags(must_have_tags or [])
    phase_tags = normalize_tags(phase_tags or [])
    score = 0.0
    reasons = {
        "goal_hits": 0,
        "weakness_hits": 0,
        "style_hits": 0,
        "must_have_hits": 0,
        "must_have_bonus": 0.0,
        "phase_hits": 0,
        "load_adjustments": 0.0,
        "equipment_boost": 0.0,
        "penalties": 0.0,
    }

    weakness_matches = len(set(exercise_tags) & set(weakness_tags))
    score += weakness_matches * 0.6
    reasons["weakness_hits"] = weakness_matches

    goal_matches = len(set(exercise_tags) & set(goal_tags))
    score += goal_matches * 0.5
    reasons["goal_hits"] = goal_matches

    matched_style_tags = list(set(exercise_tags) & set(style_tags))
    style_score = len(matched_style_tags) * 0.3
    if len(matched_style_tags) == 2:
        style_score += 0.2
    elif len(matched_style_tags) >= 3:
        style_score += 0.1
    score += style_score
    reasons["style_hits"] = len(matched_style_tags)

    must_have_matches = len(set(exercise_tags) & set(must_have_tags))
    if must_have_matches:
        score += must_have_matches * 0.35
    reasons["must_have_hits"] = must_have_matches
    must_have_bonus_tags = {"core", "posterior_chain", "neck", "stability"}
    must_have_bonus = len(set(exercise_tags) & must_have_bonus_tags) * 0.15
    score += must_have_bonus
    reasons["must_have_bonus"] = round(must_have_bonus, 2)

    total_matches = len(
        set(exercise_tags) & set(weakness_tags + goal_tags + style_tags)
    )
    if total_matches >= 3:
        score += 0.2

    phase_matches = len(set(exercise_tags) & set(phase_tags))
    score += phase_matches * 0.4
    reasons["phase_hits"] = phase_matches

    fatigue_penalty = 0.0
    if fatigue_level == "high":
        fatigue_penalty = -0.75
    elif fatigue_level == "moderate":
        fatigue_penalty = -0.35
    score += fatigue_penalty
    reasons["load_adjustments"] = fatigue_penalty

    if not set(required_equipment).issubset(set(available_equipment)):
        return -999, reasons

    phase_boost = PHASE_EQUIPMENT_BOOST.get(current_phase, set())
    equipment_bonus = 0.25 if any(eq in phase_boost for eq in available_equipment) else 0.0
    score += equipment_bonus
    reasons["equipment_boost"] = equipment_bonus

    rehab_penalty = 0.0
    if is_rehab:
        phase_penalties = {"GPP": -0.7, "SPP": -1.0, "TAPER": -0.75}
        rehab_penalty = phase_penalties.get(current_phase, -0.75)
        score += rehab_penalty
    reasons["penalties"] = rehab_penalty

    noise = random.uniform(-0.15, 0.15)
    score += noise
    reasons["randomness"] = round(noise, 4)
    reasons["final_score"] = round(score, 4)

    return round(score, 4), reasons

def is_banned_exercise(name: str, tags: list[str], fight_format: str, details: str = "") -> bool:
    """Return True if the exercise should be removed for the given sport."""
    name = name.lower()
    tags = normalize_tags(tags)
    details = details.lower()

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
            if term in name or term in tags or term in details:
                return True

    if fight_format == "boxing":
        for term in ["kick", "knee", "clinch knee strike"]:
            if term in name or term in tags or term in details:
                return True

    return False


def _normalize_fight_format(fight_format: str) -> str:
    if fight_format == "muay_thai":
        return "kickboxing"
    return fight_format

exercise_bank = json.loads((DATA_DIR / "exercise_bank.json").read_text())
for item in exercise_bank:
    validate_training_item(item, source="exercise_bank.json", require_phases=True)
    normalize_item_tags(item)

# Load universal strength list for cross-phase novelty exemptions
try:
    _universal_strength = json.loads(
        (DATA_DIR / "universal_gpp_strength.json").read_text()
    )
except Exception:
    _universal_strength = []
else:
    for item in _universal_strength:
        validate_training_item(item, source="universal_gpp_strength.json", require_phases=True)
        normalize_item_tags(item)
UNIVERSAL_STRENGTH_NAMES = {ex.get("name") for ex in _universal_strength if ex.get("name")}

logger = logging.getLogger(__name__)

MOVEMENT_PATTERN_TAGS = {
    "squat": {"squat", "quad_dominant"},
    "hinge": {"hinge", "posterior_chain", "hip_dominant", "deadlift"},
    "push": {"push", "upper_body", "press"},
    "pull": {"pull"},
    "lunge": {"lunge", "unilateral"},
    "rotation": {"rotational", "anti_rotation"},
    "carry": {"carry", "loaded_carry", "grip"},
    "core": {"core"},
    "neck": {"neck"},
}

MOVEMENT_PATTERN_KEYWORDS = {
    "squat": ["squat"],
    "hinge": ["hinge", "deadlift", "rdl", "hip hinge"],
    "push": ["press", "push", "bench"],
    "pull": ["row", "pull", "chin"],
    "lunge": ["lunge", "split squat", "step-up", "step up"],
    "rotation": ["rotation", "rotational", "anti-rotation", "anti rotation"],
    "carry": ["carry", "farmer", "suitcase"],
    "core": ["core", "trunk", "ab"],
    "neck": ["neck"],
}


def _detect_movement_pattern(exercise: dict) -> str:
    text_fields = [
        exercise.get("name", ""),
        exercise.get("movement", ""),
        exercise.get("category", ""),
        exercise.get("type", ""),
    ]
    haystack = " ".join(str(val) for val in text_fields).lower()
    for pattern, keywords in MOVEMENT_PATTERN_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return pattern
    tags = set(normalize_tags(exercise.get("tags") or []))
    for pattern, tag_set in MOVEMENT_PATTERN_TAGS.items():
        if tags & tag_set:
            return pattern
    return "unknown"


def normalize_exercise_movement(exercise: dict) -> str:
    """Ensure exercises expose a canonical movement key."""
    movement = _detect_movement_pattern(exercise)
    exercise["movement"] = movement
    return movement


def format_strength_block(phase: str, fatigue: str, exercises: list[dict]) -> str:
    """Return the formatted strength block for the given phase."""
    phase = phase.upper()
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
    base_block, _focus = phase_loads.get(
        phase, ("Default fallback block", "Ensure phase logic handled upstream.")
    )
    phase_titles = {
        "GPP": "Foundation Strength – Base Build",
        "SPP": "Fight-Specific Strength – Power Conversion",
        "TAPER": "Neural Primer – Sharpness & Freshness",
    }
    weekly_progression = {
        "GPP": "Add 1 set or ~5–10% load weekly; deload final week by ~20%.",
        "SPP": "Hold volume, increase intensity or bar speed weekly; deload final week by ~20%.",
        "TAPER": "Cut total volume 40–60%, keep intensity crisp; last 3–5 days very light.",
    }
    time_short_note = {
        "GPP": "If time short: keep top 2 lifts + 1 trunk/neck drill.",
        "SPP": "If time short: keep heavy lift + paired explosive + trunk.",
        "TAPER": "If time short: keep 1 neural primer + 1 trunk/neck drill.",
    }

    fatigue_note = ""
    if fatigue == "high":
        fatigue_note = "⚠️ High fatigue → reduce volume by 30–40%, drop last set per lift."
    elif fatigue == "moderate":
        fatigue_note = "⚠️ Moderate fatigue → reduce 1 set if performance drops."

    strength_output = [
        f"**Phase:** {phase}",
        f"**Weekly Progression:** {weekly_progression.get(phase, 'Progress weekly with small load jumps.')}",
        f"**If Time Short:** {time_short_note.get(phase, 'Keep top 2 lifts.')}",
        "",
    ]

    top_exercises = "; ".join(ex["name"] for ex in exercises)
    strength_output.append(f"**Top Exercises:** {top_exercises}")

    strength_output += [
        "",
        "**Prescription:**",
        base_block,
    ]

    if fatigue_note:
        strength_output += [
            "",
            f"**Adjustment:** {fatigue_note}",
        ]

    return "\n".join(strength_output)

def generate_strength_block(*, flags: dict, weaknesses=None, mindset_cue=None):
    phase = flags.get("phase", "GPP").upper()
    random_seed = flags.get("random_seed")
    if random_seed is not None:
        random.seed(f"{random_seed}-{phase}")
    injuries = flags.get("injuries", [])
    fatigue = flags.get("fatigue", "low")
    equipment_access = normalize_equipment_list(flags.get("equipment", []))
    fight_format = _normalize_fight_format(flags.get("fight_format", "mma"))
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
    recent_movements = set(flags.get("recent_exercises", []))
    cornerstone_terms = {"squat", "deadlift", "bench", "pull-up", "pullup"}

    style_tags = [t for s in style_list for t in STYLE_TAG_MAP.get(s, [])]
    goal_tags = [tag for g in goals for tag in GOAL_TAG_MAP.get(g, [])]
    must_have_by_phase = {
        "GPP": ["core", "posterior_chain", "neck", "stability"],
        "SPP": ["core", "posterior_chain", "neck", "stability"],
        "TAPER": ["core", "neck", "stability", "reactive"],
    }
    must_have_tags = must_have_by_phase.get(phase, [])


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
        tags_lower = set(normalize_tags(tags))
        details = " ".join(
            [
                ex.get("notes", ""),
                ex.get("method", ""),
                ex.get("movement", ""),
            ]
        )
        if not is_injury_safe_with_fields(ex, injuries, fields=("name", "notes")):
            continue
        if is_banned_exercise(ex.get("name", ""), tags, fight_format, details):
            continue
        ex_equipment = normalize_equipment_list(ex.get("equipment", []))
        if phase == "TAPER":
            if any(t in taper_banned for t in tags) or any(eq in {"barbell", "trap_bar"} for eq in ex_equipment):
                continue
            if not any(t in taper_allowed for t in tags):
                continue
        if phase not in ex.get("phases", []):
            continue

        phase_dict = PHASE_TAG_BOOST.get(phase, {})
        phase_tags = list(phase_dict.keys()) if isinstance(phase_dict, dict) else []
        method = ex.get("method", "").lower()

        score, breakdown = score_exercise(
            exercise_tags=tags,
            weakness_tags=weaknesses or [],
            goal_tags=goal_tags,
            style_tags=style_tags,
            must_have_tags=must_have_tags,
            phase_tags=phase_tags,
            current_phase=phase,
            fatigue_level=fatigue,
            available_equipment=equipment_access,
            required_equipment=ex_equipment,
            is_rehab=method == "rehab",
        )
        if score == -999:
            continue

        # Phase-based novelty enforcement with exemptions
        if prev_exercises and ex.get("name") in prev_exercises:
            if not (
                ex.get("name") in UNIVERSAL_STRENGTH_NAMES
                or any(
                    term in ex.get("name", "").lower() or term in tags_lower
                    for term in cornerstone_terms
                )
                or (
                    phase == "TAPER" and tags_lower & {"neural_primer", "speed"}
                )
            ):
                continue

        # No additional fatigue or equipment adjustments; handled in score_exercise

        if score >= 0:
            weighted_exercises.append((ex, score, breakdown))

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
            if phase not in ex.get("phases", []):
                continue
            ex_equipment = normalize_equipment_list(ex.get("equipment", []))
            if not set(ex_equipment).issubset(set(equipment_access)):
                continue
            tags = ex.get("tags", [])
            tags_lower = set(normalize_tags(tags))
            details = " ".join(
                [
                    ex.get("notes", ""),
                    ex.get("method", ""),
                    ex.get("movement", ""),
                ]
            )
            if not is_injury_safe_with_fields(ex, injuries, fields=("name", "notes")):
                continue
            if is_banned_exercise(ex.get("name", ""), tags, fight_format, details):
                continue
            if prev_exercises and ex.get("name") in prev_exercises:
                if not (
                    ex.get("name") in UNIVERSAL_STRENGTH_NAMES
                    or any(
                        term in ex.get("name", "").lower() or term in tags_lower
                        for term in cornerstone_terms
                    )
                    or (
                        phase == "TAPER" and tags_lower & {"neural_primer", "speed"}
                    )
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
        weighted_exercises += [(ex, 0, {}) for ex in fallback_exercises]

    # Keep score pairs for later lookups
    score_lookup = {ex["name"]: score for ex, score, _ in weighted_exercises}
    reason_lookup = {ex["name"]: reasons for ex, _, reasons in weighted_exercises}

    top_pairs = weighted_exercises[:target_exercises]
    top_exercises = [ex for ex, _, _ in top_pairs]
    # Remove any duplicate exercise names that slipped through scoring
    seen_exercises: set[str] = set()
    unique_top: list[dict] = []
    movement_counts: dict[str, int] = {}
    for ex in top_exercises:
        name = ex.get("name")
        if name not in seen_exercises:
            movement = normalize_exercise_movement(ex)
            if movement != "unknown" and movement_counts.get(movement, 0) >= 2:
                continue
            seen_exercises.add(name)
            movement_counts[movement] = movement_counts.get(movement, 0) + 1
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
            if not is_injury_safe_with_fields(drill, injuries, fields=("name", "notes")):
                continue
            for group in priority_strength_tags:
                if any(tag in drill.get("tags", []) for tag in group) and not any(
                    tag in existing_tags for tag in group
                ):
                    top_exercises.append(drill)
                    inserted += 1
                    break

    # --------- ISOMETRIC GUARANTEE ---------
    if phase in {"GPP", "SPP"}:
        if not any("isometric" in ex.get("tags", []) for ex in top_exercises):
            score_lookup = {ex["name"]: score for ex, score, _ in weighted_exercises}
            iso_candidates = [
                (ex, score)
                for ex, score, _ in weighted_exercises
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

    # ------- STYLE-SPECIFIC INJECTION -------
    athlete_style_set = normalize_style_tags(style_list)
    available_eq = set(equipment_access)
    inserts: list[dict] = []
    for ex in STYLE_EXERCISES:
        if phase not in ex.get("phases", []):
            continue
        if not is_injury_safe_with_fields(ex, injuries, fields=("name", "notes")):
            continue
        ex_tags = set(ex.get("tags", []))
        if not ex_tags & athlete_style_set:
            continue
        ex_eq = set(normalize_equipment_list(ex.get("equipment", [])))
        if ex_eq and ex_eq != {"bodyweight"} and not ex_eq.issubset(available_eq):
            continue
        if any(e.get("name") == ex.get("name") for e in base_exercises):
            continue
        if ex.get("movement") in recent_movements and "cornerstone" not in ex_tags:
            continue
        inserts.append(ex)

    base_exercises = inserts + base_exercises
    if len(base_exercises) > target_exercises:
        base_exercises = base_exercises[:target_exercises]

    def _apply_movement_caps(exercises: list[dict]) -> list[dict]:
        movement_counts: dict[str, int] = {}
        capped: list[dict] = []
        for ex in exercises:
            movement = normalize_exercise_movement(ex)
            if movement != "unknown" and movement_counts.get(movement, 0) >= 2:
                continue
            movement_counts[movement] = movement_counts.get(movement, 0) + 1
            capped.append(ex)

        if len(capped) < target_exercises:
            for cand, _, cand_reasons in weighted_exercises:
                if cand in capped:
                    continue
                movement = normalize_exercise_movement(cand)
                if movement != "unknown" and movement_counts.get(movement, 0) >= 2:
                    continue
                movement_counts[movement] = movement_counts.get(movement, 0) + 1
                capped.append(cand)
                reason_lookup.setdefault(cand.get("name"), cand_reasons)
                if len(capped) >= target_exercises:
                    break
        return capped

    base_exercises = _apply_movement_caps(base_exercises)

    # ------ CONFLICT GUARD: heavy RDL with med-ball rotation ------
    def _enforce_conflicts(ex_list):
        has_med_ball_rot = any(
            "medicine_ball" in normalize_equipment_list(ex.get("equipment", []))
            and "rotational" in set(normalize_tags(ex.get("tags", [])))
            for ex in ex_list
        )
        if not has_med_ball_rot:
            return
        for idx, ex in enumerate(ex_list):
            name_lower = ex.get("name", "").lower()
            if "heavy rdl" in name_lower or ("rdl" in name_lower and "heavy" in name_lower):
                for cand, _, cand_reasons in weighted_exercises:
                    cand_name = cand.get("name", "").lower()
                    if cand_name == name_lower:
                        continue
                    cand_tags = set(normalize_tags(cand.get("tags", [])))
                    cand_eq = normalize_equipment_list(cand.get("equipment", []))
                    if (
                        "medicine_ball" in cand_eq and "rotational" in cand_tags
                    ) or ("rdl" in cand_name and "heavy" in cand_name):
                        continue
                    ex_list[idx] = cand
                    reason_lookup[cand.get("name")] = cand_reasons
                    return

    _enforce_conflicts(base_exercises)

    def _finalize_injury_safe_exercises(ex_list: list[dict]) -> list[dict]:
        used_names = {ex.get("name") for ex in ex_list if ex.get("name")}
        updated: list[dict | None] = []
        for ex in ex_list:
            reasons = injury_match_details(
                ex,
                injuries,
                fields=("name", "notes"),
                risk_levels=("exclude",),
            )
            if not reasons:
                updated.append(ex)
                continue
            replacement = None
            for cand, _, cand_reasons in weighted_exercises:
                cand_name = cand.get("name")
                if not cand_name or cand_name in used_names:
                    continue
                if injury_match_details(
                    cand,
                    injuries,
                    fields=("name", "notes"),
                    risk_levels=("exclude",),
                ):
                    continue
                replacement = cand
                reason_lookup[cand_name] = cand_reasons
                used_names.add(cand_name)
                break
            if replacement:
                logger.warning(
                    "[injury-guard] strength replacing '%s' -> '%s' reasons=%s",
                    ex.get("name"),
                    replacement.get("name"),
                    reasons,
                )
                updated.append(replacement)
            else:
                logger.warning(
                    "[injury-guard] strength removing '%s' reasons=%s",
                    ex.get("name"),
                    reasons,
                )
                updated.append(None)
        return [ex for ex in updated if ex]

    base_exercises = _finalize_injury_safe_exercises(base_exercises)

    if os.getenv("INJURY_DEBUG") == "1":
        log_injury_debug(base_exercises, injuries, label=f"strength:{phase}")

    for ex in base_exercises:
        normalize_exercise_movement(ex)

    used_days = training_days[:num_strength_sessions]

    strength_output = format_strength_block(phase, fatigue, base_exercises)

    all_tags = []
    for ex in base_exercises:
        all_tags.extend(ex.get("tags", []))

    why_log = []
    for ex in base_exercises:
        name = ex.get("name")
        reasons = reason_lookup.get(name, {}).copy()
        reasons.setdefault("final_score", score_lookup.get(name, 0))
        parts = []
        if reasons.get("goal_hits"):
            parts.append(f"{reasons['goal_hits']} goal match")
        if reasons.get("weakness_hits"):
            parts.append(f"{reasons['weakness_hits']} weakness tag")
        if reasons.get("style_hits"):
            parts.append(f"{reasons['style_hits']} style tag")
        if reasons.get("phase_hits"):
            parts.append(f"{reasons['phase_hits']} phase tag")
        if reasons.get("equipment_boost"):
            parts.append("equipment boost")
        if reasons.get("load_adjustments"):
            parts.append("fatigue adjustment")
        explanation = ", ".join(parts) if parts else "balanced selection"
        why_log.append({"name": name, "reasons": reasons, "explanation": explanation})

    return {
        "block": strength_output,
        "num_sessions": len(used_days),
        "preferred_tags": list(set(all_tags)),
        "exercises": base_exercises,
        "why_log": why_log,
    }
    
