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

    if "hold" in pressure_breath:
        tags["breath_pattern"] = "breath_hold"
    elif "shallow" in pressure_breath:
        tags["breath_pattern"] = "breath_fast"
    elif "normal" in pressure_breath:
        tags["breath_pattern"] = "breath_normal"
    else:
        tags["breath_pattern"] = "breath_unknown"

    if "spike" in heart_response:
        tags["hr_response"] = "hr_up"
    elif "drop" in heart_response:
        tags["hr_response"] = "hr_down"
    elif "normal" in heart_response:
        tags["hr_response"] = "hr_stable"
    else:
        tags["hr_response"] = "hr_unknown"

    if "instant" in reset_duration:
        tags["reset_speed"] = "fast_reset"
    elif "10" in reset_duration:
        tags["reset_speed"] = "medium_reset"
    elif "1" in reset_duration:
        tags["reset_speed"] = "slow_reset"
    elif "long" in reset_duration:
        tags["reset_speed"] = "very_slow_reset"
    else:
        tags["reset_speed"] = "unknown"

    if "avoid" in motivator:
        tags["motivation_type"] = "avoid_failure"
    elif "compete" in motivator:
        tags["motivation_type"] = "competitive"
    elif "praise" in motivator:
        tags["motivation_type"] = "external_validation"
    elif "wins" in motivator:
        tags["motivation_type"] = "reward_seeker"
    else:
        tags["motivation_type"] = "motivation_unknown"

    if "coach" in emotional_trigger:
        tags["threat_trigger"] = "authority_threat"
    elif "crowd" in emotional_trigger:
        tags["threat_trigger"] = "audience_threat"
    elif "team" in emotional_trigger:
        tags["threat_trigger"] = "peer_threat"
    else:
        tags["threat_trigger"] = "general_threat"

    # === MENTAL HISTORY ===
    history = form_data.get("past_mental_struggles", "").strip()
    tags["mental_history"] = "has_history" if history else "clear_history"

    return tags