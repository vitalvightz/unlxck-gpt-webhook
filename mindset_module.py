def classify_mental_block(text: str, top_n: int = 2) -> list:
    """Classify the mental block based on input text, return top N likely matches."""
    if not text or not isinstance(text, str):
        return ["generic"]

    text = text.lower().strip()
    if any(bad in text for bad in ["n/a", "none", "idk", "na"]) or len(text.split()) < 2:
        return ["generic"]

    scores = {}
    for block, keywords in mental_blocks.items():
        match_count = sum(1 for kw in keywords if kw in text)
        if match_count:
            scores[block] = match_count

    if not scores:
        return ["generic"]

    sorted_blocks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_blocks = [block for block, _ in sorted_blocks[:top_n]]
    return top_blocks

def get_mindset_by_phase(phase: str, flags: dict) -> str:
    """Get a brief mindset strategy for top blocks in this phase."""
    blocks = flags.get("mental_block", ["generic"])
    if isinstance(blocks, str):
        blocks = [blocks]

    phase = phase.upper()
    output_lines = [f"## Mindset Strategy ({phase})"]

    for block in blocks:
        tip = mindset_bank.get(phase, {}).get(block, mindset_bank[phase].get("generic", "Stay focused."))
        output_lines.append(f"**{block.title()}** → {tip}")

    if phase == "TAPER":
        activation = mindset_bank.get("TAPER", {}).get("pre-fight_activation")
        if activation:
            output_lines.append(f"**Pre-Fight Activation** → {activation}")

    return "\n\n".join(output_lines)

def get_mental_protocols(blocks: list) -> str:
    """Return full mindset training protocols across GPP → SPP → TAPER."""
    if isinstance(blocks, str):
        blocks = [blocks]

    sections = [f"# Mental Block Strategy: {', '.join(b.title() for b in blocks)}\n"]

    for phase in ["GPP", "SPP", "TAPER"]:
        phase_lines = [f"## {phase}"]
        for block in blocks:
            entry = mindset_bank.get(phase, {}).get(block, mindset_bank[phase]["generic"])
            phase_lines.append(f"**{block.title()}** → {entry}")
        if phase == "TAPER":
            activation = mindset_bank.get("TAPER", {}).get("pre-fight_activation")
            if activation:
                phase_lines.append(f"**Pre-Fight Activation** → {activation}")
        sections.append("\n".join(phase_lines))

    return "\n\n".join(sections)