app = FastAPI()
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.post("/webhook")
async def handle_tally(request: Request):
    data = await request.json()
    answers = data["data"]["answers"]

    weight_class = answers[0]["answer"]
    weeks_out = answers[1]["answer"]
    frequency = answers[2]["answer"]
    weakness = answers[3]["answer"]
    fatigue = answers[4]["answer"]
    mindset = answers[5]["answer"]

    prompt = f"""
You are an elite strength & conditioning coach... [INSERT COACHING BRAIN]

Athlete input:
- Weight Class: {weight_class}
- Weeks Until Fight: {weeks_out}
- Training Frequency: {frequency}
- Key Weakness: {weakness}
- Fatigue Level: {fatigue}
- Mindset Barrier: {mindset}
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1500
    )

    plan = response["choices"][0]["message"]["content"]
    print(plan)
    return {"status": "ok", "plan": plan}
