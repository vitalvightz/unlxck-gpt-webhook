"""Generate mental training plans and export them as PDFs.

This module parses questionnaire responses, scores drills from the
``Drills_bank.json`` file and outputs a formatted plan.  The final
plan text is converted to a PDF using :mod:`fpdf` and uploaded to
Supabase Storage.

The ``handler`` function is the main entry point and returns the URL
to the uploaded PDF. ``build_plan_output`` is used by the test suite to
verify formatting and therefore kept separate from the export logic.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict, Iterable, List


from .contradictions import detect_contradictions
from .map_mindcode_tags import map_mindcode_tags
from .program import parse_mindcode_form
from .scoring import score_drills
from .tag_labels import human_label, humanize_list


_BANK_PATH = os.path.join(os.path.dirname(__file__), "Drills_bank.json")


def _load_bank() -> List[dict]:
    with open(_BANK_PATH) as f:
        data = json.load(f)
    return data.get("drills", [])


def _humanize_tags(tags: Iterable[str]) -> str:
    return ", ".join(humanize_list(list(tags)))


def format_drill_block(drill: dict, phase: str) -> str:
    """Return a formatted text block for a single drill."""

    block = (
        f"🧠 {phase.upper()}: {drill.get('name', '')}\n"
        f"📌 Description:\n{drill.get('description', '')}\n\n"
        f"🎯 Cue:\n{drill.get('cue', '')}\n\n"
        f"⚙️ Modalities:\n{', '.join(drill.get('modalities', []))}\n\n"
        f"🔥 Intensity:\n{drill.get('intensity', '')} | Sports: {', '.join(drill.get('sports', []))}\n\n"
        f"🧩 Notes:\n{drill.get('notes', '')}"
    )

    if drill.get("why_this_works"):
        block += f"\n\n🧠 Why This Works:\n{drill['why_this_works']}"

    if drill.get("coach_sidebar"):
        sidebar = drill["coach_sidebar"]
        if isinstance(sidebar, list):
            sidebar = "\n".join(f"– {s}" for s in sidebar)
        else:
            sidebar = f"– {sidebar}"
        block += f"\n\n🗣️ Coach Sidebar:\n{sidebar}"

    if drill.get("video_url"):
        block += f"\n\n🔗 Tutorial:\n{drill['video_url']}"

    trait_labels = humanize_list(drill.get('raw_traits', []))
    theme_labels = humanize_list(drill.get('theme_tags', []))
    block += (
        "\n\n🔖 Tags:\n"
        f"Traits → {', '.join(trait_labels)}  \n"
        f"Themes → {', '.join(theme_labels)}\n"
    )
    return block


def build_plan_output(drills: Dict[str, List[dict]], athlete: Dict) -> str:
    """Return a rich text training plan for ``athlete``.

    The output mirrors the original document-style format used when
    generating plans via Google Docs.  It is also used by the unit tests
    to verify tag humanization and contradiction injection.
    """

    lines: List[str] = []
    lines.append(
        f"# 🧠 MENTAL PERFORMANCE PLAN – {athlete.get('full_name', '').strip()}\n"
    )
    lines.append(
        f"**Sport:** {athlete.get('sport', '')} | **Style/Position:** {athlete.get('position_style', '')} | **Phase:** {athlete.get('mental_phase', '')}\n"
    )

    contradictions = detect_contradictions(set(athlete.get("all_tags", [])))
    if contradictions:
        lines.append("⚠️ **COACH REVIEW FLAGS**")
        for note in contradictions:
            lines.append(f"- {note}")
        lines.append("")

    for phase in ["GPP", "SPP", "TAPER"]:
        if drills.get(phase):
            lines.append(f"---\n## 🔷 {phase} DRILLS\n")
            for d in drills[phase]:
                lines.append(format_drill_block(d, phase))
    return "\n\n".join(lines)


_CHAR_MAP = {
    ord("–"): "-",
    ord("—"): "--",
    ord("’"): "'",
    ord("‘"): "'",
    ord("“"): '"',
    ord("”"): '"',
    ord("→"): "->",
}


def _export_pdf(doc_text: str, full_name: str) -> str:
    """Save ``doc_text`` to a PDF and return its absolute path."""

    # ``fpdf`` matches the expected API for orientation/unit/format arguments
    try:
        from fpdf import FPDF  # type: ignore
    except Exception as exc:  # pragma: no cover - environment missing fpdf
        raise RuntimeError("PDF export requires the `fpdf` package") from exc

    safe_name = full_name.replace(" ", "_") or "plan"
    filename = f"{safe_name}_mental_plan.pdf"
    pdf_path = os.path.join(tempfile.gettempdir(), filename)

    clean_text = doc_text.translate(_CHAR_MAP)

    pdf = FPDF("P", "mm", "A4")
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in clean_text.splitlines():
        pdf.multi_cell(0, 10, line)
    pdf.output(pdf_path)

    return pdf_path


def _upload_to_supabase(pdf_path: str) -> str:
    """Upload ``pdf_path`` to Supabase Storage and return its public URL."""

    import mimetypes
    from urllib import request
    from urllib.error import HTTPError
    import os

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

    filename = os.path.basename(pdf_path)
    bucket = "mental-plans"
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{filename}"

    with open(pdf_path, "rb") as f:
        data = f.read()

    content_type = mimetypes.guess_type(filename)[0] or "application/pdf"

    req = request.Request(upload_url, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {supabase_key}")
    req.add_header("Content-Type", content_type)
    req.add_header("Content-Length", str(len(data)))

    try:
        with request.urlopen(req) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed upload with status {resp.status}")
    except HTTPError as exc:
        raise RuntimeError("Supabase upload failed") from exc

    return f"{supabase_url}/storage/v1/object/public/{bucket}/{filename}"


def handler(event: Dict | None = None) -> str:
    """Process ``event`` data and return a public URL to the PDF."""

    if event is None:
        raise ValueError("event payload required")

    form_fields = event.get("form", event)
    form_data = parse_mindcode_form(form_fields)
    tags_map = map_mindcode_tags(form_data)

    all_drills = _load_bank()
    scored = score_drills(all_drills, tags_map, form_data.get("sport", ""), form_data.get("mental_phase", ""))

    buckets: Dict[str, List[dict]] = {}
    for d in scored:
        phase = d.get("phase", "UNIVERSAL").upper()
        buckets.setdefault(phase, []).append(d)

    for lst in buckets.values():
        lst.sort(key=lambda x: x["score"], reverse=True)

    # Keep top 3 drills per phase
    top_drills = {phase: lst[:3] for phase, lst in buckets.items()}

    athlete = {
        "full_name": form_data.get("full_name", ""),
        "sport": form_data.get("sport", ""),
        "position_style": form_data.get("position_style", ""),
        "mental_phase": form_data.get("mental_phase", ""),
    }

    all_tags = []
    for key, value in tags_map.items():
        if isinstance(value, list):
            all_tags.extend(f"{key}:{v}" for v in value)
        else:
            all_tags.append(f"{key}:{value}")
    athlete["all_tags"] = all_tags

    doc_text = build_plan_output(top_drills, athlete)
    pdf_path = _export_pdf(doc_text, athlete["full_name"])
    return _upload_to_supabase(pdf_path)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m mental.main <payload.json>")

    with open(sys.argv[1]) as f:
        payload = json.load(f)

    path = handler(payload)
    print(path)

