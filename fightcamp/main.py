from datetime import datetime
from fastapi import FastAPI, Request
import os, json, base64
import asyncio
from functools import partial
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Load exercise bank
exercise_bank = json.loads((DATA_DIR / "exercise_bank.json").read_text())

# Modules
from .training_context import allocate_sessions, normalize_equipment_list
from .camp_phases import calculate_phase_weeks
from .mindset_module import (
    classify_mental_block,
    get_phase_mindset_cues,
    get_mindset_by_phase,
)
from .strength import generate_strength_block
from .conditioning import generate_conditioning_block
from .recovery import generate_recovery_block
from .nutrition import generate_nutrition_block
from .rehab_protocols import generate_rehab_protocols

GOAL_NORMALIZER = {
    "Power & Explosiveness": "explosive",
    "Conditioning / Endurance": "conditioning",
    "Maximal Strength": "strength",
    "Mobility": "mobility",
    "Speed": "reactive",
    "Agility": "lateral",
    "Core Stability": "core",
    "CNS Fatigue": "cns",
    "Speed / Reaction": "reactive",
    "Lateral Movement": "lateral",
    "Rotation": "rotational",
    "Balance": "balance",
    "Shoulders": "shoulders",
    "Hip Mobility": "hip",
    "Grip Strength": "grip",
    "Posterior Chain": "posterior_chain",
    "Knees": "quad_dominant",
    "Neck": "neck",
    "Grappling": "grappler",
    "Striking": "striking",
    "Injury Prevention": "injury_prevention",
    "Mental Resilience": "mental_resilience",
    "Skill Refinement": "skill_refinement"
}

# Auth setup
if os.getenv("GOOGLE_CREDS_B64"):
    with open("clientsecrettallyso.json", "w") as f:
        decoded = base64.b64decode(os.getenv("GOOGLE_CREDS_B64"))
        f.write(decoded.decode("utf-8"))
SERVICE_ACCOUNT_FILE = 'clientsecrettallyso.json'
SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
docs_service = build('docs', 'v1', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)

app = FastAPI()

from .plan_generator import parse_tally_fields, generate_training_plan

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
    fields_list = data["data"]["fields"]
    field_dict = parse_tally_fields(fields_list)
    full_plan, full_name = generate_training_plan(field_dict)

    print("✅ Plan generated locally (First 500 chars):\n", full_plan[:500])

    loop = asyncio.get_running_loop()
    for _ in range(2):
        try:
            doc_link = await loop.run_in_executor(
                None,
                partial(create_doc, f"Fight Plan – {full_name}", full_plan)
            )
            print("✅ Google Doc Created:", doc_link)
            break
        except Exception as e:
            print("❌ Google Docs API Error (Retrying):", e)
            await asyncio.sleep(2)
    else:
        doc_link = None

    return {"doc_link": doc_link or "Document creation failed"}
