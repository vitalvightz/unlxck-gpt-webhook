from datetime import datetime
from fastapi import FastAPI, Request
import openai
import os
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Modular imports powering GPT context
from flag_router import flag_router
from mindset_module import classify_mental_block, get_mindset_by_phase
from strength import generate_strength_block
from conditioning import generate_conditioning_block
from recovery import generate_recovery_block
from nutrition import generate_nutrition_block
from injury_subs import generate_injury_subs
from utils import get_phase, get_safety_block, get_mental_protocols

# Decode and save service account credentials
if os.getenv("GOOGLE_CREDS_B64"):
    with open("clientsecrettallyso.json", "w") as f:
        decoded = base64.b64decode(os.getenv("GOOGLE_CREDS_B64"))
        f.write(decoded.decode("utf-8"))

openai.api_key = os.getenv("OPENAI_API_KEY")

DOCS_SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'clientsecrettallyso.json'
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=DOCS_SCOPES)
docs_service = build('docs', 'v1', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)

app = FastAPI()

def get_value(label, fields):
    for field in fields:
        if field.get("label", "").strip() == label.strip():
            if isinstance(field["value"], list):
                return ", ".join([
                    opt["text"] for opt in field.get("options", []) if opt["id"] in field["value"]
                ])
            return field["value"]
    return ""

def get_folder_id(folder_name):
    response = drive_service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'", spaces='drive').execute()
    folders = response.get('files', [])
    return folders[0]['id'] if folders else None

def create_doc(title, content):
    folder_id = get_folder_id("Unlxck Auto Docs")
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")
    if folder_id:
        drive_service.files().update(fileId=doc_id, addParents=folder_id, removeParents='root').execute()
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    fields = data["data"]["fields"]

    full_name = get_value("Full name", fields)
    age = get_value("Age", fields)
    weight = get_value("Weight (kg)", fields)
    weight_class = get_value("Weight Class", fields)
    height = get_value("Height (cm)", fields)
    fighting_style = get_value("Fighting Style", fields)
    stance = get_value("Stance", fields)
    status = get_value("Professional Status", fields)
    record = get_value("Current Record", fields)
    next_fight_date = get_value("Next Fight 👇", fields)
    rounds_format = get_value("Rounds & Format", fields)
    frequency = get_value("Weekly Training Frequency", fields)
    fatigue = get_value("Fatigue Level", fields)
    injuries = get_value("Any past or current injuries that we should avoid loading?", fields)
    available_days = get_value("Days Available for S&C training", fields)
    weak_areas = get_value("Where do you feel weakest right now?", fields)
    mental_block = get_value("What is your biggest mental barrier", fields)
    notes = get_value("Anything else you want us to know before we build your system?", fields)

    if next_fight_date:
        try:
            fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
            weeks_out = max(1, (fight_date - datetime.now()).days // 7)
        except Exception:
            weeks_out = "N/A"
    else:
        weeks_out = "N/A"

    if weeks_out == "N/A":
        phase = "GPP"
    else:
        try:
            wo_int = int(weeks_out)
            if wo_int > 8:
                phase = "GPP"
            elif 3 < wo_int <= 8:
                phase = "SPP"
            else:
                phase = "TAPER"
        except Exception:
            phase = "GPP"

    try: age_int = int(age)
    except: age_int = 25
    try: weight_float = float(weight)
    except: weight_float = 70.0
    try: fatigue_int = int(fatigue)
    except: fatigue_int = 1

    injuries_str = injuries if injuries else ""
    weaknesses_list = [w.strip().lower() for w in weak_areas.split(",")] if weak_areas else None

    flags = flag_router(age=age_int, fatigue_score=fatigue_int, phase=phase, weight=weight_float, weight_class=weight_class, injuries=injuries_str)
    flags["phase"] = phase
    flags["mental_block"] = classify_mental_block(mental_block)

    # Modular Context Sections
    phase_goals = get_phase(weeks_out if weeks_out != 'N/A' else 10, age_int)
    safety_block = get_safety_block(flags)
    mental_protocols = get_mental_protocols(flags["mental_block"], phase)
    mindset_context = get_mindset_by_phase(phase, flags)
    strength_context = generate_strength_block(flags, weaknesses=weaknesses_list)
    conditioning_context = generate_conditioning_block(phase, flags, fight_format=rounds_format)
    recovery_context = generate_recovery_block(age_int, phase, weight_float, weight_class, flags)
    nutrition_context = generate_nutrition_block(flags)
    injury_subs_context = generate_injury_subs(injuries_str)

    prompt = f"""
You are an elite strength & conditioning coach (MSc-level) who has trained 100+ world-class fighters in UFC, Glory, ONE Championship, and Olympic combat sports.

You follow the Unlxck Method — a high-performance system combining periodised fight camp phases (GPP → SPP → Taper), neuro-driven sprint/strength protocols, psychological recalibration tools, and integrated recovery systems used at the highest levels.

# PHASE CONTEXT
{phase_goals}

# SAFETY RULES
{safety_block}

# MINDSET STRATEGY
{mental_protocols}
{mindset_context}

# CONDITIONING INPUTS
{conditioning_context}

# STRENGTH INPUTS
{strength_context}

# RECOVERY INPUTS
{recovery_context}

# INJURY ADJUSTMENTS
{injury_subs_context}

# NUTRITION INPUTS
{nutrition_context}

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
        max_tokens=1800
    )
    full_plan = response.choices[0].message.content.strip()

    print("\n=== GPT FINAL OUTPUT ===\n")
    print(full_plan[:500])
    print("\n=== END ===\n")

    doc_link = create_doc(f"Fight Plan – {full_name}", full_plan)
    return {"doc_link": doc_link}
    
