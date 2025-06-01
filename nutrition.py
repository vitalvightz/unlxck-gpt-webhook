# Create the nutrition.py module with structured logic based on phase and weight cut status

nutrition_logic_code = '''
def generate_nutrition_guidance(phase: str, weight_cut_percentage: float) -> str:
    guidance = "**🥗 Nutrition Module**\\n"

    # Baseline guidelines
    if phase == "GPP":
        guidance += "- Emphasize nutrient density (whole foods)\\n"
        guidance += "- Moderate carbs (4-5g/kg), higher fats for energy\\n"
        guidance += "- Protein ~2g/kg\\n"

    elif phase == "SPP":
        guidance += "- Increase carbs to fuel high output blocks (5-6g/kg)\\n"
        guidance += "- Lower fats slightly to maintain body comp\\n"
        guidance += "- Protein maintained (2g/kg)\\n"
        guidance += "- Start monitoring water/salt intake\\n"

    elif phase == "TAPER":
        guidance += "- Carb taper: Reduce carbs slightly Mon–Wed\\n"
        guidance += "- Fiber taper: Cut high-residue foods from Wed\\n"
        guidance += "- Sodium taper: Reduce salt Thurs–Fri\\n"
        guidance += "- Final 2 days: Low fiber, moderate carbs, clean hydration\\n"

    else:
        guidance += "- Maintain general fueling habits and hydration\\n"

    # Weight cut logic
    if weight_cut_percentage > 6:
        guidance += "\\n⚠️ **Weight Cut Risk:** Over 6% to lose.\\n"
        guidance += "- Start water loading 6–7 days out (if cleared)\\n"
        guidance += "- Ensure fiber + sodium tapering\\n"
        guidance += "- Consider professional oversight for cut execution\\n"
    elif weight_cut_percentage > 3:
        guidance += "\\n⚠️ **Moderate Cut:** 3–6% range.\\n"
        guidance += "- Start dietary adjustments 10–14 days out\\n"
        guidance += "- Carb + sodium manipulation in taper week\\n"
    else:
        guidance += "\\n✅ No major weight cut stress detected.\\n"

    return guidance.strip()
'''

# Save to file
with open("/mnt/data/nutrition.py", "w") as f:
    f.write(nutrition_logic_code)
"/mnt/data/nutrition.py module written and ready for use."