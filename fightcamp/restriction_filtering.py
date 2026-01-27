from __future__ import annotations

import re
from typing import Iterable

from .restriction_parsing import CANONICAL_RESTRICTIONS, MIN_KEYWORD_MATCHES, ParsedRestriction
from .tagging import normalize_tags

_WORD_PATTERN = re.compile(r"[a-z]+")
_RESTRICTION_STOPWORDS = {
    "avoid",
    "no",
    "not",
    "dont",
    "don't",
    "do",
    "limit",
    "limited",
    "restriction",
    "restricted",
    "reduce",
    "flare",
    "flares",
    "when",
    "with",
    "under",
    "load",
    "heavy",
    "light",
    "prefer",
}

_RESTRICTION_KEYWORDS = {
    data["restriction"]: data["keywords"] for data in CANONICAL_RESTRICTIONS.values()
}

_LOW_CONFIDENCE_RESTRICTIONS = {"high_impact", "max_velocity"}


def _restriction_keywords(restriction: ParsedRestriction) -> list[str]:
    key = restriction.get("restriction")
    if key and key in _RESTRICTION_KEYWORDS:
        return _RESTRICTION_KEYWORDS[key]

    phrase = restriction.get("original_phrase", "")
    tokens = [w for w in _WORD_PATTERN.findall(phrase.lower()) if w not in _RESTRICTION_STOPWORDS]
    region = restriction.get("region")
    if region:
        tokens.append(region.lower())
    return tokens


def restriction_matches_item(
    restriction: ParsedRestriction,
    *,
    text: str,
    tags: Iterable[str],
) -> bool:
    if not restriction:
        return False
    keywords = _restriction_keywords(restriction)
    if not keywords:
        return False
    normalized_text = text.lower()
    tags_set = set(normalize_tags(tags))
    matches = sum(1 for keyword in keywords if keyword in normalized_text or keyword in tags_set)
    min_required = 1 if restriction.get("restriction") in _LOW_CONFIDENCE_RESTRICTIONS else MIN_KEYWORD_MATCHES
    if len(keywords) < min_required:
        min_required = 1
    return matches >= min_required


def evaluate_restriction_impact(
    restrictions: Iterable[ParsedRestriction] | None,
    *,
    text: str,
    tags: Iterable[str],
    limit_penalty: float,
) -> tuple[bool, float, list[str]]:
    if not restrictions:
        return False, 0.0, []
    exclude = False
    penalty = 0.0
    matched = []
    for restriction in restrictions:
        if not restriction_matches_item(restriction, text=text, tags=tags):
            continue
        matched.append(restriction.get("restriction", "generic_constraint"))
        strength = (restriction.get("strength") or "avoid").lower()
        if strength in {"avoid", "flare"}:
            exclude = True
        else:
            penalty += limit_penalty
    return exclude, penalty, matched
