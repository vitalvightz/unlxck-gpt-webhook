"""Extract unique rehab injury types from ``rehab_bank.json``.

Running this file prints the sorted injury types and also writes them to
``rehab_injury_types.txt`` in the same folder. It does not rely on the JSON
being perfectly formatted; it simply searches each line for a ``"type"`` field.
"""
from __future__ import annotations

import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BANK_FILE = DATA_DIR / "rehab_bank.json"
OUTPUT_FILE = Path(__file__).with_name("rehab_injury_types.txt")


def list_injury_types() -> list[str]:
    types = set()
    for line in BANK_FILE.read_text().splitlines():
        match = re.search(r'"type"\s*:\s*"([^"]+)"', line)
        if match:
            types.add(match.group(1))
    return sorted(types)


def main() -> None:
    types = list_injury_types()
    OUTPUT_FILE.write_text("\n".join(types) + "\n")
    for t in types:
        print(t)


if __name__ == "__main__":
    main()
