import re

def normalize_equipment_list(raw):
    if isinstance(raw, list):
        return [item.lower().strip() for item in raw]
    if isinstance(raw, str):
        parts = re.split(r"\s*(?:,|/| and )\s*", raw)
        return [part.lower().strip() for part in parts if part]
    return []
    
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
    "elliptical", "bodyweight", "med_balls", "battle_rope", "kettlebells"
]

def allocate_sessions(training_frequency: int, phase: str = "GPP") -> dict:
    """Return weekly session counts based on frequency and phase."""
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

    return plan.get(freq, plan[6]).get(phase, {"strength": 1, "conditioning": 1, "recovery": 1})


def calculate_exercise_numbers(training_frequency: int, phase: str) -> dict:
    """Return recommended exercise counts for each block type.

    The result multiplies allocated session counts from ``allocate_sessions`` by
    phase-specific exercise targets. Recovery days are implied by sessions not
    scheduled for strength or conditioning.
    """

    sessions = allocate_sessions(training_frequency, phase)
    phase = phase.upper()

    strength_per_day = {"GPP": 7, "SPP": 6, "TAPER": 4}
    conditioning_per_day = {"GPP": 4, "SPP": 3, "TAPER": 2}

    return {
        "strength": strength_per_day.get(phase, 0) * sessions.get("strength", 0),
        "conditioning": conditioning_per_day.get(phase, 0) * sessions.get(
            "conditioning", 0
        ),
    }
