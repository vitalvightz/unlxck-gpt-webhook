import json
import logging
from typing import Iterable, Mapping

from .injury_formatting import format_injury_summary, parse_injury_entry
from .injury_guard import INJURY_TYPE_SEVERITY, normalize_severity
from .injury_registry import (
    MINOR_SURFACE_TRAIN_THROUGH_TYPES,
    SURFACE_MINOR_TRAIN_THROUGH_NOTE,
    SURFACE_TISSUE_TYPES,
)
from .injury_taxonomy import derive_red_flag_types, derive_urgent_injury_tokens
from .injury_synonyms import parse_injury_phrase, split_injury_text
from .injury_location import canonicalize_location, get_injury_location
from .injury_location_registry import build_location_region_map, get_rehab_location_candidates
from .rehab_schema import (
    REHAB_STAGES,
    normalize_severity_bucket,
    split_phase_progression,
)
from .rehab_selector import select_rehab_candidate
from .restriction_parsing import ParsedRestriction
# Refactored: Import centralized DATA_DIR from config
from .config import DATA_DIR
logger = logging.getLogger(__name__)

# Rehab bank stores entries with fields like:
# {
#     "location": "ankle",
#     "type": "sprain",
#     "phase_progression": "GPP → SPP",
#     "drills": [
#         {"name": "...", "notes": "..."},
#         {"name": "...", "notes": "..."}
#     ]
# }
_REHAB_BANK_CACHE = None
_REHAB_LOCATIONS_CACHE = None
_REHAB_DRILLS_BY_ID_CACHE = None
_EXERCISE_BANK_CACHE = None


def get_rehab_bank() -> list[dict]:
    global _REHAB_BANK_CACHE
    if _REHAB_BANK_CACHE is None:
        _REHAB_BANK_CACHE = json.loads(
            (DATA_DIR / "rehab_bank.json").read_text(encoding="utf-8")
        )
    return _REHAB_BANK_CACHE


def get_rehab_locations() -> set[str]:
    global _REHAB_LOCATIONS_CACHE
    if _REHAB_LOCATIONS_CACHE is None:
        _REHAB_LOCATIONS_CACHE = {
            entry.get("location") for entry in get_rehab_bank() if entry.get("location")
        }
    return _REHAB_LOCATIONS_CACHE


def rehab_drill_by_id(drill_id: str | None) -> dict | None:
    """Look one rehab-bank drill up by its canonical ``id``.

    This is the only supported way to recover a drill from something an
    athlete's plan carried: display names are rewritten downstream and are not
    identity. An id the bank does not contain returns ``None`` — the caller
    refuses rather than falling back to a name search.

    An id claimed by more than one group is treated as unresolvable for the same
    reason: two drills answering to one id cannot be told apart, so neither is
    returned. ``tools/validate_rehab_bank.py`` rejects that state, so this is a
    guard against a bank that got past it, not an expected path.
    """
    global _REHAB_DRILLS_BY_ID_CACHE
    if _REHAB_DRILLS_BY_ID_CACHE is None:
        index: dict[str, dict | None] = {}
        for entry in get_rehab_bank():
            for drill in entry.get("drills", []) or []:
                identifier = str((drill or {}).get("id") or "").strip()
                if not identifier:
                    continue
                # Second claim on an id makes it ambiguous; mark it unusable.
                index[identifier] = None if identifier in index else drill
        _REHAB_DRILLS_BY_ID_CACHE = index
    return _REHAB_DRILLS_BY_ID_CACHE.get(str(drill_id or "").strip())


def prime_rehab_bank() -> None:
    get_rehab_bank()
    get_rehab_locations()


def get_exercise_bank() -> list[dict]:
    global _EXERCISE_BANK_CACHE
    if _EXERCISE_BANK_CACHE is None:
        _EXERCISE_BANK_CACHE = json.loads((DATA_DIR / "exercise_bank.json").read_text(encoding="utf-8"))
    return _EXERCISE_BANK_CACHE
def normalize_rehab_location(location: str | None) -> list[str]:
    normalized_location = canonicalize_location(location)
    if not normalized_location:
        return ["unspecified"]
    candidates: list[str] = []

    def _add(value: str | None) -> None:
        if value and value not in candidates:
            candidates.append(value)

    _add(normalized_location)
    for alias in get_rehab_location_candidates(normalized_location):
        _add(alias)
    _add(normalized_location.replace(" ", "_"))
    _add(normalized_location.replace("_", " "))

    filtered = [candidate for candidate in candidates if candidate in get_rehab_locations()]
    return filtered or candidates


def _entry_phases(entry: dict) -> list[str]:
    """Return the normalized phase tokens for a rehab bank entry."""
    return _split_phase_progression(entry.get("phase_progression", ""))


def _split_phase_progression(text: str) -> list[str]:
    """Return normalized phase tokens from either arrow encoding."""
    return split_phase_progression(text)


def _split_notes_by_phase(notes: str) -> list[tuple[str, str]]:
    """Return (phase, text) pairs if the notes use a phase progression."""
    if "\u2192" not in notes and "\u00e2\u2020\u2019" not in notes:
        return []
    segments = [seg.strip() for seg in (notes or "").replace("\u00e2\u2020\u2019", "\u2192").split("\u2192")]
    results = []
    for seg in segments:
        if ":" in seg:
            phase, desc = seg.split(":", 1)
            results.append((phase.strip().upper(), desc.strip()))
    return results

INJURY_TYPES = [
    "sprain",
    "strain",
    "tightness",
    "contusion",
    "swelling",
    "tendonitis",
    "impingement",
    "instability",
    "stiffness",
    "pain",
    "soreness",
    "hyperextension",
    "abrasion",
    "cut",
    "laceration",
    "graze",
    "blister",
    "unspecified",
]
_URGENT_INJURY_TOKENS = derive_urgent_injury_tokens()
_INJURY_RISK_ORDER = [
    "instability",
    "swelling",
    "sprain",
    "strain",
    "tendonitis",
    "impingement",
    "hyperextension",
    "pain",
    "stiffness",
    "tightness",
    "soreness",
    "contusion",
    "laceration",
    "cut",
    "abrasion",
    "graze",
    "blister",
    "unspecified",
]

REGION_GUARDRAILS = {
    "upper_limb": {
        "mild": {
            "allowed": [
                "Controlled range of motion, tempos, and isometrics.",
                "Technique-only speed work if pain-free.",
            ],
            "avoid": ["Max-effort pressing/gripping if it provokes symptoms."],
            "replace": ["Lower-body aerobic work to keep conditioning moving."],
            "red_flags": ["Night pain, numbness/tingling, or loss of strength."],
        },
        "moderate": {
            "allowed": [
                "Pain-free patterns with isometrics and scap/rotator control.",
                "Progression gate: symptoms stable 7–10 days before adding load/velocity.",
            ],
            "avoid": ["Heavy pressing, dips, overhead ballistic work, high-torque grips."],
            "replace": ["Keep conditioning via bike or lower-body sessions."],
            "red_flags": [],
        },
        "severe": {
            "allowed": ["Only symptom-calming movement after clinical review."],
            "avoid": ["Loaded pressing, overhead work, or contact."],
            "replace": ["Lower-body conditioning only."],
            "red_flags": ["Seek medical review before resuming loading."],
        },
    },
    "spine_pelvis": {
        "mild": {
            "allowed": ["Hinge patterning, trunk endurance, controlled range of motion."],
            "avoid": ["Max axial loading if it spikes pain."],
            "replace": ["Sled or bike conditioning to keep capacity."],
            "red_flags": [],
        },
        "moderate": {
            "allowed": ["Graded exposure, trunk endurance, hip capacity work."],
            "avoid": ["Heavy hinge/squat, repeated loaded flexion/rotation."],
            "replace": ["Low-impact conditioning."],
            "red_flags": [],
        },
        "severe": {
            "allowed": ["Clinical review; keep movement symptom-calming only."],
            "avoid": ["Heavy loading and aggressive range of motion."],
            "replace": ["Non-provocative aerobic work."],
            "red_flags": ["Seek medical review before resuming loading."],
        },
    },
    "hip_groin": {
        "mild": {
            "allowed": ["Controlled strength work with short exposures."],
            "avoid": ["Sudden lateral/cutting volume spikes."],
            "replace": ["Low-impact conditioning if needed."],
            "red_flags": [],
        },
        "moderate": {
            "allowed": ["Isometrics and progressive strength in pain-free range."],
            "avoid": ["Deep ROM, aggressive lateral lunges/cossacks, sprinting if it bites."],
            "replace": ["Bike/row/swim conditioning."],
            "red_flags": [],
        },
        "severe": {
            "allowed": ["Symptom-led rehab after clinical review."],
            "avoid": ["Cutting, sprinting, or contact."],
            "replace": ["Low-impact conditioning only."],
            "red_flags": ["Seek medical review before resuming load."],
        },
    },
    "knee": {
        "mild": {
            "allowed": ["Controlled squats/step-ups within tolerance."],
            "avoid": ["Big jumps in deep knee flexion volume."],
            "replace": ["Low-impact conditioning."],
            "red_flags": [],
        },
        "moderate": {
            "allowed": ["Hip-dominant strength focus."],
            "avoid": ["Repeated jumping, deep loaded knee flexion, hard decels."],
            "replace": ["Bike conditioning; reintroduce jumps last."],
            "red_flags": [],
        },
        "severe": {
            "allowed": ["Clinical review plus symptom-led rehab."],
            "avoid": ["Plyos, hard running, or cutting."],
            "replace": ["Low-impact capacity work."],
            "red_flags": ["Seek medical review before resuming impact work."],
        },
    },
    "lower_leg_foot": {
        "mild": {
            "allowed": ["Progressive loading and low-impact exposures."],
            "avoid": ["Sudden sprint/plyo spikes."],
            "replace": ["Low-impact conditioning."],
            "red_flags": [],
        },
        "moderate": {
            "allowed": [
                "Progressive calf/hamstring strength.",
                "Balance/proprioception for ankle.",
            ],
            "avoid": ["Max velocity sprinting, repeated plyos, hard cutting."],
            "replace": ["Bike/row/pool conditioning."],
            "red_flags": [],
        },
        "severe": {
            "allowed": ["Protect, then rebuild capacity after clinical review."],
            "avoid": ["Sprinting, plyos, or cutting."],
            "replace": ["Low-impact conditioning only."],
            "red_flags": ["Seek medical review before resuming impact work."],
        },
    },
}

LEGACY_LOCATION_REGION_MAP = {
    "shoulder": "upper_limb",
    "chest": "upper_limb",
    "elbow": "upper_limb",
    "forearm": "upper_limb",
    "wrist": "upper_limb",
    "hand": "upper_limb",
    "biceps": "upper_limb",
    "triceps": "upper_limb",
    "neck": "spine_pelvis",
    "upper back": "spine_pelvis",
    "lower back": "spine_pelvis",
    "si joint": "spine_pelvis",
    "hip": "hip_groin",
    "groin": "hip_groin",
    "hip flexor": "hip_groin",
    "glute": "hip_groin",
    "quad": "knee",
    "knee": "knee",
    "hamstring": "lower_leg_foot",
    "calf": "lower_leg_foot",
    "achilles": "lower_leg_foot",
    "ankle": "lower_leg_foot",
    "foot": "lower_leg_foot",
    "toe": "lower_leg_foot",
    "shin": "lower_leg_foot",
    "heel": "lower_leg_foot",
}
LOCATION_REGION_MAP = {
    **LEGACY_LOCATION_REGION_MAP,
    **build_location_region_map(),
}


REGION_LABELS = {
    "upper_limb": "Upper limb",
    "spine_pelvis": "Spine/pelvis",
    "hip_groin": "Hip/groin",
    "knee": "Knee-dominant",
    "lower_leg_foot": "Lower leg/foot",
    "unspecified": "Unspecified region",
}

# Contextual recovery tips for each injury type
INJURY_SUPPORT_NOTES = {
    "sprain": [
        "Use compression wrap or brace during sessions",
        "Avoid unstable surfaces or sharp cuts",
        "Elevate limb above heart post-training",
        "Ice for 15–20 minutes after intense sessions",
    ],
    "strain": [
        "Avoid explosive movements during early recovery",
        "Use light massage or foam rolling post-session",
        "Progressively reload tissue with tempo or isometrics",
        "Warm up thoroughly with band activation drills",
    ],
    "tightness": [
        "Use mobility drills before and after sessions",
        "Apply heat pre-session, foam roll after",
        "Check hydration and magnesium intake",
    ],
    "contusion": [
        "Avoid direct contact or sparring on affected area",
        "Use ice 2–3x/day for swelling",
        "Foam roll adjacent tissue if not painful",
    ],
    "swelling": [
        "Elevate limb above heart for 15–30 mins",
        "Use compression garments between sessions",
        "Reduce total volume if swelling persists",
    ],
    "tendonitis": [
        "Limit repetitive high-speed reps",
        "Use isometrics to load tendon safely",
        "Apply heat pre-session, ice post-session",
    ],
    "impingement": [
        "Avoid loaded end-range positions",
        "Use joint distraction or band mobilizations",
        "Do pain-free range only in strength work",
    ],
    "instability": [
        "Use wraps or braces for external support",
        "Prioritize isometrics and stability drills",
        "Avoid open-chain explosive work early phase",
    ],
    "stiffness": [
        "Foam roll or band floss before sessions",
        "Use full-ROM unloaded mobility drills",
        "Massage surrounding tissue manually",
    ],
    "pain": [
        "Avoid aggravating drills, work sub-threshold",
        "Track if pain increases post-session",
        "Prioritize soft-tissue and breath work",
    ],
    "soreness": [
        "Use mobility circuits post-training",
        "Low intensity bike or walks for recovery",
        "Apply contrast showers or compression gear",
    ],
    "hyperextension": [
        "Avoid fully locked joint positions",
        "Use straps or wraps to limit end-range",
        "Introduce tempo and joint control drills",
    ],
    "abrasion": [
        "Keep covered and clean during training",
        "Avoid friction or direct contact over the affected skin",
        "Monitor for redness, heat, pus, or worsening bleeding",
    ],
    "cut": [
        "Keep covered and clean during training",
        "Avoid contact if the wound can reopen",
        "Stop if bleeding restarts during the session",
    ],
    "laceration": [
        "Do not resume contact unless medically cleared",
        "Keep wound protected and avoid reopening the area",
        "Watch for infection signs or wound separation",
    ],
    "graze": [
        "Keep clean and covered if training",
        "Avoid rubbing/friction over the area",
        "Stop if bleeding or irritation worsens",
    ],
    "blister": [
        "Protect with padding or tape before training",
        "Avoid repeated friction over the area",
        "Stop if blister opens, bleeds, or changes gait/grip mechanics",
    ],
    "unspecified": [
        "Use general joint mobility and soft-tissue tools",
        "Don’t load until pain-free at bodyweight",
        "Consult clinician if symptoms persist >5 days",
    ],
}
RED_FLAG_TYPES = derive_red_flag_types()

BFR_SAFETY_GATE = (
    "Use only if already experienced with BFR and medically appropriate; "
    "stop if numbness/tingling occurs."
)

# Surface/skin injuries (cut, abrasion, laceration, graze, blister) are
# integumentary, not musculoskeletal. Loading-style rehab (isometrics,
# eccentrics, tendon/balance work) does nothing for skin healing and can
# reopen the wound or invite infection, so we never assign rehab drills to
# them. The correct prescription is wound care, surfaced as a single note.
SURFACE_WOUND_CARE_NOTE = (
    "Skin/surface injury — no loading rehab needed. Keep it clean and covered, "
    "avoid friction or contact that could reopen it, and monitor for infection "
    "(spreading redness, heat, swelling, pus, or fever). Return to full contact "
    "once the wound has closed."
)


def _is_surface_type(injury_type: str | None) -> bool:
    return str(injury_type or "").strip().lower() in SURFACE_TISSUE_TYPES


def _collect_surface_drills(
    injury_type: str | None,
    loc_candidates: list[str],
    current_phase: str,
) -> list[tuple[str, str]]:
    """Return wound-care drills for a surface injury at the given location.

    Surface injuries match ONLY their own surface-type bank entries — never the
    location's ``unspecified`` entries, which hold musculoskeletal loading
    drills that have no place on a skin wound. Location-specific entries are
    preferred over ``unspecified``-location fallbacks. Returns ``(name, notes)``
    pairs with the phase-appropriate note already selected.
    """
    phase = current_phase.upper()
    injury_type_lower = str(injury_type or "").strip().lower()
    matches = [
        entry
        for entry in get_rehab_bank()
        if entry.get("type") == injury_type_lower
        and (entry.get("location") in loc_candidates or entry.get("location") == "unspecified")
        and phase in _entry_phases(entry)
    ]
    # Prefer specific-location entries over the unspecified fallback.
    matches.sort(key=lambda e: e.get("location") == "unspecified")

    drills: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in matches:
        for drill in entry.get("drills", []):
            name = drill.get("name")
            if not name or name in seen:
                continue
            notes = drill.get("notes", "")
            parsed = _split_notes_by_phase(notes)
            text = notes
            if parsed:
                text = next((desc for label, desc in parsed if label == phase), "")
                if not text:
                    continue
            seen.add(name)
            drills.append((name, text))
    return drills

# ---------------------------------------------------------------------------
# Surgical Rehab Integration – function classification and formatting
# ---------------------------------------------------------------------------

# Six function buckets.  Keyword order within each list is checked
# sequentially; first match wins.  More specific terms come before generic
# ones.  These buckets are used as *guidance* for the GPT/OpenAI planner —
# not as hard constraints.
REHAB_FUNCTION_BUCKETS: dict[str, list[str]] = {
    "isometric_analgesia": [
        "isometric", "wall sit", "static hold", "sustained contraction",
        "tendon isometric", "iso hold", "spanish squat",
    ],
    "tendon_loading": [
        "eccentric", "nordic", "calf raise", "heel raise", "pogo",
        "drop landing", "progressive load", "bfr", "blood flow",
        "heavy slow resistance", "tissue tolerance",
    ],
    "activation": [
        "activation", "activate", "prime", "firing", "clamshell",
        "monster walk", "hip thrust", "lateral band walk", "banded",
        "glute bridge", "side-lying", "wake", "fire",
    ],
    "control": [
        "balance", "proprioception", "single-leg", "single leg",
        "coordination", "wobble", "pistol", "step-up", "postural",
        "trunk control", "stability", "controlled", "dead bug",
        "bird dog", "pallof", "deadbug", "wall slide",
    ],
    "mobility": [
        "mobility", "stretch", "range of motion", "distraction",
        "rom", "band floss", "ankle mob", "joint mob",
        "hip flexor", "ankle circle", "thoracic", "pigeon",
        "90/90", "couch stretch", "flexibility",
    ],
    "recovery_downregulation": [
        "recovery", "downregulation", "breathing", "parasympathetic",
        "gentle", "cool down", "diaphragmatic", "foam roll",
        "low-load", "rolling", "compress", "elevation", "restore",
        "soft tissue", "reset",
    ],
}

# Human-readable labels for each bucket (used in output formatting)
_FUNCTION_LABELS: dict[str, str] = {
    "activation": "Activation",
    "control": "Control",
    "isometric_analgesia": "Isometric analgesia",
    "mobility": "Mobility",
    "tendon_loading": "Tendon/tissue loading",
    "recovery_downregulation": "Recovery/downregulation",
}

# Short purpose descriptions for each function bucket
_FUNCTION_PURPOSES: dict[str, str] = {
    "activation": "wake up underactive tissue before main work",
    "control": "improve joint position and movement quality",
    "isometric_analgesia": "reduce irritation and improve load tolerance",
    "mobility": "improve usable range for today's session demands",
    "tendon_loading": "build tissue tolerance progressively",
    "recovery_downregulation": "reduce stiffness and restore baseline after training stress",
}

# Day-type-specific "Why today" rationale.  When day_type is provided to
# generate_rehab_protocols, this context is rendered in the annotation so
# the output explains the session-specific reason rather than only a broad
# phase rationale.
_DAY_TYPE_REHAB_WHY: dict[str, str] = {
    "sparring": (
        "minimal pre-sparring inclusion — addresses the risk point without "
        "competing with freshness or neuromuscular readiness for contact"
    ),
    "strength": (
        "prepares the specific risk point for the main lift — "
        "manages irritation and primes the pattern under load"
    ),
    "aerobic": (
        "lower-intensity session allows slightly more developmental work — "
        "tissue tolerance, control, or mobility without adding fatigue"
    ),
    "recovery": (
        "low-load recovery session — maintains movement quality and "
        "symptom control between higher-intensity days"
    ),
}

# Phase-level fallback rationale when no day_type is provided
_PHASE_REHAB_WHY: dict[str, str] = {
    "GPP": "establishes baseline control and tissue tolerance before training load ramps up",
    "SPP": "maintains movement quality and symptom control as training intensity increases",
    "TAPER": "low-noise maintenance to protect freshness and symptom stability before competition",
}

# The five rehab quality evaluator checks (surfaced in tests and guidance)
REHAB_QUALITY_CHECKS: list[str] = [
    "What exact issue is this solving?",
    "Why is it on this day specifically?",
    "Does it duplicate another rehab item already used this week?",
    "Is this the lowest effective dose?",
    "Would this still look intentional if the athlete read it line by line?",
]

# Volume ceiling per session context.  These are soft upper bounds: the model
# may exceed them with explicit justification, but they guard against filler.
_DAY_TYPE_DRILL_LIMIT: dict[str, int] = {
    "sparring": 1,
    "strength": 2,
    "aerobic": 2,
    "recovery": 2,
}
_DEFAULT_DRILL_LIMIT = 2
_HIGH_SEVERITY_BLOCK_TERMS = (
    "pogo", "jump", "hop", "hops", "bound", "sprint", "depth", "drop landing",
    "reactive", "explosive", "ballistic", "max velocity", "hard cutting", "decel",
    "loaded", "heavy", "bfr",
)
_MODERATE_SEVERITY_BLOCK_TERMS = (
    "sprint", "max velocity", "depth jump", "drop jump", "hard cutting", "ballistic", "heavy", "bfr",
)
_HIGH_SEVERITY_SAFE_FALLBACKS = (
    ("Isometric hold", "Low-load position hold to calm symptoms."),
    ("Controlled ROM", "Gentle, pain-free range-of-motion only."),
    ("Gentle mobility", "Slow mobility with no sharp pain."),
    ("Breathing/downregulation", "Nasal breathing to reduce tone and guarding."),
    ("Balance/proprioception", "Light control work with strict symptom limits."),
    ("Low-load activation", "Easy activation without impact or speed."),
)


# Returned by classify_drill_function when no keyword matched. Kept explicit so
# the ambiguous case is visible: bank *data* must never record this value on the
# strength of a non-match — see match_drill_function.
AMBIGUOUS_DRILL_FUNCTION = "control"


def match_drill_function(name: str, notes: str = "") -> str | None:
    """Return the keyword-matched function class, or ``None`` when ambiguous.

    This is the honest half of :func:`classify_drill_function`: it reports "no
    keyword matched" instead of falling back to a default, so migration tooling
    and validation never let an unclassified drill masquerade as ``"control"``.
    """
    text = f"{name} {notes}".lower()
    for bucket, keywords in REHAB_FUNCTION_BUCKETS.items():
        if any(kw in text for kw in keywords):
            return bucket
    return None


def classify_drill_function(name: str, notes: str = "") -> str:
    """Classify a rehab drill into one of the REHAB_FUNCTION_BUCKETS.

    Classification is keyword-based and is intended as *guidance* for the
    GPT/OpenAI planner — not a hard constraint.  When ambiguous, returns
    ``"control"`` as a safe default.

    Retained as the runtime fallback for legacy and not-yet-migrated bank
    entries; drills carrying explicit ``function`` metadata are read through
    ``rehab_schema.resolve_drill_function`` instead.

    Parameters
    ----------
    name:
        The drill name to classify (e.g. ``"Banded Clamshell"``).
    notes:
        Optional extra text (notes, prescription) appended to the name before
        keyword matching.

    Returns
    -------
    str
        One of the keys in ``REHAB_FUNCTION_BUCKETS``:
        ``"isometric_analgesia"``, ``"tendon_loading"``, ``"activation"``,
        ``"control"``, ``"mobility"``, or ``"recovery_downregulation"``.
    """
    return match_drill_function(name, notes) or AMBIGUOUS_DRILL_FUNCTION


def _normalize_rehab_severity(value: str | None) -> str:
    """Collapse a raw severity onto the bank contract for rendering decisions.

    The vocabulary lives in
    :func:`fightcamp.rehab_schema.normalize_severity_bucket`.
    Rendering keeps its historical ``"moderate"`` default for an unrecognised
    severity: the drill list still has to be filtered by *something*, and the
    middle bucket is the safe one to filter by.
    """
    return normalize_severity_bucket(value, default="moderate")


def _drill_is_too_aggressive_for_severity(name: str, notes: str, severity: str) -> bool:
    if severity == "low":
        return False
    text = f"{name} {notes}".lower()
    terms = _HIGH_SEVERITY_BLOCK_TERMS if severity == "high" else _MODERATE_SEVERITY_BLOCK_TERMS
    return any(term in text for term in terms)


def _phase_notes(drill: Mapping[str, object], current_phase: str) -> str | None:
    """Return the notes this drill renders in ``current_phase``, else ``None``.

    A drill whose notes are split by phase progression only appears in the
    phases it names. One with unsplit notes appears in every phase.
    """
    name = str(drill.get("name") or "")
    if not name:
        return None
    notes = str(drill.get("notes") or "")
    parsed = _split_notes_by_phase(notes)
    if not parsed:
        return notes
    for phase_label, text in parsed:
        if phase_label == current_phase.upper():
            return text
    return None


def _drill_is_prescribable(
    drill: Mapping[str, object], current_phase: str, severity: str
) -> bool:
    """True when this drill would survive rendering for this phase and severity.

    The stage-aware selector picks exactly one drill, so its candidate set has
    to be the drills that can actually be prescribed. Anything the phase or
    severity rules would strip afterwards is not a real candidate.
    """
    notes = _phase_notes(drill, current_phase)
    if notes is None:
        return False
    return not _drill_is_too_aggressive_for_severity(
        str(drill.get("name") or ""), notes, severity
    )


def _filter_drills_by_severity(drills: list[tuple[str, str]], severity: str) -> list[tuple[str, str]]:
    allowed = [drill for drill in drills if not _drill_is_too_aggressive_for_severity(drill[0], drill[1], severity)]
    if allowed:
        return allowed
    if not drills:
        return []
    if severity == "high":
        return [fallback for fallback in _HIGH_SEVERITY_SAFE_FALLBACKS if not _drill_is_too_aggressive_for_severity(fallback[0], fallback[1], severity)][:1]
    if severity == "moderate":
        return [("Controlled ROM", "Pain-free tempo mobility and control only.")]
    return drills[:1]


def _format_rehab_drill(
    name: str,
    notes: str,
    phase: str,
    function_tag: str,
    day_type: str | None = None,
) -> tuple[str, list[str]]:
    """Return the drill headline and its annotation lines separately.

    The annotation lines provide function label, purpose, and a "Why today"
    explanation that is day/session-specific when ``day_type`` is supplied,
    with phase context as a fallback.

    Parameters
    ----------
    name:
        The drill name (e.g. ``"Banded External Rotation"``).
    notes:
        Phase-specific or general drill notes appended after an em-dash.
    phase:
        Phase name (``GPP``/``SPP``/``TAPER``) used for fallback "Why today"
        context when ``day_type`` is not supplied.
    function_tag:
        One of the keys in ``REHAB_FUNCTION_BUCKETS`` (e.g. ``"activation"``).
    day_type:
        Optional session type (``'sparring'``, ``'strength'``, ``'aerobic'``,
        ``'recovery'``).  When provided, produces session-specific "Why today"
        language; otherwise falls back to ``_PHASE_REHAB_WHY``.

    Returns a tuple of:
    - ``headline``: the drill name (and notes) as a single string.
    - ``annotations``: additional lines rendered as indented continuations.

    Example output::

        headline  → "Banded External Rotation – Restore rotator cuff control"
        annotations → [
            "[Function: Activation] Purpose: wake up underactive tissue before main work.",
            "Why today: prepares the specific risk point for the main lift.",
        ]
    """
    headline = f"{name} – {notes}" if notes else name
    label = _FUNCTION_LABELS.get(function_tag, function_tag.replace("_", " ").title())
    purpose = _FUNCTION_PURPOSES.get(function_tag, "targeted rehab support")
    if day_type and day_type in _DAY_TYPE_REHAB_WHY:
        why_today = _DAY_TYPE_REHAB_WHY[day_type]
    else:
        phase_key = phase.upper()
        why_today = _PHASE_REHAB_WHY.get(phase_key, "phase-appropriate rehab support")
    annotations = [
        f"[Function: {label}] Purpose: {purpose}.",
        f"Why today: {why_today}.",
    ]
    return headline, annotations


def _rehab_bank_matches(itype: str | None, loc_candidates, current_phase: str) -> list[dict]:
    """Bank entries for this injury type + location that render in this phase."""
    return [
        entry
        for entry in get_rehab_bank()
        if (
            entry.get("type") == itype
            or entry.get("type") == "unspecified"
            or itype is None
        )
        and (
            entry.get("location") in loc_candidates
            or entry.get("location") == "unspecified"
        )
        and current_phase.upper() in _entry_phases(entry)
    ]


def _phase_drill_line(drill: dict, current_phase: str) -> tuple[str, str] | None:
    """This drill's ``(name, notes_for_phase)`` if it renders in the phase."""
    name = drill.get("name")
    if not name:
        return None
    notes = drill.get("notes", "")
    parsed = _split_notes_by_phase(notes)
    if not parsed:
        return (name, notes)
    for phase_label, text in parsed:
        if phase_label == current_phase.upper():
            return (name, text)
    return None


def _all_phase_drills(matches: list[dict], current_phase: str) -> list[tuple[str, str]]:
    """Every matching drill's phase line — the stage-unaware legacy behaviour."""
    drills: list[tuple[str, str]] = []
    for match in matches:
        for drill in match.get("drills", []):
            line = _phase_drill_line(drill, current_phase)
            if line is not None:
                drills.append(line)
    return drills


def _log_episode_selection(
    episode: dict, *, selection_mode: str, selected_id: str
) -> None:
    """Structured, machine-only trace of how one episode was programmed.

    Distinguishes the stage-aware selector from the legacy unresolved-stage
    fallback so the two paths are separable in logs. Carries identity only — no
    free-text health description.
    """
    logger.info(
        "rehab_selector athlete_id=%s injury_id=%s injury_episode_id=%s "
        "rehab_stage=%s selection_mode=%s selected_drill_id=%s",
        episode.get("athlete_id") or "",
        episode.get("injury_id") or "",
        episode.get("episode_id") or "",
        episode.get("rehab_stage") or "",
        selection_mode,
        selected_id or "",
    )


def _stage_aware_drill_for_episode(
    episode: dict,
    *,
    loc: str | None,
    loc_candidates,
    current_phase: str,
    day_type: str | None,
) -> tuple[str, str] | None:
    """The one drill the stage-aware selector prescribes for a resolved episode."""
    ep_type = episode.get("injury_type")
    matches = _rehab_bank_matches(ep_type, loc_candidates, current_phase)
    if not matches:
        return None
    ep_severity = _normalize_rehab_severity(episode.get("severity"))
    stage_candidates: list[dict] = []
    for match in matches:
        for bank_drill in match.get("drills", []):
            if not _drill_is_prescribable(bank_drill, current_phase, ep_severity):
                continue
            candidate = dict(bank_drill)
            candidate.setdefault("injury_type", match.get("type"))
            candidate.setdefault("care_pathway", "msk")
            stage_candidates.append(candidate)
    selection = select_rehab_candidate(
        injury={
            "body_region": loc,
            "body_region_aliases": loc_candidates,
            "injury_type": ep_type,
            "id": episode.get("injury_id"),
            "episode_id": episode.get("episode_id"),
            "athlete_id": episode.get("athlete_id"),
            "side": episode.get("side"),
            "severity": episode.get("severity"),
        },
        rehab_stage=episode.get("rehab_stage"),
        candidates=stage_candidates,
        available_equipment=episode.get("available_equipment"),
        exposures=episode.get("rehab_exposures") or (),
        session_context=day_type,
    )
    selected_id = selection.selected_drill_id or ""
    _log_episode_selection(episode, selection_mode="stage_aware", selected_id=selected_id)
    if not selected_id:
        return None
    for match in matches:
        for bank_drill in match.get("drills", []):
            if str(bank_drill.get("id") or "") == selected_id:
                return _phase_drill_line(bank_drill, current_phase)
    return None


def _legacy_rehab_drills_for_episode(
    *,
    episode: dict,
    loc_candidates,
    current_phase: str,
    drill_limit: int,
) -> list[tuple[str, str]]:
    """The pre-stage-aware rehab drills for ONE episode whose stage is unresolved.

    Absence of a resolved stage is never read as CALM or "no rehab": the episode
    keeps the exact behaviour it had before stage-aware selection existed —
    matched on its own injury type, location, phase and severity, in the same
    deterministic bank order — scoped strictly to this injury.
    """
    matches = _rehab_bank_matches(episode.get("injury_type"), loc_candidates, current_phase)
    if not matches:
        return []
    ep_severity = _normalize_rehab_severity(episode.get("severity"))
    drills = _filter_drills_by_severity(_all_phase_drills(matches, current_phase), ep_severity)
    result = drills[:drill_limit]
    _log_episode_selection(
        episode,
        selection_mode="legacy_unresolved_stage",
        selected_id=result[0][0] if result else "",
    )
    return result


def _select_rehab_drills_per_episode(
    *,
    episodes: list[dict],
    loc: str | None,
    loc_candidates,
    current_phase: str,
    day_type: str | None,
    drill_limit: int,
) -> list[tuple[str, str]]:
    """Programme every injury episode at this location independently, then consolidate.

    Each episode drives its OWN candidate pool from its OWN injury type, and is
    programmed by the stage-aware selector when its stage is resolved or by the
    legacy fallback when it is not. Nothing about one episode — stage, evidence,
    type, side, exposures — ever reaches another's selection.

    The per-location block is then a fair, deterministic consolidation of those
    independent prescriptions: a round-robin takes one drill from each episode
    before any episode's second, so no injury is starved out of the block purely
    because another was ordered first. Resolved episodes lead (most protective
    first); the volume ceiling still caps the block.
    """
    per_episode: list[list[tuple[str, str]]] = []
    for episode in sorted(episodes, key=_episode_sort_key):
        if episode.get("stage_resolved"):
            line = _stage_aware_drill_for_episode(
                episode,
                loc=loc,
                loc_candidates=loc_candidates,
                current_phase=current_phase,
                day_type=day_type,
            )
            per_episode.append([line] if line is not None else [])
        else:
            per_episode.append(
                _legacy_rehab_drills_for_episode(
                    episode=episode,
                    loc_candidates=loc_candidates,
                    current_phase=current_phase,
                    drill_limit=drill_limit,
                )
            )

    chosen: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for position in range(max((len(lines) for lines in per_episode), default=0)):
        for lines in per_episode:
            if position >= len(lines):
                continue
            name, notes = lines[position]
            key = str(name).strip().lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            chosen.append((name, notes))
            if len(chosen) >= drill_limit:
                return chosen
    return chosen


def generate_rehab_protocols(
    *,
    injury_string: str,
    exercise_data: list,
    current_phase: str,
    parsed_entries: list[dict] | None = None,
    seen_drills: set | None = None,
    day_type: str | None = None,
) -> tuple[str, set]:
    """Return rehab exercise suggestions for the given injuries and phase.

    Each drill is classified by function bucket (activation, control, isometric
    analgesia, mobility, tendon loading, recovery/downregulation) and formatted
    with a purpose line and a "Why today" explanation so the output reads as a
    deliberate risk-management decision rather than a template copy-paste.

    Function classification is used as *guidance* only — the same function may
    appear more than once if the injury profile genuinely requires it.

    Parameters
    ----------
    injury_string:
        Raw injury description text.
    exercise_data:
        Loaded exercise bank.
    current_phase:
        Phase name (``GPP``/``SPP``/``TAPER``).
    seen_drills:
        Legacy return/state parameter retained for compatibility with existing
        callers. Drill selection no longer deduplicates across phases.
    day_type:
        Optional session type context (``'sparring'``, ``'strength'``,
        ``'aerobic'``, ``'recovery'``).  Affects volume ceiling and "Why today"
        language.  Sparring days receive at most 1 drill; all others at most 2.
    """
    if seen_drills is None:
        seen_drills = set()
    if not injury_string and not parsed_entries:
        return "\n✅ No rehab work required.", seen_drills

    injury_phrases = split_injury_text(injury_string)
    structured_entries = [entry for entry in (parsed_entries or []) if isinstance(entry, dict)]
    merged_entries = _merge_injuries_by_location(structured_entries)
    urgent_merged_entry = next((entry for entry in merged_entries if entry.get("is_urgent")), None)
    if urgent_merged_entry:
        return _build_red_flag_block(urgent_merged_entry), seen_drills

    merged_by_key = {entry.get("group_key"): entry for entry in merged_entries if entry.get("group_key")}
    normalized_entries: list[tuple[str | None, str | None, str | None]] = []
    if structured_entries:
        for entry in merged_entries:
            location = get_injury_location(entry)
            injury_type = _select_highest_risk_type(
                (entry.get("rehab_types") or []) + ([entry.get("rehab_type")] if entry.get("rehab_type") else [])
            )
            if not injury_type and location:
                injury_type = "unspecified"
            if injury_type or location:
                normalized_entries.append((injury_type, location, entry.get("group_key")))
    else:
        for phrase in injury_phrases:
            itype, loc = parse_injury_phrase(phrase)
            if not itype:
                if loc:
                    # default to unspecified type when a location is provided
                    itype = "unspecified"
                else:
                    continue
            normalized_entries.append((itype, loc, None))

    # Prioritize specific injuries over unspecified duplicates
    normalized_entries.sort(key=lambda x: (x[0] is None or x[0] == "unspecified"))

    # Drop injuries without a body part when at least one body part was found
    if any(loc for _, loc, _ in normalized_entries):
        normalized_entries = [p for p in normalized_entries if p[1] is not None]
    unique_entries = list(dict.fromkeys(normalized_entries))

    flagged = []
    for injury in injury_phrases:
        for flag in RED_FLAG_TYPES:
            if flag in injury:
                flagged.append(injury)
                break
    if flagged:
        return (
            "\n**Red Flag Detected**\n"
            f"• {', '.join(flagged).title()} – Do not train until cleared by clinician.\n"
            "• All strength/conditioning recommendations must be manually adjusted.",
            seen_drills,
        )

    # Per-session volume ceiling — keeps rehab minimal and non-generic.
    # The model may exceed this with explicit justification, but we enforce
    # the ceiling here to prevent accidental filler.
    drill_limit = _DAY_TYPE_DRILL_LIMIT.get(day_type or "", _DEFAULT_DRILL_LIMIT)

    lines = []

    for itype, loc, group_key in unique_entries:
        if _is_surface_type(itype):
            merged = merged_by_key.get(group_key) if group_key else None
            loc_title = _render_location_heading(loc, merged)
            type_title = itype.title() if itype else "Surface"
            severity = _normalize_rehab_severity((merged or {}).get("severity"))
            # Surface/skin injuries are integumentary, not musculoskeletal: they
            # never get loading rehab or a wound-care drill list — only a single
            # note. A minor, stable graze/abrasion/blister trains through with the
            # calm hygiene note; every other surface case (cut/laceration or a
            # high-severity surface wound) gets the wound-care note. Danger gates
            # (red flags, needs-review) are enforced upstream and stay untouched.
            if itype in MINOR_SURFACE_TRAIN_THROUGH_TYPES and severity != "high":
                lines.append(f"- {loc_title} ({type_title}): {SURFACE_MINOR_TRAIN_THROUGH_NOTE}")
            else:
                lines.append(f"- {loc_title} ({type_title}): {SURFACE_WOUND_CARE_NOTE}")
            continue
        loc_candidates = normalize_rehab_location(loc)
        merged = merged_by_key.get(group_key) if group_key else None
        # Every MSK injury episode here — resolved stage or not. There is no
        # group-wide stage-aware-vs-legacy switch: each episode chooses its own
        # path, so an unresolved injury is never dropped just because a
        # co-located one has a stage.
        episodes = list((merged or {}).get("rehab_episodes") or [])
        severity = _normalize_rehab_severity((merged or {}).get("severity"))

        def _render_high_severity_note() -> None:
            loc_title = _render_location_heading(loc, merged)
            lines.append(
                f"- {loc_title}: High severity injury — use clinician-guided low-load mobility/isometrics only until symptoms settle."
            )

        if episodes:
            selected = _select_rehab_drills_per_episode(
                episodes=episodes,
                loc=loc,
                loc_candidates=loc_candidates,
                current_phase=current_phase,
                day_type=day_type,
                drill_limit=drill_limit,
            )
            if not selected:
                if severity == "high":
                    _render_high_severity_note()
                continue
        else:
            # Defensive fallback: a location with no resolvable MSK episode (e.g.
            # a bare injury string with no structured entry) keeps the legacy
            # group-level rendering for the group's type.
            matches = _rehab_bank_matches(itype, loc_candidates, current_phase)
            if not matches:
                continue
            filtered_drills = _filter_drills_by_severity(
                _all_phase_drills(matches, current_phase), severity
            )
            if severity == "high" and not filtered_drills:
                _render_high_severity_note()
                continue
            selected = filtered_drills[:drill_limit]

        if selected:
            loc_title = _render_location_heading(loc, merged)
            extra_types = merged.get("rehab_types", []) if merged else []
            display_types = [t for t in extra_types if t != "unspecified"] or extra_types
            type_title = " + ".join(t.title() for t in display_types) if display_types else (
                itype.title() if itype else "Unspecified"
            )
            lines.append(f"- {loc_title} ({type_title}):")
            for name, notes in selected:
                # PR1: the bank's explicit `function` metadata is a data
                # contract only. The rendered class stays keyword-derived
                # from the phase-specific note, which is what the stored
                # value cannot reproduce (one drill, one value, many
                # phases). rehab_schema.resolve_drill_function is the
                # forward path; PR3 switches this over.
                fn = classify_drill_function(name, notes)
                headline, annotations = _format_rehab_drill(
                    name, notes, current_phase, fn, day_type
                )
                lines.append(f"  • {headline}")
                lines.extend([f"    {ann}" for ann in annotations])

    if not lines:
        return "\n⚠️ Consult with a healthcare professional for personalized rehab guidance.", seen_drills

    if any("bfr" in line.lower() for line in lines):
        lines.append(f"- {BFR_SAFETY_GATE}")

    return "\n".join(lines), seen_drills


def _entry_is_urgent(entry: dict) -> bool:
    flags = {str(flag).strip().lower() for flag in entry.get("flags", []) if flag}
    triage_category = str(entry.get("triage_category") or "").strip()
    injury_type = str(entry.get("injury_type") or "").strip().lower()
    rehab_type = str(entry.get("rehab_type") or "").strip().lower()
    return (
        bool(triage_category)
        or "urgent" in flags
        or "structural_red_flag" in flags
        or any(flag.startswith("suspected_") for flag in flags)
        or injury_type in _URGENT_INJURY_TOKENS
        or rehab_type in _URGENT_INJURY_TOKENS
    )


def _select_highest_risk_type(types: list[str]) -> str:
    cleaned = [str(item).strip().lower() for item in types if str(item or "").strip()]
    if not cleaned:
        return "unspecified"
    for injury_type in _INJURY_RISK_ORDER:
        if injury_type in cleaned:
            return injury_type
    return cleaned[0]


def _merge_injuries_by_location(parsed_entries: list[dict]) -> list[dict]:
    severity_rank = {"low": 0, "mild": 0, "moderate": 1, "high": 2, "severe": 2}
    merged: dict[str, dict] = {}
    for raw_entry in parsed_entries:
        entry = dict(raw_entry)
        lookup_location = (
            entry.get("canonical_location")
            or entry.get("location")
            or entry.get("region")
            or "unspecified"
        )
        display_location = entry.get("display_location") or lookup_location
        laterality = entry.get("laterality") or entry.get("side")
        group_key = f"{lookup_location}::{laterality or 'unspecified'}"
        group = merged.setdefault(
            group_key,
            {
                "group_key": group_key,
                "canonical_location": lookup_location,
                "display_location": display_location,
                "rehab_types": [],
                "injury_types": [],
                "flags": [],
                "triage_categories": [],
                "severity": None,
                "laterality": laterality,
                "is_urgent": False,
                # Live rehab context. These are resolved upstream (rehab stage
                # by ``api.contracts.rehab_stage``, exposures by PR3) and are
                # carried through the merge because the selector cannot ask for
                # them: a whitelist that drops them silently disables
                # stage-aware selection for the whole plan.
                "rehab_stage": None,
                "athlete_id": None,
                "injury_id": None,
                "episode_id": None,
                "rehab_care_pathway": None,
                "available_equipment": None,
                "rehab_exposures": [],
                # Every distinct live injury episode that mapped into this
                # location, each keeping its OWN identity, stage, evidence and
                # injury type. The atomic fields above describe only the most
                # protective episode (for presentation); clinical selection reads
                # this list so no episode's context can select another's drill.
                "rehab_episodes": [],
            },
        )
        if not group.get("display_location"):
            group["display_location"] = display_location
        for key, out_key in (("rehab_type", "rehab_types"), ("injury_type", "injury_types")):
            value = str(entry.get(key) or "").strip().lower()
            if value and value not in group[out_key]:
                group[out_key].append(value)
        for injury_type in group["injury_types"]:
            if injury_type not in group["rehab_types"]:
                group["rehab_types"].append(injury_type)
        for flag in entry.get("flags", []) or []:
            flag_text = str(flag).strip().lower()
            if flag_text and flag_text not in group["flags"]:
                group["flags"].append(flag_text)
        triage = str(entry.get("triage_category") or "").strip().lower()
        if triage and triage not in group["triage_categories"]:
            group["triage_categories"].append(triage)
        severity = str(entry.get("severity") or "").strip().lower()
        if severity and (
            group["severity"] is None
            or severity_rank.get(severity, -1) > severity_rank.get(str(group["severity"]).lower(), -1)
        ):
            group["severity"] = severity
        if laterality and (group["laterality"] is None or group["laterality"] == laterality):
            group["laterality"] = laterality
        group["is_urgent"] = bool(group["is_urgent"] or _entry_is_urgent(entry))
        _merge_live_rehab_context(group, entry)
    return list(merged.values())


def _episode_context(entry: dict) -> dict | None:
    """Build one MSK injury episode's self-contained rehab context.

    Everything the selector needs to programme THIS injury and nothing about any
    other: its own identity, injury type, side, severity, equipment and exposure
    trail, plus its resolved stage *if one exists*.

    An episode is returned for every MSK injury entry, whether or not a live
    stage resolved — an absent stage must never mean "drop this injury". The
    ``stage_resolved`` flag distinguishes the two: a resolved episode is
    programmed by the stage-aware selector; an unresolved one keeps the
    pre-stage-aware behaviour. A missing stage stays ``None`` — it is never
    inferred to CALM or anything else. Surface/wound injuries are handled by
    their own pathway and never enter MSK rehab programming, so they return
    ``None`` here.
    """
    injury_type = str(entry.get("rehab_type") or entry.get("injury_type") or "").strip().lower()
    if injury_type and _is_surface_type(injury_type):
        return None
    stage = str(entry.get("rehab_stage") or "").strip().lower()
    stage_resolved = stage in REHAB_STAGES
    exposures = entry.get("rehab_exposures")
    equipment = entry.get("available_equipment")
    return {
        "rehab_stage": stage if stage_resolved else None,
        "stage_resolved": stage_resolved,
        "injury_id": str(entry.get("injury_id") or entry.get("id") or "") or None,
        "episode_id": str(entry.get("episode_id") or entry.get("injury_episode_id") or "") or None,
        "athlete_id": entry.get("athlete_id"),
        "rehab_care_pathway": entry.get("rehab_care_pathway"),
        # The injury's OWN type governs its candidate pool — never the group's
        # highest-risk type, which could belong to a different injury.
        "injury_type": injury_type or None,
        "side": entry.get("laterality") or entry.get("side"),
        "severity": str(entry.get("severity") or "").strip().lower() or None,
        "available_equipment": list(equipment) if isinstance(equipment, (list, tuple)) else None,
        "rehab_exposures": list(exposures) if isinstance(exposures, (list, tuple)) else [],
    }


def _episode_sort_key(episode: dict) -> tuple[int, int, str, str, str]:
    """Resolved episodes first (most protective first), then unresolved.

    Resolved episodes sort by stage rank so the most protective leads the atomic
    summary and the consolidation round-robin. Unresolved episodes sort after
    them, deterministically by type and identity, never inheriting a stage rank.
    """
    stage = str(episode.get("rehab_stage") or "")
    resolved = 0 if episode.get("stage_resolved") else 1
    rank = REHAB_STAGES.index(stage) if stage in REHAB_STAGES else len(REHAB_STAGES)
    return (
        resolved,
        rank,
        str(episode.get("injury_type") or ""),
        str(episode.get("episode_id") or ""),
        str(episode.get("injury_id") or ""),
    )


def _merge_live_rehab_context(group: dict, entry: dict) -> None:
    """Retain one entry's live rehab context on its location group, per episode.

    Two distinct injuries can share a location group — a sprained left ankle and
    a left-ankle tendinopathy both canonicalise to "ankle". They are separate
    injury episodes with separate evidence, stage and injury type, and neither
    may govern the other's rehab. So each episode is kept whole and independent
    in ``group["rehab_episodes"]`` (deduped by identity); clinical selection then
    runs once per episode against that episode's own candidate pool.

    The atomic ``rehab_stage`` / ``injury_id`` / ``episode_id`` / exposure fields
    are also maintained, describing the single MOST PROTECTIVE episode. They are
    a presentation convenience only (headings, back-compatible readers); they
    never stand in for the per-episode list at the selection boundary, so one
    episode's stage can no longer be paired with another's identity or evidence.
    """
    episode = _episode_context(entry)
    if episode is None:
        return

    episodes: list[dict] = group.setdefault("rehab_episodes", [])
    # Identity includes type + side so two distinct injuries with no resolved
    # identity yet (both id/episode None) are still kept apart, while a genuine
    # duplicate of the same episode is folded once.
    identity = (
        episode.get("injury_id"),
        episode.get("episode_id"),
        episode.get("injury_type"),
        episode.get("side"),
    )

    def _identity(e: dict) -> tuple:
        return (e.get("injury_id"), e.get("episode_id"), e.get("injury_type"), e.get("side"))

    if not any(_identity(e) == identity for e in episodes):
        episodes.append(episode)
    episodes.sort(key=_episode_sort_key)

    # The atomic summary tracks the most protective RESOLVED episode only — an
    # unresolved episode never becomes the group's live stage. If nothing has
    # resolved yet the summary stays unresolved; a stage is never invented.
    resolved = [e for e in episodes if e.get("stage_resolved")]
    if not resolved:
        group["rehab_stage"] = None
        group["injury_id"] = None
        group["episode_id"] = None
        group["athlete_id"] = None
        group["rehab_care_pathway"] = None
        group["available_equipment"] = None
        group["rehab_exposures"] = []
        return
    primary = resolved[0]
    group["rehab_stage"] = primary["rehab_stage"]
    group["injury_id"] = primary["injury_id"]
    group["episode_id"] = primary["episode_id"]
    group["athlete_id"] = primary["athlete_id"]
    group["rehab_care_pathway"] = primary["rehab_care_pathway"]
    group["available_equipment"] = (
        list(primary["available_equipment"])
        if isinstance(primary["available_equipment"], list)
        else None
    )
    group["rehab_exposures"] = list(primary["rehab_exposures"])


def _build_red_flag_block(entry: dict) -> str:
    location = entry.get("display_location") or entry.get("canonical_location") or "unspecified location"
    triage = ", ".join(entry.get("triage_categories", []))
    flags = ", ".join(entry.get("flags", []))
    lines = ["\n**Red Flag Detected**", f"• Location: {str(location).title()}"]
    if triage:
        lines.append(f"• Triage category: {triage}")
    if flags:
        lines.append(f"• Flags: {flags}")
    lines.append("• Do not train this injury normally until cleared by a clinician.")
    if "concussion" in triage or "suspected_concussion" in flags:
        lines.append("• No contact, sparring, high-CNS conditioning, or return-to-play progression until medically cleared.")
    lines.append("• All strength/conditioning recommendations must be manually adjusted.")
    return "\n".join(lines)


def _render_location_heading(location: str | None, merged_entry: dict | None) -> str:
    if not merged_entry:
        return location.title() if location else "Unspecified"
    display_location = str(merged_entry.get("display_location") or "").strip()
    laterality = str(merged_entry.get("laterality") or "").strip()
    canonical_location = str(merged_entry.get("canonical_location") or location or "unspecified")
    if display_location:
        if laterality and not display_location.lower().startswith(laterality.lower()):
            return f"{laterality.title()} {display_location.title()}"
        return display_location.title()
    if laterality:
        return f"{laterality.title()} {canonical_location.title()}"
    return canonical_location.title()


# ---------------------------------------------------------------------------
# Camp phase is NOT rehabilitation progress
#
# ``phase_progression`` and the phase-keyed notes below are a SELECTION key: they
# say which drill the bank offers during GPP/SPP/TAPER. They are not a statement
# that the tissue has progressed, and nothing here may be read as one. What an
# injury can currently tolerate is resolved separately, per injury, from the
# athlete's own injury and check-in history — see ``api.contracts.rehab_stage``,
# which deliberately takes no camp-phase argument.
#
# ``combine_three_phase_drills`` used to live here. It walked the bank's phase
# arrow as if it were a rehab ladder, handing drill 1 to the first phase and
# drill 2 to the second, which is exactly the conflation this separation removes.
# It had no callers and was deleted rather than rewritten; PR3 migrates the bank
# onto explicit ``rehab_stage`` values and PR4 makes them authoritative for
# selection.
# ---------------------------------------------------------------------------


def generate_support_notes(injury_string: str) -> str:
    """Return concise injury support notes consolidated for all phases."""
    phrases = split_injury_text(injury_string)
    parsed_types = set()
    for p in phrases:
        itype, loc = parse_injury_phrase(p)
        if not itype and loc:
            itype = "unspecified"
        if itype and itype in INJURY_SUPPORT_NOTES:
            parsed_types.add(itype)

    if not parsed_types:
        return ""

    lines = ["## Recovery Focus"]
    for itype in sorted(parsed_types):
        notes = INJURY_SUPPORT_NOTES[itype][:2]
        lines.append(f"- **{itype.title()}**: {'; '.join(notes)}.")

    return "\n".join(lines).strip()


def _safer_upper_body_replacements(limit: int = 15) -> list[str]:
    """Return a compact list of safer substitutes when upper-body loading is limited."""
    safe_options: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    banned_name_tokens = (
        "press",
        "bench",
        "dip",
        "push-up",
        "push up",
        "handstand",
        "toss",
        "throw",
        "slam",
        "jerk",
        "snatch",
        "clean",
        "muscle-up",
        "muscle up",
        "crawl",
    )
    banned_tags = {
        "upper_push",
        "horizontal_push",
        "press_heavy",
        "overhead",
        "dynamic_overhead",
        "dip_loaded",
        "grip_max",
        "wrist_loaded_extension",
        "wrist_extension_high",
        "explosive_upper_push",
        "mech_upper_press",
        "mech_ballistic",
    }
    equipment_priority = [
        "bodyweight",
        "bands",
        "cable",
        "dumbbells",
        "kettlebell",
        "sled",
        "rower",
        "stationary_bike",
    ]
    for entry in get_exercise_bank():
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        lowered_name = name.lower()
        if any(token in lowered_name for token in banned_name_tokens):
            continue
        tags = {str(tag).lower() for tag in entry.get("tags", [])}
        if tags & banned_tags:
            continue
        equipment = str(entry.get("equipment") or "bodyweight")
        if name in seen_names:
            continue
        seen_names.add(name)
        safe_options.append((equipment, name))

    def _sort_key(option: tuple[str, str]) -> tuple[int, str]:
        equipment, name = option
        try:
            priority = equipment_priority.index(equipment)
        except ValueError:
            priority = len(equipment_priority)
        return (priority, name)

    safe_options.sort(key=_sort_key)
    selected = [f"{name} ({equipment})" for equipment, name in safe_options[:limit]]
    return selected


def _normalize_injury_entries(injury_string: str) -> list[dict[str, str | None]]:
    injury_phrases = split_injury_text(injury_string)
    parsed_entries = []
    for phrase in injury_phrases:
        entry = parse_injury_entry(phrase)
        if entry:
            parsed_entries.append(entry)

    return _normalize_existing_injury_entries(parsed_entries)


def _normalize_existing_injury_entries(
    parsed_entries: Iterable[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    normalized_entries: list[dict[str, str | None]] = []
    for parsed_entry in parsed_entries:
        entry = dict(parsed_entry)
        phrase = str(entry.get("original_phrase") or "")
        rehab_type = (
            str(entry.get("rehab_type") or "").strip()
            or str(entry.get("injury_type") or "").strip()
            or "unspecified"
        )
        entry["rehab_type"] = rehab_type
        base_severity = INJURY_TYPE_SEVERITY.get(rehab_type, "moderate")
        phrase_severity, phrase_hits = normalize_severity(phrase)
        severity_map = {"low": "mild", "moderate": "moderate", "high": "severe"}
        mapped_severity = severity_map.get(phrase_severity, "moderate")
        if not entry.get("severity"):
            entry["severity"] = mapped_severity if phrase_hits else base_severity
        laterality = entry.get("laterality") or entry.get("side")
        entry["laterality"] = laterality
        entry["side"] = laterality
        normalized_entries.append(entry)

    seen_pairs = set()
    seen_locations = set()
    unique_entries = []
    for entry in normalized_entries:
        itype = entry.get("rehab_type")
        loc = entry.get("canonical_location")
        laterality = entry.get("laterality")
        if (itype, loc, laterality) in seen_pairs:
            continue
        if (loc, laterality) in seen_locations:
            continue
        seen_pairs.add((itype, loc, laterality))
        seen_locations.add((loc, laterality))
        unique_entries.append(entry)
    return unique_entries


def build_coach_review_entries(
    injury_string: str,
    phase: str,
    parsed_entries: Iterable[dict[str, str | None]] | None = None,
) -> list[dict]:
    """Return moderate/severe injury summaries for coach review notes."""
    entries = (
        _normalize_existing_injury_entries(parsed_entries)
        if parsed_entries is not None
        else _normalize_injury_entries(injury_string)
    )
    if not entries:
        return []

    severity_rank = {"moderate": 1, "severe": 2}
    region_entries: dict[str, dict] = {}
    for entry in entries:
        itype = entry.get("rehab_type") or entry.get("injury_type")
        # Surface/skin injuries never generate structural coach-review guidance
        # (region Do/Avoid rulesets, rehab drills, or exercise substitutions).
        # They are wound-care notes only, surfaced by the injury guardrails block.
        if _is_surface_type(itype):
            continue
        loc = entry.get("canonical_location")
        laterality = entry.get("laterality")
        severity = entry.get("severity") or INJURY_TYPE_SEVERITY.get(itype or "", "moderate")
        if severity not in {"moderate", "severe"}:
            continue
        region_key = LOCATION_REGION_MAP.get(loc or "", "unspecified")
        ruleset = REGION_GUARDRAILS.get(region_key, REGION_GUARDRAILS["lower_leg_foot"]).get(
            severity,
            REGION_GUARDRAILS["lower_leg_foot"]["moderate"],
        )
        summary = format_injury_summary(
            {
                "canonical_location": loc,
                "laterality": laterality,
                "injury_type": itype,
                "severity": severity,
                "display_location": entry.get("display_location"),
            }
        )
        rehab_drills = _rehab_drills_for_phase(itype, loc, phase, limit=3)
        existing = region_entries.get(region_key)
        if existing:
            if severity_rank.get(severity, 0) > severity_rank.get(existing["severity"], 0):
                existing["severity"] = severity
                existing["ruleset"] = ruleset
            if summary not in existing["injury_summaries"]:
                existing["injury_summaries"].append(summary)
            for drill in rehab_drills:
                if drill not in existing["rehab_drills"]:
                    existing["rehab_drills"].append(drill)
                    if len(existing["rehab_drills"]) >= 3:
                        break
            continue
        region_entries[region_key] = {
            "region_key": region_key,
            "label": "Injury safety",
            "injury_summaries": [summary],
            "severity": severity,
            "ruleset": ruleset,
            "rehab_drills": rehab_drills[:3],
        }

    return list(region_entries.values())


def rehab_drill_options_for_phase(
    itype: str,
    loc: str | None,
    phase: str,
    limit: int = 4,
    *,
    injury: dict | None = None,
    rehab_stage: str | None = None,
    available_equipment: Iterable[str] | None = None,
    exposures: Iterable[dict] = (),
    session_context: Mapping[str, object] | str | None = None,
) -> list[dict]:
    """Return the phase's rehab options, each keeping its canonical bank identity.

    Same selection and same rendered text as :func:`_rehab_drills_for_phase` —
    that function is a thin wrapper over this one, so the two can never diverge.
    The difference is that this keeps the drill's stable bank ``id`` and its
    region metadata attached to the line, which is what lets a completed rehab
    item be attributed to an injury without matching on the display name.

    Each option is ``{"line", "drill": <bank drill>, "location", "type"}``.
    """
    # Surface/skin injuries pull ONLY their own wound-care entries, never the
    # location's "unspecified" musculoskeletal loading drills.
    if _is_surface_type(itype):
        loc_candidates = normalize_rehab_location(loc)
        options: list[dict] = []
        for name, notes in _collect_surface_drills(itype, loc_candidates, phase):
            options.append(
                {
                    "line": f"{name} – {notes}" if notes else name,
                    "drill": None,
                    "location": loc,
                    "type": itype,
                }
            )
        return options[:limit]
    phase = phase.upper()
    collection_limit = 10_000 if rehab_stage and injury else limit
    options = []
    seen_lines: set[str] = set()

    def _append_drills(entry):
        for drill in entry.get("drills", []):
            name = drill.get("name")
            notes = drill.get("notes", "")
            if not name:
                continue
            parsed = _split_notes_by_phase(notes)
            if parsed:
                for phase_label, text in parsed:
                    if phase_label == phase:
                        entry_text = name if not text else f"{name} – {text}"
                        if entry_text not in seen_lines:
                            seen_lines.add(entry_text)
                            options.append(
                                {
                                    "line": entry_text,
                                    "drill": drill,
                                    "location": entry.get("location"),
                                    "type": entry.get("type"),
                                }
                            )
                        break
            else:
                entry_text = name if not notes else f"{name} – {notes}"
                if entry_text not in seen_lines:
                    seen_lines.add(entry_text)
                    options.append(
                        {
                            "line": entry_text,
                            "drill": drill,
                            "location": entry.get("location"),
                            "type": entry.get("type"),
                        }
                    )
            if len(options) >= collection_limit:
                return

    loc_candidates = normalize_rehab_location(loc)
    type_candidates = [itype, "unspecified"]
    seen_keys = set()
    for c_type in type_candidates:
        for c_loc in loc_candidates + ["unspecified"]:
            if (c_type, c_loc) in seen_keys:
                continue
            seen_keys.add((c_type, c_loc))
            for entry in get_rehab_bank():
                if entry.get("type") != c_type:
                    continue
                if entry.get("location") != c_loc:
                    continue
                if phase not in _entry_phases(entry):
                    continue
                _append_drills(entry)
                if len(options) >= collection_limit:
                    return options[:collection_limit]
    if rehab_stage and injury:
        candidates = []
        option_by_id = {}
        for option in options:
            drill = dict(option.get("drill") or {})
            drill.setdefault("injury_type", option.get("type"))
            drill.setdefault("care_pathway", "msk")
            candidates.append(drill)
            option_by_id[str(drill.get("id") or "")] = option
        result = select_rehab_candidate(
            injury=injury,
            rehab_stage=rehab_stage,
            candidates=candidates,
            available_equipment=available_equipment,
            exposures=exposures,
            session_context=session_context,
        )
        # The card contract is "the chosen drill plus its alternates", so the
        # stage-aware path returns the whole ranked list the selector chose
        # from rather than collapsing it to one entry. Position 0 is the
        # selection; everything after it is an alternate that also passed every
        # hard clinical filter.
        selected_options = [
            option_by_id[drill_id]
            for drill_id in (
                str(drill.get("id") or "") for drill in result.ranked_drills
            )
            if drill_id in option_by_id
        ]
        return selected_options[:limit]
    return options[:collection_limit]


def _rehab_drills_for_phase(itype: str, loc: str | None, phase: str, limit: int = 4) -> list[str]:
    """The rendered rehab lines for a phase. Unchanged output; see above."""
    return [option["line"] for option in rehab_drill_options_for_phase(itype, loc, phase, limit)]


def _format_restrictions_block(restrictions: Iterable[ParsedRestriction]) -> list[str]:
    if not restrictions:
        return []
    lines = ["**Restrictions (Stage-2 daily planner only)**"]
    for restriction in restrictions:
        phrase = restriction.get("original_phrase")
        if phrase:
            lines.append(f"- {phrase}")
    return lines


def format_injury_guardrails(
    phase: str,
    injuries: str,
    restrictions: Iterable[ParsedRestriction] | None = None,
    parsed_entries: Iterable[dict[str, str | None]] | None = None,
) -> str:
    """Return markdown injury guardrails for the current phase."""
    if not injuries and parsed_entries is None:
        restrictions_lines = _format_restrictions_block(restrictions or [])
        if restrictions_lines:
            return "\n".join(restrictions_lines)
        return "✅ No injury guardrails required."

    entries = (
        _normalize_existing_injury_entries(parsed_entries)
        if parsed_entries is not None
        else _normalize_injury_entries(injuries)
    )
    restrictions_list = list(restrictions or [])
    if not entries and not restrictions_list:
        return "✅ No injury guardrails required."

    lines: list[str] = []
    if entries:
        lines.append("**Injury Summary**")
    guardrails: list[tuple[str | None, str | None, dict]] = []
    for entry in entries:
        itype = entry.get("injury_type")
        loc = entry.get("canonical_location")
        laterality = entry.get("laterality")
        severity = entry.get("severity") or INJURY_TYPE_SEVERITY.get(itype or "", "moderate")
        region_key = LOCATION_REGION_MAP.get(loc or "", "unspecified")
        summary = format_injury_summary(
            {
                "canonical_location": loc,
                "laterality": laterality,
                "injury_type": itype,
                "severity": severity,
                "display_location": entry.get("display_location"),
            }
        )
        lines.append(f"- {summary}")
        # Surface/skin injuries carry no structural region guardrail — they are
        # wound-care notes only (rendered in the Rehab Priority block below).
        if _is_surface_type(itype):
            continue
        ruleset = REGION_GUARDRAILS.get(region_key, REGION_GUARDRAILS["lower_leg_foot"]).get(
            severity,
            REGION_GUARDRAILS["lower_leg_foot"]["moderate"],
        )
        guardrails.append((loc, laterality, ruleset))

    restrictions_lines = _format_restrictions_block(restrictions_list)
    if restrictions_lines:
        if lines:
            lines.append("")
        lines.extend(restrictions_lines)

    if phase.upper() == "TAPER":
        if lines:
            lines.append("")
        lines.append("_TAPER note: Glycolytic conditioning is optional when injury risk exists._")

    if entries:
        lines += ["", "**Rehab Priority**"]
        for entry in entries:
            itype = entry.get("injury_type")
            loc = entry.get("canonical_location")
            laterality = entry.get("laterality")
            severity = entry.get("severity") or INJURY_TYPE_SEVERITY.get(itype or "", "moderate")
            drills = _rehab_drills_for_phase(itype, loc, phase, limit=4)
            summary = format_injury_summary(
                {
                    "canonical_location": loc,
                    "laterality": laterality,
                    "injury_type": itype,
                    "severity": severity,
                    "display_location": entry.get("display_location"),
                }
            )
            if _is_surface_type(itype):
                # Surface/skin injuries are wound-care notes only — never a drill
                # list. Minor, stable cases train through with the calm note; all
                # others (cut/laceration or high-severity) get the wound-care note.
                if (
                    itype in MINOR_SURFACE_TRAIN_THROUGH_TYPES
                    and _normalize_rehab_severity(severity) != "high"
                ):
                    lines.append(f"- {summary}: {SURFACE_MINOR_TRAIN_THROUGH_NOTE}")
                else:
                    lines.append(f"- {summary}: {SURFACE_WOUND_CARE_NOTE}")
            elif drills:
                lines.append(f"- {summary}:")
                lines.extend([f"  - {d}" for d in drills[:4]])
            else:
                lines.append(f"- {summary}: No rehab drills available for this phase.")

    has_upper_limb = any(
        not _is_surface_type(entry.get("rehab_type") or entry.get("injury_type"))
        and LOCATION_REGION_MAP.get((entry.get("canonical_location") or ""), "unspecified") == "upper_limb"
        for entry in entries
    )
    if has_upper_limb:
        replacements = _safer_upper_body_replacements(limit=15)
        if replacements:
            lines += ["", "**Safer Replacements (Upper-Body Deload)**"]
            lines.extend([f"- {replacement}" for replacement in replacements])

    base_red_flags = [
        "Pain that worsens and stays elevated the next morning.",
        "Rapidly increasing swelling, instability, or loss of function.",
        "Numbness/tingling or night pain.",
    ]
    red_flags = []
    for _, _, ruleset in guardrails:
        for flag in ruleset.get("red_flags", []):
            if flag not in red_flags:
                red_flags.append(flag)
    if entries:
        if not red_flags:
            red_flags = base_red_flags
        else:
            for flag in base_red_flags:
                if flag not in red_flags:
                    red_flags.append(flag)

        lines += ["", "**Red Flags**"]
        lines.extend([f"- {flag}" for flag in red_flags])

    if any("bfr" in line.lower() for line in lines):
        lines.append(f"- {BFR_SAFETY_GATE}")

    return "\n".join(lines).strip()
