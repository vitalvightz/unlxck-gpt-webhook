BASE_PHASE_RATIOS = {
    # Ultra-short phases (1–3 weeks): quick tune-up, not much base-building
    1: {
        "boxing": {"GPP": 0.05, "SPP": 0.20, "TAPER": 0.75},
        "muay_thai": {"GPP": 0.10, "SPP": 0.20, "TAPER": 0.70},
        "mma": {"GPP": 0.10, "SPP": 0.25, "TAPER": 0.65},
        "kickboxing": {"GPP": 0.05, "SPP": 0.20, "TAPER": 0.75},
    },
    2: {
        "boxing": {"GPP": 0.10, "SPP": 0.30, "TAPER": 0.60},
        "muay_thai": {"GPP": 0.15, "SPP": 0.30, "TAPER": 0.55},
        "mma": {"GPP": 0.15, "SPP": 0.35, "TAPER": 0.50},
        "kickboxing": {"GPP": 0.10, "SPP": 0.30, "TAPER": 0.60},
    },
    3: {
        "boxing": {"GPP": 0.15, "SPP": 0.45, "TAPER": 0.40},
        "muay_thai": {"GPP": 0.20, "SPP": 0.45, "TAPER": 0.35},
        "mma": {"GPP": 0.20, "SPP": 0.50, "TAPER": 0.30},
        "kickboxing": {"GPP": 0.15, "SPP": 0.45, "TAPER": 0.40},
    },

    # Standard short camps (4–6 weeks)
    4: {
        "boxing": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
        "muay_thai": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
        "mma": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
        "kickboxing": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
    },
    5: {
        "boxing": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
        "muay_thai": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
        "mma": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
        "kickboxing": {"GPP": 0.25, "SPP": 0.55, "TAPER": 0.20},
    },
    6: {
        "boxing": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
        "muay_thai": {"GPP": 0.35, "SPP": 0.45, "TAPER": 0.20},
        "mma": {"GPP": 0.35, "SPP": 0.45, "TAPER": 0.20},
        "kickboxing": {"GPP": 0.30, "SPP": 0.50, "TAPER": 0.20},
    },

    # Mid-length fight camps (7–10 weeks)
    7: {
        "boxing": {"GPP": 0.35, "SPP": 0.50, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "mma": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.35, "SPP": 0.50, "TAPER": 0.15},
    },
    8: {
        "boxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "mma": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.35, "SPP": 0.50, "TAPER": 0.15},
    },
    9: {
        "boxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "mma": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.35, "SPP": 0.50, "TAPER": 0.15},
    },
    10: {
        "boxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "mma": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.35, "SPP": 0.50, "TAPER": 0.15},
    },

    # Long camps (11–16 weeks) – longer base, full development
    11: {
        "boxing": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "mma": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
    },
    12: {
        "boxing": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "mma": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
    },
    13: {
        "boxing": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "mma": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
    },
    14: {
        "boxing": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "mma": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
    },
    15: {
        "boxing": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "mma": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
    },
    16: {
        "boxing": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "muay_thai": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "mma": {"GPP": 0.45, "SPP": 0.40, "TAPER": 0.15},
        "kickboxing": {"GPP": 0.40, "SPP": 0.45, "TAPER": 0.15},
    },
}

STYLE_ADJUSTMENTS = {
    "pressure fighter": {"SPP": +0.05, "GPP": -0.05},
    "counter striker": {"GPP": +0.04, "SPP": -0.04},
    "grappler": {"GPP": +0.06, "TAPER": -0.06},
    "muay_thai": {"SPP": +0.03, "GPP": -0.03},
    "hybrid": {"SPP": +0.04, "TAPER": -0.04},
    "clinch fighter": {"GPP": +0.05, "SPP": -0.05},
    "scrambler": {"GPP": +0.03, "TAPER": -0.03},
}

STYLE_RULES = {
    "pressure fighter": {
        "SPP_MIN_PERCENT": 0.50,
        "MAX_TAPER": 0.10,
    },
    "clinch fighter": {
        "TAPER_MAX_DAYS": 7,
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
    camp_length: int,
    sport: str,
    style: str | list[str] | None = None,
    status: str | None = None,
    fatigue: str | None = None,
    weight_cut_risk: bool | None = None,
    mental_block: str | list[str] | None = None,
    weight_cut_pct: float | None = None,
) -> dict:
    """Return weeks per phase for a fight camp.

    The calculation prioritizes the base ratios for 1–16 week camps, then
    applies any style adjustments followed by min/max rules.  Output weeks
    always sum to ``camp_length`` and taper is limited to two weeks.  If the
    athlete is ``pro``/``professional`` and the camp is at least four weeks
    long, GPP time is shifted to SPP based on fatigue, weight cut and mental
    block state.
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

    # 3b. Professional adjustment based on fatigue, cut and mindset
    if status and status.strip().lower() in {"professional", "pro"} and camp_length >= 4:
        fat = (fatigue or "").strip().lower()
        cut_pct = weight_cut_pct if weight_cut_pct is not None else 0.0
        cut_flag = bool(weight_cut_risk)
        blocks: list[str] = []
        if isinstance(mental_block, str):
            blocks = [mental_block.lower()]
        elif isinstance(mental_block, list):
            blocks = [b.lower() for b in mental_block]

        if fat == "low" and not cut_flag and all(b in {"generic", "confidence"} for b in blocks):
            ratios["SPP"] += 0.10
            ratios["GPP"] -= 0.10
        elif fat in ["low", "moderate"] and cut_pct <= 5 and not any(b in {"motivation", "gas tank", "injury fear"} for b in blocks):
            ratios["SPP"] += 0.075
            ratios["GPP"] -= 0.075
        else:
            ratios["SPP"] += 0.05
            ratios["GPP"] -= 0.05

        if ratios["GPP"] < 0.15:
            diff = 0.15 - ratios["GPP"]
            ratios["GPP"] = 0.15
            ratios["SPP"] = max(0.05, ratios["SPP"] - diff)

    # 4. Re-normalize so GPP + SPP + TAPER == 1.0
    total = ratios["GPP"] + ratios["SPP"] + ratios["TAPER"]
    ratios = {k: v / total for k, v in ratios.items()}

    # Capture fractional day breakdown before week rounding
    days = {
        phase: max(0, round(ratios[phase] * camp_length * 7))
        for phase in ("GPP", "SPP", "TAPER")
    }

    # 5. Convert ratios to week counts
    weeks = {
        "GPP": max(0, round(ratios["GPP"] * camp_length)),
        "SPP": max(0, round(ratios["SPP"] * camp_length)),
        "TAPER": max(0, min(2, round(ratios["TAPER"] * camp_length))),
    }

    def _rebalance(weeks_dict: dict) -> None:
        total = weeks_dict["GPP"] + weeks_dict["SPP"] + weeks_dict["TAPER"]
        if total < camp_length:
            weeks_dict["SPP"] += camp_length - total
        elif total > camp_length:
            excess = total - camp_length
            for phase in ("TAPER", "GPP", "SPP"):
                if excess <= 0:
                    break
                cut = min(weeks_dict[phase], excess)
                weeks_dict[phase] -= cut
                excess -= cut

    _rebalance(weeks)

    if camp_length >= 3:
        weeks["GPP"] = max(1, weeks["GPP"])
        weeks["SPP"] = max(1, weeks["SPP"])
        _rebalance(weeks)

    # 6. Apply post-conversion style rules when relevant
    for s in all_styles:
        rules = STYLE_RULES.get(s)
        if rules:
            _apply_style_rules(rules, camp_length, weeks)

    # Ensure totals still sum to camp_length after adjustments
    _rebalance(weeks)

    # 7. Return dictionary with both weeks and estimated days
    return {
        **weeks,
        "days": days,
    }
