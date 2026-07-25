from .weight_cut import (
    WEIGHT_CUT_INPUTS_KNOWN,
    WEIGHT_CUT_INPUTS_MISSING_BOTH,
    WEIGHT_CUT_INPUTS_MISSING_CURRENT,
    WEIGHT_CUT_INPUTS_MISSING_TARGET,
    WEIGHT_CUT_INPUTS_UNKNOWN_STATUSES,
    parse_weight_value,
    weight_cut_risk_band,
    weight_cut_supervision_required,
)

_WEIGHT_CUT_UNKNOWN_NOTES = {
    WEIGHT_CUT_INPUTS_MISSING_TARGET: (
        "No target weight set — cut size unknown. Add a fight-week target weight "
        "for cut guidance."
    ),
    WEIGHT_CUT_INPUTS_MISSING_CURRENT: (
        "No current weight recorded — cut size unknown. Add current bodyweight "
        "for cut guidance."
    ),
    WEIGHT_CUT_INPUTS_MISSING_BOTH: (
        "No current or target weight recorded — cut size unknown. Add both for "
        "cut guidance."
    ),
}


def _is_high_pressure_weight_cut(flags: dict) -> bool:
    if not flags.get("weight_cut_risk", False):
        return False
    if float(flags.get("weight_cut_pct", 0.0) or 0.0) >= 5.0:
        return True
    fatigue = str(flags.get("fatigue", "")).strip().lower()
    days_until_fight = flags.get("days_until_fight")
    # A low-fatigue, non-aggressive active cut only counts as high-pressure inside
    # the final two weeks (<=14). Aggressive cuts (>=5%) and moderate+ fatigue stay
    # high-pressure at any distance via the clauses above. (Was <=28, which flagged
    # a routine 3-3.5% cut at D-21 as high-pressure even at low fatigue.)
    return fatigue in {"moderate", "high"} or (
        isinstance(days_until_fight, int) and days_until_fight <= 14
    )


def _resolve_weight(flags: dict) -> float | None:
    """Known bodyweight in kg, or ``None`` when it was never collected.

    Quick Build never collects bodyweight, so the athlete model can carry
    ``weight=None``. A missing weight must reduce specificity (per-kg guidance
    only) — never fabricate a default athlete to keep generation running.
    """
    weight = parse_weight_value(flags.get("weight"))
    return weight if weight > 0 else None


def _round_range(low: float, high: float, weight: float, ndigits: int = 1) -> dict:
    """A structured ``{min, max}`` g/day range from per-kg coefficients."""
    return {
        "min": round(low * weight, ndigits),
        "max": round(high * weight, ndigits),
        "per_kg": [low, high],
        "note": None,
    }


def _relative_range(low: float, high: float) -> dict:
    """Per-kg-only guidance when bodyweight is unknown: no absolute grams."""
    return {
        "min": None,
        "max": None,
        "per_kg": [low, high],
        "note": f"{low}-{high} g/kg — provide bodyweight for exact daily targets",
    }


def _macro_range(low: float, high: float, weight: float | None) -> dict:
    return _round_range(low, high, weight) if weight is not None else _relative_range(low, high)


def compute_nutrition_targets(*, flags: dict) -> dict:
    """Structured Stage 1 nutrition numbers for the planning brief.

    This emits the *same computed numbers* that :func:`generate_nutrition_block`
    renders as markdown, but as a machine-readable dict so the Stage 1 →
    structured_plan conversion can carry them through without re-deriving them
    from prose. Athlete-safe fields (macros, hydration, fuel timing, weight-cut
    risk band) live at the top level; exact acute weight-cut and supplement
    dosing live under ``coach_gated`` and must never be surfaced directly to
    athletes (coach/medical-gated only).

    When bodyweight is unknown the module is ``personalisation_limited``: it
    keeps the per-kg coefficients but never invents a weight, so ``weight_kg``
    is ``None`` and no absolute grams/millilitres are emitted.
    """
    weight = _resolve_weight(flags)
    phase = str(flags.get("phase", "GPP")).upper()
    fatigue = str(flags.get("fatigue", "low")).lower()
    weight_cut_risk = bool(flags.get("weight_cut_risk", False))
    cut_pct = float(flags.get("weight_cut_pct", 0.0) or 0.0)

    targets: dict = {
        "phase": phase,
        "weight_kg": weight,
        "personalisation_limited": weight is None,
        "meal_structure": "3 core meals + 2-3 snacks daily",
        "protein_g_per_day": _macro_range(1.7, 2.2, weight),
        "hydration_ml_per_day": (
            {
                "min": round(30 * weight, 0),
                "max": round(40 * weight, 0),
                "per_kg_l": [0.03, 0.04],
            }
            if weight is not None
            else {
                "min": None,
                "max": None,
                "per_kg_l": [0.03, 0.04],
                "note": "0.03-0.04 L/kg — provide bodyweight for exact millilitres",
            }
        ),
    }
    if weight is None:
        targets["personalisation_limited_reason"] = "missing_bodyweight"
        targets["personalisation_note"] = (
            "Bodyweight not provided — targets shown per kg. Add bodyweight to "
            "unlock exact daily grams and millilitres."
        )

    if phase == "GPP":
        targets["calorie_adjustment"] = "slight surplus (+5-10%)"
        targets["carbs_g_per_day"] = _macro_range(5, 8, weight)
        targets["protein_g_per_day"] = _macro_range(1.6, 2.0, weight)
        targets["fats_g_per_day"] = _macro_range(0.8, 1.0, weight)
    elif phase == "SPP":
        targets["calorie_adjustment"] = "moderate deficit or maintenance"
        targets["carbs_g_per_day"] = _macro_range(3, 6, weight)
        targets["protein_g_per_day"] = _macro_range(1.6, 2.2, weight)
        targets["fats_g_per_day"] = _macro_range(0.7, 1.0, weight)
    elif phase == "TAPER":
        targets["calorie_adjustment"] = "reduced volume; freshness + weight making"
        targets["carbs_g_per_day"] = (
            {
                "min": None,
                "max": round(5 * weight, 1),
                "per_kg": [None, 5],
                "note": "reduce in days before weigh-in",
            }
            if weight is not None
            else {
                "min": None,
                "max": None,
                "per_kg": [None, 5],
                "note": "<5 g/kg — reduce in days before weigh-in; provide bodyweight for exact grams",
            }
        )
        targets["protein_g_per_day"] = _macro_range(1.8, 2.5, weight)
        targets["fats_g_per_day"] = {
            "min": None,
            "max": None,
            "per_kg": None,
            "note": "moderate (~20% calories); reduce fiber 1-2 days out",
        }

    if phase in ("GPP", "SPP"):
        targets["fuel_timing"] = {
            "pre": "1.5-3h before: 1-2 g/kg carbs + ~0.3 g/kg protein",
            "intra": ">60 min sessions: 30-60 g carbs/hour + hydration",
            "post": "within 1h: 1-1.2 g/kg carbs + 0.3-0.4 g/kg protein",
        }
    elif phase == "TAPER":
        targets["fuel_timing"] = {
            "pre": "light easily digestible carbs 30-60 min before",
            "intra": "water or electrolyte drink only",
            "post": "gut-friendly carbs + protein; avoid heavy fats/fiber",
        }

    if fatigue in ("high", "moderate"):
        targets["fatigue_adjustment"] = fatigue

    days_until_fight = flags.get("days_until_fight")
    weight_cut_status = str(
        flags.get("weight_cut_status") or WEIGHT_CUT_INPUTS_KNOWN
    ).strip().lower()
    targets["weight_cut"] = {
        "active": weight_cut_risk,
        "risk_band": weight_cut_risk_band(weight_cut_risk, cut_pct, days_until_fight),
        "supervision_required": weight_cut_supervision_required(
            weight_cut_risk, cut_pct, days_until_fight
        ),
    }
    if weight_cut_status in WEIGHT_CUT_INPUTS_UNKNOWN_STATUSES:
        # Mirror the missing-bodyweight handling above: never present "no active
        # cut" as a finding when the inputs to decide that were never collected.
        # These keys are added ONLY in the unknown state — the athlete-facing
        # weight-cut summary for a known cut stays exactly
        # {active, risk_band, supervision_required}, which is a deliberate
        # coach-gating boundary. Consumers read ``.get("known", True)``.
        targets["weight_cut"]["known"] = False
        targets["weight_cut"]["unknown_reason"] = weight_cut_status
        targets["weight_cut"]["note"] = _WEIGHT_CUT_UNKNOWN_NOTES[weight_cut_status]

    # Coach/medical-gated: exact acute-cut + supplement dosing. NEVER render
    # these directly to athletes — they require qualified supervision.
    coach_gated: dict = {}
    if fatigue == "high":
        coach_gated["high_fatigue_supplements"] = {
            "GPP": "magnesium glycinate 300 mg + taurine 1.5 g (evening); electrolytes 500-700 mg sodium/serving",
            "SPP": "magnesium glycinate 300 mg + taurine 1.5 g (evening); electrolytes during/post",
            "TAPER": "magnesium glycinate 200 mg + taurine 1 g; light electrolytes only",
        }.get(phase)
    if weight_cut_risk:
        coach_gated["acute_cut_protocol"] = {
            "refeed_carbs_g_per_kg": "8-12 (heavy cut) else 4-7",
            "refeed_protein_g_per_kg_per_feeding": "0.3-0.4",
            "rehydration": "initial bolus 0.6-0.9 L + replace 150% fluid lost",
            "sodium": "20-50+ mmol/L drinks + salted snacks/broths",
            "bicarbonate_g_per_kg": "~0.3, 90-120 min pre-fight if tolerated",
            "final_carb_snack": "1-2 g/kg easily digested carbs, 1-2h pre-fight",
            "cut_pct": cut_pct,
        }
    if coach_gated:
        targets["coach_gated"] = coach_gated

    return targets


def generate_nutrition_block(*, flags: dict) -> str:
    nutrition_block = "\nNutrition Module\n"

    weight = _resolve_weight(flags)
    phase = flags.get("phase", "GPP").upper()
    fatigue = flags.get("fatigue", "low").lower()
    weight_cut_risk = flags.get("weight_cut_risk", False)
    cut_pct = float(flags.get("weight_cut_pct", 0.0) or 0.0)
    days_until_fight = flags.get("days_until_fight")
    high_pressure_cut = _is_high_pressure_weight_cut(flags)

    def _daily(low: float, high: float, unit: str = "g", ndigits: int = 1) -> str:
        """Absolute ' -> X-Y unit/day' suffix, or a per-kg-only hint without weight."""
        if weight is None:
            return " (exact daily targets need your bodyweight)"
        return f" -> {round(low * weight, ndigits)}-{round(high * weight, ndigits)} {unit}/day"

    if weight is None:
        nutrition_block += (
            "- Personalisation limited: bodyweight not provided. Ranges below are "
            "per-kg guidance — add your bodyweight to unlock exact daily targets.\n"
        )
    nutrition_block += "- 3 core meals + 2-3 snacks daily\n"
    nutrition_block += "- Whole foods focus: lean protein, complex carbs, healthy fats\n"
    nutrition_block += f"- Protein intake: 1.7-2.2 g/kg{_daily(1.7, 2.2)}\n"
    nutrition_block += f"- Hydration: 0.03-0.04 l/kg{_daily(30, 40, 'ml', 0)}\n"

    if weight_cut_risk:
        nutrition_block += "\n**Active Weight-Cut Note:**\n"
        nutrition_block += "- The cut raises recovery cost, so fueling has to protect day-to-day energy and session quality.\n"
        nutrition_block += "- Prioritize carbs, fluids, and sodium around key sessions to preserve strength expression and conditioning tolerance.\n"
        if high_pressure_cut:
            nutrition_block += "- This is a high-pressure cut window, so protect freshness and remove optional fatigue before under-fueling key work.\n"

    if phase == "GPP":
        nutrition_block += "\n**GPP Phase Focus:**\n"
        nutrition_block += "- Caloric intake: slight surplus (+5-10%) to support hypertrophy and repair\n"
        nutrition_block += f"- Carbohydrates: 5-8 g/kg{_daily(5, 8)}\n"
        nutrition_block += f"- Protein: 1.6-2.0 g/kg{_daily(1.6, 2.0)}\n"
        nutrition_block += f"- Fats: 0.8-1.0 g/kg (20-30% calories){_daily(0.8, 1.0)}\n"
    elif phase == "SPP":
        nutrition_block += "\n**SPP Phase Focus:**\n"
        nutrition_block += "- Moderate calorie deficit or maintenance for lean conditioning\n"
        nutrition_block += f"- Carbohydrates: 3-6 g/kg (focus on 4-6 g/kg around sessions){_daily(3, 6)}\n"
        nutrition_block += f"- Protein: 1.6-2.2 g/kg{_daily(1.6, 2.2)}\n"
        nutrition_block += f"- Fats: 0.7-1.0 g/kg (20-25% calories){_daily(0.7, 1.0)}\n"
    elif phase == "TAPER":
        nutrition_block += "\n**Taper Phase Focus:**\n"
        nutrition_block += "- Reduced training volume, focus on freshness and weight making\n"
        if weight is None:
            nutrition_block += "- Carbohydrates: reduce to <5 g/kg in days before weigh-in (exact daily targets need your bodyweight)\n"
        else:
            nutrition_block += f"- Carbohydrates: reduce to <5 g/kg in days before weigh-in -> <{round(5 * weight, 1)} g/day\n"
        nutrition_block += f"- Protein: maintain high intake 1.8-2.5 g/kg{_daily(1.8, 2.5)}\n"
        nutrition_block += "- Moderate fat intake (~20% calories), reduce fiber 1-2 days out\n"
        nutrition_block += "- Emphasize gut-friendly carbs (white rice, bananas, oats)\n"

    # Exact supplement/electrolyte dosing is coach/medical-gated (it lives under
    # coach_gated in compute_nutrition_targets) — the athlete layer only points
    # to the coach, it never states doses.
    if fatigue == "high":
        if phase == "GPP":
            nutrition_block += "\n**High Fatigue in GPP:**\n"
            nutrition_block += "- Increase calories by ~10-15% to support recovery\n"
            nutrition_block += "- Add intra-workout carbs: 30-60 g/hour (sports drinks/gels)\n"
            nutrition_block += "- Supplement and electrolyte support for high fatigue is coach-guided — ask your coach for the exact protocol\n"
        elif phase == "SPP":
            nutrition_block += "\n**High Fatigue in SPP:**\n"
            nutrition_block += "- Maintain calories at maintenance, prioritize carbs around sessions\n"
            nutrition_block += "- Continue intra-workout fueling 30-60 g carbs/hour\n"
            nutrition_block += "- Supplement and electrolyte support for high fatigue is coach-guided — ask your coach for the exact protocol\n"
            nutrition_block += "- Electrolytes during and post-training\n"
        elif phase == "TAPER":
            nutrition_block += "\n**High Fatigue in Taper:**\n"
            nutrition_block += "- Reduce training volume calories by ~5-10%\n"
            nutrition_block += "- Use easily digestible carbs and hydrate well\n"
            nutrition_block += "- Supplement and electrolyte support for high fatigue is coach-guided — ask your coach for the exact protocol\n"
            nutrition_block += "- Light electrolyte intake only\n"
    elif fatigue == "moderate":
        nutrition_block += "\n**Moderate Fatigue Adjustments:**\n"
        nutrition_block += "- Increase post-training carb load\n"
        nutrition_block += "- Focus on sleep-promoting foods: cherries, bananas, oats\n"

    nutrition_block += "\n**Meal Timing Guidelines:**\n"
    if phase in ["GPP", "SPP"]:
        nutrition_block += "- Pre-training: 1.5-3h before, balanced meal with 1-2 g/kg carbs + ~0.3 g/kg protein\n"
        nutrition_block += "- Intra-training (>60 min): 30-60 g carbs/hour (sports drinks/gels), hydration\n"
        nutrition_block += "- Post-training (within 1h): 1-1.2 g/kg carbs + 0.3-0.4 g/kg protein\n"
    elif phase == "TAPER":
        nutrition_block += "- Pre-training: light easily digestible carbs 30-60 min before\n"
        nutrition_block += "- Intra-training: water or electrolyte drink only\n"
        nutrition_block += "- Post-training: focus on gut-friendly carbs + protein, avoid heavy fats/fiber\n"

    # Athlete layer for an active cut: risk band + supervision + general recovery
    # priorities only. The exact acute-cut protocol (refeed/rehydration/sodium/
    # buffer dosing) is coach/medical-gated and must never be rendered here.
    if weight_cut_risk:
        risk_band = weight_cut_risk_band(weight_cut_risk, cut_pct, days_until_fight)
        supervision = weight_cut_supervision_required(
            weight_cut_risk, cut_pct, days_until_fight
        )
        nutrition_block += "\n**Weight Cut Protocol Triggered:**\n"
        nutrition_block += f"- Active weight cut (~{cut_pct}%): risk band {risk_band.upper()}\n"
        if supervision:
            nutrition_block += "- This cut requires qualified coach/medical supervision — the acute cut and post-weigh-in protocol are coach-gated\n"
        else:
            nutrition_block += "- The acute cut and post-weigh-in protocol are coach-gated — follow your coach's plan for exact amounts\n"
        nutrition_block += "- After weigh-in, refuel with easy-to-digest carbohydrate-rich foods across multiple small meals/snacks\n"
        nutrition_block += "- Rehydrate steadily with fluids + electrolytes; avoid heavy fat/fibre in the first hours post-weigh-in\n"
        nutrition_block += "- De-emphasize diuretics (caffeine/alcohol) final 24h pre-fight\n"

    return nutrition_block.strip()
