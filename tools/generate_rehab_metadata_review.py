#!/usr/bin/env python3
"""Generate ``data/rehab_metadata_review.json`` from ``data/rehab_bank.json``.

Deterministic and idempotent: the same bank (and same prior ledger) always
produces a byte-identical ledger. One record per MSK drill; surface/wound-care
drills are excluded from the loading pathway entirely.

A record is a *proposal*, not clinical truth. ``proposed`` holds conservative
candidate classifications (see ``rehab_metadata_review_lib.propose_metadata``);
only a human setting ``review_state = "reviewed"`` makes them applicable, and the
applicator still checks the source hash first.

Prior human reviews are never clobbered: a ``reviewed`` record is carried through
verbatim (its review-time ``source_hash`` preserved so staleness stays
detectable). Only ``needs_review`` records are regenerated from the current bank.

``--check`` writes nothing and exits non-zero when the on-disk ledger differs
from what would be generated, so CI can require the ledger to be up to date.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.rehab_metadata_review_lib import (  # noqa: E402
    DEFAULT_BANK,
    DEFAULT_LEDGER,
    LEDGER_VERSION,
    REVIEW_STATE_NEEDS_REVIEW,
    REVIEW_STATE_REVIEWED,
    classify_movement_archetype,
    detect_variable_demand_flags,
    iter_msk_drills,
    load_bank,
    load_ledger,
    propose_metadata,
    render_ledger,
    source_hash,
)


def _fresh_record(location: str, injury_type: str, drill: dict) -> dict:
    drill_id = str(drill.get("id") or "")
    name = drill.get("name")
    notes = drill.get("notes", "")
    archetype = classify_movement_archetype(name, notes)
    return {
        "drill_id": drill_id,
        "source_hash": source_hash(
            drill_id=drill_id,
            location=location,
            injury_type=injury_type,
            name=name,
            notes=notes,
        ),
        "location": location,
        "injury_type": injury_type,
        "name": name,
        "notes": notes,
        "movement_archetype": archetype,
        "proposed": propose_metadata(
            archetype=archetype, name=name, location=location, drill=drill
        ),
        "flags": detect_variable_demand_flags(notes),
        "review_state": REVIEW_STATE_NEEDS_REVIEW,
        "review_version": LEDGER_VERSION,
    }


def build_ledger(entries: list[dict], prior: list[dict] | None = None) -> list[dict]:
    """Return the ledger for ``entries``, carrying reviewed prior records verbatim."""
    reviewed_prior = {
        str(record.get("drill_id")): record
        for record in (prior or [])
        if isinstance(record, dict)
        and record.get("review_state") == REVIEW_STATE_REVIEWED
        and record.get("drill_id")
    }
    records: list[dict] = []
    for _group_index, _drill_index, location, injury_type, drill in iter_msk_drills(entries):
        drill_id = str(drill.get("id") or "")
        carried = reviewed_prior.get(drill_id)
        # A human review is preserved exactly as written — including its
        # review-time source hash, so a later source change is still visible as
        # staleness rather than being silently re-baselined.
        records.append(carried if carried is not None else _fresh_record(location, injury_type, drill))
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the ledger is out of date, writing nothing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    entries = load_bank(args.bank)
    prior = load_ledger(args.ledger)
    rendered = render_ledger(build_ledger(entries, prior))

    existing = args.ledger.read_text(encoding="utf-8") if args.ledger.exists() else None
    if args.check:
        if rendered == existing:
            print(f"{args.ledger.name} is up to date ({rendered.count('drill_id')} records).")
            return 0
        print(f"{args.ledger.name} is out of date (run without --check to regenerate).")
        return 1

    args.ledger.write_text(rendered, encoding="utf-8")
    record_count = len(build_ledger(entries, prior))
    print(f"Wrote {args.ledger.name}: {record_count} MSK review records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
