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
from urllib import request, parse

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


def build_plan_output(drills: Dict[str, List[dict]], athlete: Dict) -> str:
    """Return a plain text training plan for ``athlete``.

    Parameters
    ----------
    drills:
        Mapping of phase name to a list of drill dictionaries.
    athlete:
        Information about the athlete such as ``full_name`` and
        ``sport``.  ``athlete['all_tags']`` may be supplied to inject
        coach review flags based on contradictions.
    """

    lines: List[str] = []
    plan_name = f"{athlete.get('full_name', '').strip()} Mental Plan"
    lines.append(plan_name)
    lines.append(
        f"Sport: {athlete.get('sport', '')} | Style: {athlete.get('position_style', '')} | Phase: {athlete.get('mental_phase', '')}"
    )
    lines.append("")

    phase_order = {"GPP": 1, "SPP": 2, "TAPER": 3, "UNIVERSAL": 4}
    for phase in sorted(drills, key=lambda p: phase_order.get(p.upper(), 99)):
        lines.append(f"=== {phase.upper()} DRILLS ===")
        for d in drills[phase]:
            lines.append(d.get("name", "Unnamed Drill"))
            if d.get("description"):
                lines.append(d["description"])
            if d.get("cue"):
                lines.append(f"Cue → {d['cue']}")
            if d.get("modalities"):
                lines.append("Modalities: " + ", ".join(d["modalities"]))
            tags = _humanize_tags(d.get("raw_traits", []) + d.get("theme_tags", []))
            if tags:
                lines.append("Tags: " + tags)
            if d.get("notes"):
                lines.append("Notes: " + d["notes"])
            lines.append("")
        lines.append("")

    all_tags = set(athlete.get("all_tags", []))
    notes = detect_contradictions(all_tags) if all_tags else []
    if notes:
        lines.append("COACH REVIEW FLAGS")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


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
    """Upload the PDF at ``pdf_path`` to Supabase Storage and return its URL."""

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
        )

    bucket = "plans"
    filename = os.path.basename(pdf_path)
    upload_url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{parse.quote(filename)}"

    with open(pdf_path, "rb") as f:
        data = f.read()

    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "x-upsert": "true",
        "Content-Type": "application/pdf",
    }

    req = request.Request(upload_url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"Upload failed with status {resp.status}")
    except Exception as exc:  # pragma: no cover - network issues
        raise RuntimeError("Supabase upload failed") from exc

    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{parse.quote(filename)}"


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

