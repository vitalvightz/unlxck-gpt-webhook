from pathlib import Path
import json


def _load_json_strip_comments(path: Path):
    """Load JSON file while ignoring lines that start with '//' comments."""
    text = path.read_text()
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        # Remove trailing comments on the same line if they exist
        if "//" in stripped:
            line = line[: line.index("//")]
        cleaned_lines.append(line)
    return json.loads("\n".join(cleaned_lines))

from .injury_synonyms import parse_injury_phrase, split_injury_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
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
REHAB_BANK = _load_json_strip_comments(DATA_DIR / "rehab_bank.json")


def _split_notes_by_phase(notes: str) -> list[tuple[str, str]]:
    """Return (phase, text) pairs if the notes use a → progression."""
    if "→" not in notes:
        return []
    segments = [seg.strip() for seg in notes.split("→")]
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

INJURY_TYPE_SEVERITY = {
    "tightness": "mild",
    "soreness": "mild",
    "stiffness": "mild",
    "pain": "mild",
    "contusion": "mild",
    "sprain": "moderate",
    "strain": "moderate",
    "tendonitis": "moderate",
    "impingement": "moderate",
    "hyperextension": "moderate",
    "swelling": "severe",
    "instability": "severe",
    "unspecified": "moderate",
}

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

def generate_rehab_protocols(
    *, injury_string: str, exercise_data: list, current_phase: str, seen_drills: set | None = None
) -> tuple[str, set]:
    """Return rehab exercise suggestions for the given injuries and phase.

    Parameters
    ----------
    injury_string:
        Raw injury description text.
    exercise_data:
        Loaded exercise bank.
    current_phase:
        Phase name (``GPP``/``SPP``/``TAPER``).
    seen_drills:
        Set used to track drills already listed in earlier phases.
    """
    if seen_drills is None:
        seen_drills = set()
    if not injury_string:
        return "\n✅ No rehab work required."

    injury_phrases = split_injury_text(injury_string)

    parsed_entries = []
    parsed_types = []
    for phrase in injury_phrases:
        itype, loc = parse_injury_phrase(phrase)
        if not itype:
            if loc:
                # default to unspecified type when a location is provided
                itype = "unspecified"
            else:
                continue
        parsed_types.append(itype)
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
    lines = []
    def _phases(entry):
        progress = entry.get("phase_progression", "")
        return [p.strip().upper() for p in progress.split("→") if p.strip()]

    for itype, loc in unique_entries:
        matches = [
            entry
            for entry in REHAB_BANK
            if (
                entry.get("type") == itype
                or entry.get("type") == "unspecified"
                or itype is None
            )
            and (
                entry.get("location") == loc
                or entry.get("location") == "unspecified"
                or loc is None
            )
            and current_phase.upper() in _phases(entry)
        ]
        if matches:
            drills = []
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
                                entry = name
                                if text:
                                    entry = f"{name} – {text}"
                                if entry not in seen_drills:
                                    drills.append(entry)
                                    seen_drills.add(entry)
                                break
                    else:
                        entry = name
                        if notes:
                            entry = f"{name} – {notes}"
                        if entry not in seen_drills:
                            drills.append(entry)
                            seen_drills.add(entry)
            drills = drills[:2]
            if drills:
                loc_title = loc.title() if loc else "Unspecified"
                type_title = itype.title() if itype else "Unspecified"
                lines.append(f"- {loc_title} ({type_title}):")
                lines.extend([f"  • {d}" for d in drills])
    if not lines:
        return "\n⚠️ No rehab options for this phase.", seen_drills

    return "\n".join(lines), seen_drills


def combine_three_phase_drills(location: str, injury_type: str) -> list[dict]:
    """Return drills covering GPP, SPP and TAPER for the location/type pair."""
    phases = {"GPP": None, "SPP": None, "TAPER": None}

    def apply_entry(entry: dict) -> None:
        progress = entry.get("phase_progression", "")
        phase_list = [p.strip().upper() for p in progress.split("→")]
        if len(phase_list) < 2:
            return
        drills = entry.get("drills", [])
        if len(drills) < 2:
            return
        if phase_list[0] in phases and phases[phase_list[0]] is None:
            phases[phase_list[0]] = drills[0]
        if phase_list[1] in phases and phases[phase_list[1]] is None:
            phases[phase_list[1]] = drills[1]

    for entry in REHAB_BANK:
        if entry.get("location") == location and entry.get("type") == injury_type:
            apply_entry(entry)
            if all(phases.values()):
                break
    if not all(phases.values()):
        for entry in REHAB_BANK:
            if entry.get("location") == location and entry.get("type") == "unspecified":
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


def _normalize_injury_entries(injury_string: str) -> list[tuple[str, str | None]]:
    injury_phrases = split_injury_text(injury_string)
    parsed_entries = []
    for phrase in injury_phrases:
        itype, loc = parse_injury_phrase(phrase)
        if not itype:
            if loc:
                itype = "unspecified"
            else:
                continue
        parsed_entries.append((itype, loc))

    if any(loc for _, loc in parsed_entries):
        parsed_entries = [p for p in parsed_entries if p[1] is not None]

    seen_pairs = set()
    seen_locations = set()
    unique_entries = []
    for itype, loc in parsed_entries:
        if (itype, loc) in seen_pairs:
            continue
        if loc in seen_locations:
            continue
        seen_pairs.add((itype, loc))
        seen_locations.add(loc)
        unique_entries.append((itype, loc))
    return unique_entries


def build_coach_review_entries(injury_string: str, phase: str) -> list[dict]:
    """Return moderate/severe injury summaries for coach review notes."""
    entries = _normalize_injury_entries(injury_string)
    if not entries:
        return []

    severity_rank = {"moderate": 1, "severe": 2}
    region_entries: dict[str, dict] = {}
    for itype, loc in entries:
        severity = INJURY_TYPE_SEVERITY.get(itype, "moderate")
        if severity not in {"moderate", "severe"}:
            continue
        region_key = LOCATION_REGION_MAP.get(loc or "", "unspecified")
        region_label = REGION_LABELS.get(region_key, REGION_LABELS["unspecified"])
        location_label = loc.title() if loc else "Unspecified"
        ruleset = REGION_GUARDRAILS.get(region_key, REGION_GUARDRAILS["lower_leg_foot"]).get(
            severity,
            REGION_GUARDRAILS["lower_leg_foot"]["moderate"],
        )
        rehab_drills = _rehab_drills_for_phase(itype, loc, phase, limit=3)
        existing = region_entries.get(region_key)
        if existing:
            existing["locations"].add(location_label)
            if severity_rank.get(severity, 0) > severity_rank.get(existing["severity"], 0):
                existing["severity"] = severity
                existing["ruleset"] = ruleset
            for drill in rehab_drills:
                if drill not in existing["rehab_drills"]:
                    existing["rehab_drills"].append(drill)
                    if len(existing["rehab_drills"]) >= 3:
                        break
            continue
        region_entries[region_key] = {
            "region_key": region_key,
            "region_label": region_label,
            "locations": {location_label},
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
        return [p.strip().upper() for p in progress.split("→") if p.strip()]

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

    candidates = [
        (itype, loc),
        ("unspecified", loc),
        (itype, "unspecified"),
        ("unspecified", "unspecified"),
    ]
    seen_keys = set()
    for c_type, c_loc in candidates:
        if (c_type, c_loc) in seen_keys:
            continue
        seen_keys.add((c_type, c_loc))
        for entry in REHAB_BANK:
            if entry.get("type") != c_type:
                continue
            if c_loc is not None and entry.get("location") != c_loc:
                continue
            if phase not in _phases(entry):
                continue
            _append_drills(entry)
            if len(drills) >= limit:
                return drills[:limit]
    return drills[:limit]


def format_injury_guardrails(phase: str, injuries: str) -> str:
    """Return markdown injury guardrails for the current phase."""
    if not injuries:
        return "✅ No injury guardrails required."

    entries = _normalize_injury_entries(injuries)
    if not entries:
        return "✅ No injury guardrails required."

    lines = ["**Injury Summary**"]
    guardrails: list[tuple[str, str, dict]] = []
    for itype, loc in entries:
        severity = INJURY_TYPE_SEVERITY.get(itype, "moderate")
        region_key = LOCATION_REGION_MAP.get(loc or "", "unspecified")
        region_label = REGION_LABELS.get(region_key, REGION_LABELS["unspecified"])
        location_label = loc.title() if loc else "Unspecified"
        severity_color = {
            "severe": "🔴",
            "moderate": "🟠",
            "mild": "🟡",
        }.get(severity, "🟠")
        lines.append(
            f"- {region_label} ({location_label}) — {itype.title()} | Severity: {severity_color} {severity}"
        )
        ruleset = REGION_GUARDRAILS.get(region_key, REGION_GUARDRAILS["lower_leg_foot"]).get(
            severity,
            REGION_GUARDRAILS["lower_leg_foot"]["moderate"],
        )
        guardrails.append((region_label, location_label, ruleset))

    if phase.upper() == "TAPER":
        lines.append("")
        lines.append("_TAPER note: Glycolytic conditioning is optional when injury risk exists._")

    lines += ["", "**Rehab Priority**"]
    for itype, loc in entries:
        drills = _rehab_drills_for_phase(itype, loc, phase, limit=4)
        location_label = loc.title() if loc else "Unspecified"
        type_label = itype.title() if itype else "Unspecified"
        if drills:
            lines.append(f"- {location_label} ({type_label}):")
            lines.extend([f"  - {d}" for d in drills[:4]])
        else:
            lines.append(f"- {location_label} ({type_label}): No rehab drills available for this phase.")

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
    if not red_flags:
        red_flags = base_red_flags
    else:
        for flag in base_red_flags:
            if flag not in red_flags:
                red_flags.append(flag)

    lines += ["", "**Red Flags**"]
    lines.extend([f"- {flag}" for flag in red_flags])

    return "\n".join(lines).strip()
