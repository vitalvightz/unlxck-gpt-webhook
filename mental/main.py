import json, os, base64
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from mental.program import parse_mindcode_form
from mental.tags import map_tags
from mental.scoring import score_drills
from mental.contradictions import detect_contradictions
from mental.tag_labels import humanize_list

DRILLS_PATH = os.path.join(os.path.dirname(__file__), "Drills_bank.json")
with open(DRILLS_PATH, "r") as f:
    DRILL_BANK = json.load(f)["drills"]
for d in DRILL_BANK:
    d["sports"] = [s.lower() for s in d.get("sports", [])]

def format_drill_block(drill, phase):
    block = f"""🧠 {phase.upper()}: {drill['name']}

📌 Description:
{drill['description']}

🎯 Cue:
{drill['cue']}

⚙️ Modalities:
{", ".join(drill['modalities'])}

🔥 Intensity:
{drill['intensity']} | Sports: {", ".join(drill['sports'])}

🧩 Notes:
{drill['notes']}"""
    if drill.get("why_this_works"):
        block += f"\n\n🧠 Why This Works:\n{drill['why_this_works']}"
    if drill.get("coach_sidebar"):
        sidebar = "\n".join([f"– {s}" for s in drill["coach_sidebar"]]) if isinstance(drill["coach_sidebar"], list) else f"– {drill['coach_sidebar']}"
        block += f"\n\n🗣️ Coach Sidebar:\n{sidebar}"
    if drill.get("video_url"):
        block += f"\n\n🔗 Tutorial:\n{drill['video_url']}"
    trait_labels = humanize_list(drill.get('raw_traits', []))
    theme_labels = humanize_list(drill.get('theme_tags', []))
    block += (
        f"\n\n🔖 Tags:\n"
        f"Traits → {', '.join(trait_labels)}  \n"
        f"Themes → {', '.join(theme_labels)}\n"
    )
    return block

def build_plan_output(drills_by_phase, athlete_info):
    lines = [f"# 🧠 MENTAL PERFORMANCE PLAN – {athlete_info['full_name']}\n"]
    lines.append(
        f"**Sport:** {athlete_info['sport']} | **Style/Position:** {athlete_info['position_style']} | **Phase:** {athlete_info['mental_phase']}\n"
    )
    contradictions = detect_contradictions(set(athlete_info.get("all_tags", [])))
    if contradictions:
        lines.append("⚠️ **COACH REVIEW FLAGS**")
        for note in contradictions:
            lines.append(f"- {note}")
        lines.append("")
    for phase in ["GPP", "SPP", "TAPER"]:
        if drills_by_phase.get(phase):
            lines.append(f"---\n## 🔷 {phase} DRILLS\n")
            for d in drills_by_phase[phase]:
                lines.append(format_drill_block(d, phase))
    return "\n\n".join(lines)

def load_google_services(creds_b64: str, debug: bool = False):
    decoded = base64.b64decode(creds_b64)
    with open("mental_google_creds.json", "wb") as f:
        f.write(decoded)
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file("mental_google_creds.json", scopes=scopes)
    if debug:
        print(f"[DEBUG] Authenticated as: {creds.service_account_email}")
        print(f"[DEBUG] Using scopes: {', '.join(scopes)}")
    return build("docs", "v1", credentials=creds), build("drive", "v3", credentials=creds)

def get_folder_id(drive_service, folder_name):
    response = drive_service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'",
        spaces="drive",
    ).execute()
    folders = response.get("files", [])
    return folders[0]["id"] if folders else None

def handler(form_fields, creds_b64, *, debug=False):
    parsed = parse_mindcode_form(form_fields)
    full_name = parsed.get("full_name", "").strip()
    sport = parsed.get("sport", "").strip().lower()
    position_style = parsed.get("position_style", "").strip()
    phase = parsed.get("mental_phase", "").strip().upper()
    if debug:
        print(f"[DEBUG] Athlete: {full_name}, sport={sport}, style={position_style}, phase={phase}")
    if not full_name or not sport or not phase:
        raise ValueError("❌ Missing required athlete info: name, sport, or phase")
    if phase not in ["GPP", "SPP", "TAPER"]:
        print(f"⚠️ Invalid phase: '{phase}' → defaulting to GPP")
        phase = "GPP"
    tags = map_tags(parsed)
    if debug:
        print(f"[DEBUG] Generated tags: {tags}")
    scored = score_drills(DRILL_BANK, tags, sport, phase)

    all_tags = []
    for key, val in tags.items():
        if isinstance(val, list):
            all_tags.extend([f"{key}:{v}" for v in val])
        else:
            all_tags.append(f"{key}:{val}")

    drills_by_phase = {p: [] for p in ["GPP", "SPP", "TAPER"]}
    phases = ["GPP", "SPP", "TAPER"] if phase == "GPP" else ["SPP", "TAPER"] if phase == "SPP" else ["TAPER"]
    if debug:
        print(f"[DEBUG] Evaluating phases: {phases}")
    for p in phases:
        drills = [d for d in scored if d["phase"].upper() == p]
        drills_by_phase[p] = drills[:5]
        if debug:
            print(f"[DEBUG] {p} drills → {len(drills_by_phase[p])} selected")

    doc_text = (
        f"# ❌ No drills matched for {full_name} in phase {phase}\n\nCheck inputs or adjust your form selections."
        if not any(drills_by_phase.values())
        else build_plan_output(
            drills_by_phase,
            {
                "full_name": full_name,
                "sport": sport,
                "position_style": position_style,
                "mental_phase": phase,
                "all_tags": all_tags,
            },
        )
    )

    docs_service, drive_service = load_google_services(creds_b64, debug=debug)

    if debug:
        print("[DEBUG] Attempting to create document via Docs API…")
    try:
        doc = docs_service.documents().create(
            body={"title": f"{full_name} – MENTAL PERFORMANCE PLAN"}
        ).execute()
    except Exception as e:
        print(f"[DEBUG] Failed to create document: {e}")
        raise

    doc_id = doc.get("documentId")
    if debug:
        print(f"[DEBUG] Created document ID: {doc_id}")

    # Step 1: Grant editor access to your Gmail (critical)
    try:
        drive_service.permissions().create(
            fileId=doc_id,
            body={
                "type": "user",
                "role": "writer",
                "emailAddress": "unlxckedmind@gmail.com",
            },
            fields="id",
        ).execute()
        if debug:
            print("[DEBUG] Granted Gmail editor access")
    except Exception as e:
        print(f"[DEBUG] Failed to set document permissions: {e}")

    folder_id = os.environ.get("TARGET_FOLDER_ID")
    if debug:
        if folder_id:
            print(f"[DEBUG] Using target folder: {folder_id}")
        else:
            print("[DEBUG] No TARGET_FOLDER_ID specified")
    if folder_id:
        try:
            drive_service.files().update(
                fileId=doc_id,
                addParents=folder_id,
            ).execute()
            if debug:
                print(f"[DEBUG] Moved to folder ID: {folder_id}")
        except Exception as e:
            print(f"[DEBUG] Failed to move document: {e}")

    try:
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": doc_text}}]}
        ).execute()
        if debug:
            print("[DEBUG] Uploaded doc content")
    except Exception as e:
        print(f"[DEBUG] Failed to upload document text: {e}")
        raise

    return f"https://docs.google.com/document/d/{doc_id}"

# Local test
if __name__ == "__main__":
    payload_path = os.path.join(os.path.dirname(__file__), "..", "tests", "test_payload.json")
    with open(payload_path, "r") as f:
        fields = json.load(f)
    creds_b64 = os.environ.get("GOOGLE_CREDS_B64")
    if not creds_b64:
        raise EnvironmentError("GOOGLE_CREDS_B64 not set")
    debug = os.environ.get("DEBUG", "0") == "1"
    link = handler(fields, creds_b64, debug=debug)
    print("Saved to:", link)