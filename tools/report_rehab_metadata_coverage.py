#!/usr/bin/env python3
"""Deterministic coverage report for the rehab clinical-metadata migration.

Answers "which injury families are migrated enough to support later LOAD-criteria
work?" from the bank and the review ledger, without changing either. All counts
are exact and stable; ``--json`` emits the same data as a machine-readable blob.

Key distinctions, never blurred:

* ``null``  = not clinically migrated (deterministic incompleteness).
* ``unknown`` = reviewed but not defensibly classifiable.
* ``known`` = a real level (e.g. ``low``/``moderate``) — the only kind that can
  ever support loading qualification.

Review provenance comes from the ledger (``reviewed`` / ``needs_review`` / a
derived ``stale`` when a reviewed record's source hash no longer matches), never
from a bank value.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.rehab_metadata_review_lib import (  # noqa: E402
    DEFAULT_BANK,
    DEFAULT_LEDGER,
    REVIEW_STATE_REVIEWED,
    is_surface_group,
    iter_msk_drills,
    load_bank,
    load_ledger,
    source_hash,
)

_DEMAND_FIELDS = ("load", "impact", "velocity")
_CLASSIFICATION_FIELDS = (
    "rehab_stage",
    "function",
    "load",
    "impact",
    "velocity",
    "laterality_applicability",
    "contraction_type",
    "sport_specificity",
    "contact_level",
    "target_tissues",
)


def _level(value: object) -> str:
    if value is None:
        return "null"
    if value == "unknown":
        return "unknown"
    return "known"


def build_report(entries: list[dict], ledger: list[dict]) -> dict:
    total_groups = len(entries)
    surface_groups = sum(1 for e in entries if is_surface_group(e.get("type")))
    total_drills = sum(len(e.get("drills", [])) for e in entries)
    surface_drills = sum(
        len(e.get("drills", [])) for e in entries if is_surface_group(e.get("type"))
    )

    by_id = {str(r.get("drill_id")): r for r in ledger if isinstance(r, dict) and r.get("drill_id")}

    review_states: dict[str, int] = defaultdict(int)
    stale = 0
    flagged_variable_demand = 0
    field_levels: dict[str, dict[str, int]] = {f: defaultdict(int) for f in _CLASSIFICATION_FIELDS}
    fully_known_demand = 0
    # location / type / stage breakdowns
    by_key: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_stage: dict[str, int] = defaultdict(int)
    msk_drills = 0

    for _gi, _di, location, injury_type, drill in iter_msk_drills(entries):
        msk_drills += 1
        record = by_id.get(str(drill.get("id") or ""))
        state = record.get("review_state") if record else "missing"
        review_states[state] += 1
        if record and record.get("review_state") == REVIEW_STATE_REVIEWED:
            current = source_hash(
                drill_id=drill.get("id"),
                location=location,
                injury_type=injury_type,
                name=drill.get("name"),
                notes=drill.get("notes", ""),
            )
            if current != record.get("source_hash"):
                stale += 1
        if record and record.get("flags"):
            flagged_variable_demand += 1

        for field in _CLASSIFICATION_FIELDS:
            field_levels[field][_level(drill.get(field))] += 1
        if all(_level(drill.get(f)) == "known" for f in _DEMAND_FIELDS):
            fully_known_demand += 1

        key = (location, injury_type)
        by_key[key]["drills"] += 1
        if record and record.get("review_state") == REVIEW_STATE_REVIEWED:
            by_key[key]["reviewed"] += 1
        for field in ("load", "impact", "velocity", "rehab_stage"):
            if _level(drill.get(field)) == "known":
                by_key[key][f"known_{field}"] += 1
        by_stage[str(drill.get("rehab_stage"))] += 1

    return {
        "totals": {
            "groups": total_groups,
            "surface_groups": surface_groups,
            "msk_groups": total_groups - surface_groups,
            "drills": total_drills,
            "surface_drills": surface_drills,
            "msk_drills": msk_drills,
        },
        "review_states": dict(sorted(review_states.items())),
        "stale_reviews": stale,
        "variable_demand_flagged": flagged_variable_demand,
        "fully_known_mechanical_demand": fully_known_demand,
        "field_levels": {f: dict(sorted(levels.items())) for f, levels in field_levels.items()},
        "by_injury": {
            f"{loc}/{itype}": dict(sorted(counts.items()))
            for (loc, itype), counts in sorted(by_key.items())
        },
        "by_rehab_stage": dict(sorted(by_stage.items())),
    }


def _print_human(report: dict) -> None:
    t = report["totals"]
    print("REHAB METADATA COVERAGE")
    print(f"  groups: {t['groups']} (msk {t['msk_groups']}, surface {t['surface_groups']})")
    print(f"  drills: {t['drills']} (msk {t['msk_drills']}, surface {t['surface_drills']})")
    print(f"  review states: {report['review_states']}")
    print(f"  stale reviews: {report['stale_reviews']}")
    print(f"  variable-demand flagged: {report['variable_demand_flagged']}")
    print(f"  fully-known mechanical demand (load+impact+velocity): {report['fully_known_mechanical_demand']}")
    print("  field levels (null / unknown / known):")
    for field, levels in report["field_levels"].items():
        print(f"    {field:26} null={levels.get('null', 0):4} unknown={levels.get('unknown', 0):4} known={levels.get('known', 0):4}")
    print("  by injury location/type (drills / reviewed / known load / known impact / known velocity):")
    for key, counts in report["by_injury"].items():
        print(
            f"    {key:30} drills={counts.get('drills', 0):3} reviewed={counts.get('reviewed', 0):3} "
            f"load={counts.get('known_load', 0):3} impact={counts.get('known_impact', 0):3} "
            f"velocity={counts.get('known_velocity', 0):3} stage={counts.get('known_rehab_stage', 0):3}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(load_bank(args.bank), load_ledger(args.ledger))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
