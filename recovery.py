# recovery.py

def generate_recovery_block(age: int, fatigue_level: str, phase: str) -> str:
    recovery_block = ""

    # Baseline Recovery
    recovery_block += "\n**Core Recovery Strategies:**\n"
    recovery_block += "- Daily breathwork (5–10 mins post-session)\n"
    recovery_block += "- Contrast showers daily or post-training\n"
    recovery_block += "- 8–9 hours of sleep/night + 90-min blue light cutoff\n"
    recovery_block += "- Cold exposure 2–3x/week (if needed)\n"
    recovery_block += "- Mobility circuits/light recovery work daily\n"

    # Age Adjustment
    if age >= 30:
        recovery_block += "\n**Age-Specific Adjustments:**\n"
        recovery_block += "- 72h muscle group rotation\n"
        recovery_block += "- Weekly float tank session\n"
        recovery_block += "- Collagen supplementation\n"

    # Fatigue Flags
    fatigue_level = fatigue_level.lower()
    if "high" in fatigue_level:
        recovery_block += "\n**Fatigue Red Flags:**\n"
        recovery_block += "- Drop 1 session if sleep < 6.5hrs for 3+ days\n"
        recovery_block += "- Cut weekly volume by 25–40%\n"
        recovery_block += "- Replace eccentrics with isometrics if DOMS >72hrs\n"
        recovery_block += "- Monitor for appetite/mood dips (cortisol/motivation risk)\n"

    # Phase-Specific Taper Logic
    if phase == "TAPER":
        recovery_block += "\n**Fight Week Protocol (Taper):**\n"
        recovery_block += "- Reduce volume to 30–40% of taper week\n"
        recovery_block += "- Final hard session = Tue/Wed\n"
        recovery_block += "- No soreness-inducing lifts after Wed\n"
        recovery_block += "- Final 2 days = breathwork, float tank, shadow drills\n"

    elif phase == "SPP":
        recovery_block += "\n**SPP Recovery Focus:**\n"
        recovery_block += "- Manage CNS load and alactic fatigue\n"
        recovery_block += "- Introduce 1–2 full recovery days\n"

    elif phase == "GPP":
        recovery_block += "\n**GPP Recovery Focus:**\n"
        recovery_block += "- Focus on tissue prep, joint mobility\n"
        recovery_block += "- Reset sleep routine\n"

    return recovery_block.strip()