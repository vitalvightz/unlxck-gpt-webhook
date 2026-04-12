import json
import logging
from typing import Iterable

from .injury_formatting import format_injury_summary, parse_injury_entry
from .injury_guard import INJURY_TYPE_SEVERITY, normalize_severity
from .injury_synonyms import parse_injury_phrase, split_injury_text
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


def prime_rehab_bank() -> None:
    get_rehab_bank()
    get_rehab_locations()
REHAB_LOCATION_ALIASES = {
    "biceps": ["bicep"],
    "bicep": ["biceps"],
    "hamstring": ["hamstrings"],
    "hamstrings": ["hamstring"],
    "lower back": ["lower_back"],
    "lower_back": ["lower back"],
    "upper back": ["upper_back"],
    "upper_back": ["upper back"],
}


def normalize_rehab_location(location: str | None) -> list[str]:
    if not location:
        return ["unspecified"]
    candidates: list[str] = []

    def _add(value: str | None) -> None:
        if value and value not in candidates:
            candidates.append(value)

    _add(location)
    for alias in REHAB_LOCATION_ALIASES.get(location, []):
        _add(alias)
    if "_" in location:
        _add(location.replace("_", " "))
    if " " in location:
        _add(location.replace(" ", "_"))

    filtered = [candidate for candidate in candidates if candidate in get_rehab_locations()]
    return filtered or candidates


def _split_phase_progression(text: str) -> list[str]:
    """Return normalized phase tokens from either arrow encoding."""
    normalized = (text or "").replace("\u00e2\u2020\u2019", "\u2192")
    return [segment.strip().upper() for segment in normalized.split("\u2192") if segment.strip()]


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

LOCATION_REGION_MAP = {
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
    "unspecified": [
        "Use general joint mobility and soft-tissue tools",
        "Don’t load until pain-free at bodyweight",
        "Consult clinician if symptoms persist >5 days",
    ],
}
RED_FLAG_TYPES = [
    "fracture",
    "rupture",
    "dislocation",
    "post-surgery",
    "severe swelling",
    "acute nerve issue",
    "infection/inflammatory",
]

BFR_SAFETY_GATE = (
    "Use only if already experienced with BFR and medically appropriate; "
    "stop if numbness/tingling occurs."
)

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


def classify_drill_function(name: str, notes: str = "") -> str:
    """Classify a rehab drill into one of the REHAB_FUNCTION_BUCKETS.

    Classification is keyword-based and is intended as *guidance* for the
    GPT/OpenAI planner — not a hard constraint.  When ambiguous, returns
    ``"control"`` as a safe default.

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
    text = f"{name} {notes}".lower()
    for bucket, keywords in REHAB_FUNCTION_BUCKETS.items():
        if any(kw in text for kw in keywords):
            return bucket
    return "control"


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


def generate_rehab_protocols(
    *,
    injury_string: str,
    exercise_data: list,
    current_phase: str,
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
    if not injury_string:
        return "\n✅ No rehab work required.", seen_drills

    injury_phrases = split_injury_text(injury_string)

    parsed_entries = []
    for phrase in injury_phrases:
        itype, loc = parse_injury_phrase(phrase)
        if not itype:
            if loc:
                # default to unspecified type when a location is provided
                itype = "unspecified"
            else:
                continue
        parsed_entries.append((itype, loc))

    # Prioritize specific injuries over unspecified duplicates
    parsed_entries.sort(key=lambda x: (x[0] is None or x[0] == "unspecified"))

    # Drop injuries without a body part when at least one body part was found
    if any(loc for _, loc in parsed_entries):
        parsed_entries = [p for p in parsed_entries if p[1] is not None]

    seen_pairs = set()
    seen_locations = set()
    unique_entries = []
    for pair in parsed_entries:
        itype, loc = pair
        if pair in seen_pairs:
            continue
        if loc in seen_locations:
            continue
        seen_pairs.add(pair)
        seen_locations.add(loc)
        unique_entries.append(pair)

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

    def _phases(entry):
        progress = entry.get("phase_progression", "")
        return _split_phase_progression(progress)

    for itype, loc in unique_entries:
        loc_candidates = normalize_rehab_location(loc)
        matches = [
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
            and current_phase.upper() in _phases(entry)
        ]
        if matches:
            drills: list[tuple[str, str]] = []  # (name, notes_for_phase)
            for m in matches:
                for d in m.get("drills", []):
                    name = d.get("name")
                    notes = d.get("notes", "")
                    if not name:
                        continue

                    parsed = _split_notes_by_phase(notes)
                    if parsed:
                        for phase_label, text in parsed:
                            if phase_label == current_phase.upper():
                                drills.append((name, text))
                                break
                    else:
                        drills.append((name, notes))

            # Apply volume ceiling.  Function classification is recorded as
            # a tag but does NOT hard-block same-function drills — the model
            # retains authority to include multiple drills of the same class
            # when justified by the athlete's needs.
            selected = drills[:drill_limit]

            if selected:
                loc_title = loc.title() if loc else "Unspecified"
                type_title = itype.title() if itype else "Unspecified"
                lines.append(f"- {loc_title} ({type_title}):")
                for name, notes in selected:
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


def combine_three_phase_drills(location: str, injury_type: str) -> list[dict]:
    """Return drills covering GPP, SPP and TAPER for the location/type pair."""
    phases = {"GPP": None, "SPP": None, "TAPER": None}
    location_candidates = normalize_rehab_location(location)

    def apply_entry(entry: dict) -> None:
        progress = entry.get("phase_progression", "")
        phase_list = _split_phase_progression(progress)
        if len(phase_list) < 2:
            return
        drills = entry.get("drills", [])
        if len(drills) < 2:
            return
        if phase_list[0] in phases and phases[phase_list[0]] is None:
            phases[phase_list[0]] = drills[0]
        if phase_list[1] in phases and phases[phase_list[1]] is None:
            phases[phase_list[1]] = drills[1]

    for entry in get_rehab_bank():
        if entry.get("type") != injury_type:
            continue
        if entry.get("location") in location_candidates:
            apply_entry(entry)
            if all(phases.values()):
                break
    if not all(phases.values()):
        for entry in get_rehab_bank():
            if entry.get("type") != "unspecified":
                continue
            if entry.get("location") in location_candidates:
                apply_entry(entry)
                if all(phases.values()):
                    break

    if all(phases.values()):
        return [phases["GPP"], phases["SPP"], phases["TAPER"]]
    return []


def generate_support_notes(injury_string: str) -> str:
    """Return injury support notes consolidated for all phases."""
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

    lines = ["## General Injury Support Notes"]
    for itype in parsed_types:
        lines.append(f"*{itype.title()} Support Advice:*")
        lines.extend([f"- {n}" for n in INJURY_SUPPORT_NOTES[itype]])
        lines.append("")

    return "\n".join(lines).strip()


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
        base_severity = INJURY_TYPE_SEVERITY.get(entry.get("injury_type") or "", "moderate")
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
        itype = entry.get("injury_type")
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
        itype = entry.get("injury_type")
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


def _rehab_drills_for_phase(itype: str, loc: str | None, phase: str, limit: int = 4) -> list[str]:
    phase = phase.upper()
    drills: list[str] = []

    def _phases(entry):
        progress = entry.get("phase_progression", "")
        return _split_phase_progression(progress)

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
                        if entry_text not in drills:
                            drills.append(entry_text)
                        break
            else:
                entry_text = name if not notes else f"{name} – {notes}"
                if entry_text not in drills:
                    drills.append(entry_text)
            if len(drills) >= limit:
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
                if phase not in _phases(entry):
                    continue
                _append_drills(entry)
                if len(drills) >= limit:
                    return drills[:limit]
    return drills[:limit]


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
            if drills:
                lines.append(f"- {summary}:")
                lines.extend([f"  - {d}" for d in drills[:4]])
            else:
                lines.append(f"- {summary}: No rehab drills available for this phase.")

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

