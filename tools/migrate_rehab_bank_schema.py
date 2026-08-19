#!/usr/bin/env python3
"""Migrate ``data/rehab_bank.json`` onto the formal rehab-bank schema.

The migration is deterministic and idempotent: re-running it on an already
migrated bank is a no-op. It does one thing and nothing else — it adds the
structured contract fields defined in :mod:`fightcamp.rehab_schema` to every
drill.

It adds, removes and reorders no group record. The bank contains 15 group
records that duplicate an earlier record exactly; collapsing them would change
generated rehab blocks, so they stay, and are carried as declared migration debt
in ``data/rehab_bank_duplicate_debt.json`` for PR3 to resolve.

It fabricates no clinical content. Only two fields carry derived values:

* ``id`` — a deterministic slug of ``location``/``type``/``name``, suffixed on
  collision so ids stay unique.
* ``function`` — the existing keyword classification, and *only* when a keyword
  actually matched. An unmatched drill gets ``null`` (not migrated), never the
  legacy ``"control"`` default.

Everything else is written as ``null``: rehab stage, dose, equipment, impact,
load, velocity, pain ceiling, allowed severities and the progress/regress/stop
rules are clinical content that PR3 migrates.

Wound-care (skin/surface) groups get ``id`` only. They are integumentary, not
musculoskeletal, and never carry loading metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.rehab_protocols import match_drill_function  # noqa: E402
from fightcamp.rehab_schema import (  # noqa: E402
    CARE_TYPE_WOUND_CARE,
    MSK_DRILL_FIELDS,
    build_drill_id,
    care_type_for_injury_type,
)

DEFAULT_BANK = REPO_ROOT / "data" / "rehab_bank.json"


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}_{suffix}" in used:
        suffix += 1
    candidate = f"{base}_{suffix}"
    used.add(candidate)
    return candidate


def migrate_drill(
    drill: dict,
    *,
    location: str,
    injury_type: str,
    care_type: str,
    used_ids: set[str],
) -> dict:
    """Return the drill rewritten onto the schema, preserving existing values."""
    name = drill.get("name")
    migrated: dict[str, Any] = {
        "id": drill.get("id") or _unique_id(build_drill_id(location, injury_type, name), used_ids),
        "name": name,
        "notes": drill.get("notes", ""),
    }
    if care_type == CARE_TYPE_WOUND_CARE:
        return migrated

    for field in MSK_DRILL_FIELDS:
        migrated[field] = drill.get(field)
    if migrated["function"] is None:
        migrated["function"] = match_drill_function(name or "", migrated["notes"])
    return migrated


def _existing_ids(entries: list[dict]) -> set[str]:
    """Ids already stored in the bank, claimed before any new id is generated."""
    return {
        str(drill["id"])
        for entry in entries
        for drill in entry.get("drills", [])
        if isinstance(drill, dict) and drill.get("id")
    }


def migrate_entries(entries: list[dict]) -> list[dict]:
    """Return the whole bank rewritten onto the schema."""
    used_ids: set[str] = _existing_ids(entries)
    migrated: list[dict] = []
    for entry in entries:
        location = str(entry.get("location") or "")
        injury_type = str(entry.get("type") or "")
        care_type = care_type_for_injury_type(injury_type)
        record = dict(entry)
        record["drills"] = [
            migrate_drill(
                drill,
                location=location,
                injury_type=injury_type,
                care_type=care_type,
                used_ids=used_ids,
            )
            for drill in entry.get("drills", [])
        ]
        migrated.append(record)
    return migrated


def render(entries: list[dict]) -> str:
    return json.dumps(entries, indent=2, ensure_ascii=False) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK, help="rehab bank JSON path")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the bank is not already migrated, writing nothing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    original = args.bank.read_text(encoding="utf-8")
    entries = json.loads(original)
    rendered = render(migrate_entries(entries))

    if args.check:
        if rendered == original:
            print(f"{args.bank.name} is already migrated.")
            return 0
        print(f"{args.bank.name} is not migrated (run without --check to rewrite).")
        return 1

    args.bank.write_text(rendered, encoding="utf-8")
    drill_count = sum(len(entry.get("drills", [])) for entry in entries)
    print(f"Migrated {args.bank.name}: {len(entries)} groups, {drill_count} drills.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
