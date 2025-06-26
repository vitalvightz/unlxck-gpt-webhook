"""Mapping helpers for mindcode form fields.

Each mapping dictionary key corresponds to an exact option from the Google form
(lowercased).  Using lookups keeps the logic explicit and avoids broad
substring checks.
"""

from typing import Any, Dict, List, Union

from .normalization import normalize_tag_dict

# Multi-select option -> tag lookups
UNDER_PRESSURE_MAP = {
    "i hesitate before acting": "hesitate",
    "i go blank or freeze": "freeze",
    "i second-guess good decisions": "second_guess",
    "i get angry and emotional": "emotional",
    "i overthink instead of trusting instinct": "overthink",
    "i play safe or avoid mistakes": "avoidant",
    "i stop listening or can’t hear instructions": "audio_cutoff",
    "i get scared to demand the ball or take shots": "demand_avoidance",
    "i feel calm and thrive under pressure": "thrives",
}

POST_MISTAKE_MAP = {
    "i replay it over and over in my head": "mental_loop",
    "i get quieter or withdrawn": "shutdown",
    "i try to make up for it too quickly": "compensate",
    "i stop wanting the ball or engaging": "disengage",
    "i get tense or angry with myself": "self_anger",
    "i shake it off quickly and move on": "quick_reset",
    "i start thinking of what others will say": "external_judgement",
}

FOCUS_BREAKERS_MAP = {
    "the crowd / noise": "focus_crowd",
    "coach instructions": "focus_coach",
    "fear of making the wrong choice": "focus_decision_fear",
    "getting tired / out of breath": "focus_fatigue",
    "my own inner critic": "focus_self_critic",
    "teammates or opponents": "focus_social",
    "i rarely lose focus": "focus_locked",
}

CONFIDENCE_PROFILE_MAP = {
    "i train better than i perform": "gym_performer",
    "i lose confidence easily after mistakes": "fragile_confidence",
    "i struggle to perform freely in front of others": "stage_fear",
    "i don’t trust myself in high-pressure moments": "pressure_distrust",
    "i perform better when i’m emotional": "emotional_performer",
    "i need to feel in control to perform": "control_needed",
    "i am confident in myself, regardless of outcome": "stable_confidence",
}

# Single-select option -> tag lookups
BREATH_MAP = {
    "hold my breath": "breath_hold",
    "breathe shallow": "breath_fast",
    "breathe normally": "breath_normal",
    "no idea": "breath_unknown",
}

HR_RESPONSE_MAP = {
    "spikes": "hr_up",
    "drops": "hr_down",
    "feels normal": "hr_stable",
    "not sure": "hr_unknown",
}

RESET_SPEED_MAP = {
    "instantly": "fast_reset",
    "10–30 seconds": "medium_reset",
    "1–2 minutes": "slow_reset",
    "longer": "very_slow_reset",
}

MOTIVATOR_MAP = {
    "avoid failure": "avoid_failure",
    "competing with others": "competitive",
    "praise from others": "external_validation",
    "small visible wins": "reward_seeker",
}

EMOTIONAL_TRIGGER_MAP = {
    "coach criticism": "authority_threat",
    "crowd pressure": "audience_threat",
    "teammate judgement": "peer_threat",
    "i don’t know / i zoned out": "general_threat",
}


def map_mindcode_tags(form_data: Dict[str, Any]) -> Dict[str, Union[str, List[str]]]:
    """Map raw form input to controlled mental performance tags."""
    tags: Dict[str, Union[str, List[str]]] = {
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

    # === MULTI-SELECT FIELDS ===
    for field, mapping in [
        ("under_pressure", UNDER_PRESSURE_MAP),
        ("post_mistake", POST_MISTAKE_MAP),
        ("focus_breakers", FOCUS_BREAKERS_MAP),
        ("confidence_profile", CONFIDENCE_PROFILE_MAP),
    ]:
        for item in form_data.get(field, []):
            normalized = item.strip().lower()
            if normalized in mapping:
                tags[field].append(mapping[normalized])

    # === IDENTITY TRAITS ===
    tags["identity_traits"] = [
        f"trait_{x.lower().replace(' ', '_')}" for x in form_data.get("identity_traits", [])
    ]

    # === ELITE TRAITS ===
    tags["elite_traits"] = [
        f"elite_{x.lower().replace(' ', '_').replace('/', '_')}" for x in form_data.get("elite_traits", [])
    ]

    # === SINGLE SELECTS ===
    pressure_breath = form_data.get("pressure_breath", "").strip().lower()
    heart_response = form_data.get("heart_response", "").strip().lower()
    reset_duration = form_data.get("reset_duration", "").strip().lower()
    motivator = form_data.get("motivator", "").strip().lower()
    emotional_trigger = form_data.get("emotional_trigger", "").strip().lower()

    lookup_pairs = [
        ("breath_pattern", BREATH_MAP, pressure_breath),
        ("hr_response", HR_RESPONSE_MAP, heart_response),
        ("reset_speed", RESET_SPEED_MAP, reset_duration),
        ("motivation_type", MOTIVATOR_MAP, motivator),
        ("threat_trigger", EMOTIONAL_TRIGGER_MAP, emotional_trigger),
    ]
    for key, mapping, value in lookup_pairs:
        if value in mapping:
            tags[key] = mapping[value]

    # === MENTAL HISTORY ===
    history = form_data.get("past_mental_struggles", "").strip()
    tags["mental_history"] = "has_history" if history else "clear_history"

    # Deduplicate lists while preserving order
    for list_key in [
        "under_pressure",
        "post_mistake",
        "focus_breakers",
        "confidence_profile",
        "identity_traits",
        "elite_traits",
    ]:
        tags[list_key] = list(dict.fromkeys(tags[list_key]))

    # Normalize synonymous tags across all fields
    tags = normalize_tag_dict(tags)

    return tags
