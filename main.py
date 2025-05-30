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

# Core config
app = FastAPI()

# --- Utility Functions ---
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
    response = drive_service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'",
                                          spaces='drive').execute()
    folders = response.get('files', [])
    return folders[0]['id'] if folders else None

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

# --- Webhook Endpoint ---
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
        fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
        weeks_out = max(1, (fight_date - datetime.now()).days // 7)
    else:
        weeks_out = "N/A"

    prompt = f"""
You are an elite strength & conditioning coach (MSc-level) who has trained 100+ world-class fighters in UFC, Glory, ONE Championship, and Olympic combat sports.

You follow the Unlxck Method — a high-performance system combining periodised fight camp phases (GPP → SPP → Taper), neuro-driven sprint/strength protocols, and psychological recalibration tools used at the highest levels.

Based on the athlete’s input below, generate a comprehensive and tailored 3-phase Fight-Ready program including:
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
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1800
    )

    result = response.choices[0].message.content
    print("===== RETURNED PLAN =====")
    print(result)

    doc_link = create_doc(f"Fight Plan – {full_name}", result)
    print("Google Doc Link:", doc_link)
    return {"doc_link": doc_link}