"""
Convert mental training plans to rich-styled PDFs using HTML + emojis.

Takes the existing `build_plan_output()` logic and renders it into an
HTML template using full formatting (emojis, bold, line breaks, spacing).
The HTML is converted to PDF via `pdfkit` (which wraps wkhtmltopdf) and
uploaded to Supabase Storage. Retains the full Unlxck aesthetic.

Input: parsed form fields (already structured)
Output: Supabase public PDF URL
"""

import os
import json
import tempfile
import mimetypes
from urllib import request
from urllib.error import HTTPError

import pdfkit  # Requires wkhtmltopdf installed
from mental.program import parse_mindcode_form
from mental.tags import map_tags
from mental.scoring import score_drills
from mental.contradictions import detect_contradictions
from mental.tag_labels import humanize_list


DRILLS_PATH = os.path.join(os.path.dirname(__file__), "Drills_bank.json")
with open(DRILLS_PATH) as f:
    DRILL_BANK = json.load(f)["drills"]
for d in DRILL_BANK:
    d["sports"] = [s.lower() for s in d.get("sports", [])]

def format_drill_html(drill, phase):
    traits = ", ".join(humanize_list(drill.get("raw_traits", [])))
    themes = ", ".join(humanize_list(drill.get("theme_tags", [])))
    sidebar = ""
    if drill.get("coach_sidebar"):
        if isinstance(drill["coach_sidebar"], list):
            sidebar = "<br>".join(f"– {s}" for s in drill["coach_sidebar"])
        else:
            sidebar = f"– {drill['coach_sidebar']}"

    return f"""
    <div class="drill-block">
        <h3>🧠 {phase.upper()}: {drill['name']}</h3>
        <p><b>📌 Description:</b><br>{drill['description']}</p>
        <p><b>🎯 Cue:</b><br>{drill['cue']}</p>
        <p><b>⚙️ Modalities:</b><br>{', '.join(drill['modalities'])}</p>
        <p><b>🔥 Intensity:</b> {drill['intensity']} | Sports: {', '.join(drill['sports'])}</p>
        <p><b>🧩 Notes:</b><br>{drill['notes']}</p>
        {"<p><b>🧠 Why This Works:</b><br>" + drill["why_this_works"] + "</p>" if drill.get("why_this_works") else ""}
        {"<p><b>🗣️ Coach Sidebar:</b><br>" + sidebar + "</p>" if sidebar else ""}
        {"<p><b>🔗 Tutorial:</b><br>" + drill["video_url"] + "</p>" if drill.get("video_url") else ""}
        <p><b>🔖 Tags:</b><br>Traits → {traits}<br>Themes → {themes}</p>
    </div><hr>
    """

def build_plan_html(drills_by_phase, athlete):
    blocks = [f"<h1>🧠 MENTAL PERFORMANCE PLAN – {athlete['full_name']}</h1>"]
    blocks.append(f"<p><b>Sport:</b> {athlete['sport']} | <b>Style/Position:</b> {athlete['position_style']} | <b>Phase:</b> {athlete['mental_phase']}</p>")

    contradictions = detect_contradictions(set(athlete.get("all_tags", [])))
    if contradictions:
        blocks.append("<h3>⚠️ COACH REVIEW FLAGS</h3><ul>" + "".join(f"<li>{c}</li>" for c in contradictions) + "</ul>")

    for phase in ["GPP", "SPP", "TAPER"]:
        if drills_by_phase.get(phase):
            blocks.append(f"<h2>🔷 {phase} DRILLS</h2>")
            for drill in drills_by_phase[phase]:
                blocks.append(format_drill_html(drill, phase))

    return f"""
    <html><head>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 40px; }}
            h1 {{ color: #333; }}
            hr {{ border: 1px solid #ccc; margin: 30px 0; }}
            .drill-block {{ margin-bottom: 20px; }}
            p {{ margin: 5px 0 10px; }}
        </style>
    </head><body>
    {''.join(blocks)}
    </body></html>
    """

def _export_pdf_from_html(html, full_name):
    safe = full_name.replace(" ", "_") or "plan"
    path = os.path.join(tempfile.gettempdir(), f"{safe}_mental_plan.pdf")
    pdfkit.from_string(html, path)
    return path

def _upload_to_supabase(pdf_path):
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    if not url or not key:
        raise RuntimeError("Missing Supabase credentials")

    filename = os.path.basename(pdf_path)
    storage_path = f"{url}/storage/v1/object/mental-plans/{filename}"

    with open(pdf_path, "rb") as f:
        data = f.read()

    req = request.Request(storage_path, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", mimetypes.guess_type(filename)[0] or "application/pdf")
    req.add_header("Content-Length", str(len(data)))

    try:
        with request.urlopen(req) as r:
            if r.status != 200:
                raise RuntimeError("Upload failed")
    except HTTPError as e:
        raise RuntimeError("Supabase upload failed") from e

    public_base = os.getenv("SUPABASE_PUBLIC_URL", url)
    return f"{public_base}/storage/v1/object/public/mental-plans/{filename}"

def handler(form_fields: dict):
    parsed = parse_mindcode_form(form_fields)
    tags = map_tags(parsed)
    drills = score_drills(DRILL_BANK, tags, parsed.get("sport", ""), parsed.get("mental_phase", ""))

    drills_by_phase = {"GPP": [], "SPP": [], "TAPER": []}
    for d in drills:
        phase = d.get("phase", "GPP").upper()
        drills_by_phase[phase].append(d)

    for lst in drills_by_phase.values():
        lst.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Keep top 3 per phase
    top = {k: v[:3] for k, v in drills_by_phase.items()}

    all_tags = [f"{k}:{v}" for k, val in tags.items() for v in (val if isinstance(val, list) else [val])]
    athlete = {
        "full_name": parsed.get("full_name", ""),
        "sport": parsed.get("sport", ""),
        "position_style": parsed.get("position_style", ""),
        "mental_phase": parsed.get("mental_phase", ""),
        "all_tags": all_tags,
    }

    html = build_plan_html(top, athlete)
    path = _export_pdf_from_html(html, athlete["full_name"])
    return _upload_to_supabase(path)


if __name__ == "__main__":
    import sys

    with open(sys.argv[1]) as f:
        payload = json.load(f)

    link = handler(payload)
    print(link)
