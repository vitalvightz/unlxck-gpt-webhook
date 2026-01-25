from __future__ import annotations

import re
from typing import Dict, List

from .injury_synonyms import INJURY_SYNONYM_MAP, LOCATION_MAP, remove_negated_phrases

# -----------------------------
# 1) CANONICAL ALIGNMENT
# -----------------------------
# Only these injury_type keys exist in your rehab protocol database
CANONICAL_TYPES: List[str] = list(INJURY_SYNONYM_MAP.keys())

# Map medical terms to (canonical_type, flag)
MEDICAL_MAP: Dict[str, tuple[str, str]] = {
    "fracture": ("unspecified", "urgent_fracture"),
    "dislocation": ("unspecified", "urgent_dislocation"),
    "infection": ("unspecified", "urgent_infection"),
    "nerve": ("unspecified", "urgent_nerve"),
    "hernia": ("unspecified", "urgent_hernia"),
    "bursitis": ("tendonitis", "bursitis_variant"),
    "shin splints": ("pain", "shin_splints_variant"),
}

# Urgent terms should trigger a clear escalation flag without breaking rehab lookup.
URGENT_TERMS = {"fracture", "dislocation", "infection", "nerve"}

# Optional: lightweight mechanical red-flags (no NegEx here; assume pre-cleaned text)
RED_FLAG_TERMS: Dict[str, str] = {
    "locking": "mechanical_locking",
    "giving way": "instability_event",
    "buckled": "instability_event",
    "numb": "nerve_involvement",
    "tingling": "nerve_involvement",
}


def _normalize(text: str) -> str:
    """Lowercase + compress whitespace. Keep hyphens (for l-spine) and slashes (for n/a)."""
    return " ".join((text or "").lower().strip().split())


def safe_phrase_search(phrase: str, text: str) -> bool:
    """
    Boundary match that works for:
    - single words
    - multi-word phrases
    - hyphenated tokens (e.g., l-spine) when phrase includes hyphen
    """
    t = _normalize(text)
    p = _normalize(phrase)
    if not p or not t:
        return False
    pattern = rf"(?:^|\W){re.escape(p)}(?:\W|$)"
    return re.search(pattern, t) is not None


def _build_location_map(location_map: dict[str, str]) -> dict[str, list[str]]:
    canonical_map: dict[str, list[str]] = {}
    for synonym, canonical in location_map.items():
        if canonical not in canonical_map:
            canonical_map[canonical] = []
        if synonym not in canonical_map[canonical]:
            canonical_map[canonical].append(synonym)
    return canonical_map


LOCATION_MAP: dict[str, list[str]] = _build_location_map(LOCATION_MAP)


def _first_location_hit(t_clean: str) -> str:
    """
    Returns first matched canonical location.
    Deterministic: iterates LOCATION_MAP in insertion order.
    """
    for loc, syns in LOCATION_MAP.items():
        for s in syns:
            if safe_phrase_search(s, t_clean):
                return loc
    return "unspecified"


def _detect_side(t_clean: str) -> str:
    """
    Safe side detection:
    - default unspecified (not 'both')
    - no single-letter hacks
    """
    if any(safe_phrase_search(p, t_clean) for p in ["both", "bilateral"]):
        return "both"
    if safe_phrase_search("left", t_clean):
        return "left"
    if safe_phrase_search("right", t_clean):
        return "right"
    return "unspecified"


def score_injury_phrase(t_clean: str, synonym_map: Dict[str, List[str]] | None = None) -> Dict[str, str | List[str]]:
    """
    Processes ALREADY CLEANED text (post-negation, post-split).
    - Does NOT do NegEx here (assume upstream handles negation).
    - Keeps output schema stable for downstream rehab lookup.

    Expected `synonym_map` format:
      { canonical_type: ["syn1", "syn2", ...], ... }
    """
    t_clean = remove_negated_phrases(t_clean or "")
    t_clean = _normalize(t_clean)
    if not t_clean:
        return {
            "injury_type": "unspecified",
            "location": "unspecified",
            "side": "unspecified",
            "flags": [],
            "raw_text": "",
        }

    # A) Defaults (schema-stable)
    side = _detect_side(t_clean)
    injury_type = "unspecified"
    location = "unspecified"
    flags: List[str] = []
    medical_hit = False

    # B) Medical terms first (can set canonical type + flags)
    for term, (canon, flag) in MEDICAL_MAP.items():
        if safe_phrase_search(term, t_clean):
            medical_hit = True
            injury_type = canon
            flags.append(flag)
            if term in URGENT_TERMS:
                flags.append("urgent")

    # C) Red flags (independent of type)
    for term, flag in RED_FLAG_TERMS.items():
        if safe_phrase_search(term, t_clean):
            flags.append(flag)

    # D) Canonical type scoring (cap at 1.5 per category; no stacking)
    # If medical term already matched, we STILL compute scores, but we only override
    # if injury_type is unspecified (prevents "fracture" being replaced by "strain").
    type_scores: Dict[str, float] = {k: 0.0 for k in CANONICAL_TYPES}

    for cat, syns in (synonym_map or INJURY_SYNONYM_MAP).items():
        if cat not in CANONICAL_TYPES:
            continue

        # Match on canonical label OR any synonym (first hit wins for that category)
        for s in [cat] + list(syns or []):
            if safe_phrase_search(s, t_clean):
                type_scores[cat] = 1.5
                break

    # If we have no medical type set (or it's still unspecified), use best score
    if injury_type == "unspecified" and any(type_scores.values()) and not medical_hit:
        injury_type = max(type_scores.items(), key=lambda x: x[1])[0]

    # E) Location detection (deterministic)
    location = _first_location_hit(t_clean)

    # F) Extra defensive: if medical term hit but location is missing, keep unspecified
    # (do not invent location)
    # If you want, you can add additional med-term-to-location heuristics later.

    return {
        "injury_type": injury_type,
        "location": location,
        "side": side,
        "flags": sorted(set(flags)),
        "raw_text": t_clean,
    }
