from pathlib import Path
import json

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
REHAB_BANK = json.loads((DATA_DIR / "rehab_bank.json").read_text())

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

def generate_rehab_protocols(*, injury_string: str, exercise_data: list, current_phase: str) -> str:
    """Return rehab exercise suggestions for the given injuries and phase."""
    if not injury_string:
        return "\n✅ No rehab work required."

    injury_phrases = split_injury_text(injury_string)

    parsed_entries = []
    parsed_types = []
    for phrase in injury_phrases:
        itype, loc = parse_injury_phrase(phrase)
        if itype:
            parsed_types.append(itype)
        if itype or loc:
            parsed_entries.append((itype, loc))

    seen_pairs = set()
    unique_entries = []
    for pair in parsed_entries:
        if pair not in seen_pairs:
            seen_pairs.add(pair)
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
            "• All strength/conditioning recommendations must be manually adjusted."
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
                    if name and name not in drills:
                        drills.append(name)
            drills = drills[:2]
            if drills:
                lines.append(f"- {loc.title()} ({itype.title()}): {', '.join(drills)}")
    if not lines:
        return "\n⚠️ No rehab options for this phase."

    # Inject injury-specific support notes
    done_types = set()
    for itype in parsed_types:
        if itype in INJURY_SUPPORT_NOTES and itype not in done_types:
            done_types.add(itype)
            lines.append(f"\n*{itype.title()} Support Advice:*")
            lines.extend([f"- {n}" for n in INJURY_SUPPORT_NOTES[itype]])

    return "\n**Rehab Protocols**\n" + "\n".join(lines)
