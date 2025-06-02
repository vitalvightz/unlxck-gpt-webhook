from datetime import datetime
from fastapi import FastAPI, Request
import os, json, base64
import openai
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Modules
from training_context import build_training_context
from mindset_module import classify_mental_block, get_mindset_by_phase, get_mental_protocols
from strength import generate_strength_block
from conditioning import generate_conditioning_block
from recovery import generate_recovery_block
from nutrition import generate_nutrition_block
from injury_subs import generate_injury_subs

# Auth
if os.getenv("GOOGLE_CREDS_B64"):
    with open("clientsecrettallyso.json", "w") as f:
        decoded = base64.b64decode(os.getenv("GOOGLE_CREDS_B64"))
        f.write(decoded.decode("utf-8"))

openai.api_key = os.getenv("OPENAI_API_KEY")
SERVICE_ACCOUNT_FILE = 'clientsecrettallyso.json'
SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
docs_service = build('docs', 'v1', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)

app = FastAPI()

def get_value(label, fields):
    for field in fields:
        if field.get("label", "").strip() == label.strip():
            value = field.get("value")
            if isinstance(value, list):
                # Case 1: it's a list of option IDs and we have options to match
                if "options" in field:
                    return ", ".join([
                        opt["text"] for opt in field["options"] if opt.get("id") in value
                    ])
                # Case 2: it's already a list of strings (Tally sometimes sends this)
                return ", ".join(str(v) for v in value)
            return str(value).strip() if value is not None else ""
    return ""

def get_folder_id(folder_name):
    response = drive_service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'", spaces='drive').execute()
    folders = response.get('files', [])
    return folders[0]['id'] if folders else None

def create_doc(title, content):
    folder_id = get_folder_id("Unlxck Auto Docs")
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    if folder_id:
        drive_service.files().update(fileId=doc_id, addParents=folder_id, removeParents='root').execute()
    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]}).execute()
    return f"https://docs.google.com/document/d/{doc_id}"

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    fields = data["data"]["fields"]

    # Basic info
    full_name = get_value("Full name", fields)
    age = get_value("Age", fields)
    weight = get_value("Weight (kg)", fields)
    target_weight = get_value("Target Weight (kg)", fields)
    height = get_value("Height (cm)", fields)
    fighting_style_technical = get_value("Fighting Style (Technical)", fields)
    fighting_style_tactical = get_value("Fighting Style (Tactical)", fields)
    stance = get_value("Stance", fields)
    status = get_value("Professional Status", fields)
    record = get_value("Current Record", fields)
    next_fight_date = get_value("When is your next fight?", fields)
    rounds_format = get_value("Rounds x Minutes", fields)
    frequency = get_value("Weekly Training Frequency", fields)
    fatigue = get_value("Fatigue Level", fields)
    equipment_access = get_value("Equipment Access", fields)
    available_days = get_value("Time Availability for Training", fields)
    injuries = get_value("Any injuries or areas you need to work around?", fields)
    key_goals = get_value("What are your key performance goals?", fields)
    weak_areas = get_value("Where do you feel weakest right now?", fields)
    training_preference = get_value ("Do you prefer certain training styles?", fields)
    mental_block = get_value("Do you struggle with any mental blockers or mindset challenges?", fields)
    notes = get_value("Are there any parts of your previous plan you hated or loved?", fields)

    # Fight phase logic
    if next_fight_date:
        try:
            fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
            weeks_out = max(1, (fight_date - datetime.now()).days // 7)
        except:
            weeks_out = "N/A"
    else:
        weeks_out = "N/A"

    if weeks_out == "N/A":
        phase = "GPP"
    else:
        weeks_out = int(weeks_out)
        if weeks_out > 8:
            phase = "GPP"
        elif 3 < weeks_out <= 8:
            phase = "SPP"
        else:
            phase = "TAPER"

    training_context = build_training_context()

    # Build modules
    flags = training_context.copy()
    flags["mental_block"] = classify_mental_block(mental_block)

    mindset_block = get_mindset_by_phase(phase, flags)
    mental_strategies = get_mental_protocols(flags["mental_block"], phase)
    strength_block = generate_strength_block(flags=training_context, weaknesses=training_context["weaknesses"])
    conditioning_block = generate_conditioning_block(training_context)
    recovery_block = generate_recovery_block(
        age=int(age), phase=phase, weight=float(weight), weight_class=weight_class, flags=training_context
    )
    nutrition_block = generate_nutrition_block(flags=training_context)
    injury_sub_block = generate_injury_subs(injury_string=injuries)

    # 🧠 Debug: Print all blocks before GPT call re-edit and complete

    print("== NUTRITION BLOCK ==\n", nutrition_block)

        # Compile final prompt
    prompt = f"""
# CONTEXT BLOCKS – Use these to build the plan

## SAFETY
Avoid training through pain. Prioritize recovery. Emphasize technique.

## MINDSET
{mindset_block}

## MENTAL PROTOCOLS
{mental_strategies}

## STRENGTH
{strength_block["block"]}

## CONDITIONING
{conditioning_block}

## RECOVERY
{recovery_block}

## NUTRITION
{nutrition_block}

## INJURY SUBSTITUTIONS
{injury_sub_block}

---

You are an elite strength & conditioning coach (MSc-level) who has trained 100+ world-class fighters across UFC, Glory, ONE Championship, and Olympic combat sports.

Use the above **modules as source material** to create a **3-phase fight camp** (GPP, SPP, Taper).

Stick closely to the input blocks — **these are tailored insights from Unlxck’s system**.

Avoid generic theory. Be **practical and specific, include exercises and number of sets**.

Athlete Profile:
- Name: {full_name}
- Age: {age}
- Weight: {weight}kg
- Target Weight: {target_weight}kg
- Height: {height}cm
- Techincal Style: {fighting_style_technical}
- Tactical Style: {fighting_style_tactical}
- Stance: {stance}
- Level: {status}
- Record: {record}
- Fight Format: {rounds_format}
- Fight Date: {next_fight_date}
- Weeks Out: {weeks_out}
- Fatigue Level: {fatigue}
- Injuries: {injuries}
- Available S&C Days: {available_days}
- Weaknesses: {weak_areas}
- Key Goals: {key_goals}
- Mindset Challenges: {mental_block}
- Extra Notes: {notes}
"""

    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1800
        )
        full_plan = response.choices[0].message.content.strip()
        print("✅ GPT Response (First 500 chars):\n", full_plan[:500])
    except Exception as e:
        print("❌ GPT API Error:", e)
        return {"error": "Failed to generate plan from OpenAI"}

    try:
        doc_link = create_doc(f"Fight Plan – {full_name}", full_plan)
        print("✅ Google Doc Created:", doc_link)
    except Exception as e:
        print("❌ Google Docs API Error:", e)
        doc_link = None

    return {"doc_link": doc_link or "Document creation failed"}