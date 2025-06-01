from pathlib import Path

# Define the directory and file content
file_path = Path("/mnt/data/weight_cut.py")
weight_cut_module_code = """
def assess_weight_cut_risk(current_weight: float, target_weight: float) -> dict:
    \"\"\"
    Assess the risk of weight cutting based on percentage delta.
    Flags red zone if cut is > 6%.
    \"\"\"
    if not current_weight or not target_weight:
        return {"cut_percent": 0.0, "risk": "unknown", "advice": "Missing weight inputs"}

    try:
        cut_percent = ((current_weight - target_weight) / target_weight) * 100
    except ZeroDivisionError:
        return {"cut_percent": 0.0, "risk": "invalid", "advice": "Target weight must be > 0"}

    if cut_percent > 6:
        risk = "high"
        advice = "⚠️ Large weight cut detected (>6%). Adjust taper, increase recovery protocols, and monitor hydration daily."
    elif 3 < cut_percent <= 6:
        risk = "moderate"
        advice = "⚠️ Moderate cut. Prioritize sleep, hydration, and reduce glycolytic conditioning slightly."
    elif 0 < cut_percent <= 3:
        risk = "low"
        advice = "✅ Minimal cut expected. Maintain standard recovery and taper flow."
    else:
        risk = "none"
        advice = "🟢 No cut detected. Proceed normally."

    return {
        "cut_percent": round(cut_percent, 1),
        "risk": risk,
        "advice": advice
    }
"""

# Save the file
file_path.write_text(weight_cut_module_code.strip())
file_path