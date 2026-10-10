"""Read-only inventory of source metadata for a future shared training library.

Run from any directory: python tools/audit_training_library.py
Redirect stdout to retain the deterministic JSON report. No runtime bank loaders,
inferred tags, default metadata, archived banks, or athlete records are used.
Counts describe source coverage, never clinical clearance or prescription quality.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
# Explicit inventory, based on the existing consumers. Do not glob archives.
SOURCES = (
    "exercise_bank.json", "conditioning_bank.json",
    "style_conditioning_bank.json", "style_taper_conditioning.json",
    "technical_footwork_bank.json", "coordination_bank.json",
    "coordination/universal.json", "coordination/striking.json",
    "coordination/kicks.json", "coordination/mma_transitions.json",
    "coordination/grappling.json", "rehab_bank.json",
    "tactical_watch_bank.json", "fight_visualization_bank.json",
)
FIELDS = (
    "tags", "equipment", "sports", "qualities", "category", "method",
    "movement", "difficulty", "phases", "system", "mechanical_risk_tags",
    "duration", "duration_min", "total_minutes", "work_sec", "rest_sec",
    "rounds", "rpe", "rpe_max", "intensity", "notes", "description", "cue",
    "instructions", "why", "progress", "progression", "regress", "regression",
    "stop", "stop_rules", "target_regions", "rehab_stage", "function",
    "dose", "allowed_severities", "pain_ceiling", "progress_when",
    "regress_when", "stop_when", "laterality_applicability", "contact_level",
)
SPORTS = {"boxing", "mma", "kickboxing", "muay_thai", "bjj", "wrestling"}
UNKNOWN = {"unknown", "unreviewed", "unspecified"}


def field_state(row: dict, key: str) -> str:
    if key not in row:
        return "absent"
    value = row[key]
    if value is None:
        return "null"
    if isinstance(value, str):
        if not value.strip():
            return "empty"
        if value.strip().lower() in UNKNOWN:
            return "unknown"
    if value == [] or value == {}:
        return "empty"
    if isinstance(value, list) and all(
        isinstance(item, str) and item.strip().lower() in UNKNOWN for item in value
    ):
        return "unknown"
    return "populated"


def strings(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [v.strip() for v in values if isinstance(v, str) and v.strip()]


def source_rows(source: str, payload: object) -> list[dict]:
    if source == "rehab_bank.json":
        if not isinstance(payload, list):
            raise ValueError("rehab bank must be a list of groups")
        return [
            {**drill, "_audit_group": {
                "group_index": group_index, "drill_index": drill_index,
                "location": group.get("location"), "type": group.get("type"),
            }}
            for group_index, group in enumerate(payload)
            for drill_index, drill in enumerate(group["drills"])
        ]
    if source == "coordination_bank.json" and isinstance(payload, dict):
        # The legacy shim has metadata and empty exercise lists.
        return [row for value in payload.values() if isinstance(value, list) for row in value]
    if not isinstance(payload, list):
        raise ValueError(f"unexpected bank shape: {source}")
    return payload


def audit(data_dir: Path) -> dict:
    banks = []
    names: dict[str, list[dict]] = defaultdict(list)
    for source in SOURCES:
        raw = (data_dir / source).read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        rows = source_rows(source, payload)
        if any(not isinstance(row, dict) or not strings(row.get("name")) for row in rows):
            raise ValueError(f"unnamed or malformed entry in {source}")
        tags = Counter(tag for row in rows for tag in strings(row.get("tags")))
        identifiers = Counter(
            identifier for row in rows
            for identifier in strings(row.get("id") or row.get("key"))
        )
        for index, row in enumerate(rows):
            name = " ".join(row["name"].casefold().split())
            reference = {"source": source, "row": index, "name": row["name"]}
            if "_audit_group" in row:
                reference["group_context"] = row["_audit_group"]
            names[name].append(reference)
        fields = {
            key: dict(sorted(Counter(field_state(row, key) for row in rows).items()))
            for key in FIELDS
        }
        # [] is explicit no equipment, not missing equipment. Null/absent/unknown
        # remain unresolved. "none" is a legitimate equipment value.
        banks.append({
            "source": source,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "entries": len(rows),
            "rehab_groups": len(payload) if source == "rehab_bank.json" else None,
            "explicit_id_or_key": sum(bool(strings(row.get("id") or row.get("key"))) for row in rows),
            "duplicate_explicit_ids": dict(sorted((k, v) for k, v in identifiers.items() if v > 1)),
            "equipment_known": sum(field_state(row, "equipment") == "populated" or row.get("equipment") == [] for row in rows),
            "sport_field_or_explicit_tag": sum(
                any(sport not in UNKNOWN for sport in strings(row.get("sports")))
                or bool(set(strings(row.get("tags"))) & SPORTS) for row in rows
            ),
            "fields": fields,
            "tag_counts": dict(sorted(tags.items())),
        })
    duplicates = [
        {"normalized_name": name, "occurrences": refs}
        for name, refs in sorted(names.items()) if len(refs) > 1
    ]
    return {
        "method": "raw source fields; no defaults, inference, eligibility or metadata repairs",
        "total_entries": sum(bank["entries"] for bank in banks),
        "banks": banks,
        "duplicate_name_groups": len(duplicates),
        "duplicate_names": duplicates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    print(json.dumps(audit(args.data_dir), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
