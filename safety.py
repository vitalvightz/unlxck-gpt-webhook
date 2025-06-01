def get_safety_block(flags: dict) -> str:
    blocks = []
    if flags.get("fatigue") == "high":
        blocks.append("Avoid excessive volume. Prioritize neural recovery.")
    if flags.get("weight_cut_risk"):
        blocks.append("Monitor hydration + reduce high glycolytic loads.")
    if flags.get("injury_warning"):
        blocks.append("Do not load compromised joints. Use substitutions.")
    return "\n".join(blocks)
