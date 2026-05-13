from __future__ import annotations

import re


_DANGER_TERMS: tuple[dict[str, str], ...] = (
    {"phrase": "cannot bear weight", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "can't bear weight", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "cant bear weight", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "unable to bear weight", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "not able to bear weight", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "can't walk", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "cant walk", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "unable to walk", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "not able to walk", "signal": "cannot_bear_weight", "route": "restricted_rehab_only"},
    {"phrase": "giving way", "signal": "instability_event", "route": "restricted_rehab_only"},
    {"phrase": "buckled", "signal": "instability_event", "route": "restricted_rehab_only"},
    {"phrase": "rupture", "signal": "structural_severe_signal", "route": "restricted_rehab_only"},
    {"phrase": "ruptured", "signal": "structural_severe_signal", "route": "restricted_rehab_only"},
    {"phrase": "avulsion", "signal": "structural_severe_signal", "route": "restricted_rehab_only"},
)


def detect_danger_terms(cleaned: str) -> list[dict[str, str]]:
    lowered = str(cleaned or "").lower()
    if not lowered:
        return []

    matches: list[dict[str, str]] = []
    for item in _DANGER_TERMS:
        phrase = item["phrase"]
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered):
            matches.append(item)
    return matches

