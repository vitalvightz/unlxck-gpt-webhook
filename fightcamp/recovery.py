from .rehab_protocols import REHAB_BANK, INJURY_SUPPORT_NOTES
from .injury_synonyms import (
    parse_injury_phrase,
)


def _fetch_injury_drills(injuries: list, phase: str) -> list:
    """Return up to two rehab drills matching the injury info.

    Parameters
    ----------
    injuries:
        List of free-form injury descriptions from the intake form.
    phase:
        Current training phase (``GPP``, ``SPP`` or ``TAPER``).

    Injury phrases are normalized using ``INJURY_SYNONYM_MAP`` so text like
    ``"twisted wrist"`` correctly maps to the ``sprain`` type and ``wrist``
    location when filtering the rehab bank.
    """
    injuries = [i.lower() for i in injuries if i]
    phase = phase.upper()

    # Build sets of canonical types and locations from all sources
    injury_types = set()
    locations = set()

    for desc in injuries:
        itype, loc = parse_injury_phrase(desc)
        if itype:
            injury_types.add(itype)
        if loc:
            locations.add(loc)

    drills = []

    for entry in REHAB_BANK:
        entry_phases = [
            p.strip().upper()
            for p in entry.get("phase_progression", "").split("→")
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
            if name:
                entry_str = name
                if notes:
                    entry_str = f"{name} – {notes}"
                drills.append(entry_str)
                if len(drills) >= 4:
                    return drills

    return drills


def generate_recovery_block(training_context: dict) -> str:
    phase = training_context["phase"]
    fatigue = training_context["fatigue"]
    weight = float(training_context.get("weight", 0.0))
    age = int(training_context.get("age", 0))
    taper_week = phase == "TAPER"
    weight_cut_risk = training_context.get("weight_cut_risk", False)
    weight_cut_pct = training_context.get("weight_cut_pct", 0.0)

    # Heuristic: Age-based risk >34y
    age_risk = age >= 35 or training_context.get("age_risk", False)

    recovery_block = []

    # Core Recovery
    recovery_block.append("**Core Recovery Strategies:**")
    recovery_block += [
        "- Daily breathwork (5–10 mins post-session)",
        "- Post-session constant showers (1 min hot/1min cold 5x)",
        "- 8–9 hours of sleep/night + 90-min blue light cutoff",
        "- Cold exposure 2–3x/week (if needed)",
        "- Mobility circuits/light recovery work daily"
    ]

    injuries = training_context.get("injuries", [])
    injury_drills = _fetch_injury_drills(
        injuries,
        phase,
    )
    if injury_drills:
        recovery_block.append("\n**Injury-Specific Drills:**")
        recovery_block += [f"- {d}" for d in injury_drills]

    # Add injury-specific support tips
    done_types = set()
    for desc in injuries:
        itype, _ = parse_injury_phrase(desc)
        if itype and itype in INJURY_SUPPORT_NOTES and itype not in done_types:
            done_types.add(itype)
            recovery_block.append(f"\n**{itype.title()} Support Notes:**")
            recovery_block += [f"- {t}" for t in INJURY_SUPPORT_NOTES[itype]]

    # Age-based Adjustments
    if age_risk:
        recovery_block.append("\n**Age-Specific Adjustments:**")
        recovery_block += [
            "- 72h muscle group rotation",
            "- Weekly float tank or sauna session",
            "- Collagen + vitamin C pre-training"
        ]

    # Fatigue Score Flags
    if fatigue == "high":
        recovery_block.append("\n**Fatigue Red Flags:**")
        recovery_block += [
            "- Drop 1 session if sleep < 6.5hrs for 3+ days",
            "- Cut weekly volume by 25–40%",
            "- Replace eccentrics with isometrics if DOMS >72hrs",
            "- Monitor for appetite/mood dips (cortisol/motivation risk)"
        ]
    elif fatigue == "moderate":
        recovery_block.append("\n**Moderate Fatigue Notes:**")
        recovery_block += [
            "- Add 1 full rest day",
            "- Prioritize post-session nutrition & breathwork"
        ]

    # Phase-Based Adjustments
    if taper_week:
        recovery_block.append("\n**Fight Week Protocol (Taper):**")
        recovery_block += [
            "- Reduce volume to 30–40% of taper week",
            "- Final hard session = Tue/Wed",
            "- No soreness-inducing lifts after Wed",
            "- Final 2 days = breathwork, float tank, shadow drills"
        ]
    elif phase == "SPP":
        recovery_block.append("\n**SPP Recovery Focus:**")
        recovery_block += [
            "- Manage CNS load and alactic fatigue",
            "- Introduce 1–2 full recovery days"
        ]
    elif phase == "GPP":
        recovery_block.append("\n**GPP Recovery Focus:**")
        recovery_block += [
            "- Focus on tissue prep, joint mobility",
            "- Reset sleep routine"
        ]

    # Graduated Weight Cut Recovery Guidance
    if weight_cut_risk:
        if 3.0 <= weight_cut_pct < 6.0:
            recovery_block.append("\n**⚠️ Moderate Weight Cut Recovery Recommendations:**")
            recovery_block += [
                "- Monitor hydration closely; aim to avoid >2% dehydration",
                "- Prioritize quality sleep and stress management",
                "- Incorporate light mobility and stretching",
                "- Avoid excessive heat exposure or hard training sessions",
                "- Use electrolyte drinks during training and post-training"
            ]
        elif weight_cut_pct >= 6.0:
            recovery_block.append("\n**⚠️ Severe Weight Cut Recovery Warning:**")
            recovery_block += [
                "- Cut >6% → elevate recovery urgency",
                "- Add 2 float tank or Epsom salt baths in fight week",
                "- Emphasize post-weigh-in refeed: fluids, high-GI carbs",
                "- Monitor mood, sleep, and hydration hourly post-weigh-in",
                "- Consider medical supervision if possible"
            ]

    return "\n".join(recovery_block).strip()
