#!/usr/bin/env python3
"""Strictly validate ``data/rehab_metadata_review.json`` against the bank and schema.

Dedicated to the review ledger so it never weakens ``validate_rehab_bank.py``.
Exit ``0`` when clean, ``1`` on any error, so CI can block a malformed ledger.

Enforced invariants:

* every ledger drill id exists exactly once in the bank, and is MSK (no surface
  drill receives loading review metadata);
* every MSK bank drill has exactly one ledger record;
* no duplicate ledger drill ids;
* only valid review states and movement archetypes, and only known flag codes;
* every ``proposed`` value conforms to the ``rehab_schema`` enum for its field
  (or is ``null``);
* source hashes are well-formed and deterministic — a ``needs_review`` record
  must match the current source (regenerate the ledger otherwise), and a
  ``reviewed`` record must not be stale (re-review against current source).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fightcamp.rehab_schema import (  # noqa: E402
    CONTACT_LEVEL_VALUES,
    CONTRACTION_TYPE_VALUES,
    IMPACT_VALUES,
    LATERALITY_APPLICABILITY_VALUES,
    LOAD_VALUES,
    REHAB_FUNCTIONS,
    REHAB_STAGES,
    SPORT_SPECIFICITY_VALUES,
    VELOCITY_VALUES,
    canonical_rehab_locations,
)
from tools.rehab_metadata_review_lib import (  # noqa: E402
    DEFAULT_BANK,
    DEFAULT_LEDGER,
    FLAG_CODES,
    MOVEMENT_ARCHETYPES,
    REVIEW_FIELDS,
    REVIEW_STATE_NEEDS_REVIEW,
    REVIEW_STATE_REVIEWED,
    REVIEW_STATES,
    is_surface_group,
    load_bank,
    load_ledger,
    source_hash,
)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "rehab_stage": REHAB_STAGES,
    "function": REHAB_FUNCTIONS,
    "impact": IMPACT_VALUES,
    "load": LOAD_VALUES,
    "velocity": VELOCITY_VALUES,
    "laterality_applicability": LATERALITY_APPLICABILITY_VALUES,
    "contraction_type": CONTRACTION_TYPE_VALUES,
    "sport_specificity": SPORT_SPECIFICITY_VALUES,
    "contact_level": CONTACT_LEVEL_VALUES,
}


def _validate_proposed(proposed: Any, locator: str, locations: frozenset[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(proposed, dict):
        return [f"{locator}: proposed must be an object"]
    missing = [f for f in REVIEW_FIELDS if f not in proposed]
    extra = [f for f in proposed if f not in REVIEW_FIELDS]
    if missing:
        errors.append(f"{locator}: proposed missing fields {missing}")
    if extra:
        errors.append(f"{locator}: proposed has unknown fields {extra}")
    for field, allowed in _ENUM_FIELDS.items():
        value = proposed.get(field)
        if value is not None and value not in allowed:
            errors.append(f"{locator}: proposed.{field}={value!r} not in {allowed}")
    for list_field in ("target_regions", "target_tissues", "equipment"):
        value = proposed.get(list_field)
        if value is not None and not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
            errors.append(f"{locator}: proposed.{list_field} must be null or a list of strings")
    regions = proposed.get("target_regions")
    if isinstance(regions, list):
        unknown = [r for r in regions if r not in locations]
        if unknown:
            errors.append(f"{locator}: proposed.target_regions not in location registry: {unknown}")
    notes = proposed.get("evidence_notes")
    if notes is not None and not isinstance(notes, str):
        errors.append(f"{locator}: proposed.evidence_notes must be null or a string")
    return errors


def validate(entries: list[dict], ledger: list[dict]) -> list[str]:
    errors: list[str] = []
    locations = canonical_rehab_locations()

    # Bank side: MSK drills, and their identity for hash checks.
    msk_bank: dict[str, tuple[str, str, dict]] = {}
    surface_ids: set[str] = set()
    for entry in entries:
        injury_type = str(entry.get("type") or "")
        location = str(entry.get("location") or "")
        surface = is_surface_group(injury_type)
        for drill in entry.get("drills", []):
            if not isinstance(drill, dict):
                continue
            drill_id = str(drill.get("id") or "")
            if surface:
                surface_ids.add(drill_id)
            else:
                msk_bank[drill_id] = (location, injury_type, drill)

    ledger_ids = Counter(str(r.get("drill_id")) for r in ledger if isinstance(r, dict))
    for drill_id, count in ledger_ids.items():
        if count > 1:
            errors.append(f"ledger: duplicate drill_id {drill_id!r} appears {count} times")

    seen = set(ledger_ids)
    for missing_id in sorted(set(msk_bank) - seen):
        errors.append(f"bank MSK drill {missing_id!r} has no ledger record")
    for surface_id in sorted(surface_ids & seen):
        errors.append(f"surface drill {surface_id!r} must not receive MSK review metadata")

    for index, record in enumerate(ledger):
        locator = f"ledger[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{locator}: record must be an object")
            continue
        drill_id = str(record.get("drill_id") or "")
        locator = f"ledger[{drill_id or index}]"
        if not drill_id:
            errors.append(f"{locator}: missing drill_id")
            continue
        if drill_id not in msk_bank:
            errors.append(f"{locator}: drill_id not an MSK bank drill")
            continue
        state = record.get("review_state")
        if state not in REVIEW_STATES:
            errors.append(f"{locator}: invalid review_state {state!r}")
        archetype = record.get("movement_archetype")
        if archetype not in MOVEMENT_ARCHETYPES:
            errors.append(f"{locator}: invalid movement_archetype {archetype!r}")
        for flag in record.get("flags", []) or []:
            if flag not in FLAG_CODES:
                errors.append(f"{locator}: unknown flag {flag!r}")
        stored_hash = record.get("source_hash")
        if not (isinstance(stored_hash, str) and _HASH_RE.match(stored_hash)):
            errors.append(f"{locator}: source_hash must be a 64-char hex digest")
        errors.extend(_validate_proposed(record.get("proposed"), locator, locations))

        location, injury_type, drill = msk_bank[drill_id]
        current = source_hash(
            drill_id=drill_id,
            location=location,
            injury_type=injury_type,
            name=drill.get("name"),
            notes=drill.get("notes", ""),
        )
        if state == REVIEW_STATE_NEEDS_REVIEW and stored_hash != current:
            errors.append(f"{locator}: needs_review source_hash is out of date — regenerate the ledger")
        if state == REVIEW_STATE_REVIEWED and stored_hash != current:
            errors.append(
                f"{locator}: reviewed record is STALE_SOURCE_HASH — source changed since review, re-review required"
            )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = validate(load_bank(args.bank), load_ledger(args.ledger))
    if errors:
        for error in errors:
            print(f"[error] {error}")
        print(f"{len(errors)} error(s) in {args.ledger.name}.")
        return 1
    print(f"{args.ledger.name} is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
