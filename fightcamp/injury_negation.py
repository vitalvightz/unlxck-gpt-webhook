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
    for term in _NEGATION_TARGETS:
        if len(term) < 3:
            continue
        pattern = rf"(?:^|\b){re.escape(term)}(?:\b|$)"
        if re.search(pattern, lowered):
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
        return _strip_negated_chunks_fallback(text)
    return _strip_negated_chunks_fallback(text)


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
