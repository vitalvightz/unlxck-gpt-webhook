from pathlib import Path

# Updated recovery module that imports fatigue logic from fatigue_utils.py
recovery_module_code = '''
from fatigue_utils import get_fatigue_adjustments


def generate_recovery_block(age: int, fatigue_level: str, phase: str, weight: float, weight_class: str) -> str:
    recovery_block = ""

    # Weight class limits (UFC standards in kg)
    weight_class_limits = {
        "Flyweight": 56.7, "Bantamweight": 61.2, "Featherweight": 65.8,
        "Lightweight": 70.3, "Welterweight": 77.1, "Middleweight": 83.9,
        "Light Heavyweight": 93.0, "Heavyweight": 120.2
    }

    # Core Recovery
    recovery_block += "\\n**Core Recovery Strategies:**\\n"
    recovery_block += "- Daily breathwork (5–10 mins post-session)\\n"
    recovery_block += "- Contrast showers daily or post-training\\n"
    recovery_block += "- 8–9 hours of sleep/night + 90-min blue light cutoff\\n"
    recovery_block += "- Cold exposure 2–3x/week (if needed)\\n"
    recovery_block += "- Mobility circuits/light recovery work daily\\n"

    # Age-based Adjustments
    if age >= 30:
        recovery_block += "\\n**Age-Specific Adjustments:**\\n"
        recovery_block += "- 72h muscle group rotation\\n"
        recovery_block += "- Weekly float tank session\\n"
        recovery_block += "- Collagen supplementation\\n"

    # Fatigue Adjustments
    fatigue_note = get_fatigue_adjustments(fatigue_level)
    if fatigue_note:
        recovery_block += f"\\n{fatigue_note}"

    # Phase-Based Adjustments
    if phase == "TAPER":
        recovery_block += "\\n**Fight Week Protocol (Taper):**\\n"
        recovery_block += "- Reduce volume to 30–40% of taper week\\n"
        recovery_block += "- Final hard session = Tue/Wed\\n"
        recovery_block += "- No soreness-inducing lifts after Wed\\n"
        recovery_block += "- Final 2 days = breathwork, float tank, shadow drills\\n"

    elif phase == "SPP":
        recovery_block += "\\n**SPP Recovery Focus:**\\n"
        recovery_block += "- Manage CNS load and alactic fatigue\\n"
        recovery_block += "- Introduce 1–2 full recovery days\\n"

    elif phase == "GPP":
        recovery_block += "\\n**GPP Recovery Focus:**\\n"
        recovery_block += "- Focus on tissue prep, joint mobility\\n"
        recovery_block += "- Reset sleep routine\\n"

    # Weight Cut Risk Trigger
    if weight_class in weight_class_limits and weight:
        try:
            weight = float(weight)
            class_limit = weight_class_limits[weight_class]
            percent_cut = ((weight - class_limit) / weight) * 100
            if percent_cut > 6:
                recovery_block += "\\n**⚠️ Weight Cut Recovery Warning:**\\n"
                recovery_block += "- Cut >6% → elevate recovery urgency\\n"
                recovery_block += "- Add 2 float tank or Epsom salt baths in fight week\\n"
                recovery_block += "- Emphasize post-weigh-in refeed: fluids, high-GI carbs\\n"
                recovery_block += "- Monitor mood, sleep, and hydration hourly post-weigh-in\\n"
        except:
            pass

    return recovery_block.strip()
'''

path = Path("/mnt/data/recovery.py")
path.write_text(recovery_module_code.strip())