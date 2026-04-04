from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import CONDITIONING_PER_DAY, STRENGTH_PER_DAY
from .days_out_policy import DaysOutContext, build_days_out_context, get_effective_planning_inputs

EQUIP_ALIASES = {
    "med balls": "medicine_ball",
    "med ball": "medicine_ball",
    "medicine balls": "medicine_ball",
    "medicine ball": "medicine_ball",
    "band": "bands",
    "plates": "plate",
    "sandbags": "sandbag",
    "battle rope": "battle_ropes",
    "battle ropes": "battle_ropes",
}


def _split_items(value):
    if isinstance(value, str):
        return re.split(r"\s*(?:,|/|\+| and )\s*", value)
    return [value]


def normalize_equipment_list(raw):
    """Return a list of canonical equipment tokens."""
    parts: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            parts.extend(_split_items(item))
    elif isinstance(raw, str):
        parts.extend(_split_items(raw))
    else:
        return []

    normalized: list[str] = []
    for part in parts:
        key = part.lower().strip()
        if key in {"med balls / bands", "med balls/bands"}:
            normalized.extend(["medicine_ball", "bands"])
            continue
        key = EQUIP_ALIASES.get(key, key).replace(" ", "_")
        if key:
            normalized.append(key)
    return normalized
    
# ✅ Correct constant definition (not a function)
known_equipment = [
    "barbell", "dumbbell", "dumbbells", "kettlebell", "sled", "medicine_ball",
    "trap_bar", "bands", "cable", "box", "weight_vest", "landmine",
    "towel", "partner", "bench", "trx", "pullup_bar", "plate",
    "swiss_ball", "heavy_bag", "thai_pads", "neck_harness", "log",
    "tire", "atlas_stone", "water_jug", "bulgarian_bag", "sandbag",
    "treadmill", "rower", "agility_ladder", "battle_ropes", "sledgehammer",
    "climbing_rope", "bosu_ball", "foam_roller", "assault_bike",
    "stationary_bike", "step_mill", "recumbent_bike", "arm_ergometer",
    "elliptical", "pool", "bodyweight", "battle_rope", "kettlebells"
]


@dataclass(frozen=True)
class TrainingContext:
    fatigue: str
    training_frequency: int
    days_available: int
    training_days: list[str]
    injuries: list[str]
    style_technical: list[str]
    style_tactical: list[str]
    weaknesses: list[str]
    equipment: list[str]
    weight_cut_risk: bool
    weight_cut_pct: float
    fight_format: str
    status: str
    training_split: dict
    key_goals: list[str]
    training_preference: str
    mental_block: list[str] | str
    age: int
    weight: float
    prev_exercises: list[str]
    recent_exercises: list[str]
    phase_weeks: dict
    days_until_fight: int | None
    hard_sparring_days: list[str] = field(default_factory=list)
    technical_skill_days: list[str] = field(default_factory=list)
    days_out_context: DaysOutContext | None = None

    def to_flags(self) -> dict:
        """Return flags dict with both raw and effective planning values.

        When a ``days_out_context`` is present, fields that the policy marks as
        ``ignore_for_planning`` are neutralised in the top-level keys (so
        downstream consumers automatically receive the effective value) while
        the original athlete-entered values are preserved under ``raw_*`` keys.
        """
        base = asdict(self)
        # Remove the non-serialisable context object from the flat dict.
        base.pop("days_out_context", None)
        if self.days_out_context is None:
            return base
        # Build effective overlay and stash raw mirrors for overridden fields.
        effective = get_effective_planning_inputs(base, self.days_out_context)
        for key in base:
            if effective.get(key) != base[key]:
                effective[f"raw_{key}"] = base[key]
        # Attach serialisable policy summary so downstream modules can branch.
        effective["days_out_policy"] = self.days_out_context.to_dict()
        return effective

def allocate_sessions(
    training_frequency: int,
    phase: str = "GPP",
    days_out_context: DaysOutContext | None = None,
) -> dict:
    """Return weekly session counts based on frequency and phase.

    When *days_out_context* is provided the allocation is clamped by the
    days-out policy:
    * D-3 and below: strength and conditioning counts are reduced, recovery
      counts increase.
    * When ``allow_weekly_architecture`` is False the frequency-based lookup
      is bypassed entirely and a fight-week-specific minimal allocation is
      returned.
    """
    freq = max(1, min(int(training_frequency), 6))
    phase = phase.upper()

    plan = {
        1: {
            "GPP": {"strength": 1, "conditioning": 0, "recovery": 0},
            "SPP": {"strength": 0, "conditioning": 1, "recovery": 0},
            "TAPER": {"strength": 0, "conditioning": 1, "recovery": 0},
        },
        2: {
            "GPP": {"strength": 1, "conditioning": 1, "recovery": 0},
            "SPP": {"strength": 1, "conditioning": 1, "recovery": 0},
            "TAPER": {"strength": 0, "conditioning": 1, "recovery": 1},
        },
        3: {
            "GPP": {"strength": 1, "conditioning": 1, "recovery": 1},
            "SPP": {"strength": 1, "conditioning": 2, "recovery": 0},
            "TAPER": {"strength": 1, "conditioning": 1, "recovery": 1},
        },
        4: {
            "GPP": {"strength": 2, "conditioning": 1, "recovery": 1},
            "SPP": {"strength": 1, "conditioning": 2, "recovery": 1},
            "TAPER": {"strength": 1, "conditioning": 1, "recovery": 2},
        },
        5: {
            "GPP": {"strength": 2, "conditioning": 2, "recovery": 1},
            "SPP": {"strength": 2, "conditioning": 2, "recovery": 1},
            "TAPER": {"strength": 1, "conditioning": 1, "recovery": 3},
        },
        6: {
            "GPP": {"strength": 2, "conditioning": 3, "recovery": 1},
            "SPP": {"strength": 2, "conditioning": 3, "recovery": 1},
            "TAPER": {"strength": 1, "conditioning": 1, "recovery": 4},
        },
    }

    base = plan.get(freq, plan[6]).get(phase, {"strength": 1, "conditioning": 1, "recovery": 1})

    if days_out_context is None:
        return base

    perms = days_out_context.planner_permissions

    # D-0: fight-day protocol — no normal sessions
    if perms.fight_day_protocol:
        return {"strength": 0, "conditioning": 0, "recovery": 0}

    # When weekly architecture is disabled the frequency table is irrelevant.
    if not perms.allow_weekly_architecture:
        s = 1 if perms.allow_strength_anchor or perms.allow_strength_primer_only else 0
        c = 0 if perms.max_conditioning_stressors == 0 else min(1, base.get("conditioning", 0))
        r = max(1, freq - s - c)
        return {"strength": s, "conditioning": c, "recovery": r}

    # Clamp conditioning stressors
    max_cs = perms.max_conditioning_stressors
    if max_cs is not None:
        base = {**base, "conditioning": min(base.get("conditioning", 0), max_cs)}

    # Clamp strength if no full block allowed
    if not perms.allow_full_strength_block and not perms.allow_strength_anchor:
        if perms.allow_strength_primer_only:
            base = {**base, "strength": min(base.get("strength", 0), 1)}
        else:
            base = {**base, "strength": 0}

    return base


def calculate_exercise_numbers(training_frequency: int, phase: str) -> dict:
    """Return recommended exercise counts for each block type.

    The result multiplies allocated session counts from ``allocate_sessions`` by
    phase-specific exercise targets. Recovery days are implied by sessions not
    scheduled for strength or conditioning.
    """

    sessions = allocate_sessions(training_frequency, phase)
    phase = phase.upper()

    return {
        "strength": STRENGTH_PER_DAY.get(phase, 0) * sessions.get("strength", 0),
        "conditioning": CONDITIONING_PER_DAY.get(phase, 0) * sessions.get(
            "conditioning", 0
        ),
    }
