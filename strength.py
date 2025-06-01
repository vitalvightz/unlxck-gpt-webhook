def generate_strength_block(phase, age, weight_class, injuries=None, fatigue=None):
    strength_output = []

    # Injury substitution rules
    injury_subs = {
        "knee": {"squat": "belt squat", "lunge": "step-up (6'' box)"},
        "shoulder": {"overhead press": "landmine press", "bench press": "neutral grip DB press"},
        "back": {"deadlift": "trap bar deadlift"}
    }

    def substitute_exercises(base_exercises, injuries_detected):
        modified = []
        for ex in base_exercises:
            replaced = False
            for area, subs in injury_subs.items():
                if area in injuries_detected:
                    for orig, sub in subs.items():
                        if orig in ex.lower():
                            modified.append(ex.replace(orig, sub))
                            replaced = True
                            break
                if replaced:
                    break
            if not replaced:
                modified.append(ex)
        return modified

    # Phase-specific logic
    if phase == "GPP":
        exercises = ["Back Squat", "RDL", "DB Incline Press", "Pull-Ups", "Landmine Press"]
        base_block = "3x8-12 @ 60–75% 1RM with slow eccentrics, tempo 3-1-1"
        focus = "Build hypertrophy base, tendon durability, and general strength."
    elif phase == "SPP":
        exercises = ["Trap Bar Deadlift", "Band Push-Ups", "Power Clean", "Med Ball Slams"]
        base_block = "3–5x3-5 @ 85–90% 1RM with contrast training (pair with explosive move)"
        focus = "Max strength + explosive power. Contrast and triphasic methods emphasized."
    elif phase == "TAPER":
        exercises = ["Front Squat", "Landmine Push Press", "Bar Speed Bench", "Isometric Split Squat"]
        base_block = "2–3x3-5 @ 80–85%, cluster sets, minimal eccentric load"
        focus = "Maintain intensity, cut volume, CNS freshness. High bar speed focus."
    else:
        exercises = ["Back Squat", "Pull-Ups", "Bench Press"]
        base_block = "Default fallback block — check logic."
        focus = "Default phase. Ensure proper phase detection upstream."

    # Substitute based on injuries
    if injuries:
        exercises = substitute_exercises(exercises, injuries.lower())

    # Adjust volume if fatigue exists
    fatigue_note = ""
    if fatigue and "high" in fatigue.lower():
        fatigue_note = "⚠️ Fatigue detected – reduce volume by 30–40% and drop last set of each lift."

    # Output assembly
    strength_output.append("🏋️‍♂️ **Strength & Power Module**")
    strength_output.append(f"**Phase:** {phase}")
    strength_output.append(f"**Primary Focus:** {focus}")
    strength_output.append("**Top Exercises:**")
    for ex in exercises:
        strength_output.append(f"- {ex}")
    strength_output.append(f"**Prescription:** {base_block}")
    if fatigue_note:
        strength_output.append(f"**Adjustment:** {fatigue_note}")

    return "\\n".join(strength_output)
"""

with open("/mnt/data/strength.py", "w") as f:
    f.write(strength_module_code)

"✅ strength.py module rebuilt and saved. Ready for next."