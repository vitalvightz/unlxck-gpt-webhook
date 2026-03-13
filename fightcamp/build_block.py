"""HTML export builder for fight camp plans.

This module mirrors the style used for the elite mental plan export. It
constructs PDFKit-ready HTML with strict spacing and semantic tags. The resulting
HTML is converted to PDF and, if Supabase credentials are supplied, the PDF is
uploaded directly to Supabase Storage.

Environment Variables
---------------------
SUPABASE_URL is required unless ALLOW_DEFAULT_SUPABASE_URL=1 is explicitly set.
For authentication, set either SUPABASE_SERVICE_ROLE_KEY or
SUPABASE_PUBLISHABLE_KEY. When credentials are provided, the
``upload_to_supabase`` function will place the generated PDF into the
``fight-plans`` bucket. No raw HTML is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
import importlib
import logging
from typing import Optional

import os
import re
import unicodedata

logger = logging.getLogger(__name__)


def _load_optional_module(module_name: str):
    try:  # pragma: no cover - import path exercised indirectly
        return importlib.import_module(module_name)
    except ImportError:  # pragma: no cover - optional dependency absent
        return None
    except Exception:  # pragma: no cover - import side effects are environment dependent
        logger.exception("[optional-import-failed] module=%s", module_name)
        return None


markdown2 = _load_optional_module("markdown2")
pdfkit = _load_optional_module("pdfkit")

# Map of emoji and symbols that should be stripped from output
_CHAR_MAP = {
    ord("\u2026"): "...",
    ord("\u2022"): "-",
    ord("\U0001F9E0"): "",
    ord("\U0001F4CC"): "",
    ord("\U0001F3AF"): "",
    ord("\u2699"): "",
    ord("\U0001F525"): "",
    ord("\U0001F9E9"): "",
    ord("\U0001F5E3"): "",
    ord("\U0001F517"): "",
    ord("\U0001F516"): "",
    ord("\U0001F537"): "",
    ord("\u26A0"): "",
    ord("\U0001F37D"): "",
    ord("\uFE0F"): "",
}

_KNOWN_HEADINGS = [
    "Coach Notes",
    "Selection Rationale",
    "Nutrition",
    "Recovery",
    "Rehab Protocols",
    "Mindset Overview",
    "Sparring & Conditioning Adjustments Table",
    "Nutrition Adjustments for Unknown Sparring Load",
    "Athlete Profile",
    "Mindset Focus",
    "Strength & Power",
    "Conditioning",
    "Injury Guardrails",
]

_DISPLAY_NAME_MAP = {
    "battle_ropes": "Battle Ropes",
    "medicine_ball": "Medicine Ball",
    "trap_bar": "Trap Bar",
}


def _log_export_error(code: str, **context: object) -> None:
    context_str = " ".join(
        f"{key}={value}"
        for key, value in context.items()
        if value is not None and value != ""
    )
    message = f"[export-error] code={code}"
    if context_str:
        message = f"{message} {context_str}"
    logger.error(message)


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


def _escape_html_text(text: str) -> str:
    return html.escape(text, quote=False)


def _upgrade_symbols(text: str) -> str:
    """Improve typography for arrows, dashes and apostrophes."""
    return (
        text.replace("->", "\u2192")
        .replace("--", "\u2013")
        .replace("'", "\u2019")
    )


def _apply_display_name_map(text: str) -> str:
    if not text:
        return text
    for token, label in _DISPLAY_NAME_MAP.items():
        pattern = re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE)
        text = pattern.sub(label, text)
    return text


def _sanitize_markdown(text: str) -> str:
    """Normalize markdown to avoid merged headings or duplicate labels."""
    if not text:
        return text
    heading_pattern = "|".join(re.escape(h) for h in _KNOWN_HEADINGS)
    if heading_pattern:
        text = re.sub(
            rf"([A-Za-z0-9])(?=({heading_pattern}))",
            r"\1\n",
            text,
        )
        text = re.sub(
            rf"({heading_pattern})(?=\1)",
            r"\1\n",
            text,
        )
    headings_lower = {h.lower() for h in _KNOWN_HEADINGS}
    lines: list[str] = []
    last_label = ""
    for line in text.splitlines():
        stripped = line.strip()
        label = stripped.lower()
        if stripped and label in headings_lower and label == last_label:
            continue
        lines.append(line)
        if stripped and label in headings_lower:
            last_label = label
    return "\n".join(lines)


def _md_to_html(text: str) -> str:
    """Convert Markdown text to HTML with simple bullet support."""
    text = _sanitize_markdown(text)
    text = _apply_display_name_map(text)
    if markdown2 is None:  # fallback to stripping bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    time_short_pattern = re.compile(
        r"(?i)(\*\*If Time Short:\*\*|If Time Short:)\s*If time short:\s*"
    )
    system_header_pattern = re.compile(r"System:\s*\w+", re.IGNORECASE)
    red_flags_none_pattern = re.compile(
        r"^(?:\u26A0\uFE0F\s*)?Red Flags:\s*None\s*$", re.IGNORECASE
    )
    code_only_pattern = re.compile(
        r"^(?:[-\u2022]\s*)?(?:\*\*)?(tags?|equipment)(?:\*\*)?\s*:\s*"
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
        if stripped.startswith("\u2022"):
            line = re.sub(r"^\s*\u2022", "-", line)
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
    safe_text = _escape_html_text(cleaned_text)
    if markdown2:
        return markdown2.markdown(safe_text)
    # simple HTML if markdown2 unavailable
    lines = [l.rstrip() for l in safe_text.splitlines() if l.strip()]
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
    return f'<h3>{_escape_html_text(text)}</h3>'


def _subheading(text: str) -> str:
    """Return a subsection header."""
    return f'<h3>{_escape_html_text(text)}</h3>'


def _render_inline_html_text(text: str) -> str:
    return _escape_html_text(_upgrade_symbols(_clean_text(text)))


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
    selection_rationale_html: str = "",
    short_notice: bool = False,
    include_injury_sections: bool = True,
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
        title += f" - {_render_inline_html_text(full_name)}"
    lines.append(f"<h1>{title}</h1>")
    header_line = (
        f'<p><b>Sport:</b> {_render_inline_html_text(sport)} | <b>Phase Split:</b> {_render_inline_html_text(phase_split)} | '
        f'<b>Status:</b> {_render_inline_html_text(status)}'
    )
    if record:
        header_line += f' | <b>Record:</b> {_render_inline_html_text(record)}'
    if short_notice:
        header_line += " | <b>SHORT-NOTICE CAMP</b>"
    header_line += '</p><hr>'
    lines.append(header_line)

    def phase_html(block: PhaseBlock, color: str) -> str:
        parts = [
            f'<h2 style="border-left: 4px solid {color}; padding-left: 10px;">'
            f'{_render_inline_html_text(block.name)}</h2>',
            _subheading("Mindset Focus"),
            _md_to_html(block.mindset),
            _subheading("Strength & Power"),
            _md_to_html(block.strength),
            _subheading("Conditioning"),
            _md_to_html(block.conditioning),
        ]
        if include_injury_sections and block.guardrails:
            parts.extend(
                [
                    _subheading("Injury Guardrails"),
                    _md_to_html(block.guardrails),
                ]
            )
        return "\n\n".join(parts)

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
    if selection_rationale_html:
        lines += [_section_title("Selection Rationale"), selection_rationale_html]

    lines += [
        _section_title("Nutrition"),
        _md_to_html(nutrition_block),
        _section_title("Recovery"),
        _md_to_html(recovery_block),
    ]
    if include_injury_sections and rehab_html:
        lines += [
            _section_title("Rehab Protocols"),
            rehab_html,
        ]
    lines += [
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

    html = "\n\n".join(lines)

    return html


def html_to_pdf(html: str, output_path: str) -> Optional[str]:
    """Convert HTML string to PDF if pdfkit is installed."""

    if not pdfkit:
        _log_export_error("pdfkit_unavailable", stage="pdf_export", output_path=output_path)
        return None
    try:  # pragma: no cover - external call
        options = {"encoding": "UTF-8"}
        html_utf8 = html.encode("utf-8").decode("utf-8")
        pdfkit.from_string(html_utf8, output_path, options=options)
        return output_path
    except Exception:  # pragma: no cover - external renderer failures are environment dependent
        logger.exception(
            "[export-error] code=pdf_render_failed stage=pdf_export output_path=%s",
            output_path,
        )
        return None


DEFAULT_SUPABASE_URL = "https://leienvqynijrgghhzczt.supabase.co"


def _resolve_supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").strip()
    if not url:
        if os.environ.get("ALLOW_DEFAULT_SUPABASE_URL", "0") == "1":
            return DEFAULT_SUPABASE_URL
        _log_export_error("supabase_url_missing", stage="upload")
        raise RuntimeError(
            "Missing SUPABASE_URL. Set SUPABASE_URL or ALLOW_DEFAULT_SUPABASE_URL=1."
        )
    if url.upper().startswith("SUPABASE_URL="):
        url = url.split("=", 1)[1].strip()
    return url.rstrip("/")


def upload_to_supabase(pdf_path: str, bucket: str = "fight-plans") -> str:
    """Upload a PDF to Supabase Storage and return the public URL."""

    url = _resolve_supabase_url()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if not key:
        _log_export_error(
            "supabase_credentials_missing",
            stage="upload",
            bucket=bucket,
            pdf_path=pdf_path,
        )
        raise RuntimeError(
            "Missing Supabase credentials. Set SUPABASE_SERVICE_ROLE_KEY or SUPABASE_PUBLISHABLE_KEY."
        )

    import mimetypes
    from urllib import request
    from urllib.error import HTTPError
    import os as _os

    filename = _os.path.basename(pdf_path)
    storage_path = f"{url}/storage/v1/object/{bucket}/{filename}"

    with open(pdf_path, "rb") as f:
        data = f.read()

    req = request.Request(storage_path, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("apikey", key)
    req.add_header("Content-Type", mimetypes.guess_type(filename)[0] or "application/pdf")
    req.add_header("x-upsert", "true")

    try:
        with request.urlopen(req) as r:
            if r.status not in (200, 201):
                _log_export_error(
                    "supabase_upload_unexpected_status",
                    stage="upload",
                    bucket=bucket,
                    pdf_path=pdf_path,
                    status=r.status,
                )
                raise RuntimeError(f"Upload failed: HTTP {r.status}")
    except HTTPError as e:
        logger.exception(
            "[export-error] code=supabase_upload_http_error stage=upload bucket=%s pdf_path=%s status=%s",
            bucket,
            pdf_path,
            getattr(e, "code", "unknown"),
        )
        raise RuntimeError("Supabase upload failed") from e
    except Exception:
        logger.exception(
            "[export-error] code=supabase_upload_failed stage=upload bucket=%s pdf_path=%s",
            bucket,
            pdf_path,
        )
        raise

    return f"{url}/storage/v1/object/public/{bucket}/{filename}"




