from .injury_synonyms import parse_injury_phrase
from .rehab_protocols import get_rehab_bank, normalize_rehab_location


def _fetch_injury_drills(injuries: list, phase: str) -> list:
    """Return up to two rehab drills matching the injury info."""
    injuries = [i.lower() for i in injuries if i]
    phase = phase.upper()

    injury_types = set()
    locations = set()

    for desc in injuries:
        itype, loc = parse_injury_phrase(desc)
        if itype:
            injury_types.add(itype)
            if loc:
                locations.update(normalize_rehab_location(loc))

    drills = []
    for entry in get_rehab_bank():
        entry_phases = [
            p.strip().upper()
            for p in entry.get("phase_progression", "").split("->")
            if p.strip()
        ]
        if phase not in entry_phases:
            continue

        entry_loc = entry.get("location", "").lower()
        entry_type = entry.get("type", "").lower()
        loc_match = (
            entry_loc == "unspecified"
            or (entry_loc and entry_loc in locations)
            or any(entry_loc in inj for inj in injuries)
        )
        type_match = (
            entry_type == "unspecified"
            or (entry_type and entry_type in injury_types)
            or any(entry_type in inj for inj in injuries)
        )
        if not (loc_match and type_match):
            continue

        for drill in entry.get("drills", []):
            name = drill.get("name")
            notes = drill.get("notes")
            if not name:
                continue
            entry_str = f"{name} - {notes}" if notes else name
            drills.append(entry_str)
            if len(drills) >= 2:
                return drills

    return drills[:2]


def _is_high_pressure_weight_cut(training_context: dict) -> bool:
    if not training_context.get("weight_cut_risk", False):
        return False
    if float(training_context.get("weight_cut_pct", 0.0) or 0.0) >= 5.0:
        return True
    fatigue = str(training_context.get("fatigue", "")).strip().lower()
    days_until_fight = training_context.get("days_until_fight")
    return fatigue in {"moderate", "high"} or (
        isinstance(days_until_fight, int) and days_until_fight <= 28
    )


def generate_recovery_block(training_context: dict) -> str:
    phase = training_context["phase"]
    fatigue = training_context["fatigue"]
    age = int(training_context.get("age", 0))
    taper_week = phase == "TAPER"
    weight_cut_risk = training_context.get("weight_cut_risk", False)
    weight_cut_pct = float(training_context.get("weight_cut_pct", 0.0) or 0.0)
    high_pressure_cut = _is_high_pressure_weight_cut(training_context)

    age_risk = age >= 35 or training_context.get("age_risk", False)
    recovery_block = []

    recovery_block.append("**Core Recovery Strategies:**")
    recovery_block += [
        "- Daily breathwork (5-10 mins post-session)",
        "- Optional contrast shower: 1 min hot / 1 min cold x 5 (comfort-based; avoid if it disrupts sleep).",
        "- 8-9 hours of sleep/night + 90-min blue light cutoff",
        "- Cold exposure 2-3x/week (if needed)",
        "- Mobility circuits/light recovery work daily",
    ]

    if age_risk:
        recovery_block.append("\n**Age-Specific Adjustments:**")
        recovery_block += [
            "- 72h muscle group rotation",
            "- Weekly float tank or sauna session",
            "- Collagen + vitamin C pre-training",
        ]

    if fatigue == "high":
        recovery_block.append("\n**Fatigue Red Flags:**")
        recovery_block += [
            "- Drop 1 session if sleep < 6.5hrs for 3+ days",
            "- Cut weekly volume by 25-40%",
            "- Replace eccentrics with isometrics if DOMS >72hrs",
            "- Monitor for appetite/mood dips (cortisol/motivation risk)",
        ]
    elif fatigue == "moderate":
        recovery_block.append("\n**Moderate Fatigue Notes:**")
        recovery_block += [
            "- Add 1 full rest day",
            "- Prioritize post-session nutrition & breathwork",
        ]

    if taper_week:
        recovery_block.append("\n**Fight Week Protocol (Taper):**")
        recovery_block += [
            "- Reduce volume to 30-40% of taper week",
            "- Final hard session = Tue/Wed",
            "- No soreness-inducing lifts after Wed",
            "- Final 2 days = breathwork, float tank, shadow drills",
        ]
    elif phase == "SPP":
        recovery_block.append("\n**SPP Recovery Focus:**")
        recovery_block += [
            "- Manage CNS load and alactic fatigue",
            "- Introduce 1-2 full recovery days",
        ]
    elif phase == "GPP":
        recovery_block.append("\n**GPP Recovery Focus:**")
        recovery_block += [
            "- Focus on tissue prep, joint mobility",
            "- Reset sleep routine",
        ]

    if weight_cut_risk:
        recovery_block.append("\n**Active Weight-Cut Recovery Note:**")
        recovery_block += [
            "- Recovery cost is higher during the cut, so protect sleep, hydration, and between-session freshness.",
            "- Keep optional soreness and density low when they do not directly support the week's main objective.",
        ]
        if high_pressure_cut:
            recovery_block.append(
                "- High-pressure cut: protect freshness first and reduce optional fatigue before adding more work."
            )

        if 3.0 <= weight_cut_pct < 6.0:
            recovery_block.append("\n**Moderate Weight Cut Recovery Recommendations:**")
            recovery_block += [
                "- Monitor hydration closely; aim to avoid >2% dehydration",
                "- Prioritize quality sleep and stress management",
                "- Incorporate light mobility and stretching",
                "- Avoid excessive heat exposure or hard training sessions",
                "- Use electrolyte drinks during training and post-training",
            ]
        elif weight_cut_pct >= 6.0:
            recovery_block.append("\n**Severe Weight Cut Recovery Warning:**")
            recovery_block += [
                "- Cut >6% -> elevate recovery urgency",
                "- Add 2 float tank or Epsom salt baths in fight week",
                "- Emphasize post-weigh-in refeed: fluids, high-GI carbs",
                "- Monitor mood, sleep, and hydration hourly post-weigh-in",
                "- Consider medical supervision if possible",
            ]

    return "\n".join(recovery_block).strip()
