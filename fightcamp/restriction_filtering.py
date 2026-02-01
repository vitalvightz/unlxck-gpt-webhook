from __future__ import annotations

import re
from typing import Iterable, TypedDict

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
if "high_impact" in _RESTRICTION_KEYWORDS:
    _RESTRICTION_KEYWORDS.update(
        {
            "high_impact_lower": _RESTRICTION_KEYWORDS["high_impact"],
            "high_impact_upper": _RESTRICTION_KEYWORDS["high_impact"],
            "high_impact_global": _RESTRICTION_KEYWORDS["high_impact"],
        }
    )

_LOW_CONFIDENCE_RESTRICTIONS = {
    "high_impact",
    "high_impact_lower",
    "high_impact_upper",
    "high_impact_global",
    "max_velocity",
}

_HIGH_IMPACT_LOWER_TAGS = {
    "high_impact",
    "high_impact_plyo",
    "plyometric",
    "jumping",
    "ballistic_lower",
    "mech_lower_jump",
    "mech_landing_impact",
    "landing_stress_high",
    "reactive_rebound_high",
    "impact_rebound_high",
    "foot_impact_high",
    "mech_reactive",
    "mech_ballistic",
}
_HIGH_IMPACT_LOWER_KEYWORDS = {
    "jump",
    "jumps",
    "jumping",
    "hop",
    "hops",
    "bound",
    "bounds",
    "plyo",
    "plyometric",
    "sprint",
    "sprinting",
    "hurdle",
    "depth drop",
    "depth-drop",
    "burpee",
    "sprawl",
    "landing",
    "landings",
    "reactive",
}
_HIGH_IMPACT_UPPER_KEYWORDS = {
    "clap pushup",
    "clap push-up",
    "clapping pushup",
    "clapping push-up",
    "plyo pushup",
    "plyo push-up",
    "plyometric pushup",
    "plyometric push-up",
    "explosive pushup",
    "explosive push-up",
}
_RESTRICTION_SPECIFIC_STOPWORDS = {
    "high_impact": {"high", "pace", "push", "pull", "row", "fly", "low", "to", "and", "with"},
    "high_impact_lower": {"high", "pace", "push", "pull", "row", "fly", "low", "to", "and", "with"},
    "high_impact_upper": {"high", "pace", "push", "pull", "row", "fly", "low", "to", "and", "with"},
    "high_impact_global": {"high", "pace", "push", "pull", "row", "fly", "low", "to", "and", "with"},
}


class RestrictionMatch(TypedDict):
    restriction: str
    strength: str
    method: str
    confidence: float


class RestrictionGuardResult(TypedDict, total=False):
    allowed: bool
    matched: list[RestrictionMatch]
    risk: float
    no_match_hints: list[str]
    penalty: float


def _restriction_keywords(restriction: ParsedRestriction) -> list[str]:
    key = restriction.get("restriction")
    if key and key in _RESTRICTION_KEYWORDS:
        keywords = _RESTRICTION_KEYWORDS[key]
        stopwords = _RESTRICTION_SPECIFIC_STOPWORDS.get(key, set())
        return [kw for kw in keywords if kw not in stopwords]

    phrase = restriction.get("original_phrase", "")
    tokens = [w for w in _WORD_PATTERN.findall(phrase.lower()) if w not in _RESTRICTION_STOPWORDS]
    region = restriction.get("region")
    if region:
        tokens.append(region.lower())
    return tokens


def _restriction_match_detail(
    restriction: ParsedRestriction,
    *,
    text: str,
    tags: Iterable[str],
) -> tuple[bool, RestrictionMatch | None, str | None]:
    if not restriction:
        return False, None, None
    tags_set = set(normalize_tags(tags))
    restriction_key = restriction.get("restriction") or "generic_constraint"
    strength = (restriction.get("strength") or "avoid").lower()
    keywords = _restriction_keywords(restriction)
    if restriction_key in {"high_impact", "high_impact_lower", "high_impact_upper", "high_impact_global"}:
        stopwords = _RESTRICTION_SPECIFIC_STOPWORDS.get(restriction_key, set())
        keywords = [kw for kw in keywords if kw not in stopwords]
        if restriction_key == "high_impact_upper":
            keywords = list(set(keywords) | _HIGH_IMPACT_UPPER_KEYWORDS)
        elif restriction_key == "high_impact_global":
            keywords = list(set(keywords) | _HIGH_IMPACT_LOWER_KEYWORDS | _HIGH_IMPACT_UPPER_KEYWORDS)
        else:
            keywords = list(set(keywords) | _HIGH_IMPACT_LOWER_KEYWORDS)
    normalized_text = text.lower()
    tag_matches = []
    text_matches = []
    if restriction_key in {"high_impact", "high_impact_lower", "high_impact_global"} and tags_set & _HIGH_IMPACT_LOWER_TAGS:
        tag_matches.extend(sorted(tags_set & _HIGH_IMPACT_LOWER_TAGS))
    for keyword in keywords:
        if keyword in tags_set:
            tag_matches.append(keyword)
        if _keyword_in_text(keyword, normalized_text):
            text_matches.append(keyword)
    matches = set(tag_matches + text_matches)
    matches_count = len(matches)
    min_required = 1 if restriction_key in _LOW_CONFIDENCE_RESTRICTIONS else MIN_KEYWORD_MATCHES
    if len(keywords) < min_required:
        min_required = 1
    matched = matches_count >= min_required
    if not matched:
        hint = None
        if restriction_key in {"high_impact", "high_impact_lower", "high_impact_global"} and not tag_matches:
            hint = "missing high_impact tag"
        return False, None, hint
    if tag_matches and text_matches:
        method = "tag+keyword"
    elif tag_matches:
        method = "tag"
    else:
        method = "keyword"
    confidence = min(1.0, matches_count / max(min_required, 1))
    return (
        True,
        {
            "restriction": restriction_key,
            "strength": strength,
            "method": method,
            "confidence": round(confidence, 2),
        },
        None,
    )


def _keyword_in_text(keyword: str, text: str) -> bool:
    escaped = re.escape(keyword)
    if " " in keyword:
        parts = [re.escape(part) for part in keyword.split()]
        pattern = r"\b" + r"[\s-]+".join(parts) + r"\b"
    else:
        pattern = r"\b" + escaped + r"\b"
    return re.search(pattern, text) is not None


def evaluate_restriction_impact(
    restrictions: Iterable[ParsedRestriction] | None,
    *,
    text: str,
    tags: Iterable[str],
    limit_penalty: float,
) -> RestrictionGuardResult:
    if not restrictions:
        return {"allowed": True, "matched": [], "risk": 0.0, "penalty": 0.0}
    exclude = False
    penalty = 0.0
    matched: list[RestrictionMatch] = []
    no_match_hints: list[str] = []
    for restriction in restrictions:
        is_match, detail, hint = _restriction_match_detail(restriction, text=text, tags=tags)
        if hint:
            no_match_hints.append(hint)
        if not is_match or detail is None:
            continue
        matched.append(detail)
        strength = detail.get("strength", "avoid")
        if strength in {"avoid", "flare"}:
            exclude = True
        else:
            penalty += limit_penalty
    risk = 0.0
    if matched:
        risk = 1.0 if exclude else min(1.0, abs(penalty))
    result: RestrictionGuardResult = {
        "allowed": not exclude,
        "matched": matched,
        "risk": risk,
        "penalty": penalty,
    }
    if no_match_hints:
        result["no_match_hints"] = sorted(set(no_match_hints))
    return result
