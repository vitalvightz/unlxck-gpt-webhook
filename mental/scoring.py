SYNERGY_MAP = {
    ("visualisation", "breathwork"): ["quick_reset", "thrives"],
    ("game reset", "breathwork"): ["slow_reset", "emotional"],
    ("focus drill", "journaling"): ["overthink", "stage_fear"],
}

ELITE_TRAITS = {"ruthless", "dominates", "commanding"}


def check_synergy_match(drill: dict, athlete_tags):
    """Return True if drill has a valid synergy modality pair and athlete has at least one required tag."""
    modalities = {m.lower() for m in drill.get("modalities", [])}
    athlete_tags = {t.lower() for t in athlete_tags}
    for pair, required in SYNERGY_MAP.items():
        if set(pair).issubset(modalities):
            if athlete_tags.intersection(required):
                return True
            return False
    return False


def score_drill(drill: dict, athlete_tags, phase: str, athlete: dict) -> float:
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

    if any(trait in ELITE_TRAITS for trait in drill.get("raw_traits", [])):
        if not check_synergy_match(drill, athlete_tags):
            score -= 0.2

    return score
