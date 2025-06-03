# training_context.py

import re

def normalize_equipment_list(raw):
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|/| and )\s*", raw)
    return [p.strip().lower().replace(" ", "_") for p in parts if p.strip()]

def allocate_sessions(days_available: int) -> dict:
    """
    Returns a session split based on number of available training days.
    GPT will later use this info + the actual days to decide allocation.
    """
    if days_available <= 3:
        return {'strength': 1, 'conditioning': 1, 'recovery': 1}
    elif days_available == 4:
        return {'strength': 2, 'conditioning': 1, 'recovery': 1}
    elif days_available == 5:
        return {'strength': 2, 'conditioning': 2, 'recovery': 1}
    else:
        return {'strength': 3, 'conditioning': 2, 'recovery': 1}