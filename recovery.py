# recovery.py

from typing import List, Dict

def assign_recovery_days(all_days: List[str], used_days: List[str], required: int) -> List[str]:
    return [d for d in all_days if d not in used_days][:required]

def generate_recovery_block(training_context: Dict, used_days: List[str]) -> Dict:
    phase = training_context["phase"]
    fatigue = training_context["fatigue"]
    injuries = training_context.get("injuries", [])
    weight = training_context.get("weight", 75)
    weight_class = training_context.get("weight_class", "lightweight")
    age = training_context.get("age", 27)
    weight_cut_risk = training_context.get("weight_cut_risk", False)
    weight_cut_pct = training_context.get("weight_cut_pct", 0.0)
    taper_week = training_context.get("taper_week", False)
    all_days = training_context["training_days"]
    needed = training_context["training_split"]["recovery"]
    assigned_days = assign_recovery_days(all_days, used_days, needed)

    block = ["\n🛀 **RECOVERY MODULE**"]

    # Core
    block += [
        "**Core Recovery Strategies:**",
        "- Daily breathwork (5–10 mins post-session)",
        "- Contrast showers daily or post-training",
        "- 8–9 hours of sleep/night + 90-min blue light cutoff",
        "- Cold exposure 2–3x/week (if needed)",
        "- Mobility circuits/light recovery work daily"
    ]

    # Age
    if age >= 30:
        block += [
            "\n**Age-Specific Adjustments:**",
            "- 72h muscle group rotation",
            "- Weekly float tank session",
            "- Collagen supplementation"
        ]

    # Fatigue
    if fatigue == "high":
        block += [
            "\n**Fatigue Red Flags:**",
            "- Drop 1 session if sleep < 6.5hrs for 3+ days",
            "- Cut weekly volume by 25–40%",
            "- Replace eccentrics with isometrics if DOMS >72hrs",
            "- Monitor appetite/mood for CNS fatigue"
        ]
    elif fatigue == "moderate":
        block += [
            "\n**Moderate Fatigue Notes:**",
            "- Add 1 full rest day",
            "- Prioritize post-session nutrition & breathwork"
        ]

    # Phase
    if taper_week or phase == "TAPER":
        block += [
            "\n**Fight Week Protocol (Taper):**",
            "- Reduce volume to 30–40% of taper week",
            "- Final hard session = Tue/Wed",
            "- No soreness-inducing lifts after Wed",
            "- Final 2 days = breathwork, float tank, shadow drills"
        ]
    elif phase == "SPP":
        block += [
            "\n**SPP Recovery Focus:**",
            "- Manage CNS load and alactic fatigue",
            "- Introduce 1–2 full recovery days"
        ]
    elif phase == "GPP":
        block += [
            "\n**GPP Recovery Focus:**",
            "- Focus on tissue prep, joint mobility",
            "- Reset sleep routine"
        ]

    # Weight cut
    if weight_cut_risk:
        block += [
            "\n**⚠️ Weight Cut Recovery Warning:**",
            f"- Cut >{weight_cut_pct}% → elevate recovery urgency",
            "- Add 2 float tank or Epsom salt baths in fight week",
            "- Emphasize post-weigh-in refeed: fluids, high-GI carbs",
            "- Monitor mood, sleep, hydration hourly post-weigh-in"
        ]

    return {
        "block": "\n".join(block),
        "days_used": assigned_days
    }