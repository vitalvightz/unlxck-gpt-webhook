# Tag mapping for Mindcode intake form
from typing import List, Dict
import re


def _norm(text: str) -> str:
    """Normalize text to snake_case for matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


# Mapping dictionaries for each section using normalized keys
S1_MAP = {
    "hesitate": "hesitate",
    "freeze": "freeze",
    "second_guess": "second_guess",
    "emotional": "emotional",
    "overthink": "overthink",
    "avoid_mistakes": "avoid_mistakes",
    "cant_listen": "can't_listen",
    "can't_listen": "can't_listen",
    "scared": "scared",
    "thrive_pressure": "thrive_pressure",
    "thrive_under_pressure": "thrive_pressure",
}

S2_MAP = {
    "replay": "replay",
    "withdrawn": "withdrawn",
    "overcompensate": "overcompensate",
    "disengage": "disengage",
    "angry_self": "angry_self",
    "move_on": "move_on",
    "fear_judgement": "fear_judgement",
}

S3_MAP = {
    "crowd": "crowd",
    "crowd_noise": "crowd",
    "coach": "coach",
    "choice_fear": "choice_fear",
    "fatigue": "fatigue",
    "inner_critic": "inner_critic",
    "players": "players",
    "no_focus_loss": "no_focus_loss",
}

S4_MAP = {
    "instinct": "instinct",
    "think_first": "think_first",
    "freeze_choice": "freeze_choice",
    "defer": "defer",
    "mixed": "mixed",
}

S5_MAP = {
    "train_better": "train_better",
    "lose_conf": "lose_conf",
    "crowd_anx": "crowd_anx",
    "no_trust": "no_trust",
    "emotional_perf": "emotional_perf",
    "needs_control": "needs_control",
    "confident": "confident",
}

# Mental identity values are kept as-is (identity_tag_1 etc.)

S7_PRESSURE_MAP = {
    "breathe_hold": "breathe_hold",
    "tense": "tense",
    "calm": "calm",
}

S7_HR_MAP = {
    "spike": "spike",
    "drop": "drop",
    "neutral": "neutral",
}

S7_RESET_MAP = {
    "instant": "instant",
    "short": "short",
    "long": "long",
}

S7_MOTIVATION_MAP = {
    "reward": "reward",
    "punishment": "punishment",
}

S7_TRIGGER_MAP = {
    "external_loss": "external_loss",
    "internal_failure": "internal_failure",
}


SECTION_MAPS = {
    "s1_under_pressure": S1_MAP,
    "s2_mistakes": S2_MAP,
    "s3_focus": S3_MAP,
    "s5_confidence": S5_MAP,
}


def _map_list(values: List[str], mapping: Dict[str, str]) -> List[str]:
    tags = []
    for v in values or []:
        tag = mapping.get(_norm(v))
        if tag:
            tags.append(tag)
    return tags


def map_mindcode_tags(raw_inputs: Dict[str, object]) -> List[str]:
    """Convert raw form answers to canonical tag list."""
    tags: List[str] = []

    # Multi-select sections S1-S3 and S5
    for key, mapping in SECTION_MAPS.items():
        values = raw_inputs.get(key)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, list):
            tags.extend(_map_list(values, mapping))

    # Decision style is single-select (S4)
    decision_val = raw_inputs.get("s4_decision_style")
    if decision_val:
        tag = S4_MAP.get(_norm(decision_val))
        if tag:
            tags.append(tag)

    # Mental identity dropdowns - store as given
    identity_best = raw_inputs.get("s6_identity_you_best")
    if identity_best:
        tags.append(_norm(identity_best))
    elite_trait = raw_inputs.get("s6_elite_athlete_traits")
    if elite_trait:
        if isinstance(elite_trait, list):
            tags.extend([_norm(t) for t in elite_trait if t])
        else:
            tags.append(_norm(elite_trait))

    # ANS diagnostics (S7)
    pr_resp = raw_inputs.get("s7_pressure_response")
    if pr_resp:
        tag = S7_PRESSURE_MAP.get(_norm(pr_resp))
        if tag:
            tags.append(tag)
    hr_resp = raw_inputs.get("s7_hr_response")
    if hr_resp:
        tag = S7_HR_MAP.get(_norm(hr_resp))
        if tag:
            tags.append(tag)
    reset = raw_inputs.get("s7_reset_time")
    if reset:
        tag = S7_RESET_MAP.get(_norm(reset))
        if tag:
            tags.append(tag)
    motiv = raw_inputs.get("s7_motivation_type")
    if motiv:
        tag = S7_MOTIVATION_MAP.get(_norm(motiv))
        if tag:
            tags.append(tag)
    hit = raw_inputs.get("s7_hits_harder")
    if hit:
        tag = S7_TRIGGER_MAP.get(_norm(hit))
        if tag:
            tags.append(tag)

    return tags
