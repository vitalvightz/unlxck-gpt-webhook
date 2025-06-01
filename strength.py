strength_module_code = '''
def generate_strength_block(phase, age, weight_class, injuries=None, fatigue=None):
    strength_output = []

    # Progression logic per phase
    progression_map = {
        "GPP": [
            "Week 1: 3x10 @ 65%",
            "Week 2: 3x8 @ 70%",
            "Week 3: 4x8 @ 70–75%",
        ],
        "SPP": [
            "Week 1: 4x5 @ 80%",
            "Week 2: 4x3 @ 85%",
            "Week 3: 5x3 @ 90%",
        ],
        "TAPER": [
            "Week 1: 2x3 @ 75% (cluster sets, bar speed focus)",
            "Week 2: 2x2 @ 70%, only main lifts, high velocity"
        ]
    }

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
        focus = "Build hypertrophy base, tendon durability, and general strength."
    elif phase == "SPP":
        exercises = ["Trap Bar Deadlift", "Band Push-Ups", "Power Clean", "Med Ball Slams"]
        focus = "Max strength + explosive power. Contrast and triphasic methods emphasized."
    elif phase == "TAPER":
        exercises = ["Front Squat", "Landmine Push Press", "Bar Speed Bench", "Isometric Split Squat"]
        focus = "Maintain intensity, cut volume, CNS freshness. High bar speed focus."
    else:
        exercises = ["Back Squat", "Pull-Ups", "Bench Press"]
        focus = "Default phase. Ensure proper phase detection upstream."

    # Substitute based on injuries
    if injuries:
        exercises = substitute_exercises(exercises, injuries.lower())

    # Adjust volume if fatigue exists
    fatigue_note = ""
    if fatigue:
        try:
            fatigue_score = int(fatigue)
            if fatigue_score >= 7:
                fatigue_note = "⚠️ High fatigue – reduce volume by 30–40% and drop last set of each lift."
            elif 4 <= fatigue_score <= 6:
                fatigue_note = "⚠️ Moderate fatigue – monitor closely. Optionally reduce 1 set if performance drops."
        except ValueError:
            pass

    # Output assembly
    strength_output.append("🏋️‍♂️ **Strength & Power Module**")
    strength_output.append(f"**Phase:** {phase}")
    strength_output.append(f"**Primary Focus:** {focus}")
    strength_output.append("**Top Exercises:**")
    for ex in exercises:
        strength_output.append(f"- {ex}")
    strength_output.append("**Progression Plan:**")
    for line in progression_map.get(phase, ["No progression found."]):
        strength_output.append(f"- {line}")
    if fatigue_note:
        strength_output.append(f"**Adjustment:** {fatigue_note}")

    return "\\n".join(strength_output)
'''

with open("/mnt/data/strength.py", "w") as f:
    f.write(strength_module_code)

"✅ strength.py updated with week-to-week progression logic and saved."