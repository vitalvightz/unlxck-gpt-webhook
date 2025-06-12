from pathlib import Path
import json

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
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

    injuries = [i.strip().lower() for i in injury_string.split(',') if i.strip()]

    flagged = []
    for injury in injuries:
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
    for injury in injuries:
        options = REHAB_BANK.get(injury, [])
        phase_names = [op["name"] for op in options if current_phase in op.get("phases", [])]
        valid = [ex["name"] for ex in exercise_data if ex["name"] in phase_names and "rehab_friendly" in ex.get("tags", [])]
        if valid:
            lines.append(f"- {injury.title()}: {valid[0]}")
    if not lines:
        return "\n⚠️ No rehab options for this phase."
    return "\n**Rehab Protocols**\n" + "\n".join(lines)
