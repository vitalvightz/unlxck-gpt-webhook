from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .injury_guard import Decision

from .injury_exclusion_rules import INJURY_REGION_KEYWORDS, INJURY_RULES
from .injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
from .bank_schema import validate_training_item
from .tagging import normalize_item_tags, normalize_tags
# Refactored: Import centralized DATA_DIR from config
from .config import DATA_DIR
INJURY_MATCH_ALLOWLIST: list[str] = [
    "pressure fighter",
    "pressure cooker",
    "sandbox jumper",
    "ship hinge",
    "stomach ache",
]
GENERIC_SINGLE_WORD_PATTERNS = {"press", "overhead", "bench"}
CONSTRAINT_KEYWORDS = {
    "avoid",
    "no",
    "not",
    "limit",
    "limited",
    "restriction",
    "restricted",
    "contraindicated",
    "skip",
    "reduce",
}
CONSTRAINT_INTENSITY_WORDS = {
    "heavy",
    "light",
    "lighter",
    "easy",
    "easier",
    "moderate",
    "low",
    "high",
}
CONSTRAINT_MOVEMENT_WORDS = {
    "press",
    "pressing",
    "overhead",
    "squat",
    "lunge",
    "jump",
    "run",
    "sprint",
    "lift",
    "loading",
    "load",
    "deadlift",
    "bench",
    "pull",
    "push",
}
MAX_VELOCITY_EXCLUDE_KEYWORDS = [
    "assault bike",
    "echo bike",
    "air bike",
    "rower",
    "ski erg",
    "ski-erg",
    "battle rope",
    "rope wave",
]
MAX_VELOCITY_RUNNING_KEYWORDS = [
    "sprint",
    "sprints",
    "sprint start",
    "acceleration",
    "accelerations",
    "hill sprint",
    "treadmill sprint",
    "10m",
    "20m",
    "30m",
    "track",
    "shuttle sprint",
    "shuttle run",
]

MECH_KEYWORDS: list[tuple[str, list[str]]] = [
    (
        "mech_max_velocity",
        [
            "fly sprint",
            "flying sprint",
            "max sprint",
            "top speed",
            "40yd",
            "20m",
            "10m",
            "sprints",
            "sprint",
            "flying",
        ],
    ),
    (
        "mech_acceleration",
        [
            "drive phase",
            "hill sprint",
            "acceleration",
            "accel",
            "start",
            "burst",
        ],
    ),
    (
        "mech_deceleration",
        [
            "stick landing",
            "deceleration",
            "decel",
            "brake",
            "stop",
        ],
    ),
    (
        "mech_change_of_direction",
        [
            "change of direction",
            "pro agility",
            "shuffle cut",
            "cut",
            "cod",
            "pivot",
            "turn",
        ],
    ),
    (
        "mech_landing_impact",
        [
            "land and stick",
            "depth drop",
            "depth jump",
            "drop jump",
            "hard landing",
            "stick landing",
            "stick",
        ],
    ),
    (
        "mech_reactive_rebound",
        [
            "repeated hops",
            "ankle hops",
            "reactive",
            "rebound",
            "pogo",
            "bounce",
        ],
    ),
    (
        "mech_hinge_eccentric",
        [
            "tempo hinge",
            "slow lower",
            "stiff leg",
            "stiff-leg",
            "romanian",
            "good morning",
            "nordic",
            "rdl",
        ],
    ),
    (
        "mech_hinge_isometric",
        [
            "rack pull isometric",
            "isometric deadlift",
            "deadlift isometric",
            "mid-thigh iso",
            "mid thigh iso",
            "iso hinge",
        ],
    ),
    (
        "mech_squat_deep",
        [
            "pause squat",
            "deep squat",
            "full squat",
            "atg",
        ],
    ),
    (
        "mech_knee_over_toe",
        [
            "knees over toes",
            "step down",
            "sissy",
            "pistol",
            "atg",
        ],
    ),
    (
        "mech_lateral_shift",
        [
            "lateral lunge",
            "side lunge",
            "cossack",
            "skater",
        ],
    ),
    (
        "mech_rotation_high_torque",
        [
            "sledgehammer",
            "scoop toss",
            "woodchop",
            "rotational",
            "rotation",
            "twist",
        ],
    ),
    (
        "mech_anti_rotation",
        [
            "anti-rotation",
            "pressout",
            "pallof",
        ],
    ),
    (
        "mech_axial_heavy",
        [
            "overhead press",
            "back squat",
            "front squat",
            "zercher",
            "yoke",
        ],
    ),
    (
        "mech_overhead_dynamic",
        [
            "push press",
            "thruster",
            "snatch",
            "jerk",
        ],
    ),
    (
        "mech_overhead_static",
        [
            "overhead hold",
            "waiter carry",
            "strict press",
            "z press",
        ],
    ),
    (
        "mech_horizontal_push",
        [
            "chest press",
            "db press",
            "push-up",
            "push up",
            "bench",
        ],
    ),
    (
        "mech_horizontal_pull",
        [
            "inverted row",
            "cable row",
            "trx row",
            "row",
        ],
    ),
    (
        "mech_vertical_pull_heavy",
        [
            "pull-up",
            "pull up",
            "chin-up",
            "chin up",
            "lat pulldown",
        ],
    ),
    (
        "mech_grip_intensive",
        [
            "wrist roller",
            "fat grip",
            "towel",
            "pinch",
            "hang",
            "rope",
        ],
    ),
    (
        "mech_grip_static",
        [
            "static hold",
            "dead hang",
            "hold",
        ],
    ),
    (
        "mech_loaded_carry",
        [
            "suitcase carry",
            "sandbag carry",
            "yoke carry",
            "farmers",
            "farmer",
            "carry",
        ],
    ),
]

INFERRED_TAG_RULES = [
    {"keywords": ["bench press", "floor press"], "tags": ["upper_push", "horizontal_push", "press_heavy"]},
    {
        "keywords": ["overhead press", "push press", "strict press", "military press"],
        "tags": ["overhead", "upper_push", "dynamic_overhead", "press_heavy"],
    },
    {"keywords": ["snatch", "jerk"], "tags": ["overhead", "shoulder_heavy", "dynamic_overhead"]},
    {
        "keywords": ["ring dip", "bench dip", "parallel bar dip", "bar dip", "dip"],
        "tags": ["upper_push", "elbow_extension_heavy", "dip_loaded"],
    },
    {"keywords": ["handstand"], "tags": ["overhead", "wrist_loaded_extension"]},
    {"keywords": ["push-up", "pushup"], "tags": ["upper_push", "wrist_loaded_extension"]},
    {"keywords": ["front rack"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {"keywords": ["clean"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {
        "keywords": ["deadlift", "rdl", "good morning", "jefferson curl"],
        "tags": ["hinge_heavy", "axial_heavy", "lumbar_loaded", "posterior_chain_heavy"],
    },
    {"keywords": ["back squat", "front squat", "heavy squat"], "tags": ["knee_dominant_heavy", "axial_heavy"]},
    {"keywords": ["deep squat", "pistol", "cossack"], "tags": ["deep_flexion", "hip_irritant"]},
    {"keywords": ["lateral lunge", "adductor"], "tags": ["adductor_load_high"]},
    {"keywords": ["nordic", "ham curl"], "tags": ["hamstring_eccentric_high"]},
    {"keywords": ["sprint", "sprints", "max sprint", "acceleration", "accelerations"], "tags": ["max_velocity"]},
    {
        "keywords": ["jump", "plyo", "depth jump", "drop jump", "bounds", "hops", "pogo"],
        "tags": [
            "high_impact_plyo",
            "landing_stress_high",
            "reactive_rebound_high",
            "calf_rebound_high",
            "forefoot_load_high",
            "toe_extension_high",
        ],
    },
    {"keywords": ["jump rope"], "tags": ["impact_rebound_high", "foot_impact_high"]},
    {"keywords": ["bear crawl"], "tags": ["wrist_loaded_extension"]},
    {
        "keywords": ["rope climb", "towel", "thick grip", "plate pinch", "farmer", "dead hang"],
        "tags": ["grip_max", "hand_crush", "pinch_grip_high"],
    },
    {"keywords": ["bridges", "wrestler bridge"], "tags": ["neck_loaded"]},
    {"keywords": ["lateral bounds", "hard cuts"], "tags": ["ankle_lateral_impact_high"]},
    {"keywords": ["barefoot sprint"], "tags": ["foot_impact_high"]},
    {"keywords": ["contact", "sparring"], "tags": ["contact"]},
    {"keywords": ["carry", "yoke", "farmer", "suitcase carry"], "tags": ["carry_heavy"]},
    {"keywords": ["row", "seal row", "t bar row", "t-bar row", "meadows row"], "tags": ["row_heavy", "upper_back_loaded"]},
    {"keywords": ["back extension", "reverse hyper", "reverse hyperextension"], "tags": ["spine_extension_loaded", "lumbar_loaded"]},
    {"keywords": ["jefferson curl"], "tags": ["spine_flexion_loaded", "lumbar_loaded"]},
    {
        "keywords": ["run", "running", "roadwork", "jog", "treadmill"],
        "tags": ["running_volume_high", "shin_splints_risk", "calf_volume_high"],
    },
    {
        "keywords": ["agility", "shuffle", "change of direction", "cut", "decel", "deceleration"],
        "tags": ["cod_high", "decel_high"],
    },
]

AUTO_TAG_RULES = [
    {
        "keywords": ["assault bike", "air bike", "bike", "cycle", "spin bike"],
        "tags": ["aerobic", "low_impact"],
    },
    {
        "keywords": ["row", "rower", "erg", "ski erg", "ski-erg"],
        "tags": ["aerobic", "low_impact"],
    },
    {"keywords": ["treadmill", "run", "running", "jog"], "tags": ["aerobic"]},
    {"keywords": ["mobility", "stretch", "recovery", "breathing"], "tags": ["mobility", "recovery"]},
]

INJURY_TAG_ALIASES = {
    "adductors": {"long_lever_adductor", "wide_stance_adductor_high"},
    "aerobic": set(),
    "agility": {"cod_high", "decel_high"},
    "boxing": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "clinch": {"contact", "sparring", "head_impact", "striking_contact"},
    "core": {"hip_flexion_loaded", "hip_flexor_strain_risk"},
    "deadlift": {"posterior_chain_heavy", "lumbar_loaded"},
    "endurance": set(),
    "explosive": {"explosive_upper_push"},
    "grappling": {"contact", "sparring", "head_impact"},
    "grip": {
        "finger_flexor_high",
        "forearm_load_high",
        "wrist_flexor_high",
        "wrist_compression_high",
        "finger_load_high",
        "pinch_grip_high",
    },
    "hamstring": {"posterior_chain_eccentric_high"},
    "high_cns": set(),
    "hip_dominant": {
        "hip_impingement_risk",
        "hip_internal_rotation_stress",
        "hip_extension_heavy",
        "glute_load_high",
        "pelvic_shear_risk",
    },
    "kickboxing": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "lateral": {"cod_high", "decel_high"},
    "mma": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "muay_thai": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "neck": {"cervical_load", "cervical_extension_loaded", "cervical_flexion_loaded", "neck_bridge"},
    "overhead": {"dynamic_overhead", "press_heavy", "wrist_extension_high"},
    "plyometric": {"landing_stress_high", "reactive_rebound_high", "achilles_high_risk_impact", "forefoot_load_high"},
    "posterior_chain": {"posterior_chain_heavy", "lumbar_loaded", "glute_load_high", "hip_extension_heavy"},
    "pull": {"row_heavy", "deep_elbow_flexion_loaded"},
    "push": {"press_heavy", "pec_loaded", "explosive_upper_push", "wrist_extension_high"},
    "quad_dominant": {"quad_dominant_heavy", "deep_knee_flexion_loaded"},
    "reactive": {"reactive_rebound_high", "achilles_high_risk_impact", "forefoot_load_high"},
    "shoulders": {"press_heavy", "dynamic_overhead"},
    "speed": {"max_velocity", "decel_high"},
    "striking": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "triceps": {"triceps_tendon_heavy"},
    "unilateral": {"asym_load_high"},
    "upper_back": {"upper_back_loaded"},
    "upper_body": {"pec_loaded"},
    "wrestling": {"contact", "sparring", "head_impact"},
}

logger = logging.getLogger(__name__)

INJURY_DEBUG = os.environ.get("INJURY_DEBUG", "0") == "1"


def _log_exclusion(context: str, item: dict, decision: Decision) -> None:
    """
    Log exclusion details when INJURY_DEBUG is enabled and item is excluded.
    
    Args:
        context: Context string (e.g. "strength:GPP", "conditioning:SPP")
        item: Item being excluded
        decision: Decision object with action, reason, matched_tags, etc.
    """
    if not INJURY_DEBUG:
        return
    
    if decision.action != "exclude":
        return
    
    # Extract item name
    name = item.get("name") or item.get("drill") or item.get("title") or "<unnamed>"
    
    # Extract decision details
    reason = decision.reason if isinstance(decision.reason, dict) else {}
    region = reason.get("region", "unknown")
    severity = reason.get("severity", "unknown")
    matched_tags = decision.matched_tags or []
    
    # Extract triggers (tags and patterns from matches)
    matches = reason.get("matches", [])
    all_tags = set()
    all_patterns = set()
    
    for match in matches:
        if isinstance(match, dict):
            all_tags.update(match.get("tags", []))
            all_patterns.update(match.get("patterns", []))
    
    trigger_tags = sorted(all_tags) if all_tags else []
    trigger_patterns = sorted(all_patterns) if all_patterns else []
    
    # Format trigger information
    triggers = {
        "tags": trigger_tags,
        "patterns": trigger_patterns,
        "matched_tags": matched_tags,
    }
    
    # Log exclusion with context
    logger.info(
        "[INJURY_EXCLUSION] %s | name=%s | region=%s | severity=%s | risk_score=%.3f | triggers=%s",
        context,
        name,
        region,
        severity,
        decision.risk_score,
        triggers,
    )


def _log_replacement(context: str, excluded_name: str, replacement_name: str) -> None:
    """
    Log replacement details when INJURY_DEBUG is enabled.
    
    Args:
        context: Context string (e.g. "strength:GPP", "conditioning:SPP")
        excluded_name: Name of the excluded item
        replacement_name: Name of the replacement item
    """
    if not INJURY_DEBUG:
        return
    
    logger.info(
        "[INJURY_REPLACEMENT] %s | excluded=%s | replacement=%s",
        context,
        excluded_name,
        replacement_name,
    )


LOWER_BODY_CNS_TAGS = {
    "plyometric",
    "reactive",
    "posterior_chain",
    "acceleration",
    "speed",
    "sprint",
    "running",
    "jump",
    "bounds",
    "hops",
    "landing",
    "knee_dominant",
    "hip_dominant",
    "quad_dominant",
}
SHOULDER_TAG_EXCLUSIONS = {
    "face pull",
    "band face pull",
    "wall slide",
    "wall slide (shoulder mobility)",
    "dead hang",
    "scapular pull-up",
}


def expand_injury_tags(tags: Iterable[str], *, item: dict | None = None) -> set[str]:
    tag_set = {t for t in normalize_tags(tags) if t}
    expanded: set[str] = set()
    for tag in tag_set:
        expanded.update(INJURY_TAG_ALIASES.get(tag, ()))
    if "high_cns" in tag_set:
        name = str(item.get("name", "") or "") if item else ""
        if not (tag_set & LOWER_BODY_CNS_TAGS) and not match_forbidden(
            name, ["sprint", "sprints", "jump", "plyo", "hops", "bounds"], allowlist=INJURY_MATCH_ALLOWLIST
        ):
            expanded.add("high_cns_upper")
    if "shoulders" in tag_set and item:
        name = str(item.get("name", "") or "").lower()
        if name in SHOULDER_TAG_EXCLUSIONS:
            expanded.discard("dynamic_overhead")
            expanded.discard("press_heavy")
    return expanded


def _normalize_text(text: str) -> str:
    """
    Normalize text for matching by:
    - Converting to lowercase
    - Replacing hyphens and underscores with spaces
    - Removing all punctuation/parentheses
    - Collapsing whitespace
    
    This is used for word-boundary based matching.
    """
    cleaned = text.lower().replace("-", " ").replace("_", " ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def normalize_for_substring_match(text: str) -> str:
    """
    Normalize text for substring matching by:
    - Converting to lowercase  
    - Removing all non-alphanumeric characters (including spaces)
    - This allows 'rdl' to match in 'RomanianDeadlift', 'myRDL', etc.
    
    Returns:
        Normalized string with only lowercase alphanumeric characters.
    """
    # Convert to lowercase
    cleaned = text.lower()
    # Remove all non-alphanumeric characters (including spaces, hyphens, underscores, parentheses)
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
    return cleaned


def _module_for_item(item: dict) -> str:
    placement = str(item.get("placement", "") or "").lower()
    if placement == "conditioning":
        return "conditioning"
    bank = str(item.get("bank") or item.get("source") or "").lower()
    if "conditioning" in bank:
        return "conditioning"
    if item.get("system"):
        return "conditioning"
    return "strength"


def _phrase_in_text(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_text(phrase)
    phrase_tokens = normalized_phrase.split()
    if not phrase_tokens:
        return False
    escaped = r"\s+".join(re.escape(token) for token in phrase_tokens)
    pattern = rf"\b{escaped}\b"
    return re.search(pattern, text) is not None


def _infer_mechanism_tags_from_name(name: str) -> set[str]:
    normalized_name = _normalize_text(name)
    if not normalized_name:
        return set()
    inferred: set[str] = set()
    for tag, keywords in MECH_KEYWORDS:
        for phrase in keywords:
            if _phrase_in_text(normalized_name, phrase):
                inferred.add(tag)
                break
    return inferred


def match_forbidden(text: str, patterns: Iterable[str], *, allowlist: Iterable[str] | None = None) -> list[str]:
    """
    Check if text contains any forbidden patterns using multi-strategy matching.
    
    Matching strategies:
    1. Word-boundary matching (primary) - handles most cases including proper word boundaries
    2. Substring matching for multi-word patterns (fallback) - handles compound words like 'RomanianDeadlift'
    
    The substring matching is only used as a fallback when word-boundary matching finds no matches.
    This prevents "toe tap" from matching via substring when "toe taps" already matched via word boundary.
    
    Examples:
    - 'Romanian Deadlift' matches 'romanian deadlift' (word boundary)
    - 'Romanian Deadlift (RDL)' matches 'romanian deadlift' and 'rdl' (word boundary after normalization)
    - 'RomanianDeadlift' matches 'romanian deadlift' (substring for multi-word pattern, fallback)
    - 'toe taps' with patterns ['toe tap', 'toe taps'] matches only 'toe taps' (word boundary, no fallback needed)
    - 'kipping pull-up' matches 'kipping' (word boundary)
    - 'skipping rope' does NOT match 'kipping' (not a word boundary, and single-word patterns don't use substring)
    
    Args:
        text: Text to check (e.g., exercise name)
        patterns: List of forbidden patterns (e.g., ban_keywords)
        allowlist: Optional list of allowed phrases that bypass all checks
        
    Returns:
        List of matched patterns (original form, not normalized)
    """
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return []
    
    # Check allowlist first with word-boundary matching to avoid false positives
    allowlist = allowlist or []
    for phrase in allowlist:
        if _phrase_in_text(normalized_text, phrase):
            return []
    
    # First pass: try word-boundary matching for all patterns
    word_boundary_matches: list[str] = []
    seen: set[str] = set()
    substring_candidates: list[str] = []  # Patterns to check with substring matching
    
    for pattern in patterns:
        normalized_pattern = _normalize_text(pattern)
        if not normalized_pattern:
            continue
        
        phrase_tokens = normalized_pattern.split()
        
        # Skip single generic words to avoid false positives
        if len(phrase_tokens) == 1 and phrase_tokens[0] in GENERIC_SINGLE_WORD_PATTERNS:
            continue
        
        # Try word-boundary matching
        if _phrase_in_text(normalized_text, normalized_pattern):
            if pattern not in seen:
                word_boundary_matches.append(pattern)
                seen.add(pattern)
        elif len(phrase_tokens) > 1:
            # This is a multi-word pattern that didn't match via word boundary
            # Save it as a candidate for substring matching
            substring_candidates.append(pattern)
    
    # If we found any word-boundary matches, return them (primary strategy succeeded)
    if word_boundary_matches:
        return word_boundary_matches
    
    # Second pass: try substring matching for multi-word patterns (fallback)
    # Only reach here if NO word-boundary matches were found
    normalized_for_substring = normalize_for_substring_match(text)
    substring_matches: list[str] = []
    
    for pattern in substring_candidates:
        pattern_for_substring = normalize_for_substring_match(pattern)
        if pattern_for_substring and pattern_for_substring in normalized_for_substring:
            if pattern not in seen:
                substring_matches.append(pattern)
                seen.add(pattern)
    
    return substring_matches


def infer_tags_from_name(name: str) -> set[str]:
    inferred: set[str] = set()
    for rule in INFERRED_TAG_RULES:
        if match_forbidden(name, rule["keywords"], allowlist=INJURY_MATCH_ALLOWLIST):
            if "max_velocity" in rule["tags"] and not _should_apply_max_velocity(name):
                continue
            inferred.update(rule["tags"])
    inferred.update(_infer_mechanism_tags_from_name(name))
    return {t for t in normalize_tags(inferred) if t}


def _should_apply_max_velocity(name: str) -> bool:
    if match_forbidden(name, MAX_VELOCITY_EXCLUDE_KEYWORDS, allowlist=INJURY_MATCH_ALLOWLIST):
        return False
    return bool(match_forbidden(name, MAX_VELOCITY_RUNNING_KEYWORDS, allowlist=INJURY_MATCH_ALLOWLIST))


def auto_tag(item: dict) -> set[str]:
    name = str(item.get("name", "") or "")
    purpose = str(item.get("purpose", "") or "")
    equipment = item.get("equipment", "")
    if isinstance(equipment, (list, tuple, set)):
        equipment_text = " ".join(str(e) for e in equipment if e)
    else:
        equipment_text = str(equipment or "")
    fields_text = " ".join([name, purpose, equipment_text])
    tags: set[str] = set(infer_tags_from_name(name))
    for rule in AUTO_TAG_RULES:
        if match_forbidden(fields_text, rule["keywords"], allowlist=INJURY_MATCH_ALLOWLIST):
            tags.update(rule["tags"])
    return {tag for tag in normalize_tags(tags) if tag}


def ensure_tags(item: dict) -> list[str]:
    # If already processed, return existing tags
    if "_tag_source" in item:
        return item.get("tags", [])
    
    raw_tags = normalize_tags([t for t in item.get("tags", []) if t])
    if raw_tags:
        name = str(item.get("name", "") or "")
        mech_tags = _infer_mechanism_tags_from_name(name)
        if mech_tags:
            raw_tags = normalize_tags([*raw_tags, *mech_tags])
        item["tags"] = raw_tags
        item["_tag_source"] = "explicit"
        return raw_tags

    inferred = sorted(auto_tag(item))
    if not inferred:
        inferred = ["untagged"]

    item["tags"] = inferred
    item["_tag_source"] = "inferred"
    return inferred


def _map_text_to_region(text: str) -> str | None:
    for region, keywords in INJURY_REGION_KEYWORDS.items():
        if match_forbidden(text, keywords, allowlist=INJURY_MATCH_ALLOWLIST):
            return region
    return None


def normalize_injury_regions(injuries: Iterable[str]) -> set[str]:
    regions: set[str] = set()
    for injury in injuries:
        if not injury:
            continue
        normalized = _normalize_text(injury)
        direct_key = normalized.replace(" ", "_")
        if direct_key in INJURY_RULES:
            regions.add(direct_key)
            continue
        matched = False
        non_negated_phrases: list[str] = []
        for phrase in split_injury_text(injury):
            cleaned = remove_negated_phrases(phrase)
            if not cleaned:
                continue
            non_negated_phrases.append(phrase)
            injury_type, location = parse_injury_phrase(phrase)
            for candidate in (location, injury_type, phrase):
                if not candidate:
                    continue
                region = _map_text_to_region(candidate)
                if region:
                    regions.add(region)
                    matched = True
                    break
            if matched:
                break
        if not matched and non_negated_phrases:
            for phrase in non_negated_phrases:
                region = _map_text_to_region(phrase)
                if region:
                    regions.add(region)
                    matched = True
                    break
        if not matched and non_negated_phrases:
            if any(_looks_like_constraint_phrase(phrase) for phrase in non_negated_phrases):
                continue
            regions.add("unspecified")
    return regions


def _looks_like_constraint_phrase(phrase: str) -> bool:
    normalized = _normalize_text(phrase)
    if not normalized:
        return False
    tokens = set(normalized.split())
    if tokens & CONSTRAINT_KEYWORDS:
        return True
    if tokens & CONSTRAINT_INTENSITY_WORDS and tokens & CONSTRAINT_MOVEMENT_WORDS:
        return True
    return False


def injury_violation_reasons(item: dict, injuries: Iterable[str]) -> list[str]:
    reasons: set[str] = set()
    for detail in injury_match_details(item, injuries, risk_levels=("exclude",)):
        region = detail["region"]
        for keyword in detail["patterns"]:
            reasons.add(f"{region}:keyword:{_normalize_text(keyword)}")
        for tag in detail["tags"]:
            reasons.add(f"{region}:tag:{tag}")
    return sorted(reasons)


def is_injury_safe(item: dict, injuries: Iterable[str]) -> bool:
    return not injury_violation_reasons(item, injuries)


def injury_violation_reasons_with_fields(
    item: dict,
    injuries: Iterable[str],
    *,
    fields: Iterable[str] | None = None,
) -> list[str]:
    reasons: set[str] = set()
    for detail in injury_match_details(item, injuries, fields=fields, risk_levels=("exclude",)):
        region = detail["region"]
        for keyword in detail["patterns"]:
            reasons.add(f"{region}:keyword:{_normalize_text(keyword)}")
        for tag in detail["tags"]:
            reasons.add(f"{region}:tag:{tag}")
    return sorted(reasons)


def injury_flag_reasons(item: dict, injuries: Iterable[str]) -> list[str]:
    reasons: set[str] = set()
    for detail in injury_match_details(item, injuries, risk_levels=("flag",)):
        region = detail["region"]
        for keyword in detail["patterns"]:
            reasons.add(f"{region}:keyword:{_normalize_text(keyword)}")
        for tag in detail["tags"]:
            reasons.add(f"{region}:tag:{tag}")
    return sorted(reasons)


def is_injury_safe_with_fields(
    item: dict,
    injuries: Iterable[str],
    *,
    fields: Iterable[str] | None = None,
) -> bool:
    return not injury_violation_reasons_with_fields(
        item, injuries, fields=fields
    )


def filter_items_for_injuries(items: Iterable[dict], injuries: Iterable[str]) -> list[dict]:
    return [item for item in items if is_injury_safe(item, injuries)]


def injury_match_details(
    item: dict,
    injuries: Iterable[str],
    *,
    fields: Iterable[str] | None = None,
    risk_levels: Iterable[str] | None = None,
) -> list[dict]:
    if not injuries:
        return []
    fields = fields or ("name",)
    risk_levels = set(risk_levels or ("exclude",))
    field_values = {field: str(item.get(field, "") or "") for field in fields}
    name = field_values.get("name", "")
    tags = set(ensure_tags(item))
    tag_source = item.get("_tag_source", "explicit")
    tags |= infer_tags_from_name(name)
    expanded = expand_injury_tags(tags, item=item)
    tags_for_matching = tags | expanded
    if "low_impact" in tags_for_matching:
        tags_for_matching.discard("running_volume_high")
    reasons: list[dict] = []
    module = _module_for_item(item)
    allow_keyword_match = module in {"strength", "conditioning"}
    for region in normalize_injury_regions(injuries):
        rules = INJURY_RULES.get(region, {})
        for risk_level in ("exclude", "flag"):
            if risk_level not in risk_levels:
                continue
            patterns = rules.get(f"{risk_level}_keywords", rules.get("ban_keywords", []) if risk_level == "exclude" else [])
            risk_tags = {t.lower() for t in rules.get(f"{risk_level}_tags", rules.get("ban_tags", []) if risk_level == "exclude" else [])}
            tag_hits_raw = sorted(tags_for_matching & risk_tags)
            # Only allow explicit tags to trigger exclusion, except mech_* tags
            if tag_source == "explicit":
                tag_hits = tag_hits_raw
            else:
                tag_hits = [tag for tag in tag_hits_raw if tag.startswith("mech_")]
            field_hits: dict[str, list[str]] = {}
            matched_patterns: set[str] = set()
            if not tag_hits and allow_keyword_match:
                for field_name, value in field_values.items():
                    matches = match_forbidden(value, patterns, allowlist=INJURY_MATCH_ALLOWLIST)
                    if matches:
                        field_hits[field_name] = matches
                        matched_patterns.update(matches)
                        # Log exclusion for each matched ban_keyword
                        for matched_pattern in matches:
                            logger.info(
                                "[injury-exclusion] Excluding '%s' for %s injury: ban_keyword '%s' found in %s='%s'",
                                name,
                                region,
                                matched_pattern,
                                field_name,
                                value,
                            )
            if field_hits or tag_hits:
                reasons.append(
                    {
                        "region": region,
                        "fields": sorted(field_hits),
                        "patterns": sorted(matched_patterns),
                        "tags": tag_hits,
                        "risk_level": risk_level,
                    }
                )
    return reasons


def _load_style_specific_exercises() -> list[dict]:
    paths = [
        DATA_DIR / "style_specific_exercises.json",
        DATA_DIR / "style_specific_exercises",
    ]
    for path in paths:
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(
                "style_specific_exercises JSON error in "
                f"{path}: line {exc.lineno} column {exc.colno} ({exc.msg})"
            ) from exc
        if not isinstance(items, list):
            raise ValueError(
                "style_specific_exercises must be a JSON list of exercise objects. "
                f"Check {path}."
            )
        for item in items:
            validate_training_item(item, source=str(path), require_phases=True)
            normalize_item_tags(item)
        return items
    logger.warning(
        "[bank] style_specific_exercises missing. Add data/style_specific_exercises.json "
        "or data/style_specific_exercises to enable style-specific lifts."
    )
    return []


def _load_bank_items(filename: str) -> list[dict]:
    items = json.loads((DATA_DIR / filename).read_text())
    for item in items:
        validate_training_item(item, source=filename, require_phases=True)
        normalize_item_tags(item)
    return items


def collect_banks() -> dict[str, list[dict]]:
    banks: dict[str, list[dict]] = {}
    banks["exercise_bank"] = _load_bank_items("exercise_bank.json")
    banks["conditioning_bank"] = _load_bank_items("conditioning_bank.json")
    banks["style_conditioning_bank"] = _load_bank_items("style_conditioning_bank.json")
    banks["universal_gpp_strength"] = _load_bank_items("universal_gpp_strength.json")
    banks["universal_gpp_conditioning"] = _load_bank_items("universal_gpp_conditioning.json")
    banks["style_taper_conditioning"] = _load_bank_items("style_taper_conditioning.json")
    banks["style_specific_exercises"] = _load_style_specific_exercises()

    coord_data = json.loads((DATA_DIR / "coordination_bank.json").read_text())
    coordination_bank: list[dict] = []
    if isinstance(coord_data, list):
        for item in coord_data:
            validate_training_item(item, source="coordination_bank.json", require_phases=True)
            normalize_item_tags(item)
            coordination_bank.append(item)
    elif isinstance(coord_data, dict):
        for val in coord_data.values():
            if isinstance(val, list):
                for item in val:
                    validate_training_item(item, source="coordination_bank.json", require_phases=True)
                    normalize_item_tags(item)
                    coordination_bank.append(item)
    banks["coordination_bank"] = coordination_bank

    return banks


def build_bank_inferred_tags() -> list[dict]:
    entries: list[dict] = []
    for bank_name, items in collect_banks().items():
        for item in items:
            name = item.get("name", "")
            item_id = f"{bank_name}:{name}"
            explicit_tags = normalize_tags(item.get("tags", []))
            normalized_tags = ensure_tags(item)
            inferred_tags = sorted(infer_tags_from_name(name))
            entries.append(
                {
                    "item_id": item_id,
                    "bank": bank_name,
                    "name": name,
                    "explicit_tags": explicit_tags or normalized_tags,
                    "inferred_tags": inferred_tags,
                }
            )
    return entries


def build_injury_exclusion_map() -> dict[str, list[str]]:
    exclusions = {region: [] for region in INJURY_RULES}
    for bank_name, items in collect_banks().items():
        for item in items:
            name = item.get("name", "")
            item_id = f"{bank_name}:{name}"
            tags = set(ensure_tags(item))
            tags |= infer_tags_from_name(name)
            tags |= expand_injury_tags(tags, item=item)
            for region, rule in INJURY_RULES.items():
                ban_keywords = rule.get("exclude_keywords", rule.get("ban_keywords", []))
                ban_tags = {t.lower() for t in rule.get("exclude_tags", rule.get("ban_tags", []))}
                if match_forbidden(name, ban_keywords, allowlist=INJURY_MATCH_ALLOWLIST) or tags & ban_tags:
                    exclusions[region].append(item_id)
    for region in exclusions:
        exclusions[region] = sorted(set(exclusions[region]))
    return exclusions


def audit_missing_tags() -> dict[str, int]:
    counts: dict[str, int] = {}
    total = 0
    for bank_name, items in collect_banks().items():
        missing = 0
        for item in items:
            raw_tags = [t for t in item.get("tags", []) if t]
            if not raw_tags:
                missing += 1
                total += 1
        counts[bank_name] = missing
    counts["total"] = total
    return counts


def write_injury_exclusion_files(output_dir: Path | None = None) -> None:
    output_dir = output_dir or DATA_DIR
    inferred_path = output_dir / "bank_inferred_tags.json"
    exclusion_path = output_dir / "injury_exclusion_map.json"

    inferred = build_bank_inferred_tags()
    exclusion_map = build_injury_exclusion_map()

    inferred_path.write_text(json.dumps(inferred, indent=2, sort_keys=True))
    exclusion_path.write_text(json.dumps(exclusion_map, indent=2, sort_keys=True))


def log_injury_debug(items: Iterable[dict], injuries: Iterable[str], *, label: str) -> None:
    """
    DEPRECATED: This function is kept for backward compatibility but does nothing.
    Use _log_exclusion() instead for logging excluded items only.
    """
    pass
