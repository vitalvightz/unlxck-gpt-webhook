from pathlib import Path

# Define the merged weight class logic with weight cut analysis
merged_logic_code = '''
# weight_class_logic.py

weight_class_map = {
    "MMA": {
        "Flyweight": 56.7,
        "Bantamweight": 61.2,
        "Featherweight": 65.8,
        "Lightweight": 70.3,
        "Welterweight": 77.1,
        "Middleweight": 83.9,
        "Light Heavyweight": 93.0,
        "Heavyweight": 120.2
    },
    "Boxing": {
        "Flyweight": 50.8,
        "Bantamweight": 53.5,
        "Featherweight": 57.2,
        "Lightweight": 61.2,
        "Welterweight": 66.7,
        "Middleweight": 72.6,
        "Light Heavyweight": 79.4,
        "Cruiserweight": 90.7,
        "Heavyweight": 101.6
    },
    "Kickboxing": {
        "Featherweight": 60.0,
        "Lightweight": 63.5,
        "Welterweight": 67.0,
        "Middleweight": 75.0,
        "Light Heavyweight": 81.0,
        "Cruiserweight": 86.0,
        "Heavyweight": 95.0,
        "Super Heavyweight": 120.0
    }
}

def assess_weight_cut(current_weight, fight_weight_class, sport="MMA"):
    """
    Assess weight cut severity.
    """
    try:
        class_limit = weight_class_map[sport][fight_weight_class]
        cut_amount = current_weight - class_limit

        if cut_amount < 2:
            return "🟢 No significant cut — maintain performance."
        elif 2 <= cut_amount < 5:
            return "🟡 Moderate cut — monitor hydration, recovery stress."
        elif 5 <= cut_amount < 8:
            return "🔴 Aggressive cut — risk of CNS/mood disruption."
        else:
            return "🚨 Critical cut — taper hard training, maximize recovery, hydration, and rest."
    except KeyError:
        return "❓ Unknown weight class or sport — check input."
'''

# Save the merged logic to a file
file_path = Path("/mnt/data/weight_class_logic.py")
file_path.write_text(merged_logic_code)

file_path