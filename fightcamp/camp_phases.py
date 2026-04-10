from __future__ import annotations

from .phases import PHASE_REBALANCE_ORDER, PhaseEnum

GPP = PhaseEnum.GPP.value
SPP = PhaseEnum.SPP.value
TAPER = PhaseEnum.TAPER.value


def _phase_ratios(gpp: float, spp: float, taper: float) -> dict[str, float]:
    return {GPP: gpp, SPP: spp, TAPER: taper}


def _effective_phase_block_count(total_days: int) -> int:
    base = max(1, min(16, round(total_days / 7)))
    if 8 <= total_days <= 13:
        return 2
    return base


BASE_PHASE_RATIOS = {
    1: {
        "boxing": _phase_ratios(0.00, 0.60, 0.40),
        "muay_thai": _phase_ratios(0.00, 0.55, 0.45),
        "mma": _phase_ratios(0.00, 0.65, 0.35),
        "kickboxing": _phase_ratios(0.00, 0.60, 0.40),
    },
    2: {
        "boxing": _phase_ratios(0.10, 0.55, 0.35),
        "muay_thai": _phase_ratios(0.10, 0.50, 0.40),
        "mma": _phase_ratios(0.10, 0.60, 0.30),
        "kickboxing": _phase_ratios(0.10, 0.55, 0.35),
    },
    3: {
        "boxing": _phase_ratios(0.15, 0.60, 0.25),
        "muay_thai": _phase_ratios(0.20, 0.55, 0.25),
        "mma": _phase_ratios(0.15, 0.65, 0.20),
        "kickboxing": _phase_ratios(0.15, 0.60, 0.25),
    },
    4: {
        "boxing": _phase_ratios(0.24, 0.45, 0.31),
        "muay_thai": _phase_ratios(0.29, 0.40, 0.31),
        "mma": _phase_ratios(0.29, 0.40, 0.31),
        "kickboxing": _phase_ratios(0.24, 0.45, 0.31),
    },
    5: {
        "boxing": _phase_ratios(0.29, 0.40, 0.31),
        "muay_thai": _phase_ratios(0.29, 0.40, 0.31),
        "mma": _phase_ratios(0.29, 0.40, 0.31),
        "kickboxing": _phase_ratios(0.24, 0.45, 0.31),
    },
    6: {
        "boxing": _phase_ratios(0.29, 0.40, 0.31),
        "muay_thai": _phase_ratios(0.34, 0.35, 0.31),
        "mma": _phase_ratios(0.34, 0.35, 0.31),
        "kickboxing": _phase_ratios(0.29, 0.40, 0.31),
    },
    7: {
        "boxing": _phase_ratios(0.34, 0.40, 0.26),
        "muay_thai": _phase_ratios(0.39, 0.35, 0.26),
        "mma": _phase_ratios(0.39, 0.35, 0.26),
        "kickboxing": _phase_ratios(0.34, 0.40, 0.26),
    },
    8: {
        "boxing": _phase_ratios(0.39, 0.35, 0.26),
        "muay_thai": _phase_ratios(0.39, 0.35, 0.26),
        "mma": _phase_ratios(0.39, 0.35, 0.26),
        "kickboxing": _phase_ratios(0.34, 0.40, 0.26),
    },
    9: {
        "boxing": _phase_ratios(0.39, 0.35, 0.26),
        "muay_thai": _phase_ratios(0.39, 0.35, 0.26),
        "mma": _phase_ratios(0.39, 0.35, 0.26),
        "kickboxing": _phase_ratios(0.34, 0.40, 0.26),
    },
    10: {
        "boxing": _phase_ratios(0.39, 0.35, 0.26),
        "muay_thai": _phase_ratios(0.39, 0.35, 0.26),
        "mma": _phase_ratios(0.39, 0.35, 0.26),
        "kickboxing": _phase_ratios(0.34, 0.40, 0.26),
    },
    11: {
        "boxing": _phase_ratios(0.44, 0.30, 0.26),
        "muay_thai": _phase_ratios(0.44, 0.30, 0.26),
        "mma": _phase_ratios(0.44, 0.30, 0.26),
        "kickboxing": _phase_ratios(0.39, 0.35, 0.26),
    },
    12: {
        "boxing": _phase_ratios(0.44, 0.30, 0.26),
        "muay_thai": _phase_ratios(0.44, 0.30, 0.26),
        "mma": _phase_ratios(0.44, 0.30, 0.26),
        "kickboxing": _phase_ratios(0.39, 0.35, 0.26),
    },
    13: {
        "boxing": _phase_ratios(0.44, 0.30, 0.26),
        "muay_thai": _phase_ratios(0.44, 0.30, 0.26),
        "mma": _phase_ratios(0.44, 0.30, 0.26),
        "kickboxing": _phase_ratios(0.39, 0.35, 0.26),
    },
    14: {
        "boxing": _phase_ratios(0.44, 0.30, 0.26),
        "muay_thai": _phase_ratios(0.44, 0.30, 0.26),
        "mma": _phase_ratios(0.44, 0.30, 0.26),
        "kickboxing": _phase_ratios(0.39, 0.35, 0.26),
    },
    15: {
        "boxing": _phase_ratios(0.44, 0.30, 0.26),
        "muay_thai": _phase_ratios(0.44, 0.30, 0.26),
        "mma": _phase_ratios(0.44, 0.30, 0.26),
        "kickboxing": _phase_ratios(0.39, 0.35, 0.26),
    },
    16: {
        "boxing": _phase_ratios(0.44, 0.30, 0.26),
        "muay_thai": _phase_ratios(0.44, 0.30, 0.26),
        "mma": _phase_ratios(0.44, 0.30, 0.26),
        "kickboxing": _phase_ratios(0.39, 0.35, 0.26),
    },
}

STYLE_ADJUSTMENTS = {
    "pressure fighter": {SPP: +0.05, GPP: -0.05},
    "counter striker": {GPP: +0.04, SPP: -0.04},
    "grappler": {GPP: +0.06, TAPER: -0.06},
    "muay_thai": {SPP: +0.03, GPP: -0.03},
    "hybrid": {SPP: +0.04, TAPER: -0.04},
    "clinch fighter": {GPP: +0.05, SPP: -0.05},
    "scrambler": {GPP: +0.03, TAPER: -0.03},
}

STYLE_ADJUSTMENT_CAP = 0.07

STYLE_RULES = {
    "pressure fighter": {
        "SPP_MIN_PERCENT": 0.45,
        "MAX_TAPER": 0.15,
    },
    "clinch fighter": {
        "TAPER_MAX_DAYS": 10,
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
        return [item.strip().lower() for item in style.split(",") if item.strip()]
    return [item.strip().lower() for item in style if item.strip()]


def _apply_style_rules(rules: dict, camp_length: int, weeks: dict[str, int]) -> None:
    if "SPP_MIN_PERCENT" in rules:
        min_spp = int(camp_length * rules["SPP_MIN_PERCENT"])
        if weeks[SPP] < min_spp:
            diff = min_spp - weeks[SPP]
            weeks[SPP] = min_spp
            weeks[GPP] = max(1, weeks[GPP] - diff)
    if "MAX_TAPER" in rules:
        max_taper = max(1, round(camp_length * rules["MAX_TAPER"]))
        if weeks[TAPER] > max_taper:
            excess = weeks[TAPER] - max_taper
            weeks[TAPER] = max_taper
            weeks[SPP] += excess
    if "TAPER_MAX_DAYS" in rules:
        max_taper_weeks = max(1, rules["TAPER_MAX_DAYS"] // 7)
        if weeks[TAPER] > max_taper_weeks:
            delta = weeks[TAPER] - max_taper_weeks
            weeks[TAPER] = max_taper_weeks
            weeks[SPP] += delta
    if "SPP_CLINCH_RATIO" in rules:
        min_spp = int(camp_length * rules["SPP_CLINCH_RATIO"])
        if weeks[SPP] < min_spp:
            diff = min_spp - weeks[SPP]
            weeks[SPP] = min_spp
            weeks[GPP] = max(1, weeks[GPP] - diff)


def calculate_phase_weeks(
    camp_length: int,
    sport: str,
    style: str | list[str] | None = None,
    status: str | None = None,
    fatigue: str | None = None,
    weight_cut_risk: bool | None = None,
    mental_block: str | list[str] | None = None,
    weight_cut_pct: float | None = None,
    days_until_fight: int | None = None,
) -> dict:
    """Return weeks per phase for a fight camp."""
    total_days = days_until_fight if isinstance(days_until_fight, int) and days_until_fight >= 0 else camp_length * 7
    camp_length = _effective_phase_block_count(total_days)
    closest = min(BASE_PHASE_RATIOS.keys(), key=lambda value: abs((value * 7) - total_days))
    ratios = BASE_PHASE_RATIOS[closest][sport].copy()

    accumulated = {GPP: 0.0, SPP: 0.0, TAPER: 0.0}
    for current_style in _normalize_styles(style):
        if current_style in STYLE_ADJUSTMENTS:
            for phase, delta in STYLE_ADJUSTMENTS[current_style].items():
                if phase in accumulated:
                    accumulated[phase] += delta

    for phase, delta in accumulated.items():
        if delta > 0:
            delta = min(delta, STYLE_ADJUSTMENT_CAP)
        else:
            delta = max(delta, -STYLE_ADJUSTMENT_CAP)
        if phase in ratios:
            ratios[phase] = max(0.05, ratios[phase] + delta)

    all_styles = _normalize_styles(style)
    if sport in STYLE_RULES:
        all_styles.append(sport)
    for current_style in all_styles:
        rules = STYLE_RULES.get(current_style, {})
        if "SPP_MIN_PERCENT" in rules:
            ratios[SPP] = max(ratios[SPP], rules["SPP_MIN_PERCENT"])
        if "MAX_TAPER" in rules:
            ratios[TAPER] = min(ratios[TAPER], rules["MAX_TAPER"])
        if "TAPER_MAX_DAYS" in rules:
            max_taper_ratio = max(1, rules["TAPER_MAX_DAYS"] // 7) / camp_length
            ratios[TAPER] = min(ratios[TAPER], max_taper_ratio)
        if "SPP_CLINCH_RATIO" in rules:
            ratios[SPP] = max(ratios[SPP], rules["SPP_CLINCH_RATIO"])
        if "GPP_MIN_PERCENT" in rules:
            ratios[GPP] = max(ratios[GPP], rules["GPP_MIN_PERCENT"])

    if status and status.strip().lower() in {"professional", "pro"} and camp_length >= 4:
        fat = (fatigue or "").strip().lower()
        cut_pct = weight_cut_pct if weight_cut_pct is not None else 0.0
        cut_flag = bool(weight_cut_risk)
        blocks: list[str] = []
        if isinstance(mental_block, str):
            blocks = [mental_block.lower()]
        elif isinstance(mental_block, list):
            blocks = [block.lower() for block in mental_block]

        if fat == "low" and not cut_flag and all(block in {"generic", "confidence"} for block in blocks):
            ratios[SPP] += 0.10
            ratios[GPP] -= 0.10
        elif fat in ["low", "moderate"] and cut_pct <= 5 and not any(
            block in {"motivation", "gas tank", "injury fear"} for block in blocks
        ):
            ratios[SPP] += 0.075
            ratios[GPP] -= 0.075
        else:
            ratios[SPP] += 0.05
            ratios[GPP] -= 0.05

        if ratios[GPP] < 0.15:
            diff = 0.15 - ratios[GPP]
            ratios[GPP] = 0.15
            ratios[SPP] = max(0.05, ratios[SPP] - diff)

    total_ratio = ratios[GPP] + ratios[SPP] + ratios[TAPER]
    ratios = {phase: value / total_ratio for phase, value in ratios.items()}

    weeks = {
        GPP: max(0, round(ratios[GPP] * camp_length)),
        SPP: max(0, round(ratios[SPP] * camp_length)),
        TAPER: max(0, min(2, round(ratios[TAPER] * camp_length))),
    }

    def _rebalance(weeks_dict: dict[str, int]) -> None:
        total_weeks = weeks_dict[GPP] + weeks_dict[SPP] + weeks_dict[TAPER]
        if total_weeks < camp_length:
            weeks_dict[SPP] += camp_length - total_weeks
        elif total_weeks > camp_length:
            excess = total_weeks - camp_length
            for phase in PHASE_REBALANCE_ORDER:
                if excess <= 0:
                    break
                cut = min(weeks_dict[phase], excess)
                weeks_dict[phase] -= cut
                excess -= cut

    _rebalance(weeks)

    ultra_short_notice = isinstance(days_until_fight, int) and 0 <= days_until_fight < 7
    if ultra_short_notice and camp_length == 1:
        weeks[GPP] = 0
        weeks[SPP] = 0
        weeks[TAPER] = 1

    short_notice = isinstance(days_until_fight, int) and 0 <= days_until_fight <= 21
    if not short_notice:
        if camp_length >= 3:
            weeks[GPP] = max(1, weeks[GPP])
            weeks[SPP] = max(1, weeks[SPP])
        elif camp_length == 2:
            weeks[SPP] = max(1, weeks[SPP])
        _rebalance(weeks)

        if camp_length >= 2 and weeks[TAPER] == 0:
            if weeks[SPP] > 1 or (camp_length == 2 and weeks[SPP] > 0):
                weeks[SPP] -= 1
                weeks[TAPER] = 1
            elif weeks[GPP] > 1 or (camp_length == 2 and weeks[GPP] > 0):
                weeks[GPP] -= 1
                weeks[TAPER] = 1

    for current_style in all_styles:
        rules = STYLE_RULES.get(current_style, {})
        if rules:
            _apply_style_rules(rules, camp_length, weeks)

    _rebalance(weeks)

    if camp_length >= 2 and weeks[TAPER] == 0:
        if weeks[SPP] > 1 or (camp_length == 2 and weeks[SPP] > 0):
            weeks[SPP] -= 1
            weeks[TAPER] = 1
        elif weeks[GPP] > 1 or (camp_length == 2 and weeks[GPP] > 0):
            weeks[GPP] -= 1
            weeks[TAPER] = 1
        _rebalance(weeks)

    compressed_pre_fight = isinstance(days_until_fight, int) and 8 <= days_until_fight <= 13
    if compressed_pre_fight:
        weeks[GPP] = 0
        weeks[SPP] = max(1, weeks[SPP])
        weeks[TAPER] = max(1, weeks[TAPER])

        total_weeks = weeks[GPP] + weeks[SPP] + weeks[TAPER]
        if total_weeks < camp_length:
            weeks[SPP] += camp_length - total_weeks
        elif total_weeks > camp_length:
            excess = total_weeks - camp_length
            taper_cut = min(max(0, weeks[TAPER] - 1), excess)
            weeks[TAPER] -= taper_cut
            excess -= taper_cut
            if excess > 0:
                weeks[SPP] -= min(max(0, weeks[SPP] - 1), excess)

    days = {
        phase: max(0, round(total_days * (weeks[phase] / camp_length)))
        for phase in (GPP, SPP, TAPER)
    }

    def _rebalance_days(days_dict: dict[str, int]) -> None:
        total_phase_days = days_dict[GPP] + days_dict[SPP] + days_dict[TAPER]
        if total_phase_days < total_days:
            days_dict[SPP] += total_days - total_phase_days
        elif total_phase_days > total_days:
            excess = total_phase_days - total_days
            for phase in PHASE_REBALANCE_ORDER:
                if excess <= 0:
                    break
                cut = min(days_dict[phase], excess)
                days_dict[phase] -= cut
                excess -= cut

    _rebalance_days(days)

    return {
        **weeks,
        "days": days,
    }


