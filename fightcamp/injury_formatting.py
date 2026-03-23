from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Mapping

from .injury_synonyms import parse_injury_phrase, split_injury_text
from .restriction_parsing import ParsedRestriction, parse_restriction_entry, is_restriction_phrase

logger = logging.getLogger(__name__)

_LATERALITY_PATTERN = re.compile(r"\b(left|right)\b", re.IGNORECASE)
_GUIDED_SEVERITY_PATTERN = r"mild|moderate|severe"
_GUIDED_TREND_PATTERN = r"improving|stable|worsening"
_GUIDED_FUNCTIONAL_IMPACT_PATTERN = (
    r"can train fully|can train with modifications|cannot do key movements properly"
)
_GUIDED_HEADER_LOOKAHEAD = (
    rf"[^;]+?\s*(?:-|–|—)\s*(?:{_GUIDED_SEVERITY_PATTERN})\s*,\s*"
    rf"(?:{_GUIDED_TREND_PATTERN})\s*,\s*(?:{_GUIDED_FUNCTIONAL_IMPACT_PATTERN})"
)
_GUIDED_ENTRY_SPLIT_PATTERN = re.compile(rf"\s*;\s*(?={_GUIDED_HEADER_LOOKAHEAD})", re.IGNORECASE)
_GUIDED_SEGMENT_PATTERN = re.compile(
    r"^(?P<header>.*?)(?:\.\s*Avoid:\s*(?P<avoid>.*?))?(?:\.\s*Notes:\s*(?P<notes>.*))?$",
    re.IGNORECASE | re.DOTALL,
)
_GUIDED_HEADER_PATTERN = re.compile(
    rf"^(?P<area>.+?)\s*(?:-|–|—)\s*(?P<severity>{_GUIDED_SEVERITY_PATTERN})\s*,\s*"
    rf"(?P<trend>{_GUIDED_TREND_PATTERN})\s*,\s*"
    rf"(?P<functional_impact>{_GUIDED_FUNCTIONAL_IMPACT_PATTERN})\s*$",
    re.IGNORECASE,
)

_EXPLICIT_INJURY_SIGNAL_PATTERN = re.compile(
    r"\b(?:pain|painful|hurt|hurting|ache|aching|sore|soreness|strain|strained|sprain|sprained|"
    r"tear|torn|tight|tightness|stiff|stiffness|swelling|swollen|contusion|bruise|"
    r"impingement|instability|tendonitis|tendinitis|tendinopathy|hyperextension|hyperextend)\b",
    re.IGNORECASE,
)
_GUIDED_AGGRAVATOR_RESTRICTIONS: dict[str, dict[str, str | None]] = {
    "sprinting": {"restriction": "high_impact_lower", "region": None, "strength": "avoid"},
    "jumping": {"restriction": "high_impact_lower", "region": None, "strength": "avoid"},
    "deep hip flexion": {"restriction": "generic_constraint", "region": "hip", "strength": "avoid"},
    "hard rotation": {"restriction": "generic_constraint", "region": None, "strength": "avoid"},
    "lateral cutting": {"restriction": "generic_constraint", "region": None, "strength": "avoid"},
    "overhead pressing": {"restriction": "heavy_overhead_pressing", "region": "shoulder", "strength": "avoid"},
    "heavy hinging": {"restriction": "generic_constraint", "region": None, "strength": "avoid"},
    "impact/contact": {"restriction": "high_impact_global", "region": None, "strength": "avoid"},
    "clinching/grappling pressure": {"restriction": "generic_constraint", "region": None, "strength": "avoid"},
    "fast direction changes": {"restriction": "generic_constraint", "region": None, "strength": "avoid"},
    "prolonged stance/load": {"restriction": "generic_constraint", "region": None, "strength": "limit"},
}


@dataclass(frozen=True)
class GuidedInjurySummary:
    raw: str
    area: str
    severity: str
    trend: str
    functional_impact: str
    aggravators: list[str]
    notes: str


def _has_explicit_injury_signal(text: str) -> bool:
    return bool(_EXPLICIT_INJURY_SIGNAL_PATTERN.search(text or ""))


def _title_case(value: str) -> str:
    return " ".join(word.capitalize() for word in value.split())


def extract_laterality(text: str) -> str | None:
    if not text:
        return None
    match = _LATERALITY_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).lower()


def _split_guided_injury_segments(text: str) -> list[str]:
    if not text:
        return []
    return [
        segment.strip()
        for segment in _GUIDED_ENTRY_SPLIT_PATTERN.split(text.strip())
        if segment.strip()
    ]


def parse_guided_injury_summary(text: str) -> GuidedInjurySummary | None:
    if not text:
        return None
    match = _GUIDED_SEGMENT_PATTERN.match(text.strip())
    if not match:
        return None

    header = str(match.group("header") or "").strip().rstrip(".")
    header_match = _GUIDED_HEADER_PATTERN.match(header)
    if not header_match:
        return None

    avoid_text = str(match.group("avoid") or "").strip().rstrip(".")
    notes = str(match.group("notes") or "").strip()
    aggravators = [item.strip() for item in avoid_text.split(",") if item.strip()]

    return GuidedInjurySummary(
        raw=text.strip(),
        area=str(header_match.group("area") or "").strip(),
        severity=str(header_match.group("severity") or "").strip().lower(),
        trend=str(header_match.group("trend") or "").strip().lower(),
        functional_impact=str(header_match.group("functional_impact") or "").strip().lower(),
        aggravators=aggravators,
        notes=notes,
    )


def looks_like_guided_injury_text(text: str) -> bool:
    return any(
        parse_guided_injury_summary(segment) is not None
        for segment in _split_guided_injury_segments(text)
    )


def _infer_guided_location(*parts: str) -> str | None:
    combined = " ".join(part.strip() for part in parts if part and part.strip())
    if not combined:
        return None

    _, location = parse_injury_phrase(combined)
    if location:
        return location

    for phrase in split_injury_text(combined):
        _, phrase_location = parse_injury_phrase(phrase)
        if phrase_location:
            return phrase_location
    return None


def _build_guided_injury_entry(summary: GuidedInjurySummary) -> dict[str, str | None] | None:
    context = " ".join(part for part in [summary.area, summary.notes] if part).strip()
    injury_type, location = parse_injury_phrase(context)
    if not injury_type and not location:
        location = _infer_guided_location(summary.area, summary.notes)
    if not injury_type and location:
        injury_type = "unspecified"
    if not injury_type and not location:
        return None

    laterality = extract_laterality(summary.area or summary.notes or context)
    return {
        "injury_type": injury_type,
        "canonical_location": location,
        "side": laterality,
        "laterality": laterality,
        "severity": summary.severity,
        "trend": summary.trend,
        "functional_impact": summary.functional_impact,
        "original_phrase": summary.area or context,
    }


def _restriction_strength_from_summary(summary: GuidedInjurySummary) -> str:
    if summary.severity == "severe" or summary.functional_impact == "cannot do key movements properly":
        return "avoid"
    if summary.trend == "worsening":
        return "flare"
    return "limit"


def _apply_guided_area_context(
    restriction: ParsedRestriction,
    summary: GuidedInjurySummary,
) -> ParsedRestriction:
    region = restriction.get("region") or _infer_guided_location(summary.area, summary.notes)
    side = restriction.get("side") or extract_laterality(summary.area or summary.notes)
    if region:
        restriction["region"] = region
    if side:
        restriction["side"] = side
    return restriction


def _build_guided_restrictions(summary: GuidedInjurySummary) -> list[ParsedRestriction]:
    restrictions: list[ParsedRestriction] = []
    area_region = _infer_guided_location(summary.area, summary.notes)
    side = extract_laterality(summary.area or summary.notes)

    for aggravator in summary.aggravators:
        normalized_aggravator = aggravator.strip().lower()
        phrase = f"avoid {aggravator}"
        if summary.area:
            phrase = f"{phrase} for {summary.area}"
        mapped = _GUIDED_AGGRAVATOR_RESTRICTIONS.get(normalized_aggravator)
        if mapped is not None:
            restrictions.append(
                ParsedRestriction(
                    restriction=str(mapped.get("restriction") or "generic_constraint"),
                    region=area_region or mapped.get("region"),
                    strength=str(mapped.get("strength") or "avoid"),
                    side=side,
                    original_phrase=phrase,
                )
            )
            continue
        restriction = parse_restriction_entry(phrase)
        if restriction is not None:
            restrictions.append(_apply_guided_area_context(restriction, summary))

    if summary.notes and not restrictions:
        restrictions.append(
            ParsedRestriction(
                restriction="generic_constraint",
                region=area_region,
                strength=_restriction_strength_from_summary(summary),
                side=side,
                original_phrase=f"{summary.area}: {summary.notes}" if summary.area else summary.notes,
            )
        )

    return restrictions


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
    if is_restriction_phrase(phrase):
        return None
    
    injury_type, location = parse_injury_phrase(phrase)
    laterality = extract_laterality(phrase)
    if injury_type and not location and not _has_explicit_injury_signal(phrase):
        return None
    if not injury_type and not location:
        return None
    if not injury_type and location:
        injury_type = "unspecified"
    return {
        "injury_type": injury_type,
        "canonical_location": location,
        "side": laterality,
        "laterality": laterality,
        "original_phrase": phrase,
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
    
    segments = _split_guided_injury_segments(text) if looks_like_guided_injury_text(text) else [text]

    for segment in segments:
        guided_summary = parse_guided_injury_summary(segment)
        if guided_summary is not None:
            injury = _build_guided_injury_entry(guided_summary)
            if injury is not None:
                injuries.append(injury)

            for restriction in _build_guided_restrictions(guided_summary):
                logger.info(f"[restriction-parse] parsed={restriction!r}")
                restrictions.append(restriction)
            continue

        # Split into phrases
        phrases = split_injury_text(segment)

        previous_was_restriction = False
        for phrase in phrases:
            # Try to parse as restriction first
            restriction = parse_restriction_entry(phrase)
            if restriction is not None:
                logger.info(f"[restriction-parse] parsed={restriction!r}")
                restrictions.append(restriction)
                previous_was_restriction = True
                continue

            # Otherwise, parse as injury (legacy behavior)
            injury = parse_injury_entry(phrase)
            if injury is not None:
                injuries.append(injury)
                previous_was_restriction = False
                continue

            if previous_was_restriction:
                restriction = ParsedRestriction(
                    restriction="generic_constraint",
                    region=None,
                    strength="avoid",
                    side=extract_laterality(phrase),
                    original_phrase=phrase,
                )
                logger.info(f"[restriction-parse] parsed={restriction!r}")
                restrictions.append(restriction)
                previous_was_restriction = True
            else:
                previous_was_restriction = False
    
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


_RESTRICTION_GUARDRAIL_DETAILS = {
    "deep_knee_flexion": ("deep loaded knee flexion", "deep squat/lunge patterns"),
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
