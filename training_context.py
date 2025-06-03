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
        
    if not available_days:
    print("⚠️ Warning: No training days selected. Defaulting to ['Monday', 'Wednesday', 'Friday']")
    training_days = ["Monday", "Wednesday", "Friday"]

    if not frequency or int(frequency) < 1:
    print("⚠️ Warning: Frequency not set properly. Defaulting to 3 sessions/week.")
    frequency = 3

    if not fighting_style_technical:
    print("⚠️ No technical style selected. Results may be less accurate.")
    
    if not fighting_style_tactical:
    print("⚠️ No tactical style selected. Defaulting to generic style bias.")
    
    if not key_goals:
    print("⚠️ No goals provided. Training will be based on weaknesses + style only.")