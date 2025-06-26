TRAIT_SCORES = {
    # Base Traits (+0.3)
    "focused": 0.3,
    "aggressive": 0.3,
    "resilient": 0.3,

    # Elite Tier 2 (+0.5)
    "commanding": 0.5,
    "locked-in": 0.5,

    # Elite Tier 1 (+0.7)
    "dominates": 0.7,
    "ruthless": 0.7,
    "thrives": 0.7,
}

SYNERGY_LIST = {
    ("visualisation", "breathwork"): {"required_tags": ["quick_reset", "thrives"]},
    ("game reset", "breathwork"): {"required_tags": ["slow_reset", "emotional"]},
    ("focus drill", "journaling"): {"required_tags": ["overthink", "stage_fear"]},
    ("anchor cue", "self-talk"): {"required_tags": ["identity_gap", "control_need"]},
}

ELITE_TRAITS = {"dominates", "ruthless", "thrives", "commanding", "locked-in"}

import json
import os

# Load tag configuration to identify freeze and reset tags
TAG_FILE = os.path.join(os.path.dirname(__file__), "..", "tags.txt")
try:
    with open(TAG_FILE) as f:
        _tag_cfg = json.load(f)
    FREEZE_TYPE_TAGS = set(_tag_cfg["theme_tags"].get("freeze_type", []))
    RESET_SPEED_TAGS = set(_tag_cfg["theme_tags"].get("reset_speed", []))
except Exception:  # pragma: no cover - fallback if file missing
    FREEZE_TYPE_TAGS = set()
    RESET_SPEED_TAGS = set()


def get_trait_score(trait: str) -> float:
    return TRAIT_SCORES.get(trait.lower(), 0.0)


def check_synergy_match(drill: dict, athlete_tags):
    """Return True if drill has a valid synergy modality pair and athlete has at least one required tag."""
    modalities = {m.lower() for m in drill.get("modalities", [])}
    athlete_tags = {t.lower() for t in athlete_tags}
    for pair, data in SYNERGY_LIST.items():
        if set(pair).issubset(modalities):
            if set(data["required_tags"]).intersection(athlete_tags):
                return True
    return False


def score_drill(drill: dict, phase: str, athlete: dict, override_flag: bool = False) -> float:
    """Score a drill for an athlete based on phase, sport and traits."""
    score = 1.0

    intensity = drill.get("intensity", "medium").lower()
    drill_phase = drill.get("phase", "").upper()
    athlete_phase = phase.upper()

    sport = athlete.get("sport", "").lower()
    in_camp = athlete.get("in_fight_camp", False)
    athlete_tags = [t.lower() for t in athlete.get("tags", [])]
    theme_tags = [t.lower() for t in drill.get("theme_tags", [])]

    # --- Theme tag scoring
    theme_score = 0.0
    if theme_tags:
        theme_score += 0.4
        if len(theme_tags) > 1:
            theme_score += 0.2
    theme_score = min(theme_score, 0.6)

    if sport in {"mma", "boxing"} and any(t in FREEZE_TYPE_TAGS or t in RESET_SPEED_TAGS for t in theme_tags):
        theme_score += 0.05

    score += theme_score

    # --- Trait scoring
    traits = drill.get("raw_traits", [])
    trait_score = sum(get_trait_score(t) for t in traits)
    trait_score = min(trait_score, 1.2)
    score += trait_score

    # --- Phase & intensity adjustments
    if drill_phase and drill_phase == athlete_phase:
        score += 0.5

    if not override_flag and not (sport in {"mma", "boxing"} and in_camp):
        if athlete_phase == "TAPER" and intensity == "high":
            score -= 0.5
        elif athlete_phase == "GPP" and intensity == "high":
            score -= 0.2

    # --- Sport match
    drill_sports = {s.lower() for s in drill.get("sports", [])}
    if sport in drill_sports:
        score += 0.3
    elif "universal" in drill_sports and len(set(theme_tags) & set(athlete_tags)) >= 3:
        score -= 0.1

    # --- Tag specificity
    if len(set(theme_tags) & set(athlete_tags)) >= 3:
        score += 0.2

    # --- Modality synergy
    synergy_ok = check_synergy_match(drill, athlete_tags)
    if synergy_ok:
        score += 0.2

    # --- Elite trait synergy penalty
    if set(traits) & ELITE_TRAITS and not synergy_ok:
        score -= 0.2

    return score
