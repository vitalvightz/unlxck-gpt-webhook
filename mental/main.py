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
    for phase in ["GPP