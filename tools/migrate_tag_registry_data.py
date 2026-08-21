#!/usr/bin/env python3
"""Apply/check the persisted-data cleanup required by tag authority."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
STRENGTH_PATH = REPO_ROOT / "fightcamp" / "strength.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.tag_vocabulary import read_tag_vocabulary_items  # noqa: E402
from tools.validate_banks import discover_banks  # noqa: E402


BANK_ALIASES = {
    "boxer": "boxing",
    "breathing": "recovery",
    "rhythm": "coordination",
    "technical": "skill",
}

# These strings describe setup/load rather than semantic training taxonomy.
REMOVE_FROM_BANK_TAGS = {
    "bodyweight",
    "light_band",
    "partner",
    "supported",
    "wall_supported",
    # Structured field names must never be persisted inside a tags array.
    "late_windows",
    "cut_buckets_allowed",
}

REMOVE_FROM_VOCABULARY = set(REMOVE_FROM_BANK_TAGS)
ADD_TO_VOCABULARY = {"generic"}


_STRENGTH_REPLACEMENTS = (
    (
        'if late_window and ("late_windows" in tags or late_window in late_windows or "all" in late_windows):',
        'if late_window and (late_window in late_windows or "all" in late_windows):',
    ),
    (
        'if cut_bucket and (\n            "cut_buckets_allowed" in tags\n            or cut_bucket in cut_buckets_allowed\n            or "all" in cut_buckets_allowed\n        ):',
        'if cut_bucket and (\n            cut_bucket in cut_buckets_allowed\n            or "all" in cut_buckets_allowed\n        ):',
    ),
)


def _ensure_generic_tactical_watch_tag(value: dict[str, Any]) -> int:
    """Keep generic.* Tactical Watch records aligned with their runtime style family."""
    key = str(value.get("key") or "").strip()
    tags = value.get("tags")
    if not key.startswith("generic.") or not isinstance(tags, list):
        return 0
    if "tactical_watch" not in tags or "generic" in tags:
        return 0

    insert_at = tags.index("tactical_watch") + 1
    tags.insert(insert_at, "generic")
    return 1


def _migrate_tag_lists(value: Any) -> int:
    changes = 0
    if isinstance(value, dict):
        tags = value.get("tags")
        if isinstance(tags, list):
            migrated: list[Any] = []
            seen: set[str] = set()
            for item in tags:
                if not isinstance(item, str):
                    migrated.append(item)
                    continue
                stripped = item.strip()
                if stripped in REMOVE_FROM_BANK_TAGS:
                    changes += 1
                    continue
                canonical = BANK_ALIASES.get(stripped, stripped)
                if canonical != stripped:
                    changes += 1
                if canonical in seen:
                    changes += 1
                    continue
                migrated.append(canonical)
                seen.add(canonical)
            if migrated != tags:
                value["tags"] = migrated
        changes += _ensure_generic_tactical_watch_tag(value)
        for key, child in value.items():
            if key != "tags":
                changes += _migrate_tag_lists(child)
    elif isinstance(value, list):
        for child in value:
            changes += _migrate_tag_lists(child)
    return changes


def _migrated_json_text(path: Path) -> tuple[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    changes = _migrate_tag_lists(data)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", changes


def _migrated_vocabulary_text(path: Path) -> tuple[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = read_tag_vocabulary_items(path)
    migrated = [tag for tag in items if tag not in REMOVE_FROM_VOCABULARY]
    changes = len(items) - len(migrated)
    for tag in sorted(ADD_TO_VOCABULARY):
        if tag not in migrated:
            migrated.append(tag)
            changes += 1

    # Preserve whichever supported schema the shared parser accepted.
    if isinstance(data, list):
        payload: Any = migrated
    else:
        payload = dict(data)
        key = "items" if isinstance(data.get("items"), list) else "data"
        payload[key] = migrated

    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n", changes


def _migrated_strength_text(path: Path) -> tuple[str, int]:
    text = path.read_text(encoding="utf-8")
    migrated = text
    changes = 0
    for old, new in _STRENGTH_REPLACEMENTS:
        if old in migrated:
            migrated = migrated.replace(old, new)
            changes += 1
    return migrated, changes


def planned_changes() -> list[tuple[Path, str, int]]:
    changes: list[tuple[Path, str, int]] = []
    for path in discover_banks(DATA_DIR):
        text, count = _migrated_json_text(path)
        if count:
            changes.append((path, text, count))

    vocab_path = DATA_DIR / "tag_vocabulary.json"
    vocab_text, vocab_count = _migrated_vocabulary_text(vocab_path)
    if vocab_count:
        changes.append((vocab_path, vocab_text, vocab_count))

    strength_text, strength_count = _migrated_strength_text(STRENGTH_PATH)
    if strength_count:
        changes.append((STRENGTH_PATH, strength_text, strength_count))
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if migration changes are still required")
    args = parser.parse_args(argv)

    changes = planned_changes()
    if not changes:
        print("Tag registry persisted-data migration is up to date.")
        return 0

    for path, _text, count in changes:
        print(f"{path.relative_to(REPO_ROOT)}: {count} migration change(s)")

    if args.check:
        print("Tag registry persisted-data migration is not up to date.")
        return 1

    for path, text, _count in changes:
        path.write_text(text, encoding="utf-8")
    print("Applied tag registry persisted-data migration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
