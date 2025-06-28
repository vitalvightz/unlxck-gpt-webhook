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

# New multi-select questions
TRAINING_TOOLS_MAP = {
    "breathwork": "pref_breathwork",
    "cold exposure": "pref_cold_exposure",
    "journaling or reflection": "pref_journaling",
    "anchor cue (e.g word/action/object)": "pref_anchor_cue",
    "visualisation": "pref_visualisation",
    "i’m not sure yet": "pref_unknown",
}

KEY_STRUGGLES_MAP = {
    "overthinking": "overthink",
    "emotional reactions": "emotional",
    "confidence gaps / self-doubt": "fragile_confidence",
    "struggling to reset quickly": "slow_reset",
    "needing control to perform well": "control_needed",
    "identity crisis (e.g. performing different in training vs where it matters)": "gym_performer",
    "i don’t know": "unknown_struggle",
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

# Decision making styles
DECISION_MAKING_MAP = {
    "i act instantly and trust my instincts": "decide_fast",
    "i think first, then act": "decide_think",
    "i freeze when i have too many options": "decide_freeze",
    "i wait for others to decide first": "decide_wait",
    "sometimes i lead sometimes i defer": "decide_mix",
}


def map_mindcode_tags(form_data: Dict[str, Any]) -> Dict[str, Union[str, List[str]]]:
    """Compatibility wrapper that uses :func:`map_tags` then adds legacy keys."""
    from .tags import map_tags

    tags = map_tags(form_data)

    def _map_list(field: str, mapping: Dict[str, str]) -> list[str]:
        vals = []
        for item in form_data.get(field, []):
            key = item.strip().lower()
            if key in mapping:
                vals.append(mapping[key])
        return list(dict.fromkeys(vals))

    for field, mapping in [
        ("under_pressure", UNDER_PRESSURE_MAP),
        ("post_mistake", POST_MISTAKE_MAP),
        ("focus_breakers", FOCUS_BREAKERS_MAP),
        ("confidence_profile", CONFIDENCE_PROFILE_MAP),
        ("tool_preferences", TRAINING_TOOLS_MAP),
        ("key_struggles", KEY_STRUGGLES_MAP),
    ]:
        tags[field] = _map_list(field, mapping)

    return normalize_tag_dict(tags)
