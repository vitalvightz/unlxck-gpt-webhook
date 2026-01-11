"""
Convert mental training plans to clean PDFs using FPDF.

The plan text is generated from drill scores and then cleaned of emoji
and smart punctuation so the PDF is ASCII-only. The file is uploaded to
Supabase Storage for public access.

Input: parsed form fields (already structured)
Output: Supabase public PDF URL
"""

import os
import json
import tempfile
import mimetypes
from urllib import request
from urllib.error import HTTPError

try:
    from fpdf import FPDF  # type: ignore
except Exception:  # pragma: no cover - optional dependency for tests
    FPDF = None

try:
    import pdfkit  # Requires wkhtmltopdf installed
except Exception:  # pragma: no cover - optional dependency for tests
    pdfkit = None
from mental.program import parse_mindcode_form
from mental.tags import map_tags
from mental.scoring import score_drills
from mental.contradictions import detect_contradictions
from mental.tag_labels import humanize_list


DRILLS_PATH = os.path.join(os.path.dirname(__file__), "Drills_bank.json")
with open(DRILLS_PATH) as f:
    _raw_bank = json.load(f)

# Support additional drill lists like "boxing_spp_drills" by merging them
DRILL_BANK = list(_raw_bank.get("drills", []))
for k, v in _raw_bank.items():
    if k != "drills" and k.endswith("_drills") and isinstance(v, list):
        DRILL_BANK.extend(v)

for d in DRILL_BANK:
    d["sports"] = [s.lower() for s in d.get("sports", [])]

# Map of Unicode punctuation and emoji to ASCII-only equivalents
_CHAR_MAP = {
    ord("–"): "-",
    ord("—"): "-",
    ord("’"): "'",
    ord("‘"): "'",
    ord("“"): '"',
    ord("”"): '"',
    ord("→"): "->",
    ord("…"): "...",
    ord("•"): "-",
    ord("🧠"): "",
    ord("📌"): "",
    ord("🎯"): "",
    ord("⚙"): "",
    ord("🔥"): "",
    ord("🧩"): "",
    ord("🗣"): "",
    ord("🔗"): "",
    ord("🔖"): "",
    ord("🔷"): "",
    ord("⚠"): "",
    ord("️"): "",
}

def _clean_text(text: str) -> str:
    """Return ASCII-only text with emoji removed."""
    cleaned = text.translate(_CHAR_MAP)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    return cleaned

def format_drill_html(drill, phase):
    traits = ", ".join(humanize_list(drill.get("raw_traits", [])))
    themes = ", ".join(humanize_list(drill.get("theme_tags", [])))

    sidebar = ""
    if drill.get("coach_sidebar"):
        if isinstance(drill["coach_sidebar"], list):
            sidebar = "<br>".join(
                f"&ndash; {_clean_text(s)}" for s in drill["coach_sidebar"]
            )
        else:
            sidebar = f"&ndash; {_clean_text(drill['coach_sidebar'])}"

    fields = [
        f"<h3 class='drill-name'>{phase.upper()}: {_clean_text(drill['name'])}</h3>",
        f"<p class='field'><span class='field-label'>Description:</span> {_clean_text(drill['description'])}</p>",
        f"<p class='field'><span class='field-label'>Cue:</span> <b>{_clean_text(drill['cue'])}</b></p>",
        f"<p class='field'><span class='field-label'>Modalities:</span> {', '.join(_clean_text(m) for m in drill['modalities'])}</p>",
        f"<p class='field'><span class='field-label'>Intensity:</span> {_clean_text(drill['intensity'])} | Sports: {', '.join(_clean_text(s) for s in drill['sports'])}</p>",
        f"<p class='field'><span class='field-label'>Notes:</span> {_clean_text(drill['notes'])}</p>",
    ]

    if drill.get("why_this_works"):
        fields.append(
            f"<p class='field'><span class='field-label'>Why This Works:</span> {_clean_text(drill['why_this_works'])}</p>"
        )
    if sidebar:
        fields.append(f"<p class='field'><span class='field-label'>Coach Sidebar:</span> {sidebar}</p>")
    if drill.get("video_url"):
        fields.append(f"<p class='field'><span class='field-label'>Tutorial:</span> {_clean_text(drill['video_url'])}</p>")

    fields.append(
        f"<p class='field'><span class='field-label'>Tags:</span> Traits -> {_clean_text(traits)} | Themes -> {_clean_text(themes)}</p>"
    )

    return "\n".join(fields) + "<hr>"

def build_plan_html(drills_by_phase, athlete):
    blocks = [
        f"<h1 class='title'>MENTAL PERFORMANCE PLAN: {_clean_text(athlete['full_name'])}</h1>",
        (
            f"<p class='athlete-info'>Sport: {_clean_text(athlete['sport'])} | "
            f"Style/Position: {_clean_text(athlete['position_style'])} | "
            f"Phase: {_clean_text(athlete['mental_phase'])}</p>"
        ),
    ]

    contradictions = detect_contradictions(set(athlete.get("all_tags", [])))
    if contradictions:
        blocks.append("<h2 class='coach-header'>COACH REVIEW FLAGS</h2>")
        blocks.append(
            "<ul class='coach-flags'>" + "".join(f"<li>{_clean_text(c)}</li>" for c in contradictions) + "</ul>"
        )

    phase_order = ["GPP", "SPP", "TAPER"]
    start_phase = athlete.get("mental_phase", "GPP").upper()
    try:
        start_idx = phase_order.index(start_phase)
    except ValueError:
        start_idx = 0

    for phase in phase_order[start_idx:]:
        drills = drills_by_phase.get(phase)
        if not drills:
            drills = drills_by_phase.get("UNIVERSAL", [])
        if not drills:
            continue
        blocks.append(f"<h2 class='phase-header {phase.lower()}'>{phase} DRILLS</h2>")
        for drill in drills:
            blocks.append(format_drill_html(drill, phase))

    style = """
        <style>
          body {
            font-family: Arial, sans-serif;
            padding: 40px;
            line-height: 2;
            color: #000;
          }

          h1, h2, h3, p, li {
            line-height: 2;
            margin-top: 8px;
            margin-bottom: 8px;
          }

          h1.title { font-size: 18pt; font-weight: bold; }
          p.athlete-info { font-size: 12pt; }
          h2.coach-header { font-size: 14pt; font-weight: bold; color: #cc0000; }
          ul.coach-flags { font-size: 12pt; margin-left: 20pt; padding-left: 20px; }
          h2.phase-header { font-size: 16pt; font-weight: bold; }
          h2.phase-header.gpp { color: #0077cc; }
          h2.phase-header.spp { color: #cc7700; }
          h2.phase-header.taper { color: #228B22; }
          h3.drill-name { font-size: 13pt; font-weight: bold; color: #000; }
          p.field { font-size: 12pt; }
          span.field-label { font-weight: bold; }
          hr { border: none; border-top: 1px solid #ccc; margin: 15pt 0; }
        </style>
    """

    return f"<html><head>{style}</head><body>{''.join(blocks)}</body></html>"

def build_plan_output(drills_by_phase, athlete):
    """Return plain-text plan for testing and logging."""
    lines = [
        f"MENTAL PERFORMANCE PLAN -- {athlete.get('full_name', '')}",
        f"Sport: {athlete.get('sport', '')} | Style/Position: {athlete.get('position_style', '')} | Phase: {athlete.get('mental_phase', '')}",
    ]

    contradictions = detect_contradictions(set(athlete.get("all_tags", [])))
    if contradictions:
        lines.append("COACH REVIEW FLAGS")
        lines.extend(f"- {c}" for c in contradictions)

    phase_order = ["GPP", "SPP", "TAPER"]
    start_phase = athlete.get("mental_phase", "GPP").upper()
    try:
        start_idx = phase_order.index(start_phase)
    except ValueError:
        start_idx = 0

    for ph in phase_order[start_idx:]:
        drills = drills_by_phase.get(ph)
        if not drills:
            drills = drills_by_phase.get("UNIVERSAL", [])
        if not drills:
            continue
        lines.append(f"{ph} DRILLS")
        for d in drills:
            traits = ", ".join(humanize_list(d.get("raw_traits", [])))
            themes = ", ".join(humanize_list(d.get("theme_tags", [])))
            lines.append(f"{d['name']}: {d['description']}")
            if traits or themes:
                lines.append(f"Tags: Traits → {traits} | Themes → {themes}")
            lines.append("")

    return "\n".join(lines)


def format_drill_block(drill, phase):
    """Return cleaned multi-line text for a single drill."""
    lines = [
        f"{phase.upper()}: {drill['name']}",
        f"Description: {drill['description']}",
        f"Cue: {drill['cue']}",
        f"Modalities: {', '.join(drill['modalities'])}",
        f"Intensity: {drill['intensity']} | Sports: {', '.join(drill['sports'])}",
        f"Notes: {drill['notes']}",
    ]
    if drill.get("why_this_works"):
        lines.append(f"Why This Works: {drill['why_this_works']}")
    if drill.get("coach_sidebar"):
        sidebar = drill["coach_sidebar"]
        if isinstance(sidebar, list):
            lines.append("Coach Sidebar:")
            lines.extend(f"- {s}" for s in sidebar)
        else:
            lines.append(f"Coach Sidebar: {sidebar}")
    if drill.get("video_url"):
        lines.append(f"Tutorial: {drill['video_url']}")
    traits = ", ".join(humanize_list(drill.get("raw_traits", [])))
    themes = ", ".join(humanize_list(drill.get("theme_tags", [])))
    lines.append(f"Tags: Traits -> {traits} | Themes -> {themes}")
    return "\n".join(_clean_text(l) for l in lines)


def build_pdf_text(drills_by_phase, athlete):
    """Return full plan text cleaned for PDF output."""
    lines = [
        _clean_text(f"MENTAL PERFORMANCE PLAN -- {athlete.get('full_name', '')}"),
        _clean_text(
            f"Sport: {athlete.get('sport', '')} | Style/Position: {athlete.get('position_style', '')} | Phase: {athlete.get('mental_phase', '')}"
        ),
    ]

    contradictions = detect_contradictions(set(athlete.get("all_tags", [])))
    if contradictions:
        lines.append("COACH REVIEW FLAGS")
        lines.extend(_clean_text(f"- {c}") for c in contradictions)

    phase_order = ["GPP", "SPP", "TAPER"]
    start_phase = athlete.get("mental_phase", "GPP").upper()
    try:
        start_idx = phase_order.index(start_phase)
    except ValueError:
        start_idx = 0

    for ph in phase_order[start_idx:]:
        drills = drills_by_phase.get(ph)
        if not drills:
            drills = drills_by_phase.get("UNIVERSAL", [])
        if not drills:
            continue
        lines.append(f"{ph} DRILLS")
        for d in drills:
            lines.append(format_drill_block(d, ph))
            lines.append("")

    return "\n".join(lines)


def _export_pdf(text: str, full_name: str) -> str:
    """Render cleaned text to PDF using FPDF."""
    safe = full_name.replace(" ", "_") or "plan"
    path = os.path.join(tempfile.gettempdir(), f"{safe}_mental_plan.pdf")
    if FPDF is None:
        raise RuntimeError("fpdf is required for PDF export")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    for line in text.splitlines():
        pdf.multi_cell(0, 10, line)
    pdf.output(path)
    return path

def _export_pdf_from_html(html, full_name):
    safe = full_name.replace(" ", "_") or "plan"
    path = os.path.join(tempfile.gettempdir(), f"{safe}_mental_plan.pdf")
    if pdfkit is None:
        raise RuntimeError("pdfkit is required for PDF export")
    pdfkit.from_string(html, path)
    return path

def _upload_to_supabase(pdf_path):
    url = os.environ.get("SUPABASE_URL")
    if url:
        url = url.strip()
        # Guard against accidentally passing "SUPABASE_URL=https://..." as the value
        if url.lower().startswith("supabase_url="):
            url = url.split("=", 1)[1].strip()
        # Remove trailing slash if present
        url = url.rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
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

    # Use the Supabase URL directly so the full public link prints in logs.
    # GitHub no longer masks this variable since it's an Actions variable.
    public_base = url
    return f"{public_base}/storage/v1/object/public/mental-plans/{filename}"

def bucket_drills_by_phase(drills):
    """Return drills grouped by phase with UNIVERSAL kept separate."""
    buckets = {"GPP": [], "SPP": [], "TAPER": [], "UNIVERSAL": []}
    for d in drills:
        phase = d.get("phase", "GPP").upper()
        if phase not in buckets:
            phase = "GPP"
        buckets[phase].append(d)
    return buckets


def handler(form_fields: dict):
    parsed = parse_mindcode_form(form_fields)
    tags = map_tags(parsed)
    drills = score_drills(DRILL_BANK, tags, parsed.get("sport", ""), parsed.get("mental_phase", ""))

    drills_by_phase = bucket_drills_by_phase(drills)

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
    if pdfkit is not None:
        path = _export_pdf_from_html(html, athlete["full_name"])
    else:
        pdf_text = build_pdf_text(top, athlete)
        path = _export_pdf(pdf_text, athlete["full_name"])
    return _upload_to_supabase(path)


if __name__ == "__main__":
    import sys

    with open(sys.argv[1]) as f:
        payload = json.load(f)

    link = handler(payload)
    # Print the public PDF URL so it appears in CI logs and can be clicked.
    print(link, flush=True)
