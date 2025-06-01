from injury_subs import injury_subs
from exercise_bank import exercise_bank

def generate_strength_block(phase, age, weight_class, weaknesses=None, injuries=None, fatigue=None):
    strength_output = []

    def substitute_exercises(base_exercises, injuries_detected):
        modified = []
        for ex in base_exercises:
            replaced = False
            for area, subs in injury_subs.items():
                if area in injuries_detected:
                    for sub in subs:
                        if any(kw in ex.lower() for kw in sub.lower().split()):
                            modified.append(sub)
                            replaced = True
                            break
                if replaced:
                    break
            if not replaced:
                modified.append(ex)
        return modified

    def select_exercises(phase, weaknesses):
        selected = []
        for group, options in exercise_bank.items():
            if weaknesses and group not in weaknesses:
                continue
            if phase in options:
                selected += options[phase][:2]  # Take top 2 per relevant group
        return selected if selected else ["Back Squat", "Pull-Up", "DB Bench Press"]

    base_exercises = select_exercises(phase, weaknesses)

    if injuries:
        base_exercises = substitute_exercises(base_exercises, injuries.lower())

    if phase == "GPP":
        base_block = "3x8-12 @ 60–75% 1RM with slow eccentrics, tempo 3-1-1"
        focus = "Build hypertrophy base, tendon durability, and general strength."
    elif phase == "SPP":
        base_block = "3–5x3-5 @ 85–90% 1RM with contrast training (pair with explosive move)"
        focus = "Max strength + explosive power. Contrast and triphasic methods emphasized."
    elif phase == "TAPER":
        base_block = "2–3x3-5 @ 80–85%, cluster sets, minimal eccentric load"
        focus = "Maintain intensity, cut volume, CNS freshness. High bar speed focus."
    else:
        base_block = "Default fallback block — check logic."
        focus = "Default phase. Ensure proper phase detection upstream."

    fatigue_note = ""
    if fatigue:
        try:
            fatigue_score = int(fatigue)
            if fatigue_score >= 8:
                fatigue_note = "⚠️ High fatigue – cut volume by 30–40%, drop final set, reduce eccentric emphasis."
            elif 5 <= fatigue_score <= 7:
                fatigue_note = "⚠️ Moderate fatigue – reduce volume by ~15%, avoid max effort sets."
            elif fatigue_score <= 4:
                fatigue_note = "✅ Fatigue within acceptable range — proceed as programmed."
        except ValueError:
            pass

    strength_output.append("🏋️‍♂️ **Strength & Power Module**")
    strength_output.append(f"**Phase:** {phase}")
    strength_output.append(f"**Primary Focus:** {focus}")
    strength_output.append("**Top Exercises:")
    for ex in base_exercises:
        strength_output.append(f"- {ex}")
    strength_output.append(f"**Prescription:** {base_block}")
    if fatigue_note:
        strength_output.append(f"**Adjustment:** {fatigue_note}")

    return "\n".join(strength_output)