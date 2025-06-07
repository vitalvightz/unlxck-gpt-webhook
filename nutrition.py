def generate_nutrition_block(*, flags: dict) -> str:
    nutrition_block = "\n🍽️ **Nutrition Module**\n"

    weight = flags.get("weight", 70)  # default fallback
    phase = flags.get("phase", "GPP").upper()
    fatigue = flags.get("fatigue", "low").lower()
    weight_cut_risk = flags.get("weight_cut_risk", False)
    cut_pct = flags.get("weight_cut_pct", 0.0)
    
    # General Guidelines
    nutrition_block += "- 3 core meals + 2–3 snacks daily\n"
    nutrition_block += "- Whole foods focus: lean protein, complex carbs, healthy fats\n"
    nutrition_block += f"- Protein intake: 1.7–2.2 g/kg → {round(1.7*weight,1)}–{round(2.2*weight,1)} g/day\n"
    nutrition_block += f"- Hydration: 30–40 ml/kg → {round(30*weight,0)}–{round(40*weight,0)} ml/day\n"

    # Phase-specific Macronutrient & Calorie Guidance
    if phase == "GPP":
        nutrition_block += "\n**GPP Phase Focus:**\n"
        nutrition_block += f"- Caloric intake: slight surplus (+5–10%) to support hypertrophy & repair\n"
        nutrition_block += f"- Carbohydrates: 5–8 g/kg → {round(5*weight,1)}–{round(8*weight,1)} g/day\n"
        nutrition_block += f"- Protein: 1.6–2.0 g/kg → {round(1.6*weight,1)}–{round(2.0*weight,1)} g/day\n"
        nutrition_block += f"- Fats: 0.8–1.0 g/kg (20–30% calories) → {round(0.8*weight,1)}–{round(1.0*weight,1)} g/day\n"
    elif phase == "SPP":
        nutrition_block += "\n**SPP Phase Focus:**\n"
        nutrition_block += "- Moderate calorie deficit or maintenance for lean conditioning\n"
        nutrition_block += f"- Carbohydrates: 3–6 g/kg (focus on 4–6 g/kg around sessions) → {round(3*weight,1)}–{round(6*weight,1)} g/day\n"
        nutrition_block += f"- Protein: 1.6–2.2 g/kg → {round(1.6*weight,1)}–{round(2.2*weight,1)} g/day\n"
        nutrition_block += f"- Fats: 0.7–1.0 g/kg (20–25% calories) → {round(0.7*weight,1)}–{round(1.0*weight,1)} g/day\n"
    elif phase == "TAPER":
        nutrition_block += "\n**Taper Phase Focus:**\n"
        nutrition_block += "- Reduced training volume, focus on freshness & weight making\n"
        nutrition_block += f"- Carbohydrates: reduce to <5 g/kg in days before weigh-in → <{round(5*weight,1)} g/day\n"
        nutrition_block += f"- Protein: maintain high intake 1.8–2.5 g/kg → {round(1.8*weight,1)}–{round(2.5*weight,1)} g/day\n"
        nutrition_block += "- Moderate fat intake (~20% calories), reduce fiber 1–2 days out\n"
        nutrition_block += "- Emphasize gut-friendly carbs (white rice, bananas, oats)\n"

    # Fatigue + Phase Interaction
    if fatigue == "high":
        if phase == "GPP":
            nutrition_block += "\n**High Fatigue in GPP:**\n"
            nutrition_block += "- Increase calories by ~10–15% to support recovery\n"
            nutrition_block += "- Add intra-workout carbs: 30–60 g/hour (sports drinks/gels)\n"
            nutrition_block += "- Magnesium glycinate 300 mg + taurine 1.5 g (evening)\n"
            nutrition_block += "- Electrolyte drink with sodium 500–700 mg per serving\n"
        elif phase == "SPP":
            nutrition_block += "\n**High Fatigue in SPP:**\n"
            nutrition_block += "- Maintain calories at maintenance, prioritize carbs around sessions\n"
            nutrition_block += "- Continue intra-workout fueling 30–60 g carbs/hour\n"
            nutrition_block += "- Magnesium glycinate 300 mg + taurine 1.5 g (evening)\n"
            nutrition_block += "- Electrolytes during and post-training\n"
        elif phase == "TAPER":
            nutrition_block += "\n**High Fatigue in Taper:**\n"
            nutrition_block += "- Reduce training volume calories by ~5–10%\n"
            nutrition_block += "- Focus on easily digestible carbs, hydrate well\n"
            nutrition_block += "- Magnesium glycinate 200 mg + taurine 1 g\n"
            nutrition_block += "- Light electrolyte intake only\n"
    elif fatigue == "moderate":
        nutrition_block += "\n**Moderate Fatigue Adjustments:**\n"
        nutrition_block += "- Increase post-training carb load\n"
        nutrition_block += "- Focus on sleep-promoting foods: cherries, bananas, oats\n"

    # Meal Timing by Phase (Pre/Intra/Post Workout)
    nutrition_block += "\n**Meal Timing Guidelines:**\n"
    if phase in ["GPP", "SPP"]:
        nutrition_block += "- Pre-training: 1.5–3h before, balanced meal with 1–2 g/kg carbs + ~0.3 g/kg protein\n"
        nutrition_block += "- Intra-training (>60 min): 30–60 g carbs/hour (sports drinks/gels), hydration\n"
        nutrition_block += "- Post-training (within 1h): 1–1.2 g/kg carbs + 0.3–0.4 g/kg protein\n"
    elif phase == "TAPER":
        nutrition_block += "- Pre-training: light easily digestible carbs 30–60 min before\n"
        nutrition_block += "- Intra-training: water or electrolyte drink only\n"
        nutrition_block += "- Post-training: focus on gut-friendly carbs + protein, avoid heavy fats/fiber\n"

    # Weight Cut Risk Handling
    if weight_cut_risk:
        nutrition_block += "\n**⚠️ Weight Cut Protocol Triggered:**\n"
        nutrition_block += f"- Weight cut > {cut_pct}%: aggressive refeed post-weigh-in\n"
        nutrition_block += "- Carbs: 8–12 g/kg over recovery period if heavy cut, else 4–7 g/kg\n"
        nutrition_block += "- Multiple meals/snacks with high-GI carbs (rice, pasta, sports drinks)\n"
        nutrition_block += "- Protein: 0.3–0.4 g/kg per feeding (lean meat, whey)\n"
        nutrition_block += "- Avoid high fat/fiber first hours post-weigh-in\n"
        nutrition_block += "- Hydrate aggressively: initial bolus 0.6–0.9 L + replace 150% fluid lost\n"
        nutrition_block += "- Sodium intake: 20–50+ mmol/L drinks + salted snacks/broths\n"
        nutrition_block += "- De-emphasize diuretics (caffeine/alcohol) final 24h pre-fight\n"
        nutrition_block += "- Alkaline buffer (sodium bicarbonate ~0.3 g/kg) 90–120 min pre-fight if tolerated\n"
        nutrition_block += "- Final carb snack 1–2 h pre-fight: 1–2 g/kg easily digested carbs\n"

    return nutrition_block.strip()