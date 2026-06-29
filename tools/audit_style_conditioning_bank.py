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
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
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


def summarize_audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "entries_audited": len(rows),
        "late_fight_risk_flagged": sum(1 for row in rows if row["late_fight_risk_flag"]),
        "camp_action_counts": _count_values(rows, "camp_action"),
        "late_fight_action_counts": _count_values(rows, "late_fight_action"),
        "quarantine_reason_code_counts": _count_reason_codes(rows),
        "system_counts": _count_values(rows, "system"),
        "phase_counts": _count_phase_values(rows),
    }


def _markdown_escape(value: Any) -> str:
    text = _display_value(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _display_value(row.get(field, "")).strip() or "(missing)"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _count_phase_values(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        phases = row.get("phases")
        if not isinstance(phases, list) or not phases:
            counts["(missing)"] = counts.get("(missing)", 0) + 1
            continue
        for phase in phases:
            value = str(phase).strip() or "(missing)"
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _count_reason_codes(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason_codes = row.get("quarantine_reason_codes") or []
        if not reason_codes:
            counts["(none)"] = counts.get("(none)", 0) + 1
            continue
        for code in reason_codes:
            value = str(code).strip() or "(missing)"
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _render_count_list(title: str, counts: dict[str, int]) -> list[str]:
    lines = [f"### {title}", ""]
    if not counts:
        return lines + ["- None", ""]
    lines.extend(f"- {key}: {value}" for key, value in counts.items())
    lines.append("")
    return lines


def _phase_names(row: dict[str, Any]) -> set[str]:
    phases = row.get("phases")
    if not isinstance(phases, list):
        return set()
    return {str(phase).strip().upper() for phase in phases if str(phase).strip()}


def _render_table(rows: list[dict[str, Any]]) -> list[str]:
    fields = [*STYLE_CONDITIONING_REPORT_FIELDS, "quarantine_reason_codes"]
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_escape(row.get(field, "")) for field in fields) + " |")
    return lines


def _render_group(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [f"### {title}", "", f"Entries: {len(rows)}", ""]
    if rows:
        lines.extend(_render_table(rows))
        lines.append("")
    return lines


def _grouped_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "Delete/Rebuild Candidates": [row for row in rows if row["camp_action"] == "delete_or_rebuild"],
        "Rename Candidates": [row for row in rows if row["camp_action"] == "rename"],
        "Redose Candidates": [row for row in rows if row["camp_action"] == "redose"],
        "Rename + Redose Candidates": [row for row in rows if row["camp_action"] == "rename_and_redose"],
        "GPP/SPP Keep But No Late-Fight": [
            row
            for row in rows
            if row["camp_action"] == "keep"
            and row["late_fight_action"] in {"late_blocked", "not_late_eligible"}
            and _phase_names(row) & {"GPP", "SPP"}
        ],
        "Potential Late Support Candidates": [
            row for row in rows if row["late_fight_action"] == "late_support_candidate"
        ],
        "Potential Late Technical Candidates": [
            row for row in rows if row["late_fight_action"] == "late_technical_candidate"
        ],
        "Potential Late Conditioning Candidates": [
            row for row in rows if row["late_fight_action"] == "late_conditioning_candidate"
        ],
        "Manual Review": [row for row in rows if row["camp_action"] == "manual_review"],
        "Suspicious ATP-PCr Classification": [
            row for row in rows if "questionable_atp_pcr_classification" in (row.get("quarantine_reason_codes") or [])
        ],
    }


def render_markdown_report(rows: list[dict[str, Any]]) -> str:
    summary = summarize_audit_rows(rows)

    lines = [
        "# Style Conditioning Manual Cleanup Audit",
        "",
        "This report is diagnostic only. It does not rewrite, delete, rename, or redose bank entries.",
        "",
        "## Summary",
        "",
        f"- Entries audited: {summary['entries_audited']}",
        f"- Late-fight risk flagged: {summary['late_fight_risk_flagged']}",
        "",
        "## Summary Counts",
        "",
    ]
    lines.extend(_render_count_list("Camp Actions", summary["camp_action_counts"]))
    lines.extend(_render_count_list("Late-Fight Actions", summary["late_fight_action_counts"]))
    lines.extend(_render_count_list("Quarantine Reason Codes", summary["quarantine_reason_code_counts"]))
    lines.extend(_render_count_list("Systems", summary["system_counts"]))
    lines.extend(_render_count_list("Phases", summary["phase_counts"]))
    lines.extend(["## Grouped Review Queues", ""])
    for title, group_rows in _grouped_rows(rows).items():
        lines.extend(_render_group(title, group_rows))
    lines.extend(["## All Entries", ""])
    lines.extend(_render_table(rows))
    lines.append("")
    return "\n".join(lines)


def render_json_report(rows: list[dict[str, Any]]) -> str:
    payload = {"summary": summarize_audit_rows(rows), "rows": rows}
    return json.dumps(payload, indent=2) + "\n"


def write_report(rows: list[dict[str, Any]], output_path: Path, *, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output_path.write_text(render_json_report(rows), encoding="utf-8")
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
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=REPORTS_DIR / "style_conditioning_audit.json",
        help="JSON report output path. Use --no-json-output to skip.",
    )
    parser.add_argument(
        "--no-json-output",
        action="store_true",
        help="Only write the primary --output report.",
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
    wrote_paths = [args.output]
    if not args.no_json_output and args.json_output != args.output:
        write_report(rows, args.json_output, output_format="json")
        wrote_paths.append(args.json_output)
    outputs = ", ".join(str(path) for path in wrote_paths)
    print(f"Wrote {len(rows)} style-conditioning audit rows to {outputs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
