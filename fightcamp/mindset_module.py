import importlib.util
from difflib import SequenceMatcher

_SPACY_AVAILABLE = importlib.util.find_spec("spacy") is not None
_RAPIDFUZZ_AVAILABLE = importlib.util.find_spec("rapidfuzz") is not None

if _RAPIDFUZZ_AVAILABLE:
    from rapidfuzz import fuzz
else:
    class _FuzzFallback:
        @staticmethod
        def partial_ratio(a: str, b: str) -> int:
            return int(SequenceMatcher(None, a, b).ratio() * 100)

    fuzz = _FuzzFallback()

if _SPACY_AVAILABLE:
    import spacy

    # load large English model once
    try:  # pragma: no cover - model may be missing in CI
        nlp = spacy.load("en_core_web_lg")
    except Exception:  # pragma: no cover - fallback to blank model
        nlp = spacy.blank("en")
else:
    nlp = None

mindset_bank = {
    "GPP": {
        "confidence": "Use future-self visualization and complete 1 small, measurable success daily to rebuild belief.",
        "gas tank": "Anchor slow nasal breathwork post-cardio, record HR drop time to reinforce progress.",
        "injury fear": "Set weekly exposure targets with graded contact drills and track pain-free sessions.",
        "pressure": "Reframe pressure as privilege via journaling; write 'why I'm prepared' before each session.",
        "attention": "Use ",
    },
}
