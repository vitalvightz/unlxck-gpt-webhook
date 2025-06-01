def generate_mindset_block(weeks_out: int) -> str:
    """
    Generate phase-specific mindset guidance based on time to fight.
    """
    if weeks_out >= 8:
        return (
            "**🧠 Mental Focus – General Prep (GPP Phase)**\n"
            "- Build foundational habits.\n"
            "- Begin 10-min visualization sessions 3x/week (focus: clean technique, effort).\n"
            "- Introduce affirmations to counter common doubts (e.g., 'I get sharper with every round').\n"
            "- Use mindfulness 2x/week post-training to enhance self-awareness.\n"
        )

    elif 3 < weeks_out < 8:
        return (
            "**🧠 Mental Focus – Specific Prep (SPP Phase)**\n"
            "- Expand visualization to include adversity: cuts, exhaustion, pressure rounds.\n"
            "- Use cue words in training: 'explode', 'lock-in', 'breathe'.\n"
            "- Introduce breath control during high-intensity sets (box breathing, 4-4-4-4).\n"
            "- Journaling 1x/week to spot mental dips, fatigue signs, or ego distractions.\n"
        )

    else:
        return (
            "**🧠 Mental Focus – Taper Phase**\n"
            "- Morning & evening visualization (2x/day): entrances, first exchange, tough moments.\n"
            "- Reinforce ego control — remove outcome obsession, lock into process.\n"
            "- Practice short mindfulness daily (5–10 min) to enhance calm.\n"
            "- Use only 1–2 sharp cue words for fight week focus ('sharp', 'ready').\n"
        )