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

try:
    import pdfkit  # type: ignore
except Exception:  # pragma: no cover - pdfkit may be missing
    pdfkit = None

# Map of Unicode punctuation and emoji to ASCII-safe equivalents
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
    """Return ASCII-only text without emoji."""
    cleaned = text.translate(_CHAR_MAP)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    return cleaned


def _md_to_html(text: str) -> str:
    """Convert simple Markdown-style bullets to HTML."""
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    html_parts = []
    in_list = False
    for line in lines:
        line = _clean_text(line)
        if line.startswith("- ") or line.startswith("• "):
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


def _section_title(text: str) -> str:
    return f"<h2>{text}</h2>"


def _subheading(text: str) -> str:
    return f"<h3>{text}</h3>"


def build_html_document(
    *,
    full_name: str,
    sport: str,
    phase_split: str,
    status: str,
    gpp: Optional[PhaseBlock] = None,
    spp: Optional[PhaseBlock] = None,
    taper: Optional[PhaseBlock] = None,
    nutrition_block: str = "",
    recovery_block: str = "",
    rehab_html: str = "",
    mindset_overview: str = "",
    adjustments_table: str = "",
    athlete_profile_html: str = "",
) -> str:
    """Assemble the full HTML string."""

    style_sheet = """
    <style>
    body {
      font-family: Arial, sans-serif;
      font-size: 13px;
      line-height: 1.5;
      color: #222;
      margin: 40px;
    }
    h1, h2, h3 {
      margin-top: 20px;
      margin-bottom: 10px;
    }
    p, li { margin-bottom: 8px; }
    hr { border: 1px solid #ccc; margin: 30px 0; }
    ul { padding-left: 20px; }
    </style>
    """

    lines = ["<html><head>", style_sheet, "</head><body>"]

    lines.append(
        f'<h1 style="font-size: 24px;">FIGHT CAMP PLAN – {_clean_text(full_name)}</h1>'
    )
    lines.append(
        f'<p><b>Sport:</b> {_clean_text(sport)} | <b>Phase Split:</b> {phase_split} | '
        f'<b>Status:</b> {_clean_text(status)}</p><hr>'
    )

    def phase_html(block: PhaseBlock, color: str) -> str:
        parts = [
            f'<h2 style="font-size: 20px; border-left: 4px solid {color}; '
            f'padding-left: 10px;">{_clean_text(block.name)}</h2>',
            _subheading("Mindset Focus"),
            _md_to_html(block.mindset),
            _subheading("Strength & Power"),
            _md_to_html(block.strength),
            _subheading("Conditioning"),
            _md_to_html(block.conditioning),
        ]
        return "\n".join(parts)

    if gpp:
        lines.append(phase_html(gpp, "#4CAF50"))
    if spp:
        lines.append(phase_html(spp, "#FF9800"))
    if taper:
        lines.append(phase_html(taper, "#F44336"))

    lines += [
        _section_title("NUTRITION"),
        _md_to_html(nutrition_block),
        _section_title("RECOVERY"),
        _md_to_html(recovery_block),
        _section_title("REHAB PROTOCOLS"),
        rehab_html,
        _section_title("MINDSET OVERVIEW"),
        _md_to_html(mindset_overview),
        _section_title("SPARRING & CONDITIONING ADJUSTMENTS TABLE"),
        adjustments_table,
        _section_title("ATHLETE PROFILE"),
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
        pdfkit.from_string(html, output_path)
        return output_path
    except Exception:
        return None


def upload_to_supabase(pdf_path: str, bucket: str = "fight-plans") -> str:
    """Upload a PDF to Supabase Storage and return the public URL."""

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Missing Supabase credentials")

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

