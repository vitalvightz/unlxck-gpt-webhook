BASE_PHASE_RATIOS = {
    # Ultra-short phases (1-3 weeks) - Minimal GPP, mostly SPP with quick taper
    1: {
        "boxing": {"GPP": 0.0, "SPP": 0.25, "TAPER": 0.75},
        "muay_thai": {"GPP": 0.05, "SPP": 0.25, "TAPER": 0.70},
        "mma": {"GPP": 0.10, "SPP": 0.25, "TAPER": 0.65},
        "kickboxing": {"GPP": 0.0, "SPP": 0.25, "TAPER": 0.75},
    },
    2: {
        "boxing": {"GPP": 0.0, "SPP": 0.35, "TAPER": 0.65},
        "muay_thai": {"GPP": 0.10, "SPP": 0.35, "TAPER": 0.55},
        "mma": {"GPP": 0.15, "SPP": 0.35, "TAPER": 0.50},
        "kickboxing": {"GPP": 0.0, "SPP": 0.35, "TAPER": 0.65},
    },
    3: {
        "boxing": {"GPP": 0.10, "SPP": 0.50, "TAPER": 0.40},
        "muay_thai": {"GPP": 0.15, "SPP": 0.50, "TAPER": 0.35},
        "mma": {"GPP": 0.20, "SPP": 0.50, "TAPER": 0.30},
        "kickboxing": {"GPP": 0.10, "SPP": 0.50, "TAPER": 0.40},
    },
    # Standard short phases (4-6 weeks) - Balanced GPP/SPP, moderate taper
    4: {
        "boxing": {"GPP": 0.20, "SPP": 0.60, "TAPER": 0.20},
        "muay_thai": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
        "mma": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
        "kickboxing": {"GPP": 0.20, "SPP": 0.60, "TAPER": 0.20},
    },
    5: {
        "boxing": {"GPP": 0.20, "SPP": 0.60, "TAPER": 0.20},
        "muay_thai": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
        "mma": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
        "kickboxing": {"GPP": 0.20, "SPP": 0.60, "TAPER": 0.20},
    },
    6: {
        "boxing": {"GPP": 0.17, "SPP": 0.66, "TAPER": 0.17},
        "muay_thai": {"GPP": 0.20, "SPP": 0.63, "TAPER": 0.17},
        "mma": {"GPP": 0.22, "SPP": 0.61, "TAPER": 0.17},
        "kickboxing": {"GPP": 0.20, "SPP": 0.63, "TAPER": 0.17},
    },
    # Mid-length phases (7-10 weeks) - More SPP focus, reduced taper
    7: {
        "boxing": {"GPP": 0.20, "SPP": 0.65, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.25, "SPP": 0.60, "TAPER": 0.15},
        "mma": {"GPP": 0.25, "SPP": 0.60, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.20, "SPP": 0.65, "TAPER": 0.15},
    },
    8: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
    9: {
        "boxing": {"GPP": 0.20, "SPP": 0.65, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.25, "SPP": 0.60, "TAPER": 0.15},
        "mma": {"GPP": 0.25, "SPP": 0.60, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.20, "SPP": 0.65, "TAPER": 0.15},
    },
    10: {
        "boxing": {"GPP": 0.20, "SPP": 0.65, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.25, "SPP": 0.60, "TAPER": 0.15},
        "mma": {"GPP": 0.25, "SPP": 0.60, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.20, "SPP": 0.65, "TAPER": 0.15},
    },
    # Long phases (11-16 weeks) - Higher GPP for MMA, stable SPP/taper
    11: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.30, "SPP": 0.575, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
    12: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.30, "SPP": 0.575, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
    13: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.30, "SPP": 0.575, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
    14: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.30, "SPP": 0.575, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
    15: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.30, "SPP": 0.575, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
    16: {
        "boxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "muay_thai": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
        "mma": {"GPP": 0.30, "SPP": 0.575, "TAPER": 0.125},
        "kickboxing": {"GPP": 0.25, "SPP": 0.625, "TAPER": 0.125},
    },
}

STYLE_ADJUSTMENTS = {
    "pressure fighter": {"SPP": +0.05, "GPP": -0.05},
    "counter striker": {"GPP": +0.04, "SPP": -0.04},
    "grappler": {"GPP": +0.06, "TAPER": -0.06},
    "striker": {"SPP": +0.08, "GPP": -0.08},
    "muay_thai": {"SPP": +0.03, "GPP": -0.03},
    "hybrid stance": {"SPP": +0.04, "TAPER": -0.04},
    "clinch fighter": {"GPP": +0.05, "SPP": -0.05},
}

STYLE_RULES = {
    "pressure fighter": {
        "SPP_MIN_PERCENT": 0.65,
        "MAX_TAPER": 0.10,
    },
    "clinch fighter": {
        "TAPER_MAX_DAYS": 5,
        "SPP_CLINCH_RATIO": 0.40,
    },
    "grappler": {
        "GPP_MIN_PERCENT": 0.35,
    },
    "boxing": {
        "SPP_BOXING_RATIO": 0.50,
    },
}


def calculate_phase_weeks(camp_length: int, sport: str, style: str | None = None) -> dict:
    """Return the number of weeks per phase for a fight camp."""
    closest = min(BASE_PHASE_RATIOS.keys(), key=lambda x: abs(x - camp_length))
    ratios = BASE_PHASE_RATIOS[closest][sport].copy()

    if style in STYLE_ADJUSTMENTS:
        for phase, delta in STYLE_ADJUSTMENTS[style].items():
            if phase in ratios:
                ratios[phase] = max(0.05, ratios[phase] + delta)

    weeks = {
        "GPP": round(ratios["GPP"] * camp_length),
        "SPP": round(ratios["SPP"] * camp_length),
        "TAPER": round(ratios["TAPER"] * camp_length),
    }

    if style in STYLE_RULES:
        rules = STYLE_RULES[style]
        if "SPP_MIN_PERCENT" in rules:
            min_spp = int(camp_length * rules["SPP_MIN_PERCENT"])
            if weeks["SPP"] < min_spp:
                diff = min_spp - weeks["SPP"]
                weeks["SPP"] = min_spp
                weeks["GPP"] = max(1, weeks["GPP"] - diff)
        if "MAX_TAPER" in rules:
            max_taper = int(camp_length * rules["MAX_TAPER"])
            if weeks["TAPER"] > max_taper:
                excess = weeks["TAPER"] - max_taper
                weeks["TAPER"] = max_taper
                weeks["SPP"] += excess
        if "TAPER_MAX_DAYS" in rules:
            max_taper_weeks = max(1, rules["TAPER_MAX_DAYS"] // 7)
            if weeks["TAPER"] > max_taper_weeks:
                delta = weeks["TAPER"] - max_taper_weeks
                weeks["TAPER"] = max_taper_weeks
                weeks["SPP"] += delta

    weeks = {k: max(1, v) for k, v in weeks.items()}
    weeks["TAPER"] = min(2, weeks["TAPER"])
    return weeks
