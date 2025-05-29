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
You are an MSc-level strength & conditioning coach for elite fighters (UFC, GLORY, Olympic). Build a tailored 8-week physical + mental system based on the Unlxck Method (GPP → SPP → taper), neural sprint logic, and cognitive recalibration tools.

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

Fight Context:
- Time Until Fight: {weeks_out} weeks
- Format: {rounds_format}
- Weekly Training Frequency: {frequency}
- Fatigue Level: {fatigue}
- Injuries: {injuries}
- S&C Days Available: {available_days}

Performance Gaps:
- Physical Weaknesses: {weak_areas}
- Performance Leak: {leak}
- Mental Limiter: {mental_block}
- Notes: {notes}

Design a structured 3-phase system (GPP → SPP → taper) with:
- Weekly physical targets
- Conditioning priorities
- 1 mental recalibration task per week
- Clear red flags

Output as clean plain text.
    """

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1400
    )

    result = response["choices"][0]["message"]["content"]
    return {"plan": result}