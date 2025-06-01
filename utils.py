def get_phase(weeks_out: int, age: int) -> str:
    if weeks_out > 8:
        return "# Phase: GPP\nLong-term preparation. Build general capacity, fix imbalances."
    elif 3 < weeks_out <= 8:
        return "# Phase: SPP\nMid-camp intensity. Sharpen energy systems, fight specificity."
    else:
        return "# Phase: TAPER\nFinal tuning. Prioritize CNS freshness, maintain sharpness."

def get_safety_block(flags: dict) -> str:
    block = []
    if flags.get("fatigue") == "high":
        block.append("- Reduce volume in CNS-intensive lifts (e.g., deadlift, power cleans)")
    if "knee" in flags.get("injuries", ""):
        block.append("- Avoid deep squats or jumps. Use belt squats or sled work")
    if not block:
        return "# No red flag safety constraints."
    return "# SAFETY FLAGS:\n" + "\n".join(block)

def get_mental_protocols(mental_block: str, phase: str) -> str:
    strategy = {
        "fear": "Introduce discomfort-based simulations (e.g., cue sparring, surprise drills)",
        "confidence": "Integrate anchor phrases, post-session journaling for wins",
        "focus": "Minimize cognitive overload, 1-task workouts, breath-focused conditioning",
        "motivation": "Use progress journaling, phase milestones, visual triggers",
        "generic": "Include one anchor phrase per week (e.g., 'Control chaos', 'Stay in the round')"
    }
    return f"# MENTAL PROTOCOL ({mental_block.title()} - {phase} Phase):\n" + strategy.get(mental_block, strategy["generic"])
