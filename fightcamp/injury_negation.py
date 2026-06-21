import re
from collections.abc import Iterable

from .normalization import strip_surrounding_punctuation as _strip_surrounding_punct
from .regex_config import compile_regex

NEGATION_CUES = {
    "no",
    "not",
    "never",
    "without",
    "deny",
    "denies",
    "denied",
    "neither",
    "ruled out",
}

_NEGATION_CUE_PATTERN = compile_regex("injury_synonyms", "negation_cue_pattern")

_NEGATION_TARGETS: list[str] = sorted(
    {
        term.strip()
        for term in ["injury", "injured", "issue", "issues", "problem", "problems"]
        if term and term.strip()
    },
    key=len,
    reverse=True,
)


def register_negation_targets(extra_terms: Iterable[str]) -> None:
    global _NEGATION_TARGETS
    merged = {
        term.strip()
        for term in ([*_NEGATION_TARGETS, *list(extra_terms)])
        if term and term.strip()
    }
    _NEGATION_TARGETS = sorted(merged, key=len, reverse=True)


def _normalize_injury_text_separators(text: str) -> str:
    _INJURY_TEXT_SEPARATORS = [
        ",",
        ";",
        "\n",
        " - ",
        f" {chr(0x2013)} ",
        f" {chr(0x2014)} ",
        " then ",
        " + ",
        "+",
        "/",
        "|",
    ]
    _LEGACY_MOJIBAKE_DASH_SEPARATORS = [
        f" {chr(0x00e2)}{chr(0x20ac)}{chr(0x201c)} ",
        f" {chr(0x00e2)}{chr(0x20ac)}{chr(0x201d)} ",
    ]
    normalized = text
    for sep in [*_INJURY_TEXT_SEPARATORS, *_LEGACY_MOJIBAKE_DASH_SEPARATORS]:
        normalized = normalized.replace(sep, ". ")
    return normalized


def _has_negated_injury(text: str) -> bool:
    lowered = text.lower()
    if not _NEGATION_CUE_PATTERN.search(lowered):
        return False
    if re.search(r"\bruled\s+out\s+\w+", lowered):
        return True
    # A negation cue at the start of a phrase negates the whole phrase even when
    # no generic injury word ("injury"/"issue") follows it. This catches
    # symptom-level negations like "no shoulder pain" or "no shin splints" that
    # the entity-based Negex pass misses because the symptom is not a named
    # entity. Only leading cues fire, so mid-phrase mentions such as "knee pain
    # without brace" are left intact.
    leading = lowered.strip().split()
    if leading and leading[0] in {
        "no", "not", "never", "without", "neither", "deny", "denies", "denied"
    }:
        return True
    # Negation scopes forward: only treat a generic target word as negated when a
    # cue actually precedes it. This keeps "knee pain without brace" intact (the
    # cue follows the symptom) while still catching "never had knee issues".
    cue_alt = r"\b(?:no|not|never|without|neither|deny|denies|denied|ruled\s+out)\b"
    for term in _NEGATION_TARGETS:
        if len(term) < 3 or term not in lowered:
            continue
        if re.search(cue_alt + r"[\w\s,'\"-]*?\b" + re.escape(term) + r"\b", lowered):
            return True
    return False


def negation_detection_available() -> bool:
    from .injury_synonyms import _NEGSPACY_AVAILABLE, get_nlp

    return bool(get_nlp() and _NEGSPACY_AVAILABLE)


def contains_negated_injury(text: str) -> bool:
    if not text:
        return False
    return _has_negated_injury(text)


def remove_negated_phrases(text: str) -> str:
    """Strip words marked as negated by Negex from the text."""
    from .injury_synonyms import _NEGSPACY_AVAILABLE, get_nlp

    if not text:
        return ""
    nlp = get_nlp()
    if nlp and _NEGSPACY_AVAILABLE:
        doc = nlp(text)
        if any(tok._.negex for tok in doc):
            tokens = [tok.text for tok in doc if not tok._.negex]
            return " ".join(tokens).strip()
        # Negex only marks named entities, so symptom-level negations such as
        # "no shoulder pain" slip through. Drop only chunks that *begin* with a
        # negation cue (clinical forward-scope) instead of returning the text
        # untouched. Embedded negations like "shoulder clicking no pain" are
        # left for Negex so we never discard the non-negated half of a chunk.
        return _strip_leading_negation_chunks(text)
    return _strip_negated_chunks_fallback(text)


_LEADING_NEGATION_CUES = {
    "no", "not", "never", "without", "neither", "deny", "denies", "denied",
}


def _strip_leading_negation_chunks(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[()]", " ", normalized)
    normalized = re.sub(r"\b(and|but|also|however|except)\b,?", ". ", normalized)
    normalized = _normalize_injury_text_separators(normalized)
    chunks = [
        cleaned
        for chunk in re.split(r"\.\s*", normalized)
        if (cleaned := _strip_surrounding_punct(chunk))
    ]
    kept: list[str] = []
    for cleaned in chunks:
        # Ignore a leading field label ("notes: no fracture ...") so the cue is
        # still seen at the start of the clause.
        words = re.sub(r"^\w+:\s*", "", cleaned).split()
        # Drop a clause only when its negation scopes the clause itself: it
        # begins with a cue ("no shoulder pain") or explicitly rules an injury
        # out ("ruled out fracture"). Trailing negations such as "shoulder
        # clicking no pain" keep the non-negated injury content.
        if words and words[0] in _LEADING_NEGATION_CUES:
            continue
        if re.search(r"\bruled\s+out\b", cleaned):
            continue
        kept.append(cleaned)
    # If nothing was negated, return the text untouched so we never reflow
    # punctuation/casing for callers that rely on the original structure (e.g.
    # swelling-context severity escalation).
    if len(kept) == len(chunks):
        return text
    return ". ".join(kept).strip()


def _strip_negated_chunks_fallback(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[()]", " ", normalized)
    normalized = re.sub(r"\b(and|but|also|however|except)\b,?", ". ", normalized)
    normalized = _normalize_injury_text_separators(normalized)
    phrases = [
        cleaned
        for chunk in re.split(r"\.\s*", normalized)
        if (cleaned := _strip_surrounding_punct(chunk))
    ]
    if not phrases:
        return ""
    kept = [phrase for phrase in phrases if not _has_negated_injury(phrase)]
    return ". ".join(kept).strip()
