from datetime import datetime
from fastapi import FastAPI, Request
import os, json, base64
import openai
import asyncio
from functools import partial
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pathlib import Path

# Load exercise bank
exercise_bank = json.loads(Path("exercise_bank.json").read_text())

# Modules
from training_context import allocate_sessions, normalize_equipment_list
from mindset_module import (
    classify_mental_block,
    get_mental_protocols,
    get_phase_mindset_cues,
)
from strength import generate_strength_block
from conditioning import generate_conditioning_block
from recovery import generate_recovery_block
from nutrition import generate_nutrition_block
from injury_subs import generate_injury_subs

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
    "Grappling": "grappling",
    "Striking": "striking",
    "Injury Prevention": "injury prevention",
    "Mental Resilience": "mental resilience",
    "Skill Refinement": "skill refinement"
}

# Auth setup
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
                if "options" in field:
                    return ", ".join([opt["text"] for opt in field["options"] if opt.get("id") in value])
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

    # Extract and normalize fields
    def normalize_list(field):
        return [w.strip().lower() for w in field.split(",")] if field else []

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
    training_preference = get_value("Do you prefer certain training styles?", fields)
    mental_block = get_value("Do you struggle with any mental blockers or mindset challenges?", fields)
    notes = get_value("Are there any parts of your previous plan you hated or loved?", fields)

    # Determine training phase
    if next_fight_date:
        try:
            fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
            weeks_out = max(1, (fight_date - datetime.now()).days // 7)
            if weeks_out > 10:
                phase = "GPP"
            elif 6 <= weeks_out <= 10:
                phase = "SPP"
            elif 3 <= weeks_out < 6:
                phase = "SPP"
            else:
                phase = "TAPER"
        except Exception:
            phase = "GPP"
            weeks_out = "N/A"
    else:
        phase = "GPP"
        weeks_out = "N/A"

    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "kickboxer": "kickboxing",
        "muay thai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "grappler": "mma",
        "karate": "kickboxing"
    }
    raw_tech_style = fighting_style_technical.strip().lower()
    mapped_format = style_map.get(raw_tech_style, "mma")

    # Core context
    training_context = {
        "phase": phase,
        "fatigue": fatigue.lower(),
        "days_available": int(frequency),
        "training_days": available_days.split(", "),
        "injuries": normalize_list(injuries),
        "style_technical": raw_tech_style,
        "style_tactical": fighting_style_tactical.strip().lower(),
        "weaknesses": normalize_list(weak_areas),
        "equipment": normalize_equipment_list(equipment_access),
        "weight_cut_risk": float(weight) - float(target_weight) >= 0.05 * float(target_weight),
        "weight_cut_pct": round((float(weight) - float(target_weight)) / float(target_weight) * 100, 1),
        "fight_format": mapped_format,
        "training_split": allocate_sessions(int(frequency)),
        "key_goals": [GOAL_NORMALIZER.get(g.strip(), g.strip()).lower() for g in key_goals.split(",") if g.strip()],
        "training_preference": training_preference.strip().lower() if training_preference else "",
        "mental_block": classify_mental_block(mental_block),
        "age": int(age) if age.isdigit() else 0,
        "weight": float(weight) if weight.replace('.', '', 1).isdigit() else 0.0,
        "prev_exercises": [],
    }

    # Module generation
    mental_block = get_mindset_by_phase(phase, training_context)
    mental_strategies = get_mental_protocols(training_context["mental_block"])
    phase_mindset_cues = get_phase_mindset_cues(training_context["mental_block"])

    # === Strength blocks per phase with repeat filtering ===
    gpp_flags = {**training_context, "phase": "GPP"}
    gpp_block = generate_strength_block(
        flags=gpp_flags,
        weaknesses=training_context["weaknesses"],
        mindset_cue=phase_mindset_cues.get("GPP"),
    )
    gpp_ex_names = [ex["name"] for ex in gpp_block["exercises"]]

    spp_flags = {**training_context, "phase": "SPP", "prev_exercises": gpp_ex_names}
    spp_block = generate_strength_block(
        flags=spp_flags,
        weaknesses=training_context["weaknesses"],
        mindset_cue=phase_mindset_cues.get("SPP"),
    )
    spp_ex_names = [ex["name"] for ex in spp_block["exercises"]]

    taper_flags = {**training_context, "phase": "TAPER", "prev_exercises": spp_ex_names}
    taper_block = generate_strength_block(
        flags=taper_flags,
        weaknesses=training_context["weaknesses"],
        mindset_cue=phase_mindset_cues.get("TAPER"),
    )
    strength_block = "\n\n".join([gpp_block["block"], spp_block["block"], taper_block["block"]])

    conditioning_block, _ = generate_conditioning_block(training_context)
    recovery_block = generate_recovery_block(training_context)
    nutrition_block = generate_nutrition_block(flags=training_context)
    injury_sub_block = generate_injury_subs(injury_string=injuries, exercise_data=exercise_bank)


    # Mental Block Strategy Injection Per Phase
    def build_mindset_prompt(phase_name: str):
        if training_context["mental_block"] and training_context["mental_block"][0].lower() != "generic":
            cues = get_phase_mindset_cues(training_context["mental_block"])
            return f"\n🚫 **Mental Block – {', '.join(training_context['mental_block']).upper()} ({phase_name} Phase)**:\n{cues.get(phase_name, '')}\n"
        else:
            return f"\n🧠 **Mental Strategy ({phase_name} Phase)**:\n{get_mindset_by_phase(phase_name, training_context)}\n"

    # Add block-level mindset cues into each phase manually (this is what GPT actually sees)
    gpp_mindset = build_mindset_prompt("GPP")
    spp_mindset = build_mindset_prompt("SPP")
    taper_mindset = build_mindset_prompt("TAPER")

    prompt = f"""
# CONTEXT BLOCKS – Use these to build the plan

## SAFETY
Avoid training through pain. Prioritize recovery. Emphasize technique.

## MINDSET
Top Block(s): {', '.join(training_context['mental_block']).title()}

## STRENGTH
### GPP
{gpp_mindset}
{gpp_block["block"]}

### SPP
{spp_mindset}
{spp_block["block"]}

### TAPER
{taper_mindset}
{taper_block["block"]}

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

Use the following blocks as reference – they are pre-analyzed insights from Unlxck’s system. As an elite coach, you may evolve, modify, or improve them based on logic, athlete style, and fight phase. Prioritize specificity, realism, and performance logic. Do not repeat exercises across phases unless clearly justified by tapering or periodization. Be **practical and specific, include exercises and number of sets**.

Athlete Profile:
- Name: {full_name}
- Age: {age}
- Weight: {weight}kg
- Target Weight: {target_weight}kg
- Height: {height}cm
- Technical Style: {fighting_style_technical}
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
- Mindset Challenges: {', '.join(training_context['mental_block'])}
- Extra Notes: {notes}
    """


    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        full_plan = response.choices[0].message.content.strip()
        print("✅ GPT Response (First 500 chars):\n", full_plan[:500])
    except Exception as e:
        print("❌ GPT API Error:", e)
        return {"error": "Failed to generate plan from OpenAI"}

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
