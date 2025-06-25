from typing import Dict, List

def map_tags(form_data: Dict) -> Dict:
    """Map raw form input to controlled mental performance tags."""
    tags = {
        "freeze_type": "stay_loose",
        "overthink_type": "decisive",
        "focus_breaker": "none_reported",
        "reset_speed": "unknown",
        "hr_response": "hr_unknown",
        "breath_pattern": "breath_unknown",
        "motivation_type": "motivation_unknown",
        "threat_trigger": "general_threat",
        "mental_history": "clear_history",
    }

    # Extract lists from multi-selects
    under_pressure: List[str] = form_data.get("under_pressure", [])
    post_mistake: List[str] = form_data.get("post_mistake", [])
    focus_breakers: List[str] = form_data.get("focus_breakers", [])

    # Extract singles
    pressure_breath = form_data.get("pressure_breath", "").strip().lower()
    heart_response = form_data.get("heart_response", "").strip().lower()
    reset_duration = form_data.get("reset_duration", "").strip().lower()
    motivator = form_data.get("motivator", "").strip().lower()
    emotional_trigger = form_data.get("emotional_trigger", "").strip().lower()
    past_mental = form_data.get("past_mental_struggles", "").strip()

    # --- Freeze type (multi-select)
    if "I go blank or freeze" in under_pressure or "I hesitate before acting" in under_pressure:
        tags["freeze_type"] = "physical_freeze"
    elif "I overthink instead of trusting instinct" in under_pressure or "I second-guess good decisions" in under_pressure:
        tags["freeze_type"] = "mental_freeze"
    else:
        tags["freeze_type"] = "stay_loose"

    # --- Overthink type (multi-select)
    if any(x in under_pressure + post_mistake for x in [
        "I overthink instead of trusting instinct",
        "I second-guess good decisions",
        "I replay it over and over in my head"
    ]):
        tags["overthink_type"] = "overthinker"
    elif any(x in under_pressure + post_mistake for x in [
        "I hesitate before acting",
        "I stop wanting the ball or engaging"
    ]):
        tags["overthink_type"] = "doubter"
    else:
        tags["overthink_type"] = "decisive"

    # --- Focus breaker (multi-select)
    if "The crowd / noise" in focus_breakers:
        tags["focus_breaker"] = "distracted_by_crowd"
    elif "Coach instructions" in focus_breakers:
        tags["focus_breaker"] = "coach_noise"
    elif "Fear of making the wrong choice" in focus_breakers or "My own inner critic" in focus_breakers:
        tags["focus_breaker"] = "self_conflict"
    elif "Teammates or opponents" in focus_breakers:
        tags["focus_breaker"] = "opponent_noise"
    elif "Getting tired / out of breath" in focus_breakers:
        tags["focus_breaker"] = "fatigue"
    elif "I rarely lose focus" in focus_breakers:
        tags["focus_breaker"] = "none_reported"
    else:
        tags["focus_breaker"] = "none_reported"

    # --- Reset speed (single-select)
    if "instantly" in reset_duration:
        tags["reset_speed"] = "fast_reset"
    elif "10–30" in reset_duration:
        tags["reset_speed"] = "medium_reset"
    elif "1–2" in reset_duration:
        tags["reset_speed"] = "slow_reset"
    elif "longer" in reset_duration:
        tags["reset_speed"] = "very_slow_reset"
    else:
        tags["reset_speed"] = "unknown"

    # --- Heart rate response (single-select)
    if "spikes" in heart_response:
        tags["hr_response"] = "hr_up"
    elif "drops" in heart_response:
        tags["hr_response"] = "hr_down"
    elif "normal" in heart_response:
        tags["hr_response"] = "hr_stable"
    else:
        tags["hr_response"] = "hr_unknown"

    # --- Breath pattern (single-select)
    if "hold" in pressure_breath:
        tags["breath_pattern"] = "breath_hold"
    elif "shallow" in pressure_breath:
        tags["breath_pattern"] = "breath_fast"
    elif "normally" in pressure_breath:
        tags["breath_pattern"] = "breath_normal"
    else:
        tags["breath_pattern"] = "breath_unknown"

    # --- Motivation type (single-select)
    if "small visible wins" in motivator:
        tags["motivation_type"] = "reward_seeker"
    elif "avoid failure" in motivator:
        tags["motivation_type"] = "avoid_failure"
    elif "competing with others" in motivator:
        tags["motivation_type"] = "competitive"
    elif "praise from others" in motivator:
        tags["motivation_type"] = "external_validation"
    else:
        tags["motivation_type"] = "motivation_unknown"

    # --- Threat trigger (single-select)
    if "coach criticism" in emotional_trigger:
        tags["threat_trigger"] = "authority_threat"
    elif "teammate judgement" in emotional_trigger:
        tags["threat_trigger"] = "peer_threat"
    elif "crowd pressure" in emotional_trigger:
        tags["threat_trigger"] = "audience_threat"
    else:
        tags["threat_trigger"] = "general_threat"

    # --- Mental history (free text)
    if past_mental:
        tags["mental_history"] = "has_history"
    else:
        tags["mental_history"] = "clear_history"

    return tags