"""Validate active rehab content independently of mechanical classification."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fightcamp.rehab_clinical import (  # noqa: E402
    load_clinical_policies, load_pathway_catalog, validate_clinical_bank, validate_pathway_catalog,
)


def main() -> int:
    try:
        policies = load_clinical_policies()
        bank = json.loads((Path(__file__).resolve().parents[1] / "data" / "rehab_bank.json").read_text(encoding="utf-8"))
        catalog = load_pathway_catalog()
        errors = validate_pathway_catalog(catalog) + validate_clinical_bank(policies, bank)
    except (ValueError, KeyError, OSError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(error)
    if not errors:
        print(f"Rehab pathway families: {len(catalog.families)}; profiles: {len(policies)}; "
              f"active: {sum(p.status == 'active' for p in policies)}; "
              f"promotable transitions: {sum(t.promotable for p in policies for t in p.transitions)}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
