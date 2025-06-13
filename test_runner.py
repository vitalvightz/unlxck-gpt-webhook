import json
from fightcamp.plan_generator import generate_training_plan

if __name__ == "__main__":
    sample_fields = {
        "Full name": "Test Fighter",
        "Age": "28",
        "Weight (kg)": "77",
        "Target Weight (kg)": "70",
        "Height (cm)": "175",
        "Fighting Style (Technical)": "mma",
        "Fighting Style (Tactical)": "pressure",
        "Stance": "orthodox",
        "Professional Status": "professional",
        "Current Record": "5-1",
        "When is your next fight?": "2024-12-01",
        "Rounds x Minutes": "3x5",
        "Weekly Training Frequency": "4",
        "Fatigue Level": "Moderate",
        "Equipment Access": "full gym",
        "Time Availability for Training": "Mon, Tue, Thu, Fri",
        "Any injuries or areas you need to work around?": "knee, shoulder",
        "What are your key performance goals?": "Strength, Conditioning / Endurance",
        "Where do you feel weakest right now?": "grappling, clinch",
        "Do you prefer certain training styles?": "strength, power",
        "Do you struggle with any mental blockers or mindset challenges?": "confidence, motivation",
        "Are there any parts of your previous plan you hated or loved?": "Hated long runs",
    }
    plan, _ = generate_training_plan(sample_fields)
    print(plan)
