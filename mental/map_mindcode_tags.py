"""Mapping helpers for mindcode form fields."""

# Valid input phrases per field. These mirror the Google form options and allow
# simple mapping without long ``if/elif`` chains.
BREATH_OPTIONS = ["hold", "shallow", "normal"]
HR_OPTIONS = ["spike", "drop", "normal"]
RESET_OPTIONS = ["instant", "10", "1", "long"]
MOTIVATOR_OPTIONS = ["avoid", "compete", "praise", "wins"]
TRIGGER_OPTIONS = ["coach", "crowd", "team"]

BREATH_MAP = {
    "hold": "breath_hold",
    "shallow": "breath_fast",
    "normal": "breath_normal",
}

HR_RESPONSE_MAP = {
    "spike": "hr_up",
    "drop": "hr_down",
    "normal": "hr_stable",
}

RESET_SPEED_MAP = {
    "instant": "fast_reset",
    "10": "medium_reset",
    "1": "slow_reset",
    "long": "very_slow_reset",
}

MOTIVATOR_MAP = {
    "avoid": "avoid_failure",
    "compete": "competitive",
    "praise": "external_validation",
    "wins": "reward_seeker",
}

EMOTIONAL_TRIGGER_MAP = {
    "coach": "authority_threat",
    "crowd": "audience_threat",
    "team": "peer_threat",
}


def map_mindcode_tags(form_data: dict) -> dict:
    """Maps mental form inputs into controlled tag outputs."""
    tags = {
        "under_pressure": [],
        "post_mistake": [],
        "focus_breakers": [],
        "confidence_profile": [],
        "identity_traits": [],
        "elite_traits": [],
        "breath_pattern": "breath_unknown",
        "hr_response": "hr_unknown",
        "reset_speed": "unknown",
        "motivation_type": "motivation_unknown",
        "threat_trigger": "general_threat",
        "mental_history": "clear_history",
    }

    # === UNDER PRESSURE ===
    for item in form_data.get("under_pressure", []):
        item = item.lower()
        if "freeze" in item or "blank" in item:
            tags["under_pressure"].append("freeze")
        elif "overthink" in item:
            tags["under_pressure"].append("overthink")
        elif "hesitate" in item:
            tags["under_pressure"].append("hesitate")
        elif "second-guess" in item:
            tags["under_pressure"].append("second_guess")
        elif "emotional" in item:
            tags["under_pressure"].append("emotional")
        elif "safe" in item or "avoid" in item:
            tags["under_pressure"].append("avoidant")
        elif "stop listening" in item:
            tags["under_pressure"].append("audio_cutoff")
        elif "scared" in item:
            tags["under_pressure"].append("demand_avoidance")
        elif "thrive" in item:
            tags["under_pressure"].append("thrives")

    # === POST MISTAKE ===
    for item in form_data.get("post_mistake", []):
        item = item.lower()
        if "replay" in item:
            tags["post_mistake"].append("mental_loop")
        elif "quieter" in item or "withdrawn" in item:
            tags["post_mistake"].append("shutdown")
        elif "make up" in item:
            tags["post_mistake"].append("compensate")
        elif "stop wanting" in item:
            tags["post_mistake"].append("disengage")
        elif "angry" in item:
            tags["post_mistake"].append("self_anger")
        elif "shake it off" in item:
            tags["post_mistake"].append("quick_reset")
        elif "others" in item:
            tags["post_mistake"].append("external_judgement")

    # === FOCUS BREAKERS ===
    for item in form_data.get("focus_breakers", []):
        item = item.lower()
        if "crowd" in item or "noise" in item:
            tags["focus_breakers"].append("focus_crowd")
        elif "coach" in item:
            tags["focus_breakers"].append("focus_coach")
        elif "fear" in item or "wrong" in item:
            tags["focus_breakers"].append("focus_decision_fear")
        elif "tired" in item or "breath" in item:
            tags["focus_breakers"].append("focus_fatigue")
        elif "critic" in item:
            tags["focus_breakers"].append("focus_self_critic")
        elif "teammates" in item or "opponents" in item:
            tags["focus_breakers"].append("focus_social")
        elif "rarely" in item:
            tags["focus_breakers"].append("focus_locked")

    # === CONFIDENCE PROFILE ===
    for item in form_data.get("confidence_profile", []):
        item = item.lower()
        if "train better" in item:
            tags["confidence_profile"].append("gym_performer")
        elif "lose confidence" in item:
            tags["confidence_profile"].append("fragile_confidence")
        elif "perform freely" in item:
            tags["confidence_profile"].append("stage_fear")
        elif "high-pressure" in item:
            tags["confidence_profile"].append("pressure_distrust")
        elif "emotional" in item:
            tags["confidence_profile"].append("emotional_performer")
        elif "control" in item:
            tags["confidence_profile"].append("control_needed")
        elif "confident" in item:
            tags["confidence_profile"].append("stable_confidence")

    # === IDENTITY TRAITS ===
    tags["identity_traits"] = [
        f"trait_{x.lower().replace(' ', '_')}" for x in form_data.get("identity_traits", [])
    ]

    # === ELITE TRAITS ===
    tags["elite_traits"] = [
        f"elite_{x.lower().replace(' ', '_').replace('/', '_')}" for x in form_data.get("elite_traits", [])
    ]

    # === SINGLE SELECTS ===
    pressure_breath = form_data.get("pressure_breath", "").lower()
    heart_response = form_data.get("heart_response", "").lower()
    reset_duration = form_data.get("reset_duration", "").lower()
    motivator = form_data.get("motivator", "").lower()
    emotional_trigger = form_data.get("emotional_trigger", "").lower()

    for key, mapping, value in [
        ("breath_pattern", BREATH_MAP, pressure_breath),
        ("hr_response", HR_RESPONSE_MAP, heart_response),
        ("reset_speed", RESET_SPEED_MAP, reset_duration),
        ("motivation_type", MOTIVATOR_MAP, motivator),
        ("threat_trigger", EMOTIONAL_TRIGGER_MAP, emotional_trigger),
    ]:
        for phrase, tag in mapping.items():
            if phrase in value:
                tags[key] = tag
                break

    # === MENTAL HISTORY ===
    history = form_data.get("past_mental_struggles", "").strip()
    tags["mental_history"] = "has_history" if history else "clear_history"

    # Deduplicate list-based tags
    for list_key in [
        "under_pressure",
        "post_mistake",
        "focus_breakers",
        "confidence_profile",
        "identity_traits",
        "elite_traits",
    ]:
        tags[list_key] = list(set(tags[list_key]))

    return tags
