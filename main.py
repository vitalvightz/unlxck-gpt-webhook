from datetime import datetime
from openai import OpenAI
import re

# Placeholder for your function to extract form values
def get_value(field):
    # Implementation for retrieving values from the form submission
    pass

# --- Safety and Injury Handling ---
SAFETY_RULES = {
    "spinal": "• BAN axial loading (squats, OH presses)\n• Use anti-flexion core work",
    "concussion": "• NO impact drills for 30 days\n• Vestibular rehab only",
    "aortic": "• IMMEDIATE medical clearance required"
}

EXERCISE_LIBRARY = {
    "shoulder": {
        "substitutes": {
            "overhead press": "landmine press",
            "pull-ups": "ring rows"
        },
        "protocols": {
            "instability": "• Add 3x15 banded ER/IR daily\n• Limit ROM to 90° flexion"
        }
    },
    "knee": {
        "substitutes": {
            "squats": "belt squats",
            "lunges": "step-ups (6\" box)"
        }
    }
}

# --- Helper Functions ---
def classify_mental_block(block_text):
    if not block_text or not isinstance(block_text, str):
        return "generic"

    text = block_text.lower().strip()

    non_answers = ["n/a", "none", "nothing", "idk", "not sure", "no", "skip", "na"]
    if any(phrase in text for phrase in non_answers) or len(text.split()) < 2:
        return "generic"

    mental_blocks = {
        "confidence": ["confidence", "doubt", "self-belief", "don't believe", "imposter"],
        "gas tank": ["gas", "cardio", "tired", "fade", "gassed", "conditioning"],
        "injury fear": ["injury", "hurt", "reinjure", "scared to tear", "pain"],
        "pressure": ["pressure", "nerves", "stress", "expectation", "choke"],
        "attention": ["focus", "distracted", "adhd", "concentration", "mental lapse"]
    }

    for block, keywords in mental_blocks.items():
        if any(re.search(rf"\\b{kw}\\b", text) for kw in keywords):
            return block

    return "generic"

def get_phase(weeks_out: int, age: int) -> str:
    if not isinstance(weeks_out, int):
        return "• MAINTAIN GPP protocols (no fight date)"
    taper_start = 3 if age < 30 else 4
    if weeks_out >= 8:
        return "• GPP PHASE: Aerobic base + hypertrophy"
    elif weeks_out >= taper_start:
        return f"• SPP PHASE: Fight-specific power (taper in {weeks_out - taper_start + 1}w)"
    else:
        return "• TAPER PHASE: Peak intensity, 30-50% volume drop"

# Collect form inputs
full_name = get_value("Full name")
age = get_value("Age")
weight = get_value("Weight (kg)")
weight_class = get_value("Weight Class")
height = get_value("Height (cm)")
fighting_style = get_value("Fighting Style")
stance = get_value("Stance")
status = get_value("Professional Status")
record = get_value("Current Record")
next_fight_date = get_value("Next Fight 👇")
rounds_format = get_value("Rounds & Format")
frequency = get_value("Weekly Training Frequency")
fatigue = get_value("Fatigue Level")
injuries = get_value("Any past or current injuries that we should avoid loading?")
available_days = get_value("Days Available for S&C training")
weak_areas = get_value("Where do you feel weakest right now?")
mental_block = get_value("What is your biggest mental barrier")
notes = get_value("Anything else you want us to know before we build your system?")

# Calculate weeks out from next fight
if next_fight_date:
    fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
    weeks_out = max(1, (fight_date - datetime.now()).days // 7)
else:
    weeks_out = "N/A"

# --- Safety Logic Injection ---
safety_prompts = []
for term, rule in SAFETY_RULES.items():
    if term in injuries.lower():
        safety_prompts.append(rule)

if "shoulder" in injuries.lower():
    safety_prompts.append(EXERCISE_LIBRARY["shoulder"]["protocols"].get("instability", ""))
    safety_prompts.extend([f"• {k} → {v}" for k,v in EXERCISE_LIBRARY["shoulder"]["substitutes"].items()])

# Mental mapping
mental_category = classify_mental_block(mental_block)
mental_protocols = {
    "confidence": "• DAILY power pose ritual + achievement journaling",
    "gas tank": "• HYPOXIC training visualization + round 10 mindset drills",
    "injury fear": "• GRADED exposure therapy with progressively heavier loads",
    "pressure": "• SIMULATED high-stakes scenarios in training",
    "attention": "• Use Pomodoro training + visual cue anchoring",
    "generic": "• STANDARD visualization protocols"
}[mental_category]

# Construct the prompt
prompt = f"""
You are an elite strength & conditioning coach (MSc-level) who has trained 100+ world-class fighters in UFC, Glory, ONE Championship, and Olympic combat sports.

You follow the Unlxck Method — a high-performance system combining periodised fight camp phases (GPP → SPP → Taper), neuro-driven sprint/strength protocols, psychological recalibration tools, and integrated recovery systems used at the highest levels.

{get_phase(weeks_out if weeks_out != 'N/A' else 10, int(age))}
{''.join([f"{line}\n" for line in safety_prompts])}
{mental_protocols}

Based on the athlete’s input below, generate a tailored 3-phase Fight-Ready program including:
1. Weekly physical training targets (S&C + conditioning focus, with breakdown by energy system: ATP-PCr, glycolytic, aerobic)
2. Phase-specific goals based on time to fight
3. One key mindset tool or mental focus for each phase
4. Recovery strategies based on fatigue, age, and tapering principles
5. Red flags to watch for based on their inputs (fatigue, taper risk, recovery needs)
6. Use logic based on age, fight format (e.g. 3x3 vs 5x5), fatigue, and injury
7. Specify exact exercise names, loads (RPE or %1RM), reps, rest times, and movement types in S&C and conditioning sessions.

Athlete Profile:
- Name: {full_name}
- Age: {age}
- Weight: {weight}kg
- Weight Class: {weight_class}
- Height: {height}cm
- Style: {fighting_style}
- Stance: {stance}
- Level: {status}
- Record: {record}
- Fight Format: {rounds_format}
- Fight Date: {next_fight_date}
- Weeks Out: {weeks_out}
- S&C Frequency: {frequency}/week
- Fatigue Level: {fatigue}
- Injuries: {injuries}
- Available S&C Days: {available_days}
- Physical Weaknesses: {weak_areas}
- Mental Blocker: {mental_block}
- Extra Notes: {notes}

... [rest of Unlxck programming prompt continues as before]
"""

# Send to OpenAI
client = OpenAI(api_key="your_api_key")
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.3,
    max_tokens=1600
)

# Output
output_text = response.choices[0].message.content
print(output_text)