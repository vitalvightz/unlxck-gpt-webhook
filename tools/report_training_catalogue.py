"""Reproduce catalogue coverage: python tools/report_training_catalogue.py.

--output reports/training_catalogue_coverage.json writes reviewable JSON.
No athlete records, runtime defaults, or inferred tags are used.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fightcamp.training_catalogue import (  # noqa: E402
    DATA_DIR, METADATA_FIELDS, SOURCE_CLASSES, build_catalogue,
)


def coverage_report(data_dir: Path = DATA_DIR) -> dict:
    entries = build_catalogue(data_dir, strict=False)
    names = defaultdict(list)
    banks = []
    for source in SOURCE_CLASSES:
        rows = [entry for entry in entries if entry["source"] == source]
        banks.append({
            "source": source,
            "sha256": hashlib.sha256((data_dir / source).read_bytes()).hexdigest(),
            "total_entries": len(rows),
            "physical_candidates_requiring_validation": sum(row["eligibility"]["physical_candidate"] for row in rows),
            "rehabilitation_requiring_pathway_validation": sum(row["content_class"] == "rehabilitation" for row in rows),
            "non_exercise_educational_care_visualisation": sum(row["content_class"] in {"tactical_educational", "care_instruction", "visualisation"} for row in rows),
            "without_stable_ids": sum(row["catalogue_id"] is None for row in rows),
            "excluded_from_normal_workout_selection": sum(not row["eligibility"]["normal_workout_candidate"] for row in rows),
            "metadata_states": {
                field: dict(sorted(Counter(row["metadata"][field]["state"] for row in rows).items()))
                for field in METADATA_FIELDS
            },
        })
    for entry in entries:
        names[" ".join(entry["name"].casefold().split())].append(entry["catalogue_id"])
    duplicates = {name: ids for name, ids in sorted(names.items()) if len(ids) > 1}
    return {
        "schema_version": 1,
        "method": "Raw source evidence and pinned identities; candidates are not permission to prescribe.",
        "total_entries": len(entries),
        "physical_candidates_requiring_validation": sum(e["eligibility"]["physical_candidate"] for e in entries),
        "rehabilitation_requiring_pathway_validation": sum(e["content_class"] == "rehabilitation" for e in entries),
        "non_exercise_educational_care_visualisation": sum(e["content_class"] in {"tactical_educational", "care_instruction", "visualisation"} for e in entries),
        "without_stable_ids": sum(e["catalogue_id"] is None for e in entries),
        "prescription_permissions_granted": 0,
        "hidden_filters": {"difficulty": "No reviewed difficulty coverage; never default to Beginner."},
        "duplicate_name_groups": len(duplicates),
        "banks": banks,
        "duplicate_names": duplicates,
        # Each source row is retained, including unknown metadata and non-workout content.
        "entries": [{
            "catalogue_id": entry["catalogue_id"], "source": entry["source"],
            "name": entry["name"], "content_class": entry["content_class"],
            "boundary": entry["eligibility"]["boundary"],
            "exclusion_reason": None if entry["eligibility"]["normal_workout_candidate"] else entry["eligibility"]["reason"],
            "equipment_state": entry["metadata"]["equipment"]["state"],
            "metadata_gap_counts": dict(sorted(Counter(
                entry["metadata"][field]["state"] for field in METADATA_FIELDS
                if entry["metadata"][field]["state"] != "known"
            ).items())),
        } for entry in entries],
    }


def report_json(report: dict) -> str:
    # Compact per-entry lines keep this generated evidence reviewable in a PR.
    summary = {key: value for key, value in report.items() if key != "entries"}
    prefix = json.dumps(summary, indent=2, ensure_ascii=True).rstrip()[:-1].rstrip()
    rows = ",\n".join("    " + json.dumps(row, ensure_ascii=True) for row in report["entries"])
    return prefix + ',\n  "entries": [\n' + rows + '\n  ]\n}\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = report_json(coverage_report(args.data_dir))
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
