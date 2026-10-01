"""Validate active rehab content independently of mechanical classification."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fightcamp.rehab_clinical import load_clinical_policies, validate_clinical_bank  # noqa: E402


def main() -> int:
    try:
        policies = load_clinical_policies()
        bank = json.loads((Path(__file__).resolve().parents[1] / "data" / "rehab_bank.json").read_text(encoding="utf-8"))
        errors = validate_clinical_bank(policies, bank)
    except (ValueError, KeyError, OSError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(error)
    if not errors:
        print(f"Rehab policies valid: {len(policies)}; active: {sum(p.status == 'active' for p in policies)}")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
