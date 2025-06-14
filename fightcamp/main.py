from datetime import datetime
import os, json, base64
import asyncio
from functools import partial
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:  # Google libraries may be missing in minimal environments
    service_account = None
    build = None
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
    "Coordination / Proprioception": "coordination",
    "Coordination/Proprioception": "coordination",
    "Grappling": "grappler",
    "Striking": "striking",
    "Injury Prevention": "injury_prevention",
    "Mental Resilience": "mental_resilience",
    "Skill Refinement": "skill_refinement"
}

# Map uncommon weakness labels to internal tags
WEAKNESS_NORMALIZER = {
    "coordination / proprioception": ["coordination"],
    "coordination/proprioception": ["coordination"],
}

# Auth setup
try:
    b64_creds = os.getenv("GOOGLE_CREDS_B64")
    if b64_creds:
        with open("clientsecrettallyso.json", "w") as f:
            decoded = base64.b64decode(b64_creds)
            f.write(decoded.decode("utf-8"))
    SERVICE_ACCOUNT_FILE = "clientsecrettallyso.json"
    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]

    if service_account and build:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        docs_service = build("docs", "v1", credentials=creds)
        drive_service = build("drive", "v3", credentials=creds)
    else:
        docs_service = drive_service = None
        print("⚠️  Google libraries missing; docs export disabled.")
except Exception as e:
    docs_service = drive_service = None
    print("⚠️  Google credentials not found; docs export disabled.", e)

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
    if not drive_service:
        return None
    response = drive_service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'",
        spaces="drive",
    ).execute()
    folders = response.get("files", [])
    return folders[0]["id"] if folders else None

def create_doc(title, content):
    if not docs_service or not drive_service:
        return None
    folder_id = get_folder_id("Unlxck Auto Docs")
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    if folder_id:
        drive_service.files().update(
            fileId=doc_id, addParents=folder_id, removeParents="root"
        ).execute()
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
    ).execute()
    return f"https://docs.google.com/document/d/{doc_id}"


async def generate_plan(data: dict):
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
    frequency_raw = get_value("Weekly Training Frequency", fields)
    fatigue = get_value("Fatigue Level", fields)
    equipment_access = get_value("Equipment Access", fields)
    available_days = get_value("Time Availability for Training", fields)

    # Normalize schedule info
    training_days = [d.strip() for d in available_days.split(',') if d.strip()]
    try:
        training_frequency = int(frequency_raw)
    except (TypeError, ValueError):
        training_frequency = len(training_days)
    injuries = get_value("Any injuries or areas you need to work around?", fields)
    key_goals = get_value("What are your key performance goals?", fields)
    weak_areas = get_value("Where do you feel weakest right now?", fields)
    training_preference = get_value("Do you prefer certain training styles?", fields)
    mental_block = get_value("Do you struggle with any mental blockers or mindset challenges?", fields)
    notes = get_value("Are there any parts of your previous plan you hated or loved?", fields)

    # Calculate weeks out from fight date
    weeks_out: int | str
    if next_fight_date:
        try:
            fight_date = datetime.strptime(next_fight_date, "%Y-%m-%d")
            weeks_out = max(1, (fight_date - datetime.now()).days // 7)
        except Exception:
            weeks_out = "N/A"
    else:
        weeks_out = "N/A"

    style_map = {
        "mma": "mma",
        "boxer": "boxing",
        "boxing": "boxing",
        "kickboxer": "kickboxing",
        "muay thai": "muay_thai",
        "bjj": "mma",
        "wrestler": "mma",
        "grappler": "mma",
        "karate": "kickboxing"
    }
    raw_tech_style = fighting_style_technical.strip().lower()
    mapped_format = style_map.get(raw_tech_style, "mma")
    tactical_styles = normalize_list(fighting_style_tactical)
    if stance.strip().lower() == "hybrid" and "hybrid" not in tactical_styles:
        tactical_styles.append("hybrid")

    weight_val = float(weight) if weight.replace('.', '', 1).isdigit() else 0.0
    target_val = float(target_weight) if target_weight.replace('.', '', 1).isdigit() else 0.0
    weight_cut_risk_flag = weight_val - target_val >= 0.05 * target_val if target_val else False
    weight_cut_pct_val = round((weight_val - target_val) / target_val * 100, 1) if target_val else 0.0
    mental_block_class = classify_mental_block(mental_block or "")

    camp_len = weeks_out if isinstance(weeks_out, int) else 8
    phase_weeks = calculate_phase_weeks(
        camp_len,
        mapped_format,
        tactical_styles,
        status,
        fatigue,
        weight_cut_risk_flag,
        mental_block_class,
        weight_cut_pct_val,
    )

    # Core context
    training_context = {
        "fatigue": fatigue.lower(),
        "training_frequency": training_frequency,
        "days_available": len(training_days),
        "training_days": training_days,
        "injuries": normalize_list(injuries),
        "style_technical": raw_tech_style,
        "style_tactical": tactical_styles,
        "weaknesses": [
            tag
            for item in normalize_list(weak_areas)
            for tag in WEAKNESS_NORMALIZER.get(item.lower(), [item.lower()])
        ],
        "equipment": normalize_equipment_list(equipment_access),
        "weight_cut_risk": weight_cut_risk_flag,
        "weight_cut_pct": weight_cut_pct_val,
        "fight_format": mapped_format,
        "training_split": allocate_sessions(training_frequency),
        "key_goals": [GOAL_NORMALIZER.get(g.strip(), g.strip()).lower() for g in key_goals.split(",") if g.strip()],
        "training_preference": training_preference.strip().lower() if training_preference else "",
        "mental_block": mental_block_class,
        "age": int(age) if age.isdigit() else 0,
        "weight": float(weight) if weight.replace('.', '', 1).isdigit() else 0.0,
        "prev_exercises": [],
        "phase_weeks": phase_weeks,
    }

    # Module generation
    phase_mindset_cues = get_phase_mindset_cues(training_context["mental_block"])

    # === Strength blocks per phase with repeat filtering ===
    strength_blocks = []
    gpp_ex_names = []
    spp_ex_names = []
    gpp_block = None
    spp_block = None
    taper_block = None

    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        gpp_flags = {**training_context, "phase": "GPP"}
        gpp_block = generate_strength_block(
            flags=gpp_flags,
            weaknesses=training_context["weaknesses"],
            mindset_cue=phase_mindset_cues.get("GPP"),
        )
        gpp_ex_names = [ex["name"] for ex in gpp_block["exercises"]]
        strength_blocks.append(gpp_block["block"])

    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        spp_flags = {**training_context, "phase": "SPP", "prev_exercises": gpp_ex_names}
        spp_block = generate_strength_block(
            flags=spp_flags,
            weaknesses=training_context["weaknesses"],
            mindset_cue=phase_mindset_cues.get("SPP"),
        )
        spp_ex_names = [ex["name"] for ex in spp_block["exercises"]]
        strength_blocks.append(spp_block["block"])

    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        taper_flags = {**training_context, "phase": "TAPER", "prev_exercises": spp_ex_names}
        taper_block = generate_strength_block(
            flags=taper_flags,
            weaknesses=training_context["weaknesses"],
            mindset_cue=phase_mindset_cues.get("TAPER"),
        )
        strength_blocks.append(taper_block["block"])

    strength_block = "\n\n".join(strength_blocks)

    # Generate conditioning blocks per phase
    gpp_cond_block = ""
    spp_cond_block = ""
    taper_cond_block = ""

    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        gpp_cond_block, _ = generate_conditioning_block({**training_context, "phase": "GPP"})

    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        spp_cond_block, _ = generate_conditioning_block({**training_context, "phase": "SPP"})

    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        taper_cond_block, _ = generate_conditioning_block({**training_context, "phase": "TAPER"})

    gpp_rehab_block = ""
    spp_rehab_block = ""
    taper_rehab_block = ""
    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        gpp_rehab_block = generate_rehab_protocols(
            injury_string=injuries,
            exercise_data=exercise_bank,
            current_phase="GPP",
        )
        if gpp_rehab_block.strip().startswith("**Red Flag Detected**"):
            spp_rehab_block = gpp_rehab_block
            taper_rehab_block = gpp_rehab_block
    if not gpp_rehab_block.strip().startswith("**Red Flag Detected**"):
        if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
            spp_rehab_block = generate_rehab_protocols(
                injury_string=injuries,
                exercise_data=exercise_bank,
                current_phase="SPP",
            )
        if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
            taper_rehab_block = generate_rehab_protocols(
                injury_string=injuries,
                exercise_data=exercise_bank,
                current_phase="TAPER",
            )
    current_phase = next(
        (p for p in ["GPP", "SPP", "TAPER"] if phase_weeks[p] > 0 or phase_weeks["days"][p] >= 1),
        "GPP",
    )
    recovery_block = generate_recovery_block({**training_context, "phase": current_phase})
    nutrition_block = generate_nutrition_block(flags={**training_context, "phase": current_phase})


# Mental Block Strategy Injection Per Phase
    def build_mindset_prompt(phase_name: str):
        blocks = training_context.get("mental_block", ["generic"])
        if isinstance(blocks, str):
            blocks = [blocks]

        if blocks[0].lower() != "generic":
            return get_mindset_by_phase(phase_name, training_context)
        else:
            return get_mindset_by_phase(phase_name, {"mental_block": ["generic"]})

    gpp_mindset = build_mindset_prompt("GPP")
    spp_mindset = build_mindset_prompt("SPP")
    taper_mindset = build_mindset_prompt("TAPER")

    rehab_sections = ["## REHAB PROTOCOLS"]
    if gpp_rehab_block:
        rehab_sections += ["### GPP", gpp_rehab_block.strip(), ""]
    if spp_rehab_block:
        rehab_sections += ["### SPP", spp_rehab_block.strip(), ""]
    if taper_rehab_block:
        rehab_sections += ["### TAPER", taper_rehab_block.strip(), ""]

    fight_plan_lines = ["# FIGHT CAMP PLAN"]
    phase_num = 1

    if phase_weeks["GPP"] > 0 or phase_weeks["days"]["GPP"] >= 1:
        fight_plan_lines += [
            f"## PHASE {phase_num}: GENERAL PREPARATION PHASE (GPP) – {phase_weeks['GPP']} WEEKS ({phase_weeks['days']['GPP']} DAYS)",
            "",
            "### Mindset Focus",
            gpp_mindset,
            "",
            "### Strength & Power",
            gpp_block["block"] if gpp_block else "",
            "",
            "### Conditioning",
            gpp_cond_block,
            "",
        ]
        phase_num += 1

    if phase_weeks["SPP"] > 0 or phase_weeks["days"]["SPP"] >= 1:
        fight_plan_lines += [
            f"## PHASE {phase_num}: SPECIFIC PREPARATION PHASE (SPP) – {phase_weeks['SPP']} WEEKS ({phase_weeks['days']['SPP']} DAYS)",
            "",
            "### Mindset Focus",
            spp_mindset,
            "",
            "### Strength & Power",
            spp_block["block"] if spp_block else "",
            "",
            "### Conditioning",
            spp_cond_block,
            "",
        ]
        phase_num += 1

    if phase_weeks["TAPER"] > 0 or phase_weeks["days"]["TAPER"] >= 1:
        fight_plan_lines += [
            f"## PHASE {phase_num}: TAPER – {phase_weeks['TAPER']} WEEKS ({phase_weeks['days']['TAPER']} DAYS)",
            "",
            "### Mindset Focus",
            taper_mindset,
            "",
            "### Strength & Power",
            taper_block["block"] if taper_block else "",
            "",
            "### Conditioning",
            taper_cond_block,
            "",
        ]

    fight_plan_lines += [
        "## NUTRITION",
        nutrition_block,
        "",
        "## RECOVERY",
        recovery_block,
        "",
    ] + rehab_sections + [
        "",
        "## MINDSET OVERVIEW",
        f"Primary Block(s): {', '.join(training_context['mental_block']).title()}",
        "",
        "### Sparring & Conditioning Adjustments",
        "",
        "| Scenario | Adjustment |",
        "| --- | --- |",
        "| Technical sparring today | Keep S&C but **cut volume by 30%**. |",
        "| No sparring this week | Add an **extra glycolytic conditioning session** (e.g., 5x3min bag rounds). |",
        "",
        "---",
        "",
        "### **5. Nutrition Adjustments for Unknown Sparring Load**",
        "- **On Expected Hard Sparring Days:**",
        "  - Increase intra-workout carbs (e.g., 30g HBCD during session).",
        "  - Post-session: 1.2g/kg carbs + 0.4g/kg protein within 30 mins.",
        "- **If Sparring Was Unexpectedly Hard:**",
        "  - Add 500mg sodium + 20oz electrolyte drink immediately.",
        "",
        "## ATHLETE PROFILE",
        f"- Name: {full_name}",
        f"- Age: {age}",
        f"- Weight: {weight}kg",
        f"- Target Weight: {target_weight}kg",
        f"- Height: {height}cm",
        f"- Technical Style: {fighting_style_technical}",
        f"- Tactical Style: {fighting_style_tactical}",
        f"- Stance: {stance}",
        f"- Status: {status}",
        f"- Record: {record}",
        f"- Fight Format: {rounds_format}",
        f"- Fight Date: {next_fight_date}",
        f"- Weeks Out: {weeks_out}",
        f"- Phase Weeks: {phase_weeks['GPP']} GPP / {phase_weeks['SPP']} SPP / {phase_weeks['TAPER']} Taper",
        f"- Phase Days: {phase_weeks['days']['GPP']} GPP / {phase_weeks['days']['SPP']} SPP / {phase_weeks['days']['TAPER']} Taper",
        f"- Fatigue Level: {fatigue}",
        f"- Injuries: {injuries}",
        f"- Training Availability: {available_days}",
        f"- Weaknesses: {weak_areas}",
        f"- Key Goals: {key_goals}",
        f"- Mindset Challenges: {', '.join(training_context['mental_block'])}",
        f"- Notes: {notes}",
    ]
     
    fight_plan_text = "\n".join(fight_plan_lines)

    full_plan = fight_plan_text
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


def main():
    data_file = Path("test_data.json").resolve()
    if not data_file.exists():
        raise FileNotFoundError(f"Test data file not found: {data_file}")
    with open(data_file, "r") as f:
        data = json.load(f)
    result = asyncio.run(generate_plan(data))
    print("\nPlan link:", result.get("doc_link"))


if __name__ == "__main__":
    main()
