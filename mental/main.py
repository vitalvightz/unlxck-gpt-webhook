import json
import os
import base64
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from mental.program import parse_mindcode_form
from mental.tags import map_tags
from mental.scoring import score_drills

# Load drill bank
with open("Drills_bank.json", "r") as f:
    DRILL_BANK = json.load(f)["drills"]

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
    if drill.get("video_url"):
        block += f"\n\n🔗 Tutorial:\n{drill['video_url']}"
    block += f"\n\n🔖 Tags:\nTraits → {', '.join(drill['raw_traits'])}  \nThemes → {', '.join(drill['theme_tags'])}\n"
    return block

def build_plan_output(drills_by_phase, athlete_info):
    lines = [f"# 🧠 MENTAL PERFORMANCE PLAN – {athlete_info['full_name']}\n"]
    lines.append(f"**Sport:** {athlete_info['sport']} | **Style/Position:** {athlete_info['position_style']} | **Phase:** {athlete_info['mental_phase']}\n")
    for phase in ["GPP", "SPP", "TAPER"]:
        if drills_by_phase.get(phase):
            lines.append(f"---\n## 🔷 {phase} DRILLS\n")
            for d in drills_by_phase[phase]:
                lines.append(format_drill_block(d, phase))
    return "\n\n".join(lines)

def load_google_docs_service(creds_b64: str):
    decoded = base64.b64decode(creds_b64)
    with open("mental_google_creds.json", "wb") as f:
        f.write(decoded)
    creds = Credentials.from_service_account_file("mental_google_creds.json", scopes=["https://www.googleapis.com/auth/documents"])
    return build("docs", "v1", credentials=creds)

def handler(form_fields, creds_b64):
    parsed = parse_mindcode_form(form_fields)
    tags = map_tags(parsed)
    sport = parsed["sport"].strip().lower()
    phase = parsed["mental_phase"]

    # Score drills
    scored = score_drills(DRILL_BANK, tags, sport, phase)
    drills_by_phase = {"GPP": [], "SPP": [], "TAPER": []}

    if phase == "GPP":
        phases = ["GPP", "SPP", "TAPER"]
    elif phase == "SPP":
        phases = ["SPP", "TAPER"]
    elif phase == "TAPER":
        phases = ["TAPER"]
    else:
        phases = []

    for p in phases:
        filtered = [d for d in scored if d["phase"].lower() == p.lower()]
        drills_by_phase[p] = filtered[:5]

    # Build output
    doc_text = build_plan_output(drills_by_phase, parsed)

    # Create doc
    service = load_google_docs_service(creds_b64)
    doc = service.documents().create(body={"title": f"{parsed['full_name']} – MENTAL PERFORMANCE PLAN"}).execute()
    doc_id = doc.get("documentId")

    service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": doc_text}}]}
    ).execute()

    return f"https://docs.google.com/document/d/{doc_id}"

# Test locally with payload and env var
if __name__ == "__main__":
    with open("test_payload.json", "r") as f:
        fields = json.load(f)
    link = handler(fields, os.environ["GOOGLE_CREDS_B64"])
    print("Saved to:", link)