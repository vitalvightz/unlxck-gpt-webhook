from fastapi import FastAPI, Request
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    answers = data["data"]["answers"]

    full_name = answers[0]["answer"]
    age = answers[1]["answer"]
    weight = answers[2]["answer"]
    weight_class = answers[3]["answer"]
    height = answers[4]["answer"]
    fighting_style = answers[5]["answer"]
    stance = answers[6]["answer"]
    status = answers[7]["answer"]
    record = answers[8]["answer"]
    weeks_out = answers[9]["answer"]
    rounds_format = answers[10]["answer"]
    frequency = answers[11]["answer"]
    fatigue = answers[12]["answer"]
    injuries = answers[13]["answer"]
    available_days = answers[14]["answer"]
    weak_areas = ", ".join(answers[15]["choices"]) if "choices" in answers[15] else answers[15]["answer"]
    leak = answers[16]["answer"]
    mental_block = answers[17]["answer"]
    notes = answers[18]["answer"]

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
- Fight Timeline: {weeks_out} weeks out
- S&C Frequency: {frequency}/week
- Fatigue Level: {fatigue}
- Injuries: {injuries}
- Available S&C Days: {available_days}
- Physical Weaknesses: {weak_areas}
- Performance Leak: {leak}
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

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1400
    )

    result = response["choices"][0]["message"]["content"]
    return {"plan": result}