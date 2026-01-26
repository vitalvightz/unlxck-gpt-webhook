from __future__ import annotations

import logging
import re
from typing import Mapping

from .injury_synonyms import parse_injury_phrase, split_injury_text
from .restriction_parsing import ParsedRestriction, parse_restriction_entry, _contains_trigger_token

logger = logging.getLogger(__name__)

_LATERALITY_PATTERN = re.compile(r"\b(left|right)\b", re.IGNORECASE)


def _title_case(value: str) -> str:
    return " ".join(word.capitalize() for word in value.split())


def extract_laterality(text: str) -> str | None:
    if not text:
        return None
    match = _LATERALITY_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).lower()


def parse_injury_entry(phrase: str) -> dict[str, str | None] | None:
    """Parse a single injury phrase.
    
    This function filters out constraint phrases and only returns injury data.
    For full separation of injuries and constraints, use parse_injuries_and_restrictions().
    
    Args:
        phrase: A single injury phrase
        
    Returns:
        Dict with injury data, or None if not an injury (e.g., if it's a constraint)
    """
    # Filter out constraint phrases first
    if _contains_trigger_token(phrase):
        return None
    
    injury_type, location = parse_injury_phrase(phrase)
    laterality = extract_laterality(phrase)
    if not injury_type and not location:
        return None
    if not injury_type and location:
        injury_type = "unspecified"
    return {
        "injury_type": injury_type,
        "canonical_location": location,
        "side": laterality,
        "laterality": laterality,
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
    
    # Split into phrases
    phrases = split_injury_text(text)
    
    for phrase in phrases:
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
