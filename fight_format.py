# fight_format.py

def interpret_fight_format(rounds_format: str) -> dict:
    """
    Analyzes fight format (e.g. '3x3', '5x5') and returns energy system priorities.
    """
    if not rounds_format:
        return {
            "energy_focus": "balanced",
            "conditioning_priority": ["aerobic", "glycolytic"]
        }

    try:
        rounds, minutes = map(int, rounds_format.lower().split('x'))
        total_duration = rounds * minutes
    except (ValueError, AttributeError):
        # If parsing fails, default to balanced assumption
        return {
            "energy_focus": "balanced",
            "conditioning_priority": ["aerobic", "glycolytic"]
        }

    if rounds == 5 and minutes >= 5:
        return {
            "energy_focus": "long-duration",
            "conditioning_priority": ["glycolytic", "aerobic"]
        }
    elif rounds == 3 and minutes == 3:
        return {
            "energy_focus": "explosive bursts",
            "conditioning_priority": ["ATP-PCr", "glycolytic"]
        }
    elif total_duration >= 20:
        return {
            "energy_focus": "hybrid-endurance",
            "conditioning_priority": ["aerobic", "glycolytic"]
        }
    else:
        return {
            "energy_focus": "mixed",
            "conditioning_priority": ["glycolytic", "ATP-PCr"]
        }