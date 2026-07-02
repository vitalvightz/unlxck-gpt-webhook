import importlib.util
import logging
import os
import re
import threading
from difflib import SequenceMatcher

from .normalization import strip_surrounding_punctuation as _strip_surrounding_punct
from .injury_negation import (
    register_negation_targets,
    remove_negated_phrases,
)
from .regex_config import compile_regex
from .injury_taxonomy import get_required_flags
from .injury_location_registry import build_location_synonym_map

_SPACY_AVAILABLE = importlib.util.find_spec("spacy") is not None
_RAPIDFUZZ_AVAILABLE = importlib.util.find_spec("rapidfuzz") is not None
_NEGSPACY_AVAILABLE = _SPACY_AVAILABLE and importlib.util.find_spec("negspacy") is not None

if _RAPIDFUZZ_AVAILABLE:
    from rapidfuzz import fuzz
else:
    class _FuzzFallback:
        @staticmethod
        def partial_ratio(a: str, b: str) -> int:
            return int(SequenceMatcher(None, a, b).ratio() * 100)

    fuzz = _FuzzFallback()

# spaCy (with thinc/numpy/blis) costs ~50MB of RSS just to import, before any
# model is loaded. Importing it lazily keeps web workers light at boot — they
# only pay for it if a request actually reaches the injury-parsing path — and
# noticeably speeds up cold starts on small instances. The heavy stack is
# imported on first use via _import_spacy_stack() below.
spacy = None
PhraseMatcher = None
Negex = None
Token = None
_SPACY_IMPORTED = False

# Guards all lazy spaCy initialization (stack import, pipeline load, matcher
# build). FastAPI runs sync endpoints on a thread pool, so two requests can
# race into the first initialization; an RLock (get_nlp holds it while calling
# _import_spacy_stack) with flags set only after the work completes ensures
# late arrivals block until the state is fully built instead of observing a
# half-initialized module.
_SPACY_INIT_LOCK = threading.RLock()


def _import_spacy_stack() -> None:
    """Populate the module-level spaCy symbols on first use."""
    global spacy, PhraseMatcher, Negex, Token, _SPACY_IMPORTED
    if _SPACY_IMPORTED or not _SPACY_AVAILABLE:
        return
    with _SPACY_INIT_LOCK:
        if _SPACY_IMPORTED:
            return
        import spacy as _spacy
        from spacy.matcher import PhraseMatcher as _PhraseMatcher
        from spacy.tokens import Token as _Token  # needed to register extensions

        spacy = _spacy
        PhraseMatcher = _PhraseMatcher
        Token = _Token
        if _NEGSPACY_AVAILABLE:
            from negspacy.negation import Negex as _Negex

            Negex = _Negex
        _SPACY_IMPORTED = True

_DEGRADED_LOGGED = False
logger = logging.getLogger(__name__)

_NLP = None
_NLP_INITIALIZED = False
_MATCHERS_INITIALIZED = False
INJURY_MATCHER = None
INJURY_MATCH_ID_TO_CANONICAL: dict[int, str] = {}
LOCATION_MATCHER = None
LOC_MATCH_ID_TO_CANONICAL: dict[int, str] = {}


def _log_dependency_status() -> None:
    global _DEGRADED_LOGGED
    if _DEGRADED_LOGGED:
        return
    missing = []
    if not _SPACY_AVAILABLE:
        missing.append("spaCy")
    if not _NEGSPACY_AVAILABLE:
        missing.append("NegEx")
    if not _RAPIDFUZZ_AVAILABLE:
        missing.append("rapidfuzz")
    if missing:
        _DEGRADED_LOGGED = True
        logger.warning(
            "[injury-parse] Degraded parsing mode: missing %s. Features disabled: %s.",
            ", ".join(missing),
            ", ".join(
                feature
                for feature, available in (
                    ("phrase matching", _SPACY_AVAILABLE),
                    ("negation detection", _NEGSPACY_AVAILABLE),
                    ("fuzzy matching", _RAPIDFUZZ_AVAILABLE),
                )
                if not available
            ),
        )


_log_dependency_status()


def _spacy_disabled_by_env() -> bool:
    """UNLXCK_DISABLE_SPACY=1 keeps this process on the regex fallback path.

    Intended for the memory-constrained web tier, where injury text is only
    parsed for display (advisories, plan cards) and the ~95MB spaCy stack +
    en_core_web_sm model is not worth the RSS. The worker/planner processes,
    which do the authoritative injury parsing for exercise exclusion, should
    never set this.
    """
    return os.getenv("UNLXCK_DISABLE_SPACY", "0").strip() == "1"


def get_nlp():
    global _NLP, _NLP_INITIALIZED
    if _NLP_INITIALIZED:
        return _NLP
    with _SPACY_INIT_LOCK:
        if _NLP_INITIALIZED:
            return _NLP
        try:
            if not _SPACY_AVAILABLE:
                _NLP = None
                return _NLP
            if _spacy_disabled_by_env():
                logger.info(
                    "[injury-parse] spaCy disabled via UNLXCK_DISABLE_SPACY=1; "
                    "using regex fallback parsing in this process."
                )
                _NLP = None
                return _NLP
            try:
                _import_spacy_stack()
            except Exception:
                _NLP = None
                return _NLP
            try:
                # The injury pipeline relies only on tokenization, NER (which feeds
                # Negex), sentence boundaries (the parser, which Negex uses for
                # termination boundaries) and the negex component. The tagger,
                # lemmatizer and attribute_ruler produce POS/lemma annotations that are
                # never read here, so disabling them trims per-doc processing time
                # without changing matching or negation behavior.
                _NLP = spacy.load(
                    "en_core_web_sm",
                    disable=["tagger", "lemmatizer", "attribute_ruler"],
                )
            except Exception:
                _NLP = None
                return _NLP
            if Token is not None:
                Token.set_extension("negex", default=False, force=True)
            if _NEGSPACY_AVAILABLE and _NLP is not None and "negex" not in _NLP.pipe_names:
                try:
                    _NLP.add_pipe("negex", last=True)
                except Exception:  # pragma: no cover - Negex might not be registered
                    _NLP.add_pipe(Negex(_NLP), last=True)
            return _NLP
        finally:
            _NLP_INITIALIZED = True


def get_matchers(nlp):
    global _MATCHERS_INITIALIZED
    global INJURY_MATCHER, INJURY_MATCH_ID_TO_CANONICAL, LOCATION_MATCHER, LOC_MATCH_ID_TO_CANONICAL
    if _MATCHERS_INITIALIZED:
        return INJURY_MATCHER, INJURY_MATCH_ID_TO_CANONICAL, LOCATION_MATCHER, LOC_MATCH_ID_TO_CANONICAL
    with _SPACY_INIT_LOCK:
        if _MATCHERS_INITIALIZED:
            return INJURY_MATCHER, INJURY_MATCH_ID_TO_CANONICAL, LOCATION_MATCHER, LOC_MATCH_ID_TO_CANONICAL
        if not nlp or PhraseMatcher is None:
            _MATCHERS_INITIALIZED = True
            return INJURY_MATCHER, INJURY_MATCH_ID_TO_CANONICAL, LOCATION_MATCHER, LOC_MATCH_ID_TO_CANONICAL
        # Build into locals and publish to the module globals only when fully
        # populated, so no reader can observe a half-built matcher.
        injury_matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        injury_map: dict[int, str] = {}
        for _canonical, _syns in INJURY_SYNONYM_MAP.items():
            patterns = [_canonical] + _syns
            # PhraseMatcher with attr="LOWER" only needs token text, so tokenize the
            # patterns with make_doc instead of running the full tagger/parser/NER
            # pipeline over every synonym (the spaCy-recommended fast path).
            docs = [nlp.make_doc(p) for p in patterns]
            match_id = nlp.vocab.strings.add(_canonical)
            injury_matcher.add(_canonical, docs)
            injury_map[match_id] = _canonical

        location_matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        location_map: dict[int, str] = {}
        for _key, _canonical in LOCATION_MAP.items():
            doc = nlp.make_doc(_key)
            match_id = nlp.vocab.strings.add(_key)
            location_matcher.add(_key, [doc])
            location_map[match_id] = _canonical

        INJURY_MATCHER = injury_matcher
        INJURY_MATCH_ID_TO_CANONICAL = injury_map
        LOCATION_MATCHER = location_matcher
        LOC_MATCH_ID_TO_CANONICAL = location_map
        _MATCHERS_INITIALIZED = True
    return INJURY_MATCHER, INJURY_MATCH_ID_TO_CANONICAL, LOCATION_MATCHER, LOC_MATCH_ID_TO_CANONICAL

# Heavier weight to categories we want to prefer when there’s overlap
TYPE_PRIORITY = {
    "instability": 1.00,
    "sprain": 0.90,
    "impingement": 0.85,
    "tendonitis": 0.80,
    "strain": 0.78,
    "hyperextension": 0.75,
    "laceration": 0.72,
    "cut": 0.71,
    "abrasion": 0.70,
    "graze": 0.69,
    "blister": 0.68,
    "stiffness": 0.66,
    "tightness": 0.64,
    "contusion": 0.62,
    "swelling": 0.62,
    "soreness": 0.60,
    "pain": 0.58,
    "unspecified": 0.10,
}

# Words/phrases that are strong, near-exclusive hints for given categories.
# Used to disambiguate when PhraseMatcher hits collide (e.g., sprain vs instability).
EXCLUSIVE_HINTS = {
    "sprain": {
        "rolled", "rolling", "inversion", "eversion",
        "ligament", "ligament tear", "ligament pop",
        "acl", "mcl", "lcl", "pcl",
        "twist", "twisted"
    },
    "instability": {
        "gave way", "giving way", "apprehension", "fear", "afraid",
        "don’t trust", "don't trust", "can’t trust", "can't trust",
        "dislocate", "dislocated", "sublux", "subluxation",
        "unreliable", "unstable"
    },
}

# Per-category fuzzy thresholds (defaults remain 85 if not listed)
FUZZY_THRESHOLDS = {
    "pain": 90,
    "tightness": 88,
    "stiffness": 88,
    "soreness": 90,
    # others default to 85
}

# Cues for deterministic disambiguation among pain/tightness/stiffness/soreness
SORENESS_HINTS = {
    "doms", "delayed onset", "next day", "next morning", "after workout",
    "after training", "after session", "post workout", "post training", "post session",
    "recovery", "recovering",
}
STIFFNESS_HINTS = {
    "morning", "after rest", "after sitting", "after sleeping",
    "won't bend", "won't extend", "limited motion", "limited range", "limited rom",
    "can't bend", "can't extend", "can't move",
}
TIGHTNESS_HINTS = {
    "tight", "tightness", "feels tight", "restricted", "warm up", "warming up",
    "loosen", "loosen up", "loosened", "looser", "needs stretching",
}

TENDONITIS_REQUIRED_HINTS = {
    "tendonitis", "tendinosis", "tendinopathy", "overuse", "repetitive",
    "chronic", "recurring", "flare", "flare up", "activity pain", "use pain",
    # Specific tendon/patellar references are themselves strong tendinopathy
    # signals (unlike generic "pain"/"sore"), so they satisfy the gate that
    # otherwise guards against over-calling tendonitis on vague complaints.
    "tendon pain", "tendon ache", "tendon sore", "tendon hurt",
    "patellar tendon", "patellar tendinopathy",
    "jumper's knee", "jumpers knee", "jumper knee",
}

IMPINGEMENT_GATE_HINTS = {
    "pinch", "pinching", "jam", "jamming", "block", "blocking", "stuck", "sticking",
    "won't lift", "won't raise", "won't rotate", "won't turn", "won't reach",
    "painful arc", "painful range", "bone on bone", "impinge", "impingement",
}
IMPINGEMENT_LOW_SPECIFICITY = {"click", "clicking", "clunk", "clunking", "catch", "catching"}

# Spine/back context routing (phrase-level)
SPINE_HINTS = {
    "neck": {"neck", "cervical", "c-spine"},
    "upper_back": {"upper back", "upper-back", "thoracic", "t-spine", "mid back", "mid-back"},
    "lower_back": {"lower back", "lower-back", "lumbar", "l-spine", "sciatic", "sciatica", "sacrum"},
}
POSTERIOR_THIGH_HINTS = {"back of thigh", "back thigh", "rear thigh", "posterior thigh"}
# Negation helpers are re-exported for backward compatibility.
# New code should import from fightcamp.injury_negation.


# Compiled boundary-match patterns keyed by normalized phrase. Phrases come
# from finite synonym/hint sets, so this cache is bounded; it avoids recompiling
# the same pattern on every hint-scoring call (a hot path during plan generation).
_PHRASE_IN_TEXT_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Boundary-aware phrase check for degraded mode and hint scoring."""
    cleaned_phrase = " ".join(str(phrase or "").lower().strip().split())
    cleaned_text = " ".join(str(text or "").lower().strip().split())
    if not cleaned_phrase or not cleaned_text:
        return False
    pattern = _PHRASE_IN_TEXT_PATTERN_CACHE.get(cleaned_phrase)
    if pattern is None:
        pattern = re.compile(rf"(?<!\w){re.escape(cleaned_phrase)}(?!\w)")
        _PHRASE_IN_TEXT_PATTERN_CACHE[cleaned_phrase] = pattern
    return pattern.search(cleaned_text) is not None


def _taxonomy_flags_for(category: str) -> tuple[str, ...]:
    return tuple(get_required_flags(category))


STRUCTURAL_RED_FLAG_MAP: dict[str, tuple[str, ...]] = {
    # Dislocation / subluxation
    "partial dislocation": _taxonomy_flags_for("dislocation"),
    "dislocation": _taxonomy_flags_for("dislocation"),
    "dislocated": _taxonomy_flags_for("dislocation"),
    "subluxation": _taxonomy_flags_for("dislocation"),
    "sublux": _taxonomy_flags_for("dislocation"),

    # Ligament tear / rupture
    "acl tear": _taxonomy_flags_for("acl_tear"),
    "mcl tear": _taxonomy_flags_for("mcl_tear"),
    "lcl tear": _taxonomy_flags_for("lcl_tear"),
    "pcl tear": _taxonomy_flags_for("pcl_tear"),
    "ligament tear": _taxonomy_flags_for("ligament_tear"),
    "torn ligament": _taxonomy_flags_for("ligament_tear"),
    "ruptured ligament": _taxonomy_flags_for("ligament_tear"),
    "blown ligament": _taxonomy_flags_for("ligament_tear"),

    # Tendon tear / rupture
    "tendon tear": _taxonomy_flags_for("tendon_rupture"),
    "torn tendon": _taxonomy_flags_for("tendon_rupture"),
    "tendon rupture": _taxonomy_flags_for("tendon_rupture"),
    "ruptured tendon": _taxonomy_flags_for("tendon_rupture"),
    "tendon snap": _taxonomy_flags_for("tendon_rupture"),
    "tendon snapped": _taxonomy_flags_for("tendon_rupture"),
    "felt tendon snap": _taxonomy_flags_for("tendon_rupture"),
    "felt tendon pop": _taxonomy_flags_for("tendon_rupture"),
    "tendon popped": _taxonomy_flags_for("tendon_rupture"),

    # Muscle rupture
    "muscle rupture": _taxonomy_flags_for("muscle_rupture"),
    "muscle ruptured": _taxonomy_flags_for("muscle_rupture"),

    # Bone
    "fracture": ("structural_red_flag", "suspected_fracture", "urgent"),
    "broken bone": ("structural_red_flag", "suspected_fracture", "urgent"),

    # Concussion / head injury
    "concussion": ("structural_red_flag", "suspected_concussion", "urgent"),
    "concussed": ("structural_red_flag", "suspected_concussion", "urgent"),
    "head injury": ("structural_red_flag", "suspected_concussion", "urgent"),
    "head knock": ("structural_red_flag", "suspected_concussion", "urgent"),
    "head impact": ("structural_red_flag", "suspected_concussion", "urgent"),
    "got rocked": ("structural_red_flag", "suspected_concussion", "urgent"),
    "knocked out": ("structural_red_flag", "suspected_concussion", "urgent"),
    "ko'd": ("structural_red_flag", "suspected_concussion", "urgent"),
    "k.o.'d": ("structural_red_flag", "suspected_concussion", "urgent"),
    "blacked out": ("structural_red_flag", "suspected_concussion", "urgent"),
    "dizzy after head impact": ("structural_red_flag", "suspected_concussion", "urgent"),
    "headache after sparring": ("structural_red_flag", "suspected_concussion", "urgent"),
    "blurred vision after hit": ("structural_red_flag", "suspected_concussion", "urgent"),
    "nausea after head impact": ("structural_red_flag", "suspected_concussion", "urgent"),
}


TRIAGE_CATEGORY_MAP: dict[str, str] = {
    "acl tear": "acl_tear",
    "mcl tear": "mcl_tear",
    "lcl tear": "lcl_tear",
    "pcl tear": "pcl_tear",
    "ligament tear": "ligament_tear",
    "torn ligament": "ligament_tear",
    "ruptured ligament": "ligament_tear",
    "blown ligament": "ligament_tear",
    "tendon tear": "tendon_rupture",
    "torn tendon": "tendon_rupture",
    "tendon rupture": "tendon_rupture",
    "ruptured tendon": "tendon_rupture",
    "tendon snap": "tendon_rupture",
    "tendon snapped": "tendon_rupture",
    "felt tendon snap": "tendon_rupture",
    "felt tendon pop": "tendon_rupture",
    "tendon popped": "tendon_rupture",
    "muscle rupture": "muscle_rupture",
    "muscle ruptured": "muscle_rupture",
    "partial dislocation": "dislocation",
    "dislocation": "dislocation",
    "dislocated": "dislocation",
    "subluxation": "dislocation",
    "sublux": "dislocation",
    "fracture": "fracture",
    "broken bone": "fracture",
    "concussion": "concussion",
    "concussed": "concussion",
    "head injury": "concussion",
    "head knock": "concussion",
    "head impact": "concussion",
    "got rocked": "concussion",
    "knocked out": "concussion",
    "ko'd": "concussion",
    "k.o.'d": "concussion",
    "blacked out": "concussion",
    "dizzy after head impact": "concussion",
    "headache after sparring": "concussion",
    "blurred vision after hit": "concussion",
    "nausea after head impact": "concussion",
    "infection": "infection",
    "hernia": "hernia",
}


def detect_structural_red_flags(text: str) -> list[str]:
    """Return deterministic structural red-flag tags for severe injury phrases."""
    cleaned = " ".join(str(text or "").lower().strip().split())
    if not cleaned:
        return []

    flags: list[str] = []
    for phrase, structural_flags in STRUCTURAL_RED_FLAG_MAP.items():
        if not _phrase_in_text(phrase, cleaned):
            continue
        for flag in structural_flags:
            if flag not in flags:
                flags.append(flag)
    if not flags:
        return []
    # Always surface the generic structural_red_flag tag alongside the specific
    # signals, and return a deterministic sorted list so callers (and the
    # composed score path) see a stable, complete set.
    flags.append("structural_red_flag")
    return sorted(set(flags))


def detect_triage_category(text: str) -> str:
    """Return deterministic triage category for structural/urgent injury phrases."""
    cleaned = text
    if not cleaned:
        return ""

    for phrase, category in TRIAGE_CATEGORY_MAP.items():
        if _phrase_in_text(phrase, cleaned):
            return category

    if any(_phrase_in_text(term, cleaned) for term in ("numb", "tingling", "nerve")):
        return "nerve_involvement"

    return ""


INJURY_SYNONYM_MAP = {
    # NOTE: Severe structural/dislocation phrases are intentionally kept out of
    # broad rehab synonym buckets. Triage pattern matching routes those signals
    # before ordinary rehab typing is used.
    # Ligament - now with every joint instability phrase imaginable
    "sprain": [
        "rolling", "rolled", "twist", "twisted",
        "folded",
        "ligament strain", "ligament sprain", "ligament gone",
        "joint shift", "knee went", "ankle went", "wrist went",
        "click out", "shift out", "unhinged",
        "stretched ligament",
        "sprain", "sprained", "inversion", "eversion", "rolled over", "turned over"
    ],

    # Muscle/Tendon - every possible pull/tear description
    "strain": [
        "pull", "pulled", "tug", "tugged", "rip", "ripped",
        "cramp", "cramping", "charley horse", "seize", "seized",
        "lock", "locked", "knot", "knotted", "ball", "balled", "grab", "grabbed",
        "pinged", "twinge", "twinging", "sharp pain", "acute pain",
        "muscle went",
        "strain", "strained", "muscle failure",
        "overworked", "worked too hard"
    ],
    # Tightness - every stiffness phrase
    "tightness": [
        "tight", "tightness", "glued",
        "needs release", "needs stretching",
        "hard to move", "limited motion", "reduced range", "can't reach", "can't stretch",
        "warming up", "slow to loosen", "loosen", "loosen up", "looser",
        "like a rock", "like concrete", "like a board", "like a log",
        "needs massage", "needs foam roll", "needs lacrosse ball"
    ],


    "abrasion": [
        "abrasion",
        "abrased",
        "abrase",
        "scrape",
        "scraped",
        "scraped up",
        "skin scrape",
        "surface scrape",
        "superficial scrape",
        "friction burn",
        "mat burn",
        "turf burn",
        "road rash",
        "raspberry",
        "skin rubbed",
        "rubbed raw",
        "skin rubbed raw",
        "skin taken off",
        "skin off",
        "skin came off",
        "surface wound",
        "superficial wound",
        "carpet burn",
        "floor burn",
        "canvas burn",
    ],
    "cut": [
        "cut",
        "cuts",
        "small cut",
        "minor cut",
        "skin cut",
        "open cut",
        "split skin",
        "skin split",
        "nick",
        "nicked",
        "slice",
        "sliced",
        "slash",
        "slashed",
        "wound",
        "small wound",
        "open wound",
        "surface cut",
        "bleeding cut",
    ],
    "laceration": [
        "laceration",
        "lacerated",
        "deep cut",
        "bad cut",
        "gash",
        "gashed",
        "deep gash",
        "split open",
        "opened up",
        "cut open",
        "needs stitches",
        "needed stitches",
        "requires stitches",
        "stitches",
        "stitched",
        "staples",
        "stapled",
    ],
    "graze": [
        "graze",
        "grazed",
        "graze wound",
        "surface graze",
        "skin graze",
        "minor graze",
        "scratch",
        "scratched",
        "scratch mark",
        "scratches",
        "skin scratch",
    ],
    "blister": [
        "blister",
        "blisters",
        "blistered",
        "blood blister",
        "friction blister",
        "water blister",
        "heel blister",
        "toe blister",
        "skin bubble",
        "bubble on skin",
        "hot spot",
        "boot rub",
        "shoe rub",
        "glove rub",
    ],

    # Bruise - every impact description
    # Note: "knee" was removed from this list as it caused false positives,
    # misclassifying tendon injuries like "patellar tendon" as contusions.
    # "kneed" (verb) and "from knee" (impact) remain as they correctly indicate impact injuries.
    "contusion": [
        "bruise", "bruised", "black and blue",
        "discoloration", "discolored",
        "kicked", "kneed", "elbowed",
        "dead leg", "corked", "cork",
        "dent", "dented", "indent", "indentation",
        "hit", "struck", "banged", "banged up",
        "trauma", "traumatic", "blunt", "blunt force",
        "from strike", "from kick", "from knee", "from elbow", "from hit"
    ],

    # Swelling - every fluid retention phrase
    "swelling": [
        "swell", "swollen", "swelling", "puffy", "puffiness", "inflamed",
        "inflammation", "balloon", "ballooned", "blown up", "bloated",
        "pumped", "pumped up", "full", "fullness", "round", "rounded",
        "heat", "warmth", "fluid", "fluid retention",
        "edema", "oedema", "can't see bone", "can't see definition",
        "looks fat", "looks bigger", "looks swollen", "looks puffy",
        "like a balloon", "like a melon", "like a sausage"
    ],

    # Tendon Overuse - every chronic tendon phrase
    # Includes patellar-specific terms added to fix misclassification of jumper's knee
    # and patellar tendinopathy as contusions instead of tendonitis.
    "tendonitis": [
        "tendon pain", "tendon ache", "tendon sore", "tendon hurt",
        "tendonitis", "tendinosis", "tendinopathy", "grind",
        "gritty", "grittiness", "flare", "flare up",
        "overuse", "repetitive",
        "angry", "irritated", "irritation",
        "acting up", "playing up", "misbehaving", "problem area",
        "always sore", "always hurts", "never goes away",
        "recurring", "comes and goes", "use pain", "activity pain",
        "patellar tendon", "patellar tendinopathy",
        "jumper's knee", "jumpers knee", "jumper knee"
    ],

    # Pinching - every joint catching phrase
    "impingement": [
        "pinch", "pinching", "click", "clicking", "clunk", "clunking",
        "catch", "catching", "jam", "jamming", "block", "blocking",
        "won't lift", "won't raise", "won't reach",
        "painful arc", "painful range", "limited by pain", "stopped by pain",
        "shoulder catch", "hip catch", "elbow catch", "wrist catch",
        "ankle catch", "knee catch", "joint catch", "bone on bone",
        "rubbing", "grinding", "bone rub", "impinge", "impingement"
    ],

    # Joint Instability - every giving way phrase
    "instability": [
        "loose", "looseness", "slip", "slipping", "slide", "sliding",
        "unreliable", "unstable", "instability", "scary", "fear",
        "apprehension", "nervous", "nervousness", "hesitant", "hesitation",
        "trust issues", "don't trust", "afraid to move", "scared to move",
        "feels wrong", "feels off", "feels loose", "feels unstable",
        "feels unreliable", "feels dangerous", "feels unsafe"
    ],

    # Stiff Joint - every limited motion phrase
    "stiffness": [
        "stiff", "stiffness", "frozen", "freezing", "rusty", "rusted",
        "stuck", "sticking", "won't move", "won't bend", "won't flex",
        "won't extend", "won't rotate", "won't turn", "won't twist",
        "limited", "limitation", "reduced", "reduction", "restricted",
        "restriction", "can't move", "can't bend", "can't flex",
        "can't extend", "can't rotate", "can't turn", "can't twist",
        "morning", "first thing", "after rest", "after sitting",
        "after sleeping", "needs cracking", "needs popping", "needs loosening",
        "needs warming", "needs working", "needs mobilization"
    ],

    # General Pain - every pain descriptor
    "pain": [
        "pain", "painful", "hurt", "hurting", "ache", "aching",
        "soring", "sharp", "sharper", "stabbing", "sting", "stinging",
        "throb", "throbbing", "pulse", "pulsing", "burn", "burning",
        "nag", "nagging", "constant", "persistent", "ongoing", "chronic",
        "acute", "radiating", "radiate", "shooting", "traveling", "moving",
        "deep", "internal", "localized",
        "diffuse", "spread", "spreading", "widespread", "focused", "focal",
        "point", "specific", "general", "all over", "everywhere", "nowhere",
        "shin splint", "shin splints", "medial tibial stress syndrome", "mtss",
    ],

    # Soreness - every recovery phrase
    "soreness": [
        "sore", "soreness", "doms", "delayed", "delayed onset", "muscle soreness",
        "muscle pain", "muscle ache", "muscle hurt", "muscle fatigue",
        "beat up", "beaten up", "worked", "worked out", "trained", "trained hard",
        "recovery", "recovering", "post workout", "post training", "post session",
        "after workout", "after training", "after session", "next day", "next morning",
        "48 hour", "48 hours", "two day", "two days", "good pain", "good hurt",
        "bad pain", "bad hurt", "too much", "overdid it", "pushed too hard",
        "went too hard", "over trained", "over worked", "over reached"
    ],

    # Hyperextension - every overstretched phrase
    "hyperextension": [
        "hyperextend", "hyperextended", "hyperextension", "overextend", "overextended",
        "overextension", "overstretch", "overstretched", "overstretching",
        "bent back", "bent backward", "bent backwards", "folded back", "folded backward",
        "folded backwards", "locked out", "locked back", "locked backward",
        "locked backwards", "too far", "went too far", "pushed too far",
        "extended too far", "straightened too far", "reversed", "reversal",
        "backwards", "backward", "wrong way", "opposite way", "other way",
        "knee hyperextend", "elbow hyperextend", "wrist hyperextend",
        "finger hyperextend", "toe hyperextend", "joint hyperextend"
    ],

    # Vague catch-all type has no specific synonyms. Any description that
    # fails to match the above categories is treated as "unspecified".
    "unspecified": []
}

LEGACY_LOCATION_MAP = {
    # Toes and foot
    "toe": "toe",
    "toes": "toe",
    "big toe": "toe",
    "pinky toe": "toe",
    "toenail": "toe",
    "digit": "toe",
    "first toe": "toe",
    "second toe": "toe",
    "third toe": "toe",
    "fourth toe": "toe",
    "phalanges": "toe",
    "toe bones": "toe",
    "distal phalanx": "toe",
    "middle phalanx": "toe",
    "proximal phalanx": "toe",
    "toe knuckles": "toe",
    "toe joints": "toe",
    "hallux": "toe",
    "lesser toes": "toe",
    "foot": "foot",
    "feet": "foot",
    "forefoot": "foot",
    "midfoot": "foot",
    "hindfoot": "foot",
    "sole": "foot",
    "arch": "foot",
    "instep": "foot",
    "ball of foot": "foot",
    "outside foot": "foot",
    "inside foot": "foot",
    "metatarsals": "foot",
    "metatarsal": "foot",
    "tarsals": "foot",
    "foot bones": "foot",
    "navicular": "foot",
    "cuboid": "foot",
    "cuneiforms": "foot",
    "arch bones": "foot",
    "heel": "heel",
    "heels": "heel",
    "heel bone": "heel",
    "calcaneus": "heel",
    "back of foot": "heel",
    "heel pad": "heel",
    "calcaneal tuberosity": "heel",
    "ankle": "ankle",
    "ankles": "ankle",
    "ankle joint": "ankle",
    "malleolus": "ankle",
    "lateral ankle": "ankle",
    "medial ankle": "ankle",
    "talus": "ankle",
    "ankle bones": "ankle",
    "malleoli": "ankle",
    "medial malleolus": "ankle",
    "lateral malleolus": "ankle",
    "ankle knobs": "ankle",
    "achilles": "achilles",
    "achilles tendon": "achilles",
    "tendo calcaneus": "achilles",
    "heel cord": "achilles",
    "calf tendon": "achilles",
    "heel attachment": "achilles",
    "arm": "unspecified",
    "arms": "unspecified",
    "upper arm": "unspecified",
    "upper arms": "unspecified",
    "lower arm": "forearm",
    "lower arms": "forearm",
    "bicep": "biceps",
    "biceps": "biceps",
    "front arm": "biceps",
    "guns": "biceps",
    "short head": "biceps",
    "long head": "biceps",
    "humerus": "biceps",
    "upper arm bone": "biceps",
    "calf": "calf",
    "calves": "calf",
    "gastrocnemius": "calf",
    "soleus": "calf",
    "back of leg": "calf",
    "fibula": "shin",
    "outer calf bone": "shin",
    "chest": "chest",
    "pec": "chest",
    "pecs": "chest",
    "pectorals": "chest",
    "sternum": "chest",
    "breastbone": "chest",
    "upper chest": "chest",
    "ribs": "chest",
    "rib cage": "chest",
    "collarbone": "chest",
    "core": "core",
    "abs": "core",
    "abdominal": "core",
    "six pack": "core",
    "transverse": "core",
    "rectus": "core",
    "elbow": "elbow",
    "elbows": "elbow",
    "funny bone": "elbow",
    "olecranon": "elbow",
    "elbow joint": "elbow",
    "elbow bone": "elbow",
    "eye": "eye",
    "eyes": "eye",
    "eyeball": "eye",
    "orbital": "eye",
    "eyelid": "eye",
    "socket": "eye",
    "face": "face",
    "cheek": "face",
    "facial cheek": "face",
    "face cheek": "face",
    "cheekbone": "face",
    "jawbone": "jaw",
    "brow": "face",
    "zygomatic": "face",
    "maxilla": "face",
    "mandible": "face",
    "nasal": "face",
    "nose bone": "face",
    "fingers": "fingers",
    "finger": "fingers",
    "digits": "fingers",
    "thumb": "fingers",
    "index": "fingers",
    "middle": "fingers",
    "metacarpals": "fingers",
    "metacarpal": "fingers",
    "finger bones": "fingers",
    "knuckles": "hand",
    "forearm": "forearm",
    "forearms": "forearm",
    "wrist extensors": "forearm",
    "forearm bones": "forearm",
    "glutes": "glutes",
    "butt": "glutes",
    "buttocks": "glutes",
    "ass": "glutes",
    "cheeks": "unspecified",
    "butt cheek": "glutes",
    "butt cheeks": "glutes",
    "glute cheek": "glutes",
    "glute cheeks": "glutes",
    "backside": "glutes",
    "coccyx": "glutes",
    "pelvis": "glutes",
    "groin": "groin",
    "adductors": "groin",
    "inner thigh": "groin",
    "inner leg": "groin",
    "pubic": "groin",
    "pubis": "groin",
    "ischium": "groin",
    "pelvic bones": "groin",
    "hamstring": "hamstring",
    "hamstrings": "hamstring",
    "hammies": "hamstring",
    "hammy": "hamstring",
    "back of thigh": "hamstring",
    "back thigh": "hamstring",
    "rear thigh": "hamstring",
    "posterior thigh": "hamstring",
    "biceps femoris": "hamstring",
    "femur": "unspecified",
    "thigh bone": "unspecified",
    "hand": "hand",
    "hands": "hand",
    "palm": "hand",
    "thenar": "hand",
    "carpals": "hand",
    "hand bones": "hand",
    "hip": "hip",
    "hips": "hip",
    "hip flexor": "hip",
    "hipflexor": "hip",
    "hipflexors": "hip",
    "hip flexors": "hip",
    "hip joint": "hip",
    "iliac": "hip",
    "acetabulum": "hip",
    "femur head": "hip",
    "hip socket": "hip",
    "hip ball": "hip",
    "jaw": "jaw",
    "chin": "jaw",
    "tmj": "jaw",
    "jawline": "jaw",
    "jaw joint": "jaw",
    "upper jaw": "jaw",
    "knee": "knee",
    "knees": "knee",
    "patella": "knee",
    "kneecap": "knee",
    "knee joint": "knee",
    "acl": "knee",
    "mcl": "knee",
    "lcl": "knee",
    "pcl": "knee",
    "meniscus": "knee",
    "cruciate": "knee",
    "cruciate ligament": "knee",
    "medial ligament": "knee",
    "lateral ligament": "knee",
    "posterior ligament": "knee",
    "anterior ligament": "knee",
    "lower back": "lower back",
    "lower_back": "lower back",
    "spine": "unspecified",
    "lumbar": "lower back",
    "l-spine": "lower back",
    "sacrum": "lower back",
    "tailbone": "lower back",
    "lumbar vertebrae": "lower back",
    "lower spine": "lower back",
    "base of spine": "lower back",
    "neck": "neck",
    "cervical": "neck",
    "c-spine": "neck",
    "trapezius": "neck",
    "throat": "neck",
    "sternocleidomastoid": "neck",
    "cervical vertebrae": "neck",
    "neck spine": "neck",
    "obliques": "obliques",
    "love handles": "obliques",
    "side abs": "obliques",
    "waist": "obliques",
    "external obliques": "obliques",
    "side ribs": "obliques",
    "leg": "unspecified",
    "legs": "unspecified",
    "lower leg": "shin",
    "lower legs": "shin",
    "quad": "quads",
    "quads": "quads",
    "quadriceps": "quads",
    "thigh": "quads",
    "outer thigh": "quads",
    "upper thigh": "quads",
    "upper leg": "quads",
    "upper legs": "quads",
    "thighs": "quads",
    "front thigh": "quads",
    "vastus lateralis": "quads",
    "shin": "shin",
    "shins": "shin",
    "tibia": "shin",
    "front of leg": "shin",
    "shin bone": "shin",
    "outer shin": "shin",
    "shoulder": "shoulder",
    "shoulders": "shoulder",
    "deltoid": "shoulder",
    "rotator cuff": "shoulder",
    "shoulder blade": "shoulder",
    "scapula": "shoulder",
    "clavicle": "chest",
    "humerus head": "shoulder",
    "arm ball": "shoulder",
    "tricep": "triceps",
    "triceps": "triceps",
    "back arm": "triceps",
    "horseshoe": "triceps",
    "upper back": "upper back",
    "thoracic": "upper back",
    "t-spine": "upper back",
    "rhomboids": "upper back",
    "traps": "upper back",
    "middle back": "upper back",
    "thoracic vertebrae": "upper back",
    "upper spine": "upper back",
    "wrist": "wrist",
    "wrists": "wrist",
    "carpal": "wrist",
    "scaphoid": "wrist",
    "lunate": "wrist",
    "radius": "wrist",
    "ulna": "wrist",
    "forearm ends": "wrist",
}

LOCATION_MAP = dict(LEGACY_LOCATION_MAP)
LOCATION_MAP.update(build_location_synonym_map())

register_negation_targets(
    list(INJURY_SYNONYM_MAP.keys())
    + [syn for syns in INJURY_SYNONYM_MAP.values() for syn in syns]
    + list(LOCATION_MAP.keys())
)


def canonicalize_injury_type(text: str, threshold: int = 85) -> str | None:
    """
    Return the canonical injury type using:
    1) Phrase matches (non-negated) to collect candidates,
    2) Exclusive-hint scoring to separate overlapping categories (e.g., sprain vs instability),
    3) Fuzzy fallback with per-category thresholds,
    4) Priority tie-breaks via TYPE_PRIORITY.
    """
    from .injury_scoring import score_injury_phrase

    scored = score_injury_phrase(text or "")
    scored_type = scored.get("injury_type")
    if scored_type and scored_type != "unspecified":
        return scored_type

    nlp = get_nlp()
    if not nlp:
        lowered = text.lower()
        for canonical, syns in INJURY_SYNONYM_MAP.items():
            for phrase in [canonical] + syns:
                if _phrase_in_text(phrase, lowered):
                    return canonical
        return None
    doc = nlp(text.lower())
    injury_matcher, injury_map, _, _ = get_matchers(nlp)
    if not injury_matcher:
        return None

    candidates: dict[str, float] = {}

    # 1) Phrase matcher first (fast / precise), ignore negated spans
    hits = []
    for match_id, start, end in injury_matcher(doc):
        span = doc[start:end]
        if any(tok._.negex for tok in span):
            continue
        hits.append(injury_map.get(match_id))

    for c in hits:
        if not c:
            continue
        # Base score for a direct phrase hit
        candidates[c] = candidates.get(c, 0.0) + 1.5

    # 2) Exclusive-hints to disambiguate overlaps
    text_no_neg = " ".join(tok.text for tok in doc if not tok._.negex)
    for cat, hints in EXCLUSIVE_HINTS.items():
        if any(_phrase_in_text(h, text_no_neg) for h in hints):
            candidates[cat] = candidates.get(cat, 0.0) + 1.0

    # Conservative gating for low-specificity tokens
    if "impingement" in candidates:
        has_gate = any(_phrase_in_text(h, text_no_neg) for h in IMPINGEMENT_GATE_HINTS)
        has_low = any(_phrase_in_text(h, text_no_neg) for h in IMPINGEMENT_LOW_SPECIFICITY)
        if has_low and not has_gate:
            candidates.pop("impingement", None)

    if "tendonitis" in candidates:
        if not any(_phrase_in_text(h, text_no_neg) for h in TENDONITIS_REQUIRED_HINTS):
            candidates.pop("tendonitis", None)

    # Deterministic precedence among soreness/stiffness/tightness/pain
    if not (set(candidates.keys()) - {"soreness", "stiffness", "tightness", "pain"}):
        if any(_phrase_in_text(h, text_no_neg) for h in SORENESS_HINTS):
            return "soreness"
        if any(_phrase_in_text(h, text_no_neg) for h in STIFFNESS_HINTS):
            return "stiffness"
        if any(_phrase_in_text(h, text_no_neg) for h in TIGHTNESS_HINTS):
            return "tightness"
        if "pain" in candidates:
            return "pain"

    # 3) Fuzzy fallback on the cleaned text (non-negated tokens only)
    cleaned = text_no_neg.strip()
    if cleaned and not candidates:
        for canonical, synonyms in INJURY_SYNONYM_MAP.items():
            thr = FUZZY_THRESHOLDS.get(canonical, threshold)
            if fuzz.partial_ratio(canonical, cleaned) >= thr:
                candidates[canonical] = candidates.get(canonical, 0.0) + 0.9
            for phrase in synonyms:
                if fuzz.partial_ratio(phrase, cleaned) >= thr:
                    candidates[canonical] = candidates.get(canonical, 0.0) + 0.8

    if not candidates:
        return None

    # 4) Apply category priority as a tie-break modifier
    def _final_score(cat: str, base: float) -> float:
        return base * TYPE_PRIORITY.get(cat, 0.1)

    best_cat = max(candidates.items(), key=lambda kv: _final_score(kv[0], kv[1]))[0]

    # Special rule: if both "sprain" and "instability" are present, force decision by hints.
    if {"sprain", "instability"}.issubset(set(candidates.keys())):
        sprain_hint = any(_phrase_in_text(h, text_no_neg) for h in EXCLUSIVE_HINTS["sprain"])
        instab_hint = any(_phrase_in_text(h, text_no_neg) for h in EXCLUSIVE_HINTS["instability"])
        if sprain_hint and not instab_hint:
            return "sprain"
        if instab_hint and not sprain_hint:
            return "instability"
        # If both/neither hints: keep priority-based winner already chosen.
    return best_cat


LOCATION_MAP = {**LEGACY_LOCATION_MAP, **build_location_synonym_map()}


def canonicalize_location(text: str, threshold: int = 85) -> str | None:
    """
    Return canonical location with:
    1) Phrase match (non-negated),
    2) Context routing for 'spine/back' mentions into neck / upper_back / lower_back,
    3) Fuzzy fallback (partial-ratio).
    """
    nlp = get_nlp()
    if not nlp:
        lowered = text.lower()
        for key in sorted(LOCATION_MAP.keys(), key=len, reverse=True):
            if _phrase_in_text(key, lowered):
                return LOCATION_MAP[key]
        return None
    doc = nlp(text.lower())
    _, _, location_matcher, location_map = get_matchers(nlp)
    if not location_matcher:
        return None

    # 1) Phrase match (fast), ignore negated spans
    for match_id, start, end in location_matcher(doc):
        span = doc[start:end]
        if any(tok._.negex for tok in span):
            continue
        loc = location_map.get(match_id)
        matched_text = span.text.lower()

        # 2) Context routing if spine/back-ish
        txt = text.lower()
        if _phrase_in_text("spine", txt) or _phrase_in_text("back", txt):
            # Explicit posterior-thigh phrases must beat generic back routing.
            if matched_text in POSTERIOR_THIGH_HINTS:
                return loc
            if any(_phrase_in_text(h, txt) for h in SPINE_HINTS["neck"]):
                return "neck"
            if any(_phrase_in_text(h, txt) for h in SPINE_HINTS["upper_back"]):
                return "upper back"
            if any(_phrase_in_text(h, txt) for h in SPINE_HINTS["lower_back"]):
                return "lower back"
            return None if loc == "unspecified" else loc

        return loc

    # 3) Fuzzy fallback on non-negated tokens only
    cleaned = " ".join(tok.text for tok in doc if not tok._.negex).strip()
    if not cleaned:
        return None
    best = None
    best_score = 0
    for key, canonical in LOCATION_MAP.items():
        if len(key) <= 4:
            continue
        score = fuzz.partial_ratio(key, cleaned)
        if score >= threshold and score > best_score:
            best = canonical
            best_score = score

    # Context routing for spine/back if we only reached fuzzy stage
    if best in {None, "lower back"}:
        txt = cleaned
        if _phrase_in_text("spine", txt) or _phrase_in_text("back", txt):
            if any(_phrase_in_text(h, txt) for h in SPINE_HINTS["neck"]):
                return "neck"
            if any(_phrase_in_text(h, txt) for h in SPINE_HINTS["upper_back"]):
                return "upper back"
            if any(_phrase_in_text(h, txt) for h in SPINE_HINTS["lower_back"]):
                return "lower back"
            return None

    return best


def parse_injury_phrase(phrase: str) -> tuple[str | None, str | None]:
    """Extract canonical injury type and location from an injury phrase."""
    cleaned = remove_negated_phrases(phrase.lower())
    cleaned = _strip_surrounding_punct(cleaned)
    if not cleaned:
        return None, None
    if detect_structural_red_flags(cleaned):
        return "unspecified", canonicalize_location(cleaned)
    tendonitis_hard_map_terms = {
        "tendonitis",
        "tendinitis",
        "tennis elbow",
        "golfer's elbow",
        "golfers elbow",
        "golfer’s elbow",
    }
    if any(term in cleaned for term in tendonitis_hard_map_terms):
        location = canonicalize_location(cleaned)
        if location is None and ("elbow" in cleaned):
            location = "elbow"
        return "tendonitis", location
    doc_text = cleaned
    injury_type = canonicalize_injury_type(doc_text)
    location = canonicalize_location(doc_text)
    return injury_type, location


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

_AND_PROTECT_TOKEN = "__inj_and_keep__"
_BOUNDARY_PATTERN = compile_regex("injury_synonyms", "boundary_pattern")
_AND_PATTERN = compile_regex("injury_synonyms", "and_pattern", flags=re.IGNORECASE)

_BODY_PART_HINTS = {
    "ankle", "wrist", "shoulder", "knee", "hip", "back", "elbow", "hand", "foot",
    "calf", "hamstring", "quad", "groin", "neck", "shin", "thigh",
}
_MECHANISM_CONTINUATION_HINTS = {
    "gave way", "twisted", "locked", "felt unstable", "overextended", "buckled", "planted",
    "gave", "way", "unstable", "plant", "locked up",
}


def _contains_hint(text: str, hints: set[str]) -> bool:
    lowered = f" {text.lower()} "
    return any(f" {hint} " in lowered for hint in hints)


def _protect_mechanism_and_connectors(text: str) -> str:
    if " and " not in text.lower():
        return text
    result = text
    offset = 0
    for match in _AND_PATTERN.finditer(text):
        start, end = match.span()
        left_boundary = max([m.end() for m in _BOUNDARY_PATTERN.finditer(text, 0, start)] or [0])
        right_match = _BOUNDARY_PATTERN.search(text, end)
        right_boundary = right_match.start() if right_match else len(text)
        left = text[left_boundary:start].strip()
        right = text[end:right_boundary].strip()
        if not left or not right:
            continue
        left_has_body = _contains_hint(left, _BODY_PART_HINTS)
        right_has_body = _contains_hint(right, _BODY_PART_HINTS)
        right_mechanism_only = _contains_hint(right, _MECHANISM_CONTINUATION_HINTS) and not right_has_body
        if left_has_body and right_mechanism_only:
            patched_start = start + offset
            patched_end = end + offset
            result = result[:patched_start] + _AND_PROTECT_TOKEN + result[patched_end:]
            offset += len(_AND_PROTECT_TOKEN) - (end - start)
    return result


def _merge_mechanism_continuation_phrases(phrases: list[str]) -> list[str]:
    merged: list[str] = []
    for phrase in phrases:
        if (
            merged
            and _contains_hint(merged[-1], _BODY_PART_HINTS)
            and _contains_hint(phrase, _MECHANISM_CONTINUATION_HINTS)
            and not _contains_hint(phrase, _BODY_PART_HINTS)
        ):
            merged[-1] = f"{merged[-1]} {phrase}".strip()
            continue
        merged.append(phrase)
    return merged


def _normalize_injury_text_separators(text: str) -> str:
    normalized = text
    for sep in [*_INJURY_TEXT_SEPARATORS, *_LEGACY_MOJIBAKE_DASH_SEPARATORS]:
        normalized = normalized.replace(sep, ". ")
    return normalized


def split_injury_text(raw_text: str) -> list[str]:
    """Normalize free-form injury text into a list of phrases using spaCy."""
    nlp = get_nlp()
    if not nlp:
        if not raw_text:
            return []
        text = _protect_mechanism_and_connectors(raw_text.lower())
        text = re.sub(r"[()]", " ", text)
        text = re.sub(r"\b(and|but|also)\b,?", ". ", text)
        text = _normalize_injury_text_separators(text)
        phrases = [
            cleaned.replace(_AND_PROTECT_TOKEN, " and ")
            for chunk in text.split(".")
            if (cleaned := _strip_surrounding_punct(chunk))
        ]
        return _merge_mechanism_continuation_phrases(phrases)
    text = _protect_mechanism_and_connectors(raw_text.lower())
    text = re.sub(r"[()]", " ", text)
    # Replace common connectors with punctuation so spaCy can split sentences
    text = re.sub(r"\b(and|but|also)\b,?", ". ", text)
    text = _normalize_injury_text_separators(text)
    doc = nlp(text)
    phrases = [
        cleaned.replace(_AND_PROTECT_TOKEN, " and ")
        for sent in doc.sents
        if (cleaned := _strip_surrounding_punct(sent.text))
    ]
    return _merge_mechanism_continuation_phrases(phrases)
