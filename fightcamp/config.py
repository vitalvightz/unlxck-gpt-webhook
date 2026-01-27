# Refactored: Centralized shared constants to reduce duplication across modules
# Previously defined separately in main.py, strength.py, conditioning.py, etc.
from pathlib import Path

PHASE_EQUIPMENT_BOOST = {
    "GPP": {"barbell", "trap_bar", "sled", "pullup_bar"},
    "SPP": {"landmine", "cable", "medicine_ball", "bands"},
    "TAPER": {"medicine_ball", "bodyweight", "bands", "partner"},
}

PHASE_TAG_BOOST = {
    "GPP": {"triphasic": 1, "tempo": 1, "eccentric": 1},
    "SPP": {"contrast": 1.5, "explosive": 1.5},
    "TAPER": {"neural_primer": 2, "cluster": 2, "speed": 2},
}

PHASE_SYSTEM_RATIOS = {
    "GPP": {"aerobic": 0.5, "glycolytic": 0.3, "alactic": 0.2},
    "SPP": {"glycolytic": 0.5, "alactic": 0.3, "aerobic": 0.2},
    "TAPER": {"alactic": 0.7, "aerobic": 0.3, "glycolytic": 0.0},
}

STAGE_1 = "STAGE_1"
STAGE_2 = "STAGE_2"

STYLE_CONDITIONING_RATIO = {
    "GPP": 0.20,
    "SPP": 0.60,
    "TAPER": 0.05,
}

STRENGTH_PER_DAY = {"GPP": 7, "SPP": 6, "TAPER": 4}
CONDITIONING_PER_DAY = {"GPP": 4, "SPP": 3, "TAPER": 3}

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
INJURY_RULES_VERSION = "20260126.1"


def trim_to_injury_guard_shortlist(items: list) -> list:
    """
    Refactored: Utility to trim a list to the injury guard shortlist size.
    
    This replaces duplicate implementations of _trim_drills in conditioning.py
    and ensures consistent shortlist sizing across modules.
    
    Args:
        items: List of items (exercises, drills, or tuples) to trim
        
    Returns:
        Trimmed list limited to INJURY_GUARD_SHORTLIST items
    """
    return items[:INJURY_GUARD_SHORTLIST]
