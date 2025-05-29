from fastapi import FastAPI, Request
import openai
import os
from datetime import datetime

openai.api_key = os.getenv("OPENAI_API_KEY")
app = FastAPI()

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    fields = data["data"]["fields"]

    # Helper function to get value by label
    def get_value(label):
        for field in fields:
            if field.get("label", "").strip() == label.strip():
                if isinstance(field["value"], list):
                    # For dropdowns or checkboxes, resolve text
                    return ", ".join(
                        [opt["text"] for opt in field.get("options", []) if opt["id"] in field["value"]]
                    )
                return field["value"]
        return ""

    # Parse all values from Tally form
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

    # Convert date to weeks out
    if next_fight_date:
        fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
        weeks_out = max(1, (fight_date - datetime.now()).days // 7)
    else:
        weeks_out = "N/A"

    prompt = f"""
You are an elite strength & conditioning coach (MSc-level) who has trained 100+ world-class fighters in UFC, Glory, ONE Championship, and Olympic combat sports.

You follow the Unlxck Method — a high-performance system combining periodised fight camp phases (GPP → SPP → Taper), neuro-driven sprint/strength protocols, and psychological recalibration tools used at the highest levels.

Based on the athlete’s input below, generate a tailored 3-phase Fight-Ready program including:
1. Weekly physical training targets (S&C + conditioning focus)
2. Phase-specific goals based on time to fight
3. One key mindset tool or mental focus for each phase
4. Red flags to watch for based on their inputs (fatigue, taper risk, recovery needs)

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

Your coaching logic must follow these rules (Unlxck Coaching Brain):
• Use 3-phase camp logic:
  • GPP (12–8 weeks out): build strength base, aerobic capacity, durability
  • SPP (8–3 weeks out): sharpen force output, alactic/anaerobic conditioning
  • Taper (final 2 weeks): maintain intensity, cut volume, refeed for performance
• Program S&C using triphasic → max strength → contrast methods (e.g. trap bar jumps, isos, clusters)
• Scale sprint/conditioning volume to weight class, fatigue, and fight distance
• Include mindset anchors (visualisation, cue words, ego control) per phase
• Trigger red flags if: weight cut is above 6%, RPE is high, taper period is too short
• Nutrition rules:
  • Maintain high protein (~2g/kg), carbs based on training phase
  • Final week = low-residue diet → refeed with high-GI carbs + fluids post-weigh-in
  • Flag risky cuts or poor taper fueling

Always program like the fighter is preparing for a world title. Your tone should be clear, grounded, and elite — no filler, no simplifications.
    """

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1400
    )

    result = response.choices[0].message.content
    return {"plan": result}
