from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from fightcamp.bank_schema import KNOWN_SYSTEMS, SYSTEM_ALIASES
from fightcamp.injury_filtering import collect_banks
from fightcamp.tagging import load_tag_vocabulary, normalize_tags


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def normalize_system(raw: str | None) -> str:
    system = (raw or "").strip().lower()
    return SYSTEM_ALIASES.get(system, system or "unknown")


def audit_bank(name: str, items: list[dict], tag_vocab: set[str]) -> dict:
    counts = {
        "total": len(items),
        "missing_name": 0,
        "missing_tags": 0,
        "missing_phases": 0,
        "unknown_systems": 0,
        "unknown_tags": 0,
        "duplicate_names": 0,
    }
    name_counter = Counter()
    unknown_systems: Counter[str] = Counter()
    unknown_tags: Counter[str] = Counter()

    for item in items:
        name_value = item.get("name", "")
        if not str(name_value).strip():
            counts["missing_name"] += 1
        else:
            name_counter[str(name_value).strip()] += 1

        tags = normalize_tags(item.get("tags", []))
        if not tags:
            counts["missing_tags"] += 1
        if tag_vocab:
            for tag in tags:
                if tag not in tag_vocab:
                    unknown_tags[tag] += 1

        phases = item.get("phases")
        if phases is None or (isinstance(phases, list) and not phases):
            counts["missing_phases"] += 1

        if "system" in item:
            system = normalize_system(item.get("system"))
            if system not in KNOWN_SYSTEMS:
                unknown_systems[system] += 1

    counts["duplicate_names"] = sum(1 for _, count in name_counter.items() if count > 1)
    counts["unknown_systems"] = sum(unknown_systems.values())
    counts["unknown_tags"] = sum(unknown_tags.values())

    return {
        "counts": counts,
        "unknown_systems": unknown_systems,
        "unknown_tags": unknown_tags,
        "duplicate_names": [name for name, count in name_counter.items() if count > 1],
    }


def main() -> None:
    tag_vocab = load_tag_vocabulary()
    banks = collect_banks()
    summary_counts = defaultdict(int)

    print("🏦 Bank Audit Report")
    print("====================\n")

    for bank_name, items in banks.items():
        report = audit_bank(bank_name, items, tag_vocab)
        counts = report["counts"]
        print(f"Bank: {bank_name}")
        print(json.dumps(counts, indent=2))

        if report["unknown_systems"]:
            print("  Unknown systems:")
            for system, count in report["unknown_systems"].most_common():
                print(f"    - {system}: {count}")

        if report["unknown_tags"]:
            print("  Unknown tags:")
            for tag, count in report["unknown_tags"].most_common():
                print(f"    - {tag}: {count}")

        if report["duplicate_names"]:
            print("  Duplicate names:")
            for name in report["duplicate_names"]:
                print(f"    - {name}")

        print("")
        for key, value in counts.items():
            summary_counts[key] += value

    print("Summary")
    print(json.dumps(summary_counts, indent=2))


if __name__ == "__main__":
    main()
