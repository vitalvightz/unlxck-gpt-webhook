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

def allocate_sessions(days_available: int) -> dict:
    if days_available <= 3:
        return {'strength': 1, 'conditioning': 1, 'recovery': 1}
    elif days_available == 4:
        return {'strength': 2, 'conditioning': 1, 'recovery': 1}
    elif days_available == 5:
        return {'strength': 2, 'conditioning': 2, 'recovery': 1}
    else:
        return {'strength': 3, 'conditioning': 2, 'recovery': 1}