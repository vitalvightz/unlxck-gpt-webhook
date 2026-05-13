import importlib.util
import re
from collections.abc import Iterable

from .normalization import strip_surrounding_punctuation as _strip_surrounding_punct
from .regex_config import compile_regex

_SPACY_AVAILABLE = importlib.util.find_spec("spacy") is not None
_NEGSPACY_AVAILABLE = _SPACY_AVAILABLE and importlib.util.find_spec("negspacy") is not None

if _SPACY_AVAILABLE:
    import spacy
    from spacy.tokens import Token
else:
    spacy = None
    Token = None

_NLP = None
_NLP_INITIALIZED = False

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

_NEGATION_TARGETS = {
    "injury", "injured", "issue", "issues", "problem", "problems",
    "pain", "sore", "soreness", "stiff", "stiffness", "tight", "tightness",
    "sprain", "strain", "tear", "fracture", "broken", "break", "dislocation",
    "subluxation", "concussion", "numbness", "tingling", "weakness", "swelling",
    "bruise", "contusion", "cut", "laceration", "tendon", "ligament",
}


def register_negation_targets(extra_terms: Iterable[str]) -> None:
    for term in extra_terms:
        cleaned = str(term or "").strip().lower()
        if not cleaned:
            continue
        _NEGATION_TARGETS.add(cleaned)


def _get_nlp():
    global _NLP, _NLP_INITIALIZED
    if _NLP_INITIALIZED:
        return _NLP
    _NLP_INITIALIZED = True
    if not _SPACY_AVAILABLE:
        _NLP = None
        return _NLP
    try:
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = None
        return _NLP
    if Token is not None:
        Token.set_extension("negex", default=False, force=True)
    if _NEGSPACY_AVAILABLE and _NLP is not None and "negex" not in _NLP.pipe_names:
        try:
            _NLP.add_pipe("negex", last=True)
        except Exception:
            pass
    return _NLP


def _has_negated_injury(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered or not _NEGATION_CUE_PATTERN.search(lowered):
        return False
    return any(re.search(rf"(?:^|\\b){re.escape(term)}(?:\\b|$)", lowered) for term in _NEGATION_TARGETS)


def negation_detection_available() -> bool:
    return bool(_get_nlp() and _NEGSPACY_AVAILABLE)


def contains_negated_injury(text: str) -> bool:
    if not text:
        return False
    return _has_negated_injury(text)


def _strip_negated_chunks_fallback(text: str) -> str:
    normalized = (text or "").lower()
    normalized = re.sub(r"[()]", " ", normalized)
    normalized = re.sub(r"\b(and|but|also|however|except)\b,?", ". ", normalized)
    normalized = re.sub(r"\s*(?:-|–|—|â€”|â€“)+\s*", ". ", normalized)
    phrases = [
        cleaned
        for chunk in re.split(r"\.\s*", normalized)
        if (cleaned := _strip_surrounding_punct(chunk))
    ]
    if not phrases:
        return ""
    kept = [phrase for phrase in phrases if not _has_negated_injury(phrase)]
    return ". ".join(kept).strip()


def remove_negated_phrases(text: str) -> str:
    if not text:
        return ""
    nlp = _get_nlp()
    if nlp and _NEGSPACY_AVAILABLE:
        doc = nlp(text)
        if any(getattr(tok._, "negex", False) for tok in doc):
            tokens = [tok.text for tok in doc if not getattr(tok._, "negex", False)]
            return " ".join(tokens).strip()
    return _strip_negated_chunks_fallback(text)
