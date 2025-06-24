"""Mapping functions for mental performance tags."""
from typing import Dict, List


def map_tags(form_data: Dict) -> Dict:
    """Map raw form input to controlled mental performance tags."""
    tags = {
        "freeze_type": "stay_loose",
        "overthink_type": "decisive",
        "focus_breaker": "none_reported",
        "reset_speed": "unknown",
        "hr_response": "hr_unknown",
        "breath_pattern": "breath_normal",
        "motivation_type": "motivation_unknown",
        "threat_trigger": "general_threat",
        "mental_history": "clear_history",
    }

    # Extract inputs
    under_pressure: List[str] = form_data.get("under_pressure", [])
    post_mistake: List[str] = form_data.get("post_mistake", [])
    focus_breakers: List[str] = form_data.get("focus_breakers", [])

    pressure_breath: str = form_data.get("pressure_breath", "").lower()
    heart_response: str = form_data.get("heart_response", "").lower()
    reset_duration: str = form_data.get("reset_duration", "").lower()
    motivator: str = form_data.get("motivator", "").lower()
    emotional_trigger: str = form_data.get("emotional_trigger", "").lower()
    past_mental: str = form_data.get("past_mental_struggles", "").strip()

    # Freeze type
    if "I go blank or freeze" in under_pressure or "I hesitate before acting" in under_pressure:
        tags["freeze_type"] = "physical_freeze"
    elif "I overthink instead of trusting instinct" in under_pressure or "I second-guess good decisions" in under_pressure:
        tags["freeze_type"] = "mental_freeze"

    # Overthink type
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

    # Focus breaker
    if "The crowd / noise" in focus_breakers:
        tags["focus_breaker"] = "distracted_by_crowd"
    elif "Fear of making the wrong choice" in focus_breakers or "My own inner critic" in focus_breakers:
        tags["focus_breaker"] = "self_conflict"
    elif "Teammates or opponents" in focus_breakers:
        tags["focus_breaker"] = "social_disruption"

    # Reset speed
    if "instantly" in reset_duration:
        tags["reset_speed"] = "fast_reset"
    elif "10–30" in reset_duration:
        tags["reset_speed"] = "medium_reset"
    elif "1–2" in reset_duration:
        tags["reset_speed"] = "slow_reset"
    elif "longer" in reset_duration:
        tags["reset_speed"] = "very_slow_reset"

    # Heart rate response
    if "spikes" in heart_response:
        tags["hr_response"] = "hr_up"
    elif "drops" in heart_response:
        tags["hr_response"] = "hr_down"
    elif "normal" in heart_response:
        tags["hr_response"] = "hr_stable"

    # Breath pattern
    if "hold" in pressure_breath:
        tags["breath_pattern"] = "breath_hold"
    elif "shallow" in pressure_breath:
        tags["breath_pattern"] = "breath_fast"
    elif "normally" in pressure_breath:
        tags["breath_pattern"] = "breath_normal"

    # Motivation type
    if "small visible wins" in motivator:
        tags["motivation_type"] = "reward_seeker"
    elif "avoid failure" in motivator:
        tags["motivation_type"] = "avoid_failure"
    elif "competing with others" in motivator:
        tags["motivation_type"] = "competitive"
    elif "praise from others" in motivator:
        tags["motivation_type"] = "external_validation"

    # Threat trigger
    if "coach criticism" in emotional_trigger:
        tags["threat_trigger"] = "authority_threat"
    elif "teammate judgement" in emotional_trigger:
        tags["threat_trigger"] = "peer_threat"
    elif "crowd pressure" in emotional_trigger:
        tags["threat_trigger"] = "audience_threat"

    # Mental history
    if past_mental:
        tags["mental_history"] = "has_history"

    return tags