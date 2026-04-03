from __future__ import annotations

import logging
import re
from typing import Mapping

from . import injury_synonyms
from .injury_synonyms import parse_injury_phrase, split_injury_text
from .normalization import normalize_lower_text, strip_surrounding_punctuation as _strip_surrounding_punct
from .restriction_parsing import ParsedRestriction, parse_restriction_entry, is_restriction_phrase

logger = logging.getLogger(__name__)

_LATERALITY_PATTERN = re.compile(r"\b(left|right)\b", re.IGNORECASE)
_RESTRICTION_SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.!?;\n]+")
_LIST_SPLIT_PATTERN = re.compile(r"\s*,\s*|\s+\band\b\s+", re.IGNORECASE)
_LEADING_RESTRICTION_TRIGGERS = (
    "do not",
    "don't",
    "dont",
    "cannot",
    "can't",
    "cant",
    "avoid",
    "limit",
    "reduce",
    "skip",
    "no",
)
_LEADING_RESTRICTION_TRIGGER_PATTERN = re.compile(
    r"^\s*(?P<trigger>"
    + "|".join(re.escape(trigger) for trigger in _LEADING_RESTRICTION_TRIGGERS)
    + r")(?=\b|:)\s*:?\s*(?P<remainder>.+?)\s*$",
    re.IGNORECASE,
)


def _title_case(value: str) -> str:
    return " ".join(word.capitalize() for word in value.split())


def extract_laterality(text: str) -> str | None:
    if not text:
        return None
    match = _LATERALITY_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).lower()


def _strip_display_laterality(display_location: str, laterality: str | None) -> str:
    cleaned = str(display_location or "").strip()
    if not cleaned or not laterality:
        return cleaned
    return re.sub(rf"^\s*{re.escape(laterality)}\s+", "", cleaned, count=1, flags=re.IGNORECASE).strip() or cleaned


def _split_restriction_sentences(text: str) -> list[str]:
    return [
        cleaned
        for chunk in _RESTRICTION_SENTENCE_BOUNDARY_PATTERN.split(text)
        if (cleaned := chunk.strip())
    ]


def _expand_triggered_restriction_clause(clause: str) -> list[str]:
    normalized_clause = normalize_lower_text(clause)
    if not normalized_clause:
        return []

    match = _LEADING_RESTRICTION_TRIGGER_PATTERN.match(normalized_clause)
    if not match:
        return []

    trigger = match.group("trigger").lower()
    remainder = re.sub(r",\s+and\s+", ", ", match.group("remainder"), flags=re.IGNORECASE)
    items = [
        cleaned
        for raw_item in _LIST_SPLIT_PATTERN.split(remainder)
        if (
            cleaned := _strip_surrounding_punct(
                re.sub(
                    rf"^\s*{re.escape(trigger)}(?=\b|:)\s*:?\s*",
                    "",
                    raw_item.strip(),
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
        )
    ]
    if not items:
        return []

    return [f"{trigger} {item}" for item in items]


def parse_injury_entry(phrase: str) -> dict[str, str | None] | None:
    """Parse a single injury phrase.
    
    This function filters out constraint phrases and only returns injury data.
    For full separation of injuries and constraints, use parse_injuries_and_restrictions().
    
    Args:
        phrase: A single injury phrase
        
    Returns:
        Dict with injury data, or None if not an injury (e.g., if it's a constraint)
    """
    original_phrase = str(phrase or "").strip()
    if not original_phrase:
        return None

    phrase_to_parse = original_phrase
    if injury_synonyms.contains_negated_injury(original_phrase) and not injury_synonyms.negation_detection_available():
        phrase_to_parse = injury_synonyms.remove_negated_phrases(original_phrase)
        if not phrase_to_parse:
            return None

    # Filter out constraint phrases after fallback negation cleanup so mixed
    # inputs like "no shoulder pain - knee soreness" still yield the active injury.
    if is_restriction_phrase(phrase_to_parse):
        return None

    injury_type, location = parse_injury_phrase(phrase_to_parse)
    laterality = extract_laterality(original_phrase)
    if not injury_type and not location:
        return None
    if not injury_type and location:
        injury_type = "unspecified"
    return {
        "injury_type": injury_type,
        "canonical_location": location,
        "side": laterality,
        "laterality": laterality,
        "original_phrase": original_phrase,
    }


def parse_injuries_and_restrictions(text: str) -> tuple[list[dict[str, str | None]], list[ParsedRestriction]]:
    """Parse injury text into separate lists of injuries and restrictions.
    
    This is the main entry point that properly separates constraint phrases
    from actual injury descriptions.
    
    Args:
        text: Raw injury/constraint text from user input
        
    Returns:
        Tuple of (injuries, restrictions) where:
        - injuries: List of injury dicts (legacy format)
        - restrictions: List of ParsedRestriction objects
    """
    injuries: list[dict[str, str | None]] = []
    restrictions: list[ParsedRestriction] = []
    
    if not text:
        return injuries, restrictions
    
    for sentence in _split_restriction_sentences(text):
        inherited_restriction_phrases = _expand_triggered_restriction_clause(sentence)
        if inherited_restriction_phrases:
            for phrase in inherited_restriction_phrases:
                restriction = parse_restriction_entry(phrase)
                if restriction is not None:
                    logger.info(f"[restriction-parse] parsed={restriction!r}")
                    restrictions.append(restriction)
            continue

        for phrase in split_injury_text(sentence):
            # Try to parse as restriction first
            restriction = parse_restriction_entry(phrase)
            if restriction is not None:
                logger.info(f"[restriction-parse] parsed={restriction!r}")
                restrictions.append(restriction)
                continue

            # Otherwise, parse as injury (legacy behavior)
            injury = parse_injury_entry(phrase)
            if injury is not None:
                injuries.append(injury)
    
    # Log the complete list of restrictions after parsing finishes
    logger.info(f"[restriction-parse] total restrictions parsed: {len(restrictions)}")
    
    return injuries, restrictions


def format_injury_summary(injury_obj: Mapping[str, str | None]) -> str:
    canonical_location = injury_obj.get("canonical_location")
    laterality = injury_obj.get("side") or injury_obj.get("laterality")
    injury_type = injury_obj.get("injury_type")
    severity = injury_obj.get("severity")
    display_location = _strip_display_laterality(
        str(injury_obj.get("display_location") or "").strip(),
        laterality,
    )

    if display_location:
        location_label = _title_case(display_location)
    else:
        location_label = _title_case(canonical_location) if canonical_location else "Unspecified Location"
    if laterality:
        location_label = f"{_title_case(laterality)} {location_label}"

    injury_label = _title_case(injury_type) if injury_type else "Unspecified"
    severity_label = _title_case(severity) if severity else "Unspecified"

    return f"{location_label} — {injury_label} (Severity: {severity_label})"


def format_restriction_summary(restriction: ParsedRestriction) -> str:
    """Format a ParsedRestriction into a human-readable summary.
    
    Args:
        restriction: ParsedRestriction object
        
    Returns:
        Formatted string like "Knee — Deep Knee Flexion (Strength: Avoid)"
    """
    region = restriction.get("region")
    side = restriction.get("side")
    restriction_name = restriction.get("restriction", "")
    strength = restriction.get("strength", "unspecified")
    
    # Format region
    if region:
        region_label = _title_case(region)
        if side:
            region_label = f"{_title_case(side)} {region_label}"
    else:
        region_label = "Unspecified Region"
    
    # Format restriction name (convert underscores to spaces)
    restriction_label = _title_case(restriction_name.replace("_", " "))
    
    # Format strength
    strength_label = _title_case(strength)
    
    return f"{region_label} — {restriction_label} (Strength: {strength_label})"


_RESTRICTION_GUARDRAIL_DETAILS = {
    "deep_knee_flexion": ("deep loaded knee flexion", "deep squat/lunge patterns"),
    "deep_hip_flexion": ("deep hip flexion", "loaded pike/tuck/knee-drive patterns"),
    "heavy_overhead_pressing": ("heavy overhead pressing", "overhead press/jerk/thruster/overhead slams"),
    "high_impact": ("high impact", "jumping/plyo/impact running"),
    "high_impact_lower": ("high impact (lower)", "jumping/plyo/bounds/landing drills"),
    "high_impact_upper": ("high impact (upper)", "clap/plyo push-ups and explosive pressing"),
    "high_impact_global": ("high impact", "jumping/plyo/impact running"),
    "loaded_flexion": ("loaded flexion", "weighted sit-ups/loaded crunches"),
    "max_velocity": ("max velocity sprinting", "max sprints/overspeed work"),
}


def format_restriction_guardrail(restriction: ParsedRestriction) -> str:
    """Format a ParsedRestriction into a guardrail line for plan output."""
    region = restriction.get("region")
    side = restriction.get("side")
    restriction_key = restriction.get("restriction", "")
    strength = restriction.get("strength", "avoid")

    if region:
        region_label = _title_case(region)
        if side:
            region_label = f"{_title_case(side)} {region_label}"
    else:
        region_label = "General"

    strength_label = _title_case(strength)
    detail = _RESTRICTION_GUARDRAIL_DETAILS.get(restriction_key)
    if detail:
        label, examples = detail
        return f"{region_label}: {strength_label} {label} ({examples})"

    restriction_label = _title_case(restriction_key.replace("_", " ")) or "Activity modifications"
    return f"{region_label}: {strength_label} {restriction_label}"
