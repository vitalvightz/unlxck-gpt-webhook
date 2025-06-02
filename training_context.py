# training_context.py

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


def build_training_context() -> dict:
    """
    Returns the full user profile including training_days and desired session split.
    GPT will be responsible for allocating which module lands on which day.
    """
    training_context = {
        "phase": "SPP",
        "fatigue": "moderate",
        "days_available": 5,
        "training_days": ["Monday", "Tuesday", "Thursday", "Friday", "Saturday"],
        "injuries": ["hamstring"],
        "style": "brawler",
        "weaknesses": ["core", "balance"],
        "equipment": ["barbell", "dumbbells", "bike"],
        "weight_cut_risk": True,
        "weight_cut_pct": 5.0,
        "fight_format": "3x5"
    }

    training_context["training_split"] = allocate_sessions(training_context["days_available"])
    return training_context