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
    GPP: {"triphasic": 1, "tempo": 1, "eccentric": 1},
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
