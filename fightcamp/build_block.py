"""HTML export builder for fight camp plans.

This module mirrors the style used for the elite mental plan export. It
constructs PDFKit-ready HTML with strict spacing and semantic tags. The resulting
HTML is converted to PDF and, if Supabase credentials are supplied, the PDF is
uploaded directly to Supabase Storage.

Environment Variables
---------------------
SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are optional. When provided, the
``upload_to_supabase`` function will place the generated PDF into the ``fight-plans``
bucket. No raw HTML is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import os
import re
import unicodedata

try:
    import markdown2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    markdown2 = None

try:
    import pdfkit  # type: ignore
except Exception:  # pragma: no cover - pdfkit may be missing
    pdfkit = None

# Map of emoji and symbols that should be stripped from output
_CHAR_MAP = {
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
    ord("🍽"): "",
    ord("️"): "",
}


def _clean_text(text: str) -> str:
    """Return UTF-8 cleaned text without unwanted emoji."""
    cleaned = text.translate(_CHAR_MAP)
    result_chars = []
    for ch in cleaned:
        cat = unicodedata.category(ch)
        name = unicodedata.name(ch, "")
        if cat in {"So", "Co", "Cs"}:
            continue
        if "VARIATION SELECTOR" in name:
            continue
        result_chars.append(ch)
    return "".join(result_chars)


def _upgrade_symbols(text: str) -> str:
    """Improve typography for arrows, dashes and apostrophes."""
    return (
        text.replace("->", "→")
        .replace("--", "–")
        .replace("'", "’")
    )


def _md_to_html(text: str) -> str:
    """Convert Markdown text to HTML with simple bullet support."""
    if markdown2 is None:  # fallback to stripping bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    time_short_pattern = re.compile(
        r"(?i)(\*\*If Time Short:\*\*|If Time Short:)\s*If time short:\s*"
    )
    system_header_pattern = re.compile(r"System:\s*\w+", re.IGNORECASE)
    red_flags_none_pattern = re.compile(
        r"^(?:⚠️\s*)?Red Flags:\s*None\s*$", re.IGNORECASE
    )
    code_only_pattern = re.compile(
        r"^(?:[-•]\s*)?(?:\*\*)?(tags?|equipment)(?:\*\*)?\s*:\s*"
        r"[\[\(]?[a-z0-9_ ,/+.-]+[\]\)]?\s*$",
        re.IGNORECASE,
    )
    cleaned_lines = []
    in_system_section = False
    red_flags_none_written = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if code_only_pattern.match(stripped):
            continue
        line = time_short_pattern.sub(r"\1 ", line)
        stripped = line.lstrip()
        if system_header_pattern.search(stripped):
            in_system_section = True
            red_flags_none_written = False
        if stripped.startswith("•"):
            line = re.sub(r"^\s*•", "-", line)
        if red_flags_none_pattern.match(stripped):
            if in_system_section and not red_flags_none_written:
                cleaned_lines.append(
                    red_flags_none_pattern.sub(
                        "Red Flags: none noted unless listed", line
                    )
                )
                red_flags_none_written = True
            continue
        if stripped.startswith("- **Drill:") and cleaned_lines:
            cleaned_lines.append("")
        cleaned_lines.append(line)
    cleaned_text = _upgrade_symbols(_clean_text("\n".join(cleaned_lines)))
    if markdown2:
        return markdown2.markdown(cleaned_text)
    # simple HTML if markdown2 unavailable
    lines = [l.rstrip() for l in cleaned_text.splitlines() if l.strip()]
    html_parts = []
    in_list = False
    for line in lines:
        heading_match = re.match(r"^(#+)\s+(.*)", line)
        if heading_match:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            level = min(len(heading_match.group(1)), 6)
            text = heading_match.group(2).strip()
            html_parts.append(f"<h{level}>{text}</h{level}>")
            continue
        if line.startswith("- "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{line[2:].strip()}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{line}</p>")
    if in_list:
        html_parts.append("</ul>")
    return "\n".join(html_parts)




@dataclass
class PhaseBlock:
    name: str
    weeks: int
    days: int
    mindset: str
    strength: str
    conditioning: str
    guardrails: str


def _section_title(text: str) -> str:
    """Return a section header."""
    return f'<h3>{text}</h3>'


def _subheading(text: str) -> str:
    """Return a subsection header."""
    return f'<h3>{text}</h3>'


def build_html_document(
    *,
    full_name: str,
    sport: str,
    phase_split: str,
    status: str,
    record: str = "",
    gpp: Optional[PhaseBlock] = None,
    spp: Optional[PhaseBlock] = None,
    taper: Optional[PhaseBlock] = None,
    nutrition_block: str = "",
    recovery_block: str = "",
    rehab_html: str = "",
    mindset_overview: str = "",
    adjustments_table: str = "",
    sparring_nutrition_html: str = "",
    athlete_profile_html: str = "",
    coach_notes: str = "",
) -> str:
    """Assemble the full HTML string."""

    style_sheet = """
    <style>
    body {
      font-family: Arial, sans-serif;
      font-size: 11.5pt;
      line-height: 1.4;
      color: #222;
      margin: 30px;
    }
    h1 {font-size:24pt; margin-top:20px; margin-bottom:10px; font-weight:bold;}
    h2 {font-size:18pt; margin-top:25px; margin-bottom:14px; font-weight:bold; text-align:left; text-decoration: underline;}
    h3 {font-size:14pt; margin-top:25px; margin-bottom:8px; font-weight:bold; text-align:left;}
    h4 {font-size:12pt; margin-top:12px; margin-bottom:6px; font-weight:bold; text-align:left;}
    p {font-size:11.5pt; margin-bottom:6px; text-align:left; line-height:1.4;}
    li {font-size:11.5pt; margin-bottom:6px; text-align:left; line-height:1.4;}
    hr { border: 1px solid #ccc; margin: 40px 0; }
    ul { padding-left: 18px; margin-bottom:12px; }
    </style>
    """

    lines = ["<html><head>", style_sheet, "</head><body>"]

    title = "FIGHT CAMP PLAN"
    if full_name:
        title += f" – {_clean_text(full_name)}"
    lines.append(f"<h1>{title}</h1>")
    header_line = (
        f'<p><b>Sport:</b> {_clean_text(sport)} | <b>Phase Split:</b> {phase_split} | '
        f'<b>Status:</b> {_clean_text(status)}'
    )
    if record:
        header_line += f' | <b>Record:</b> {_clean_text(record)}'
    header_line += '</p><hr>'
    lines.append(header_line)

    def phase_html(block: PhaseBlock, color: str) -> str:
        parts = [
            f'<h2 style="border-left: 4px solid {color}; padding-left: 10px;">'
            f'{_upgrade_symbols(_clean_text(block.name))}</h2>',
            _subheading("Mindset Focus"),
            _md_to_html(block.mindset),
            _subheading("Strength & Power"),
            _md_to_html(block.strength),
            _subheading("Conditioning"),
            _md_to_html(block.conditioning),
            _subheading("Injury Guardrails"),
            _md_to_html(block.guardrails),
        ]
        return "\n".join(parts)

    if gpp:
        lines.append(phase_html(gpp, "#4CAF50"))
        lines.append("<br><br>")
        if spp or taper:
            lines.append("<hr>")
    if spp:
        lines.append(phase_html(spp, "#FF9800"))
        lines.append("<br><br>")
        if taper:
            lines.append("<hr>")
    if taper:
        lines.append(phase_html(taper, "#F44336"))
        lines.append("<br><br>")

    if coach_notes:
        lines += [_section_title("Coach Notes"), _md_to_html(coach_notes)]

    lines += [
        _section_title("Nutrition"),
        _md_to_html(nutrition_block),
        _section_title("Recovery"),
        _md_to_html(recovery_block),
        _section_title("Rehab Protocols"),
        rehab_html,
        _section_title("Mindset Overview"),
        _md_to_html(mindset_overview),
        _section_title("Sparring & Conditioning Adjustments Table"),
        adjustments_table,
        _section_title("Nutrition Adjustments for Unknown Sparring Load"),
        sparring_nutrition_html,
        _section_title("Athlete Profile"),
        athlete_profile_html,
        "</body></html>",
    ]

    html = "\n".join(lines)

    return html


def html_to_pdf(html: str, output_path: str) -> Optional[str]:
    """Convert HTML string to PDF if pdfkit is installed."""

    if not pdfkit:
        return None
    try:  # pragma: no cover - external call
        options = {"encoding": "UTF-8"}
        html_utf8 = html.encode("utf-8").decode("utf-8")
        pdfkit.from_string(html_utf8, output_path, options=options)
        return output_path
    except Exception:
        return None


def upload_to_supabase(pdf_path: str, bucket: str = "fight-plans") -> str:
    """Upload a PDF to Supabase Storage and return the public URL."""

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase credentials")
    url = url.strip()
    if url.upper().startswith("SUPABASE_URL="):
        url = url.split("=", 1)[1].strip()
    url = url.rstrip("/")

    import mimetypes
    from urllib import request
    from urllib.error import HTTPError
    import os as _os

    filename = _os.path.basename(pdf_path)
    storage_path = f"{url}/storage/v1/object/{bucket}/{filename}"

    with open(pdf_path, "rb") as f:
        data = f.read()

    req = request.Request(storage_path, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", mimetypes.guess_type(filename)[0] or "application/pdf")
    req.add_header("Content-Length", str(len(data)))

    try:  # pragma: no cover - external call
        with request.urlopen(req) as r:
            if r.status != 200:
                raise RuntimeError("Upload failed")
    except HTTPError as e:  # pragma: no cover - external call
        raise RuntimeError("Supabase upload failed") from e

    return f"{url}/storage/v1/object/public/{bucket}/{filename}"
