from __future__ import annotations

import re

_SEVERITY_HINTS = {
    "mild": {"mild", "minor", "light", "low"},
    "moderate": {"moderate", "medium"},
    "severe": {"severe", "serious", "high"},
}

INJURY_TYPE_SEVERITY = {
    "tightness": "mild",
    "soreness": "mild",
    "stiffness": "mild",
    "pain": "mild",
    "contusion": "mild",
    "sprain": "moderate",
    "strain": "moderate",
    "tendonitis": "moderate",
    "impingement": "moderate",
    "hyperextension": "moderate",
    "swelling": "severe",
    "instability": "severe",
    "unspecified": "moderate",
}


def detect_severity_hint(text: str | None) -> str | None:
    if not text:
        return None
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = set(normalized.split())
    for severity, hints in _SEVERITY_HINTS.items():
        if tokens.intersection(hints):
            return severity
    return None


def resolve_injury_severity(injury_type: str | None, text: str | None = None) -> str:
    hint = detect_severity_hint(text)
    if hint:
        return hint
    return INJURY_TYPE_SEVERITY.get(injury_type or "", "moderate")
