#!/usr/bin/env python3
"""Apply source-hash-verified reviewed metadata from the ledger into the rehab bank.

Deterministic and idempotent. Only ``review_state == "reviewed"`` records whose
stored source hash still matches the current drill are applied; a stale review
(source changed since it was reviewed) is skipped and reported, never applied
against different source material.

Applying a record writes only the ``proposed`` fields it explicitly classified
(non-null); a ``null`` proposed value means "still unresolved" and leaves the
bank untouched. Nothing outside the mechanical review fields is touched — dose,
pain_ceiling, severities and clinical rules belong to a later criteria PR — and
drill ids, ordering and wound-care groups are preserved exactly.

``--check`` writes nothing and exits non-zero when applying would change the
committed bank. ``--report`` prints what was applied and what was skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.rehab_metadata_review_lib import (  # noqa: E402
    DEFAULT_BANK,
    DEFAULT_LEDGER,
    REVIEW_FIELDS,
    REVIEW_STATE_REVIEWED,
    iter_msk_drills,
    load_ledger,
    render_bank,
    source_hash,
)


def _reviewed_by_id(ledger: list[dict]) -> dict[str, dict]:
    return {
        str(record.get("drill_id")): record
        for record in ledger
        if isinstance(record, dict)
        and record.get("review_state") == REVIEW_STATE_REVIEWED
        and record.get("drill_id")
    }


def apply_reviews(entries: list[dict], ledger: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Return ``(new_entries, applied_ids, stale_ids)`` — pure, no I/O.

    ``entries`` is deep-copied; input is never mutated.
    """
    reviewed = _reviewed_by_id(ledger)
    result = json.loads(json.dumps(entries))  # deep copy, order preserved
    applied: list[str] = []
    stale: list[str] = []
    for _group_index, _drill_index, location, injury_type, drill in iter_msk_drills(result):
        record = reviewed.get(str(drill.get("id") or ""))
        if record is None:
            continue
        current_hash = source_hash(
            drill_id=drill.get("id"),
            location=location,
            injury_type=injury_type,
            name=drill.get("name"),
            notes=drill.get("notes", ""),
        )
        if current_hash != record.get("source_hash"):
            stale.append(str(drill.get("id")))
            continue
        proposed = record.get("proposed") or {}
        wrote = False
        for field in REVIEW_FIELDS:
            value = proposed.get(field)
            if value is None:
                continue  # unresolved — leave the bank as it is
            if drill.get(field) != value:
                wrote = True
            drill[field] = value
        if wrote:
            applied.append(str(drill.get("id")))
    return result, applied, stale


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when applying would change the committed bank; write nothing",
    )
    parser.add_argument("--report", action="store_true", help="print applied/stale detail")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    original = args.bank.read_text(encoding="utf-8")
    entries = json.loads(original)
    ledger = load_ledger(args.ledger)
    new_entries, applied, stale = apply_reviews(entries, ledger)
    rendered = render_bank(new_entries)

    if args.report or args.check:
        print(f"reviewed applied: {len(applied)}  stale skipped: {len(stale)}")
        if args.report and stale:
            print("stale drill_ids:", ", ".join(sorted(stale)))

    if args.check:
        if rendered == original:
            print(f"{args.bank.name} already reflects reviewed metadata.")
            return 0
        print(f"{args.bank.name} is out of date with reviewed ledger metadata.")
        return 1

    args.bank.write_text(rendered, encoding="utf-8")
    print(f"Applied {len(applied)} reviewed record(s) to {args.bank.name} ({len(stale)} stale skipped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
