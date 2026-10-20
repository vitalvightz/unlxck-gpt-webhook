"""Read-only proof for the narrowly reviewed vocabulary retirement.

The original 196-item audit remains immutable. Absence from a bank is never
sufficient: keep generated safety tags, aliases, scoring and historical uses.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fightcamp.tag_vocabulary import read_tag_vocabulary_items  # noqa: E402
from fightcamp.tagging import TAG_SYNONYMS, normalize_tag  # noqa: E402
from tools.audit_tag_registry import audit_registry  # noqa: E402
from tools.check_tag_registry import authority_failures, load_review_decisions  # noqa: E402
from tools.injury_tag_authority import collect_generated_injury_tags  # noqa: E402

REVIEW = ROOT / "tools/tag_retirement_review.json"
REGISTER = ROOT / "reports/metadata_integrity/remediation.json"
VOCABULARY = ROOT / "data/tag_vocabulary.json"
TEXT_SUFFIXES = {".py", ".json", ".ts", ".tsx", ".js", ".mjs", ".cjs",
                 ".sql", ".yml", ".yaml", ".toml", ".html", ".sh", ".ps1"}


def digest(path: Path) -> str:
    # Match the existing LF-normalized source evidence across Git checkouts.
    from tools.replay_combat_round_metadata import pre_combat_round_source
    from tools.replay_safety_metadata import original_safety_source
    relative = path.relative_to(ROOT).as_posix()
    return hashlib.sha256(pre_combat_round_source(relative, original_safety_source(relative, path.read_bytes()))).hexdigest()


def original_vocabulary_source(current: bytes) -> bytes:
    """Reconstruct frozen audit evidence, accepting only the exact 16-line edit.

    Audit replay additionally verifies these bytes against its original digest.
    This adapter is never used by the planner or bank validation.
    """
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    original = (json.dumps(review["original_vocabulary"], indent=2) + "\n").encode()
    removed_lines = {b'  "' + tag.encode() + b'",\n' for tag in review["retired_tags"]}
    expected = b"".join(line for line in original.splitlines(keepends=True) if line not in removed_lines)
    if current.replace(b"\r\n", b"\n") != expected:
        raise ValueError("Unreviewed tag vocabulary drift")
    return original


def reference_paths() -> list[Path]:
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    # Include archived data, migrations, deployment configuration and tooling.
    # Frozen audit snapshots are evidence, rather than active consumers.
    excluded = {"tools/metadata_integrity_original_sources.json",
                "tools/tag_retirement_review.json",
                "tools/metadata_integrity_baseline.json",
                "tools/canonical_metadata_baseline.json",
                "tools/metadata_integrity_review.json"}
    return [ROOT / name for name in tracked if name and
            Path(name).suffix in TEXT_SUFFIXES and name not in excluded and
            name != "data/tag_vocabulary.json" and
            not name.startswith(("reports/", "tests/", "web/e2e/", "docs/", "notes/"))]


def token_references(tags: set[str], paths: list[Path]) -> dict[str, list[dict]]:
    """Conservative literal scan, including lowercase/spaced legacy spellings.

    Spaced matches are retained separately: prose mentions must be reviewed,
    but do not by themselves declare tags or make normalization vocabulary-bound.
    """
    result = {tag: [] for tag in sorted(tags)}
    if not tags:
        return result
    forms = {tag: tag for tag in tags}
    for tag in tags:
        forms[tag.replace("_", " ")] = tag
        forms[tag.replace("_", "-")] = tag
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(s) for s in sorted(forms)) + r")(?![\w])", re.I)
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in pattern.finditer(line):
                form = match.group().lower()
                result[forms[form]].append({
                    "file": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name,
                    "line": line_number, "form": form,
                    "kind": "identifier" if form == forms[form] else "legacy_spelling_or_prose",
                })
    return result


def retirement_failures(review: dict, registry: dict, references: dict) -> list[str]:
    retired = set(review["retired_tags"])
    failures = []
    protected = (set(registry["bank_tag_details"]) |
                 set(registry["scoring_sources_by_tag"]) |
                 set(registry["runtime_files_by_tag"]) |
                 collect_generated_injury_tags() |
                 {normalize_tag(value) for value in TAG_SYNONYMS.values()})
    if retired & protected:
        failures.append("Retirement touches active tag authority: " + str(sorted(retired & protected)))
    for tag, receipts in references.items():
        for receipt in receipts:
            if receipt["kind"] == "identifier" or receipt not in review["retained_prose_references"].get(tag, []):
                failures.append("Unreviewed consumer: " + tag + " " + str(receipt))
    return failures


def main() -> int:
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    original = json.loads(REGISTER.read_text(encoding="utf-8"))["issues"]
    classified = review["findings"]
    failures = []
    if digest(REGISTER) != review["original_register_sha256"]:
        failures.append("Original audit register changed")
    if len(classified) != len(original) or {x["issue_id"] for x in classified} != {x["issue_id"] for x in original}:
        failures.append("Every audit finding must be classified exactly once")
    if any(x["classification"] not in {"confirmed_defect", "intentional_distinction", "requires_investigation"} or
           not x["rationale"] for x in classified):
        failures.append("Invalid classification or missing rationale")
    retired = set(review["retired_tags"])
    vocabulary = read_tag_vocabulary_items(VOCABULARY)
    if vocabulary != [tag for tag in review["original_vocabulary"] if tag not in retired]:
        failures.append("Vocabulary changed beyond the reviewed retirement (including order)")
    for name, expected in review["protected_source_sha256"].items():
        if digest(ROOT / name) != expected:
            failures.append("Protected bank/configuration/history changed: " + name)
    registry = audit_registry()
    failures.extend(authority_failures(registry, set(vocabulary),
                                      generated_injury_tags=collect_generated_injury_tags(),
                                      review_decisions=load_review_decisions()))
    paths = reference_paths()
    failures.extend(retirement_failures(review, registry, token_references(retired, paths)))
    if failures:
        print("Tag retirement check failed:\n" + "\n".join(failures))
        return 1
    print(f"Tag retirement check passed: {len(classified)} classified findings; "
          f"{len(retired)} retired declarations; {len(vocabulary)} retained tags; "
          f"{len(paths)} scanned production/configuration/tooling files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
