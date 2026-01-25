from __future__ import annotations

import re
from typing import Mapping

from .injury_synonyms import parse_injury_phrase

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
