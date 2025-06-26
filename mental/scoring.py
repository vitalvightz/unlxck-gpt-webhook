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


def score_drill(drill: dict, phase: str, athlete: dict) -> float:
    """Score a drill for an athlete based on phase and traits."""
    score = 1.0

    intensity = drill.get("intensity", "medium").lower()
    sport = athlete.get("sport", "").lower()
    in_camp = athlete.get("in_fight_camp", False)

    if sport not in {"mma", "boxing"} or not in_camp:
        if phase == "TAPER" and intensity == "high":
            score -= 0.5
        elif phase == "GPP" and intensity == "high":
            score -= 0.2

    # --- Trait scoring
    traits = drill.get("raw_traits", [])
    trait_score = sum(get_trait_score(t) for t in traits)
    trait_score = min(trait_score, 1.2)
    score += trait_score

    athlete_tags = athlete.get("tags", [])
    synergy_ok = check_synergy_match(drill, athlete_tags)

    # --- Synergy bonus
    if synergy_ok:
        score += 0.2

    # --- Elite trait synergy penalties
    drill_traits = set(traits)
    has_elite_trait = bool(drill_traits & ELITE_TRAITS)

    if has_elite_trait and not synergy_ok:
        score -= 0.2

    elite_trait_count = len(drill_traits & ELITE_TRAITS)
    if elite_trait_count >= 2 and not synergy_ok:
        score -= 0.2

    return score
