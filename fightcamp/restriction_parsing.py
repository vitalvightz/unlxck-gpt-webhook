from __future__ import annotations

import re
from typing import TypedDict

from .injury_synonyms import parse_injury_phrase


# Minimum number of keyword matches required to confidently identify a canonical restriction
# This threshold prevents false positives from single-word matches
MIN_KEYWORD_MATCHES = 2


class ParsedRestriction(TypedDict, total=False):
    """Model for parsed physical restrictions/constraints.
    
    Fields:
        restriction: Canonical restriction key (e.g., "deep_knee_flexion", "heavy_overhead_pressing")
        region: Anatomical region affected (e.g., "knee", "shoulder")
        strength: Intensity of the restriction ("avoid", "limit", "reduce") - NOT severity
        side: Laterality if specified ("left", "right")
        original_phrase: The original text phrase
    """
    restriction: str
    region: str | None
    strength: str
    side: str | None
    original_phrase: str


# Trigger tokens that indicate a constraint/restriction rather than an injury
CONSTRAINT_TRIGGER_TOKENS = {
    "avoid",
    "no",
    "not",
    "don't",
    "dont",
    "do not",
    "cannot",
    "can't",
    "cant",
    "limit",
    "limited",
    "restricted",
    "restriction",
    "not comfortable",
    "flare",
    "flares",
    "contraindicated",
    "skip",
    "reduce",
    "irritates",
    "aggravates",
}

# Canonical restriction mappings for common phrases
CANONICAL_RESTRICTIONS = {
    "deep knee flexion": {
        "restriction": "deep_knee_flexion",
        "region": "knee",
        "keywords": ["deep", "knee", "flexion", "squat", "depth"],
    },
    "heavy overhead pressing": {
        "restriction": "heavy_overhead_pressing",
        "region": "shoulder",
        "keywords": ["heavy", "overhead", "press", "pressing"],
    },
    "high impact": {
        "restriction": "high_impact",
        "region": None,
        "keywords": ["high", "impact", "jump", "jumping", "plyo"],
    },
    "loaded flexion": {
        "restriction": "loaded_flexion",
        "region": None,
        "keywords": ["loaded", "flexion", "under load"],
    },
    "max velocity": {
        "restriction": "max_velocity",
        "region": None,
        "keywords": ["max", "velocity", "sprint", "sprinting"],
    },
}

_LATERALITY_PATTERN = re.compile(r"\b(left|right)\b", re.IGNORECASE)


def _extract_laterality(text: str) -> str | None:
    """Extract laterality (left/right) from text."""
    if not text:
        return None
    match = _LATERALITY_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).lower()


def _normalize_text(text: str) -> str:
    """Normalize text for matching."""
    return text.lower().strip()


def _contains_trigger_token(text: str) -> bool:
    """Check if text contains any constraint trigger token."""
    normalized = _normalize_text(text)
    
    # Check for multi-word triggers first
    for trigger in ["do not", "not comfortable", "hurts when"]:
        if trigger in normalized:
            return True
    
    # Check single-word triggers
    tokens = set(normalized.split())
    return bool(tokens & CONSTRAINT_TRIGGER_TOKENS)


def is_restriction_phrase(text: str) -> bool:
    """Check whether a phrase should be treated as a restriction."""
    if not text:
        return False
    if _contains_trigger_token(text):
        return True
    restriction_key, _ = _match_canonical_restriction(text)
    if not restriction_key:
        return False
    injury_type, _ = parse_injury_phrase(text)
    return injury_type is None


def _infer_restriction_strength(text: str) -> str:
    """Infer the strength/intensity of the restriction from trigger words."""
    normalized = _normalize_text(text)
    
    # Use word boundaries for "no" to avoid matching "no" in other words
    # Check for "no" as standalone word using token set
    tokens = set(normalized.split())
    
    if any(word in normalized for word in ["avoid", "do not", "don't", "dont", "not comfortable"]):
        return "avoid"
    elif "no" in tokens:  # Check "no" as standalone token
        return "avoid"
    elif any(word in normalized for word in ["limit", "limited", "restricted", "restriction", "reduce"]):
        return "limit"
    elif any(word in normalized for word in ["flare", "flares"]):
        return "flare"
    
    return "avoid"  # default


def _match_canonical_restriction(text: str) -> tuple[str | None, str | None]:
    """Match text against canonical restrictions.
    
    Returns:
        Tuple of (restriction_key, region) or (None, None) if no match.
    """
    normalized = _normalize_text(text)
    tokens = set(normalized.split())
    
    best_match = None
    best_score = 0
    
    for restriction_name, restriction_data in CANONICAL_RESTRICTIONS.items():
        keywords = restriction_data["keywords"]
        matches = sum(1 for keyword in keywords if keyword in normalized or keyword in tokens)
        
        if matches > best_score:
            best_score = matches
            best_match = (restriction_data["restriction"], restriction_data["region"])
    
    # Require at least MIN_KEYWORD_MATCHES for confidence to avoid false positives
    if best_score >= MIN_KEYWORD_MATCHES:
        return best_match
    
    return None, None


def _infer_region_from_text(text: str) -> str | None:
    """Infer anatomical region from text if not matched canonically."""
    normalized = _normalize_text(text)
    
    # Simple keyword matching for common regions
    region_keywords = {
        "knee": ["knee", "knees"],
        "shoulder": ["shoulder", "shoulders"],
        "ankle": ["ankle", "ankles"],
        "hip": ["hip", "hips"],
        "back": ["back", "spine", "lumbar"],
        "wrist": ["wrist", "wrists"],
        "elbow": ["elbow", "elbows"],
    }
    
    for region, keywords in region_keywords.items():
        if any(keyword in normalized for keyword in keywords):
            return region
    
    return None


def parse_restriction_entry(phrase: str) -> ParsedRestriction | None:
    """Parse a constraint/restriction phrase into structured data.
    
    Args:
        phrase: Text phrase potentially describing a restriction
        
    Returns:
        ParsedRestriction dict if phrase is a constraint, None otherwise
    """
    if not phrase:
        return None
    
    # Check if this looks like a constraint
    if not is_restriction_phrase(phrase):
        return None
    
    # Try to match against canonical restrictions
    restriction_key, region = _match_canonical_restriction(phrase)
    
    # If no canonical match, create generic restriction
    if not restriction_key:
        restriction_key = "generic_constraint"
        region = _infer_region_from_text(phrase)
    
    # Extract laterality
    laterality = _extract_laterality(phrase)
    
    # Determine strength
    strength = _infer_restriction_strength(phrase)
    
    return ParsedRestriction(
        restriction=restriction_key,
        region=region,
        strength=strength,
        side=laterality,
        original_phrase=phrase,
    )
