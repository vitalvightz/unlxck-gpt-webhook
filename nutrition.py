def generate_nutrition_block(*, flags: dict) -> str:
    nutrition_block = "\n🍽️ **Nutrition Module**\n"

    # General Recommendations
    nutrition_block += "- 3 core meals + 2–3 snacks per day\n"
    nutrition_block += "- Prioritize whole foods: lean protein, complex carbs, healthy fats\n"
    nutrition_block += "- 1.7–2.2g protein per kg bodyweight\n"
    nutrition_block += "- Hydration: 30–40ml per kg of bodyweight\n"

    # Fatigue Adaptations
    fatigue = flags.get("fatigue")
    if fatigue == "high":
        nutrition_block += "\n**Fatigue Nutrition Tips:**\n"
        nutrition_block += "- Add intra-workout carbs (15–30g per hour of training)\n"
        nutrition_block += "- Increase daily calories by ~10%\n"
        nutrition_block += "- Magnesium + electrolyte supplementation (evening)\n"
    elif fatigue == "moderate":
        nutrition_block += "\n**Moderate Fatigue Adjustments:**\n"
        nutrition_block += "- Increase post-training carb load\n"
        nutrition_block += "- Focus on sleep-promoting foods (cherries, banana, oats)\n"

    # Phase-Based Adjustments
    phase = flags.get("phase", "GPP").upper()
    if phase == "GPP":
        nutrition_block += "\n**GPP Phase Focus:**\n"
        nutrition_block += "- Slight caloric surplus (+5–10%) to support hypertrophy and tissue repair\n"
        nutrition_block += "- Emphasize protein intake (2.0–2.2g/kg) and healthy fats for hormonal balance\n"
    elif phase == "SPP":
        nutrition_block += "\n**SPP Phase Focus:**\n"
        nutrition_block += "- Shift to moderate-high carbs (4–6g/kg) around sessions for explosive performance\n"
        nutrition_block += "- Slight calorie deficit or maintenance for lean conditioning\n"
    elif phase == "TAPER":
        nutrition_block += "\n**Taper Phase Focus:**\n"
        nutrition_block += "- Prioritize gut-friendly carbs (white rice, bananas, oats)\n"
        nutrition_block += "- Increase carb % in final 48h to fill glycogen stores\n"
        nutrition_block += "- Avoid heavy fats and fibers 24h before fight\n"

    # Taper Week Adjustments (additional to phase)
    if flags.get("taper_week"):
        nutrition_block += "\n**Taper Week Nutrition:**\n"
        nutrition_block += "- Reduce total calories by ~15%\n"
        nutrition_block += "- Increase carb % in final 2 days\n"
        nutrition_block += "- Emphasize digestion-friendly meals pre-fight\n"

    # Weight Cut Risk
    if flags.get("weight_cut_risk"):
        cut_pct = flags.get("weight_cut_pct", 0)
        nutrition_block += "\n**⚠️ Weight Cut Protocol Triggered:**\n"
        nutrition_block += f"- Weight cut >{cut_pct}% → elevated cut strategy\n"
        nutrition_block += "- Use refeed protocol post-weigh-in (high-GI carbs + sodium-rich fluids)\n"
        nutrition_block += "- Monitor sleep, hydration, and energy levels daily\n"
        if cut_pct >= 6.0:
            nutrition_block += "- Sodium protocol: 10g/day until 72h out → 5g/day → 2g/day weigh-in\n"

    return nutrition_block.strip()