from datetime import datetime
from fastapi import FastAPI, Request
import openai
import os
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Decode and save service account credentials
if os.getenv("GOOGLE_CREDS_B64"):
    with open("clientsecrettallyso.json", "w") as f:
        decoded = base64.b64decode(os.getenv("GOOGLE_CREDS_B64"))
        f.write(decoded.decode("utf-8"))

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# Google Docs and Drive setup
DOCS_SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'clientsecrettallyso.json'
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=DOCS_SCOPES
)
docs_service = build('docs', 'v1', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)

# Find folder ID by name
def get_folder_id(folder_name):
    response = drive_service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'",
                                          spaces='drive').execute()
    folders = response.get('files', [])
    return folders[0]['id'] if folders else None

# Create doc in folder
def create_doc(title, content):
    folder_id = get_folder_id("Unlxck Auto Docs")
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")

    if folder_id:
        drive_service.files().update(fileId=doc_id, addParents=folder_id, removeParents='root').execute()

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": content
                    }
                }
            ]
        }
    ).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

app = FastAPI()

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
    text = block_text.lower()
    if any(term in text for term in ["confidence", "doubt", "self-belief", "don't believe"]):
        return "confidence"
    elif any(term in text for term in ["gas", "cardio", "round", "tired", "fade"]):
        return "gas tank"
    elif any(term in text for term in ["injury", "hurt", "reinjure"]):
        return "injury fear"
    elif any(term in text for term in ["pressure", "nerves", "stress", "expectation"]):
        return "pressure"
    elif any(term in text for term in ["focus", "distracted", "adhd"]):
        return "attention"
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

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    fields = data["data"]["fields"]

    def get_value(label):
        for field in fields:
            if field.get("label", "").strip() == label.strip():
                if isinstance(field["value"], list):
                    return ", ".join([
                        opt["text"] for opt in field.get("options", []) if opt["id"] in field["value"]
                    ])
                return field["value"]
        return ""

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

    mental_category = classify_mental_block(mental_block)
    mental_protocols = {
        "confidence": "• DAILY power pose ritual + achievement journaling",
        "gas tank": "• HYPOXIC training visualization + round 10 mindset drills",
        "injury fear": "• GRADED exposure therapy with progressively heavier loads",
        "pressure": "• SIMULATED high-stakes scenarios in training",
        "attention": "• Use Pomodoro training + visual cue anchoring",
        "generic": "• STANDARD visualization protocols"
    }[mental_category]

    safety_block = ''.join([f"{line}\n" for line in safety_prompts])

    prompt = f"""
You are an elite strength & conditioning coach (MSc-level) who has trained 100+ world-class fighters in UFC, Glory, ONE Championship, and Olympic combat sports.

You follow the Unlxck Method — a high-performance system combining periodised fight camp phases (GPP → SPP → Taper), neuro-driven sprint/strength protocols, psychological recalibration tools, and integrated recovery systems used at the highest levels.

{get_phase(weeks_out if weeks_out != 'N/A' else 10, int(age))}
{safety_block}
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
"""

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1600
    )

    result = response.choices[0].message.content
    print("===== RETURNED PLAN =====")
    print(result)

    doc_link = create_doc(f"Fight Plan – {full_name}", result)
    print("Google Doc Link:", doc_link)
    return {"doc_link": doc_link}
    