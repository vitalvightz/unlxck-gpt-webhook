injury_subs = {
    # ===== LOWER BODY ===== #
    "feet": ["Sled Push", "Sled Drag (Forward)", "Reverse Lunge"],
    "ankle": ["Step-Up (Bodyweight)", "Glute Bridge", "Trap Bar Deadlift"],
    "shin": ["Heels-Elevated Goblet Squat", "Isometric Wall Sit", "Sled Drag (Forward)"],
    "calf": ["Box Squat", "Step-Up (Bodyweight)", "Deadlift with Pause"],
    "knee": ["Belt Squat", "Step-Up (6\" Box)", "Reverse Lunge"],
    "hamstring": ["Glute Bridge", "Trap Bar Deadlift", "Single-Leg RDL (Kettlebell)"],
    "quad": ["Hamstring Curl", "Step-Up (Bodyweight)", "Romanian Deadlift"],
    "hip flexors": ["Glute Bridge", "Hip Thrust", "Single-Leg RDL"],
    "glutes": ["Quad Extension", "Heels-Elevated Goblet Squat", "Bike Sprints"],

    # ===== CORE/TORSO ===== #
    "core": ["Bird-Dog", "Pallof Press (Isometric Hold)", "Deadbug (Band-Resisted)"],
    "lower back": ["Trap Bar Deadlift", "Leg Press", "Hip Thrust"],
    "obliques": ["Anti-Rotation Press", "Pallof Hold", "Seated Medicine Ball Rotation"],
    "ribs": ["Hollow-Body Hold", "Deadbug", "Side Plank (Banded)"],

    # ===== UPPER BODY ===== #
    "upper back": ["Face Pull", "Band Row", "TRX Row"],
    "chest": ["Landmine Press", "DB Fly", "Swiss Ball Press"],
    "shoulders": ["Landmine Press", "Neutral Grip DB Press", "Band-Resisted Push Press"],
    "bicep": ["Triceps Focus", "Hammer Grip Row", "Towel Pull-Up"],
    "triceps": ["Bicep Work", "Push-Up (Weighted)", "Landmine Press"],

    # ===== NECK/GRIP ===== #
    "neck": ["Band-Resisted Shrugs", "Chin Tucks", "Isometric Neck Hold"],
    "jaw": ["Neural Neck Flexion", "Isometric Neck Hold", "Band-Resisted Shrugs"],
    "hand": ["Wrist Wraps + Barbell Work", "Machine Press", "Neutral Grip DB Press"],
    "wrist": ["Neutral Grip DB Press", "Trap Bar Press", "Cable Rotations"],
    "forearm": ["Landmine Press", "Belt Squat", "Towel Hang"]
}

def generate_injury_subs(*, injury_string: str, exercise_data: list) -> str:
    """
    Generates injury-specific exercise substitutions from a predefined list,
    validating against available exercises in the database.
    
    Args:
        injury_string: Comma-separated injury areas (e.g., "knee, shoulder")
        exercise_data: List of exercises in JSON format
        
    Returns:
        Formatted substitution guidelines or fallback messages
    """
    if not injury_string:
        return "\n✅ No injury substitutions needed."

    injury_string = injury_string.lower()
    result_lines = []
    
    for injury_key, subs in injury_subs.items():
        if injury_key in injury_string:
            valid_subs = [
                ex["name"] for ex in exercise_data 
                if any(s.lower() == ex["name"].lower() for s in subs)
                and "rehab_friendly" in ex.get("tags", [])
            ]
            
            if valid_subs:
                result_lines.append(f"- {injury_key.title()}: {', '.join(valid_subs)}")

    if not result_lines:
        return "\n⚠️ No known substitutions found. Please review manually."

    return "\n🔁 **Injury Substitution Guidelines**\n" + "\n".join(result_lines)