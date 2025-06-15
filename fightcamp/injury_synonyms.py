INJURY_SYNONYM_MAP = {
    # Ligament - now with every joint instability phrase imaginable
    "sprain": [
        "pop", "popped", "pop sound", "rolling", "rolled", "twist", "twisted",
        "wobbly", "wobble", "unstable", "instability", "gave way", "gave out",
        "folded", "buckled", "collapse", "loose", "shifty", "slippy", "sliding",
        "tore ligament", "ligament pop", "ligament tear", "ligament gone",
        "joint separation", "joint shift", "knee went", "ankle went", "wrist went",
        "partial dislocation", "sublux", "subluxation", "dislocate", "dislocated",
        "out of socket", "popped out", "click out", "shift out", "unhinged",
        "grade 1", "grade 2", "grade 3", "hyperextend", "overstretched", "overextension",
        "stretched ligament", "torn ligament", "ruptured ligament", "blown ligament",
        "sprain", "sprained", "inversion", "eversion", "rolled over", "turned over",
        "acl", "acl tear", "acl injury", "acl surgery", "acl reconstruction",
        "acl rehab"
    ],

    # Muscle/Tendon - every possible pull/tear description
    "strain": [
        "pull", "pulled", "tug", "tugged", "tear", "torn", "rip", "ripped",
        "cramp", "cramping", "charley horse", "dead leg", "seize", "seized",
        "lock", "locked", "knot", "knotted", "ball", "balled", "grab", "grabbed",
        "ping", "pinged", "twinge", "twinging", "sharp pain", "acute pain",
        "muscle tear", "muscle rupture", "muscle pop", "muscle snap", "muscle went",
        "tendon tear", "tendon pop", "tendon snap", "tendon rupture",
        "hamstring", "calf", "quad", "groin", "pec", "bicep", "tricep",
        "strain", "strained", "grade 1", "grade 2", "grade 3", "muscle failure",
        "tendon failure", "overstretched", "overworked", "worked too hard"
    ],

    # Tightness - every stiffness phrase
    "tightness": [
        "tight", "tightness", "stiff", "stiffness", "locked", "locking",
        "won't move", "restricted", "stuck", "glued", "frozen", "rusty",
        "needs cracking", "needs popping", "needs release", "needs stretching",
        "hard to move", "limited motion", "reduced range", "can't extend",
        "can't flex", "can't rotate", "can't reach", "can't stretch",
        "morning stiffness", "first move", "warming up", "slow to loosen",
        "like a rock", "like concrete", "like a board", "like a log",
        "needs massage", "needs foam roll", "needs lacrosse ball"
    ],

    # Bruise - every impact description
    "contusion": [
        "bruise", "bruised", "abrase", "abrasion", "black", "blue", "black and blue", "purple",
        "discoloration", "discolored", "kicked", "knee", "kneed", "elbow",
        "elbowed", "dead leg", "corked", "cork", "impact", "swollen",
        "dent", "dented", "indent", "indentation", "mark", "marked",
        "hit", "hitted", "struck", "stricken", "banged", "banged up",
        "trauma", "traumatic", "blunt", "blunt force", "from strike",
        "from kick", "from knee", "from elbow", "from impact", "from hit"
    ],

    # Swelling - every fluid retention phrase
    "swelling": [
        "swell", "swollen", "swelling", "puffy", "puffiness", "inflamed",
        "inflammation", "balloon", "ballooned", "blown up", "bloated",
        "pumped", "pumped up", "full", "fullness", "round", "rounded",
        "hot", "heat", "warm", "warmth", "fluid", "fluid retention",
        "edema", "oedema", "can't see bone", "can't see definition",
        "looks fat", "looks bigger", "looks swollen", "looks puffy",
        "like a balloon", "like a melon", "like a sausage"
    ],

    # Tendon Overuse - every chronic tendon phrase
    "tendonitis": [
        "tendon", "tendon pain", "tendon ache", "tendon sore", "tendon hurt",
        "tendonitis", "tendinosis", "tendinopathy", "grinding", "grind",
        "gritty", "grittiness", "achy", "aching", "flare", "flare up",
        "burn", "burning", "overuse", "repetitive", "chronic", "constant",
        "tender", "tenderness", "angry", "irritated", "irritation",
        "acting up", "playing up", "misbehaving", "problem area",
        "always sore", "always hurts", "never goes away", "persistent",
        "recurring", "comes and goes", "use pain", "activity pain"
    ],

    # Pinching - every joint catching phrase
    "impingement": [
        "pinch", "pinching", "click", "clicking", "clunk", "clunking",
        "catch", "catching", "jam", "jamming", "block", "blocking",
        "stuck", "sticking", "won't lift", "won't raise", "won't rotate",
        "won't turn", "won't reach", "won't extend", "won't move",
        "painful arc", "painful range", "limited by pain", "stopped by pain",
        "shoulder catch", "hip catch", "elbow catch", "wrist catch",
        "ankle catch", "knee catch", "joint catch", "bone on bone",
        "rubbing", "grinding", "bone rub", "impinge", "impingement"
    ],

    # Joint Instability - every giving way phrase
    "instability": [
        "loose", "looseness", "slip", "slipping", "slide", "sliding",
        "dislocate", "dislocating", "sublux", "subluxation", "partial",
        "partial dislocation", "give way", "giving way", "gave way",
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
        "pain", "painful", "hurt", "hurting", "ache", "aching", "sore",
        "soring", "sharp", "sharper", "stabbing", "sting", "stinging",
        "throb", "throbbing", "pulse", "pulsing", "burn", "burning",
        "nag", "nagging", "graze", "grazed", "constant", "persistent", "ongoing", "chronic",
        "acute", "radiating", "radiate", "shooting", "traveling", "moving",
        "deep", "superficial", "surface", "internal", "external", "localized",
        "diffuse", "spread", "spreading", "widespread", "focused", "focal",
        "point", "specific", "general", "all over", "everywhere", "nowhere"
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

LOCATION_MAP = {
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
    "fibula": "calf",
    "outer calf bone": "calf",
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
    "cheeks": "face",
    "backside": "glutes",
    "coccyx": "glutes",
    "pelvis": "glutes",
    "groin": "groin",
    "adductors": "groin",
    "inner thigh": "groin",
    "pubic": "groin",
    "pubis": "groin",
    "ischium": "groin",
    "pelvic bones": "groin",
    "hamstring": "hamstring",
    "hamstrings": "hamstring",
    "hammies": "hamstring",
    "hammy": "hamstring",
    "posterior thigh": "hamstring",
    "biceps femoris": "hamstring",
    "femur": "hamstring",
    "thigh bone": "hamstring",
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
    "spine": "lower back",
    "lumbar": "lower back",
    "sacrum": "lower back",
    "tailbone": "lower back",
    "lumbar vertebrae": "lower back",
    "lower spine": "lower back",
    "base of spine": "lower back",
    "neck": "neck",
    "cervical": "neck",
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
    "quad": "quads",
    "quads": "quads",
    "quadriceps": "quads",
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
    "clavicle": "shoulder",
    "humerus head": "shoulder",
    "arm ball": "shoulder",
    "tricep": "triceps",
    "triceps": "triceps",
    "back arm": "triceps",
    "horseshoe": "triceps",
    "upper back": "upper back",
    "thoracic": "upper back",
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


from rapidfuzz import fuzz
import spacy
from spacy.matcher import PhraseMatcher
from negspacy.negation import Negex
from spacy.tokens import Token  # ✅ needed to register extensions

# load the large english model once
try:
    nlp = spacy.load("en_core_web_lg")
except Exception:  # pragma: no cover - model might not be available in tests
    nlp = spacy.blank("en")

# register the .negex extension (avoid AttributeError)
Token.set_extension("negex", default=False, force=True)

# add Negex for negation detection
try:
    nlp.add_pipe("negex", last=True)
except Exception:  # pragma: no cover - Negex might not be registered
    nlp.add_pipe(Negex(nlp), last=True)
# Build phrase matchers for injury and location keywords
INJURY_MATCHER = PhraseMatcher(nlp.vocab, attr="LOWER")
INJURY_MATCH_ID_TO_CANONICAL: dict[int, str] = {}
for _canonical, _syns in INJURY_SYNONYM_MAP.items():
    patterns = [_canonical] + _syns
    docs = [nlp(p) for p in patterns]
    match_id = nlp.vocab.strings.add(_canonical)
    INJURY_MATCHER.add(_canonical, docs)
    INJURY_MATCH_ID_TO_CANONICAL[match_id] = _canonical

LOCATION_MATCHER = PhraseMatcher(nlp.vocab, attr="LOWER")
LOC_MATCH_ID_TO_CANONICAL: dict[int, str] = {}
for _key, _canonical in LOCATION_MAP.items():
    doc = nlp(_key)
    match_id = nlp.vocab.strings.add(_key)
    LOCATION_MATCHER.add(_key, [doc])
    LOC_MATCH_ID_TO_CANONICAL[match_id] = _canonical

def remove_negated_phrases(text: str) -> str:
    """Strip words marked as negated by Negex from the text."""
    doc = nlp(text)
    tokens = [tok.text for tok in doc if not tok._.negex]
    return " ".join(tokens).strip()

def canonicalize_injury_type(text: str, threshold: int = 85) -> str | None:
    """Return the canonical injury type for the given text using spaCy."""
    doc = nlp(text.lower())

    # phrase matcher first - skip spans that contain negated tokens
    for match_id, start, end in INJURY_MATCHER(doc):
        span = doc[start:end]
        if any(tok._.negex for tok in span):
            continue
        return INJURY_MATCH_ID_TO_CANONICAL.get(match_id)

    # fallback to fuzzy matching on non-negated tokens only
    cleaned = " ".join(tok.text for tok in doc if not tok._.negex).strip()
    if not cleaned:
        return None
    for canonical, synonyms in INJURY_SYNONYM_MAP.items():
        if fuzz.partial_ratio(canonical, cleaned) >= threshold:
            return canonical
        for phrase in synonyms:
            if fuzz.partial_ratio(phrase, cleaned) >= threshold:
                return canonical
    return None


def canonicalize_location(text: str, threshold: int = 85) -> str | None:
    """Return the canonical body part for the provided text using spaCy."""
    doc = nlp(text.lower())

    # phrase matcher, skip spans containing negated tokens
    for match_id, start, end in LOCATION_MATCHER(doc):
        span = doc[start:end]
        if any(tok._.negex for tok in span):
            continue
        return LOC_MATCH_ID_TO_CANONICAL.get(match_id)

    cleaned = " ".join(tok.text for tok in doc if not tok._.negex).strip()
    if not cleaned:
        return None
    for key, canonical in LOCATION_MAP.items():
        if len(key) > 4 and fuzz.partial_ratio(key, cleaned) >= threshold:
            return canonical
    return None


def parse_injury_phrase(phrase: str) -> tuple[str | None, str | None]:
    """Extract canonical injury type and location from an injury phrase."""
    doc_text = phrase.lower()
    injury_type = canonicalize_injury_type(doc_text)
    location = canonicalize_location(doc_text)
    return injury_type, location


def split_injury_text(raw_text: str) -> list[str]:
    """Normalize free-form injury text into a list of phrases using spaCy."""
    text = raw_text.lower()
    # Replace common connectors with punctuation so spaCy can split sentences
    for sep in [",", ";", "\n", " - ", " – ", " — ", " and ", " but ", " then ", " also "]:
        text = text.replace(sep, ". ")
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]