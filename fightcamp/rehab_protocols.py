from pathlib import Path
import json

from .injury_synonyms import parse_injury_phrase

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

INJURY_TYPES = ["sprain", "strain", "tightness", "contusion", "swelling", "tendonitis", "impingement", "instability", "stiffness", "pain", "soreness", "hyperextension", "unspecified"]
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

    import re
    phrases = re.split(r'[,.;&]|(?:\band\b)|(?:\bbut\b)|(?:\balso\b)', injury_string.lower())
    injury_phrases = [p.strip() for p in phrases if p.strip()]

    parsed_entries = []
    for phrase in injury_phrases:
        itype, loc = parse_injury_phrase(phrase)
        if itype and loc:
            parsed_entries.append((itype, loc))

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

    for itype, loc in parsed_entries:
        matches = [
            entry for entry in REHAB_BANK
            if entry.get("type") == itype
            and entry.get("location") == loc
            and current_phase.upper() in _phases(entry)
        ]
        if matches:
            drills = [d["name"] for m in matches for d in m.get("drills", [])][:2]
            if drills:
                lines.append(f"- {loc.title()} ({itype.title()}): {', '.join(drills)}")
    if not lines:
        return "\n⚠️ No rehab options for this phase."
    return "\n**Rehab Protocols**\n" + "\n".join(lines)
