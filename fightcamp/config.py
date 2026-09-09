import re
from pathlib import Path

from .phases import PhaseEnum

GPP = PhaseEnum.GPP.value
SPP = PhaseEnum.SPP.value
TAPER = PhaseEnum.TAPER.value

PHASE_EQUIPMENT_BOOST = {
    GPP: {"barbell", "trap_bar", "sled", "pullup_bar"},
    SPP: {"landmine", "cable", "medicine_ball", "bands"},
    TAPER: {"medicine_ball", "bodyweight", "bands", "partner"},
}

PHASE_TAG_BOOST = {
    GPP: {"triphasic": 1, "eccentric": 1},
    SPP: {"contrast": 1.5, "explosive": 1.5},
    TAPER: {
        "late_strength_touch": 2,
        "maximal_strength_maintenance": 2,
        "neural_primer": 1.5,
        "speed": 1.25,
        "cluster": 1,
    },
}

PHASE_SYSTEM_RATIOS = {
    GPP: {"aerobic": 0.5, "glycolytic": 0.3, "alactic": 0.2},
    SPP: {"glycolytic": 0.5, "alactic": 0.3, "aerobic": 0.2},
    TAPER: {"alactic": 0.7, "aerobic": 0.3, "glycolytic": 0.0},
}


def conditioning_phase_workload_envelope(
    *, phase: str, system: str
) -> tuple[float | None, float | None]:
    """Active-work target and elapsed cap for one phase/system conditioning dose.

    These are not new global targets: they restate the lower active-work edge
    and elapsed cap already published by the rendered GPP/SPP phase dose
    guidance. Returned as ``(target_active_work_seconds, elapsed_cap_minutes)``,
    or ``(None, None)`` where no phase guidance applies (notably TAPER, whose
    dose stays with the countdown policy).

    Single owner for the question "how much work does this session owe?", shared
    by Stage 1 session resolution (how many drills a system keeps) and session
    composition (when a session is complete). A bank prescription, injury and
    recovery filtering, and role-level safety remain authoritative over it.
    """
    phase = str(phase or "").upper()
    system = str(system or "").strip().lower()
    if system == "glycolytic" and phase == GPP:
        # Existing GPP combat-pressure floor: 6-8 x 60 sec hard.
        return 6 * 60.0, 30.0
    if phase == GPP:
        # 3 x 3 min is the low edge of the existing GPP 3-5 x 3-5 min template.
        return 9 * 60.0, 30.0
    if phase == SPP:
        # 4 x 2 min is the low edge of the existing SPP 4-6 x 2-5 min template.
        return 8 * 60.0, 25.0
    return None, None

STAGE_1 = "STAGE_1"
STAGE_2 = "STAGE_2"

STYLE_CONDITIONING_RATIO = {
    GPP: 0.10,
    SPP: 0.35,
    TAPER: 0.00,
}

# Stage 1 should surface a surplus candidate menu for Stage 2 to choose from.
# These are candidate-output counts, not final prescribed session counts.
STRENGTH_PER_DAY = {GPP: 9, SPP: 8, TAPER: 6}
CONDITIONING_PER_DAY = {GPP: 6, SPP: 5, TAPER: 5}

# Central data directory path - used by multiple modules to access JSON data files
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Top-K Injury Guard Configuration
# ================================
# Maximum number of exercises/drills to consider for injury guard evaluation
# Used in both strength.py and conditioning.py for consistent shortlist sizing
#
# Top-K shortlist is built AFTER initial injury filtering to ensure we only
# evaluate safe candidates. This prevents candidate starvation where all
# top candidates are excluded, leaving nothing to select.
INJURY_GUARD_SHORTLIST = 125

# Minimum candidate pool size after filtering (starvation safeguard)
# If the post-filter candidate pool falls below this threshold, we widen K
MIN_CANDIDATE_POOL = 6

# Maximum K value when widening to prevent starvation
# We will widen K up to this value by doubling (e.g., 125 → 250 → 500)
MAX_INJURY_GUARD_SHORTLIST = 500

# Version string for injury rules (increment when rules change to invalidate cache)
# Format: YYYYMMDD.N (date + sequence number)
# Update this whenever INJURY_RULES, INJURY_REGION_KEYWORDS, or scoring weights change
INJURY_RULES_VERSION = "20260624.1"


def trim_to_injury_guard_shortlist(items: list) -> list:
    """
    Refactored: Utility to trim a list to the injury guard shortlist size.

    This replaces duplicate implementations of _trim_drills in conditioning.py
    and ensures consistent shortlist sizing across modules.

    Args:
        items: List of items (exercises, drills, or tuples) to trim

    Returns:
        Trimmed list limited to INJURY_GUARD_SHORTLIST
    """
    return items[:INJURY_GUARD_SHORTLIST]



_DOSE_MINUTES_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:[-\u2013]\s*\d+(?:\.\d+)?)?\s*min"
)


def conditioning_dose_minutes(dose: dict) -> float | None:
    """Elapsed minutes a conditioning dose states, from its own bank fields."""
    if not isinstance(dose, dict):
        return None
    for key in ("total_minutes", "duration_min"):
        value = dose.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, float(value))
    text = str(dose.get("duration") or dose.get("timing") or "").lower()
    match = _DOSE_MINUTES_PATTERN.search(text)
    return float(match.group(1)) if match else None


def conditioning_dose_active_work_seconds(dose: dict) -> float | None:
    """Active work a conditioning dose carries at its own bank prescription.

    Interval drills state it as ``work_sec`` x ``rounds``; continuous work
    states it as elapsed duration, which for continuous work is the same thing.
    Single owner so Stage 1 session resolution and session composition measure a
    dose the same way. Never alters a prescription — only measures one.
    """
    if not isinstance(dose, dict):
        return None
    try:
        work_sec = float(dose.get("work_sec"))
        rounds = float(dose.get("rounds"))
    except (TypeError, ValueError):
        work_sec = rounds = 0.0
    if work_sec > 0 and rounds > 0:
        return work_sec * rounds
    minutes = conditioning_dose_minutes(dose)
    return minutes * 60.0 if minutes is not None else None


_ROUNDS_FORMAT_PATTERN = re.compile(r"^\s*(\d+)\s*[xX\u00d7]\s*(\d+(?:\.\d+)?)\s*$")


def athlete_round_seconds(rounds_format: str | None) -> float | None:
    """Seconds per round the athlete actually fights, from their own intake.

    ``rounds_format`` is the canonical "<rounds> x <minutes>" intake value (the
    "Rounds x Minutes" field). This is the single place that reads a round
    duration from athlete input; there is no default and no assumed three-minute
    round, so an unparseable or absent value returns ``None`` and every bank
    prescription keeps its authored duration.
    """
    match = _ROUNDS_FORMAT_PATTERN.match(str(rounds_format or ""))
    if not match:
        return None
    minutes = float(match.group(2))
    return minutes * 60.0 if minutes > 0 else None
