def generate_nutrition_block(*, flags: dict) -> str:
    nutrition_block = "\n🍽️ **Nutrition Module**\n"

    # Base General Guidelines
    nutrition_block += "- 3 core meals + 2–3 snacks per day\n"
    nutrition_block += "- Prioritize whole foods: lean protein, complex carbs, healthy fats\n"
    nutrition_block += "- Hydration: 30–40 ml/kg bodyweight daily\n"

    weight = flags.get("weight", 70)  # Default 70kg if missing
    phase = flags.get("phase", "GPP").upper()
    fatigue = flags.get("fatigue", "low").lower()
    weight_cut_risk = flags.get("weight_cut_risk", False)
    cut_pct = flags.get("weight_cut_pct", 0)

    # Phase-Based Macronutrient Targets (g/kg)
    if phase == "GPP":
        nutrition_block += "\n**GPP Phase (Off-Season/Base Training):**\n"
        nutrition_block += f"- Carbs: 5–8 g/kg → {weight * 5:.0f}–{weight * 8:.0f} g/day\n"
        nutrition_block += f"- Protein: 1.6–2.0 g/kg → {weight * 1.6:.0f}–{weight * 2.0:.0f} g/day\n"
        nutrition_block += f"- Fat: 0.8–1.0 g/kg → {weight * 0.8:.0f}–{weight:.0f} g/day (~20–30% calories)\n"
        nutrition_block += "- Meal timing: Balanced meal 2–4 h pre-training; optional small carb/protein snack 30–60 min before; sports drinks/gels during long sessions; post-workout carbs 1.0–1.2 g/kg + protein 0.3–0.4 g/kg within 1 h\n"
        nutrition_block += "- Hydrate ~0.5–1.0 L/hour during training; monitor sweat loss and electrolytes especially in heavy sweat\n"

    elif phase == "SPP":
        nutrition_block += "\n**SPP Phase (Fight Camp):**\n"
        nutrition_block += f"- Carbs: 3–6 g/kg → {weight * 3:.0f}–{weight * 6:.0f} g/day (higher end on heavy session days)\n"
        nutrition_block += f"- Protein: 1.6–2.2 g/kg → {weight * 1.6:.0f}–{weight * 2.2:.0f} g/day\n"
        nutrition_block += f"- Fat: 0.7–1.0 g/kg → {weight * 0.7:.0f}–{weight:.0f} g/day (~20–25% calories)\n"
        nutrition_block += "- Meal timing: Continue GPP strategy; include carb + protein snacks between double sessions\n"
        nutrition_block += "- Hydration: Monitor weight daily; maintain electrolytes; avoid dehydration as weight loss method\n"

    elif phase == "TAPER":
        nutrition_block += "\n**Taper Phase (Final Week/Weigh-In):**\n"
        nutrition_block += f"- Carbs: <5 g/kg to deplete glycogen pre-weigh-in; post-weigh-in refuel 8–12 g/kg if heavy cut, 4–7 g/kg for modest cut\n"
        nutrition_block += f"- Protein: 1.8–2.5 g/kg to preserve lean mass\n"
        nutrition_block += f"- Fat: Moderate (~20% calories)\n"
        nutrition_block += "- Reduce fiber 1–2 days pre-fight\n"
        nutrition_block += "- Post-weigh-in: distribute high-GI carbs + 0.3–0.4 g/kg protein per feeding; avoid high-fat/fiber initially\n"
        nutrition_block += "- Hydrate aggressively post-weigh-in (1.5–2 L/kg fluid lost) with sodium-rich fluids\n"
        nutrition_block += "- Pre-fight: alkaline buffer (sodium bicarbonate ~0.3 g/kg) if tolerated; caffeine 3–6 mg/kg ~60 min pre-fight; carb-rich snack 1–2 g/kg 1–2 h before bout\n"

    # Fatigue Adaptations — Phase Specific
    if fatigue == "high":
        if phase == "GPP":
            nutrition_block += "\n**High Fatigue (GPP):**\n"
            nutrition_block += "- Add intra-workout carbs (15–30 g/hr)\n"
            nutrition_block += "- Increase daily calories by ~10%\n"
            nutrition_block += "- Magnesium glycinate 300 mg + taurine 1.5 g + electrolyte tablets in evening\n"
        elif phase == "SPP":
            nutrition_block += "\n**High Fatigue (SPP):**\n"
            nutrition_block += "- Prioritize post-workout recovery meals\n"
            nutrition_block += "- Caffeine 3–6 mg/kg before sessions\n"
            nutrition_block += "- Creatine 3–5 g/day; beta-alanine 3–6 g/day\n"
        elif phase == "TAPER":
            nutrition_block += "\n**High Fatigue (Taper):**\n"
            nutrition_block += "- Emphasize gut-friendly carbs (white rice, bananas, oats)\n"
            nutrition_block += "- Use calming supplements: magnesium + electrolytes with exact dosing\n"

    elif fatigue == "moderate":
        nutrition_block += "\n**Moderate Fatigue:**\n"
        nutrition_block += "- Increase post-training carb load\n"
        nutrition_block += "- Include sleep-promoting foods (cherries, banana, oats)\n"

    # Weight Cut Protocol
    if weight_cut_risk:
        nutrition_block += f"\n**⚠️ Weight Cut Protocol Triggered (> {cut_pct} %):**\n"
        nutrition_block += "- Use refeed post-weigh-in with high-GI carbs and sodium-rich fluids\n"
        nutrition_block += "- Monitor sleep, hydration, and energy daily\n"
        if cut_pct >= 6.0:
            nutrition_block += "- Sodium intake: 10 g/day until 72 h out → 5 g/day → 2 g/day at weigh-in\n"

    return nutrition_block.strip()