#!/usr/bin/env python3
"""Generate a manual cleanup audit for style_conditioning_bank.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
REPORTS_DIR = REPO_ROOT / "reports"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.style_conditioning_quarantine import (  # noqa: E402
    STYLE_CONDITIONING_REPORT_FIELDS,
    classify_style_conditioning_entry,
)


def _load_entries(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected {path} to contain a JSON list.")
    malformed_indexes = [index for index, entry in enumerate(data) if not isinstance(entry, dict)]
    if malformed_indexes:
        indexes = ", ".join(str(index) for index in malformed_indexes[:20])
        extra = "" if len(malformed_indexes) <= 20 else f", and {len(malformed_indexes) - 20} more"
        raise ValueError(f"Expected every {path} entry to be an object; malformed indexes: {indexes}{extra}.")
    return data


def _display_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(part) for part in value)
    if value is None:
        return ""
    return str(value)


def style_conditioning_audit_row(entry: dict[str, Any]) -> dict[str, Any]:
    classification = classify_style_conditioning_entry(entry)
    row = {
        "name": entry.get("name", ""),
        "system": entry.get("system", ""),
        "phases": entry.get("phases", []),
        "rpe": entry.get("rpe", ""),
        "intensity": entry.get("intensity", ""),
        "lactate_load": entry.get("lactate_load", ""),
        "movement_cost": entry.get("movement_cost", ""),
        "impact_cost": entry.get("impact_cost", ""),
        "late_windows": entry.get("late_windows", []),
    }
    row.update(classification)
    return row


def audit_style_conditioning_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [style_conditioning_audit_row(entry) for entry in entries]


def _markdown_escape(value: Any) -> str:
    text = _display_value(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown_report(rows: list[dict[str, Any]]) -> str:
    total = len(rows)
    late_risk = sum(1 for row in rows if row["late_fight_risk_flag"])
    manual_review = sum(1 for row in rows if row["recommended_action"] == "manual_review")
    delete_candidates = sum(1 for row in rows if row["recommended_action"] == "delete_candidate")

    lines = [
        "# Style Conditioning Manual Cleanup Audit",
        "",
        "This report is diagnostic only. It does not rewrite, delete, rename, or redose bank entries.",
        "",
        "## Summary",
        "",
        f"- Entries audited: {total}",
        f"- Late-fight risk flagged: {late_risk}",
        f"- Manual review actions: {manual_review}",
        f"- Delete candidates: {delete_candidates}",
        "",
        "## Entries",
        "",
        "| " + " | ".join(STYLE_CONDITIONING_REPORT_FIELDS) + " | quarantine_reason_codes |",
        "| " + " | ".join("---" for _ in (*STYLE_CONDITIONING_REPORT_FIELDS, "quarantine_reason_codes")) + " |",
    ]
    for row in rows:
        fields = [_markdown_escape(row.get(field, "")) for field in STYLE_CONDITIONING_REPORT_FIELDS]
        fields.append(_markdown_escape(row.get("quarantine_reason_codes", [])))
        lines.append("| " + " | ".join(fields) + " |")
    lines.append("")
    return "\n".join(lines)


def write_report(rows: list[dict[str, Any]], output_path: Path, *, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    else:
        output_path.write_text(render_markdown_report(rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit style-conditioning entries for manual cleanup.")
    parser.add_argument(
        "--bank",
        type=Path,
        default=DATA_DIR / "style_conditioning_bank.json",
        help="Path to style_conditioning_bank.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "style_conditioning_audit.md",
        help="Report output path.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default=None,
        help="Report format. Defaults to json for .json outputs, otherwise markdown.",
    )
    args = parser.parse_args(argv)

    output_format = args.format or ("json" if args.output.suffix.lower() == ".json" else "markdown")
    rows = audit_style_conditioning_entries(_load_entries(args.bank))
    write_report(rows, args.output, output_format=output_format)
    print(f"Wrote {len(rows)} style-conditioning audit rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
