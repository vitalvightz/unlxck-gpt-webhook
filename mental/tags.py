from typing import Dict, List

from .normalization import normalize_tag_dict
from .map_mindcode_tags import TRAINING_TOOLS_MAP, KEY_STRUGGLES_MAP

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
        "decision_making": "decision_unknown",
        "mental_history": "clear_history",
        "preferred_modality": [],
        "struggles_with": [],
    }

    # Extract lists from multi-selects
    under_pressure: List[str] = form_data.get("under_pressure", [])
    post_mistake: List[str] = form_data.get("post_mistake", [])
    focus_breakers: List[str] = form_data.get("focus_breakers", [])
    tool_preferences: List[str] = form_data.get("tool_preferences", [])
    key_struggles: List[str] = form_data.get("key_struggles", [])

    # Extract singles
    pressure_breath = form_data.get("pressure_breath", "").strip().lower()
    heart_response = form_data.get("heart_response", "").strip().lower()
    reset_duration = form_data.get("reset_duration", "").strip().lower()
    motivator = form_data.get("motivator", "").strip().lower()
    emotional_trigger = form_data.get("emotional_trigger", "").strip().lower()
    decision_choice = form_data.get("decision_making", "").strip().lower()

    # Map tool preference and struggle lists to tags
    preferred_modality: List[str] = []
    for item in tool_preferences:
        val = item.strip().lower()
        if val in TRAINING_TOOLS_MAP:
            preferred_modality.append(TRAINING_TOOLS_MAP[val])

    struggles_with: List[str] = []
    for item in key_struggles:
        val = item.strip().lower()
        if val in KEY_STRUGGLES_MAP:
            struggles_with.append(KEY_STRUGGLES_MAP[val])

    tags["preferred_modality"] = preferred_modality
    tags["struggles_with"] = struggles_with

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

    # --- Decision making (single-select)
    if "instantly" in decision_choice or "instinct" in decision_choice:
        tags["decision_making"] = "decide_fast"
    elif "think" in decision_choice:
        tags["decision_making"] = "decide_think"
    elif "freeze" in decision_choice:
        tags["decision_making"] = "decide_freeze"
    elif "wait" in decision_choice:
        tags["decision_making"] = "decide_wait"
    elif "sometimes" in decision_choice:
        tags["decision_making"] = "decide_mix"
    else:
        tags["decision_making"] = "decision_unknown"

    # --- Mental history (free text)
    if past_mental:
        tags["mental_history"] = "has_history"
    else:
        tags["mental_history"] = "clear_history"

    # Deduplicate preference lists
    tags["preferred_modality"] = list(dict.fromkeys(tags["preferred_modality"]))
    tags["struggles_with"] = list(dict.fromkeys(tags["struggles_with"]))

    # Normalize synonymous tags across all fields
    tags = normalize_tag_dict(tags)

    return tags
