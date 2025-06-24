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
    if any("freeze" in x.lower() or "stuck" in x.lower() for x in under_pressure):
        tags["freeze_type"] = "physical_freeze"
    elif any("panic" in x.lower() or "overthink" in x.lower() for x in under_pressure):
        tags["freeze_type"] = "mental_freeze"

    # Overthink type
    if any("overthink" in x.lower() for x in under_pressure + post_mistake):
        tags["overthink_type"] = "overthinker"
    elif any("doubt" in x.lower() or "hesitat" in x.lower() for x in under_pressure + post_mistake):
        tags["overthink_type"] = "doubter"

    # Focus breaker
    if any("crowd" in x.lower() or "audience" in x.lower() for x in focus_breakers):
        tags["focus_breaker"] = "distracted_by_crowd"
    elif any("score" in x.lower() or "result" in x.lower() for x in focus_breakers):
        tags["focus_breaker"] = "result_focused"
    elif any("opponent" in x.lower() or "trash" in x.lower() for x in focus_breakers):
        tags["focus_breaker"] = "opponent_noise"

    # Reset speed
    if "under" in reset_duration or "<" in reset_duration or "10" in reset_duration:
        tags["reset_speed"] = "fast_reset"
    elif "30" in reset_duration or "half" in reset_duration:
        tags["reset_speed"] = "medium_reset"
    elif "min" in reset_duration or "60" in reset_duration:
        tags["reset_speed"] = "slow_reset"

    # Heart rate response
    if "speed" in heart_response or "increase" in heart_response or "up" in heart_response:
        tags["hr_response"] = "hr_up"
    elif "slow" in heart_response or "decrease" in heart_response or "down" in heart_response:
        tags["hr_response"] = "hr_down"
    elif "same" in heart_response or "no change" in heart_response:
        tags["hr_response"] = "hr_stable"

    # Breath pattern
    if "hold" in pressure_breath:
        tags["breath_pattern"] = "breath_hold"
    elif "fast" in pressure_breath or "shallow" in pressure_breath:
        tags["breath_pattern"] = "breath_fast"
    elif "slow" in pressure_breath or "deep" in pressure_breath:
        tags["breath_pattern"] = "breath_slow"

    # Motivation type
    if "reward" in motivator or "praise" in motivator:
        tags["motivation_type"] = "reward_seeker"
    elif "avoid" in motivator or "fear" in motivator:
        tags["motivation_type"] = "avoid_failure"
    elif "compete" in motivator or "win" in motivator:
        tags["motivation_type"] = "competitive"
    elif "intrinsic" in motivator or "myself" in motivator:
        tags["motivation_type"] = "self_driven"

    # Threat trigger
    if "shame" in emotional_trigger or "critic" in emotional_trigger:
        tags["threat_trigger"] = "ego_threat"
    elif "fear" in emotional_trigger or "safety" in emotional_trigger:
        tags["threat_trigger"] = "safety_threat"

    # Mental history
    if past_mental:
        tags["mental_history"] = "has_history"

    return tags
