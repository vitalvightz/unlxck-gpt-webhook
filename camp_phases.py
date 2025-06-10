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
    "muay_thai": {"SPP": +0.03, "GPP": -0.03},
    "hybrid": {"SPP": +0.04, "TAPER": -0.04},
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
}


def _normalize_styles(style: str | list[str] | None) -> list[str]:
    if style is None:
        return []
    if isinstance(style, str):
        return [s.strip().lower() for s in style.split(',') if s.strip()]
    return [s.strip().lower() for s in style if s.strip()]


def _apply_style_rules(rules: dict, camp_length: int, weeks: dict) -> None:
    """Adjust phase weeks according to style rules."""
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
    if "SPP_CLINCH_RATIO" in rules:
        min_spp = int(camp_length * rules["SPP_CLINCH_RATIO"])
        if weeks["SPP"] < min_spp:
            diff = min_spp - weeks["SPP"]
            weeks["SPP"] = min_spp
            weeks["GPP"] = max(1, weeks["GPP"] - diff)
def calculate_phase_weeks(
    camp_length: int, sport: str, style: str | list[str] | None = None
) -> dict:
    """Return weeks per phase for a fight camp.

    The calculation prioritizes the base ratios for 1–16 week camps, then
    applies any style adjustments followed by min/max rules.  Output weeks
    always sum to ``camp_length`` and taper is limited to two weeks.
    """

    # 1. Clamp camp_length and fetch base ratios
    camp_length = max(1, min(16, camp_length))
    closest = min(BASE_PHASE_RATIOS.keys(), key=lambda x: abs(x - camp_length))
    ratios = BASE_PHASE_RATIOS[closest][sport].copy()

    # 2. Apply style adjustments
    for s in _normalize_styles(style):
        if s in STYLE_ADJUSTMENTS:
            for phase, delta in STYLE_ADJUSTMENTS[s].items():
                if phase in ratios:
                    ratios[phase] = max(0.05, ratios[phase] + delta)

    # 3. Apply style rules for min/max enforcement on ratios
    all_styles = _normalize_styles(style)
    if sport in STYLE_RULES:
        all_styles.append(sport)
    for s in all_styles:
        rules = STYLE_RULES.get(s, {})
        if "SPP_MIN_PERCENT" in rules:
            ratios["SPP"] = max(ratios["SPP"], rules["SPP_MIN_PERCENT"])
        if "MAX_TAPER" in rules:
            ratios["TAPER"] = min(ratios["TAPER"], rules["MAX_TAPER"])
        if "TAPER_MAX_DAYS" in rules:
            max_taper_ratio = max(1, rules["TAPER_MAX_DAYS"] // 7) / camp_length
            ratios["TAPER"] = min(ratios["TAPER"], max_taper_ratio)
        if "SPP_CLINCH_RATIO" in rules:
            ratios["SPP"] = max(ratios["SPP"], rules["SPP_CLINCH_RATIO"])
        if "GPP_MIN_PERCENT" in rules:
            ratios["GPP"] = max(ratios["GPP"], rules["GPP_MIN_PERCENT"])

    # 4. Re-normalize so GPP + SPP + TAPER == 1.0
    total = ratios["GPP"] + ratios["SPP"] + ratios["TAPER"]
    ratios = {k: v / total for k, v in ratios.items()}

    # 5. Convert ratios to weeks
    spp_w = round(ratios["SPP"] * camp_length)
    taper_w = min(2, round(ratios["TAPER"] * camp_length))
    gpp_w = camp_length - spp_w - taper_w

    # 6. Clamp to at least one week where possible
    gpp_w = max(1, gpp_w)
    spp_w = max(1, spp_w)
    total_weeks = gpp_w + spp_w + taper_w
    if total_weeks < camp_length:
        spp_w += camp_length - total_weeks
    elif total_weeks > camp_length:
        reduce_by = total_weeks - camp_length
        gpp_w = max(1, gpp_w - reduce_by)

    # 7. Return dictionary
    return {"GPP": gpp_w, "SPP": spp_w, "TAPER": taper_w}
