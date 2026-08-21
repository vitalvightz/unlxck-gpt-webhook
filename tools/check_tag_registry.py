#!/usr/bin/env python3
"""Block new tag-registry drift while bounded legacy source aliases are retired."""

from __future__ import annotations

from tools.audit_tag_registry import audit_registry


# Existing raw source aliases are tolerated temporarily so the authority gate can
# block all new drift without requiring risky whole-bank rewrites in this PR.
# This debt may shrink at any time; introducing a new alias or changing one of
# these mappings is a failure.
LEGACY_BANK_ALIAS_DEBT = {
    "boxer": "boxing",
    "breathing": "recovery",
    "rhythm": "coordination",
    "technical": "skill",
}


def authority_failures(report: dict) -> list[str]:
    failures: list[str] = []

    for key in (
        "aliases_in_vocabulary",
        "vocabulary_collisions",
        "bank_missing_vocab",
        "scoring_missing_vocab",
        "runtime_missing_vocab",
        "scoring_zero_bank_coverage",
    ):
        if report.get(key):
            failures.append(f"{key}: {report[key]}")

    bank_aliases = report.get("bank_aliases", {})
    unexpected_aliases = {
        raw: canonical
        for raw, canonical in bank_aliases.items()
        if LEGACY_BANK_ALIAS_DEBT.get(raw) != canonical
    }
    if unexpected_aliases:
        failures.append(f"unexpected_bank_aliases: {unexpected_aliases}")

    # Alias debt is allowed to disappear as banks are migrated. Do not require
    # all four legacy aliases to remain present.
    vocabulary = {
        row["tag"]
        for row in report.get("coverage", [])
        if row.get("in_vocabulary")
    }
    vocabulary.update(report.get("vocab_unused", []))
    vocabulary.update(report.get("bank_missing_vocab", []))
    vocabulary.update(report.get("runtime_missing_vocab", []))
    vocabulary.update(report.get("scoring_missing_vocab", []))

    missing_synonym_targets = sorted(
        set(report.get("synonym_canonicals", [])) - vocabulary
    )
    if missing_synonym_targets:
        failures.append(f"synonym_targets_missing_from_vocabulary: {missing_synonym_targets}")

    return failures


def main() -> int:
    report = audit_registry()
    failures = authority_failures(report)
    if failures:
        print("Tag authority gate failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    remaining_alias_debt = {
        raw: canonical
        for raw, canonical in report.get("bank_aliases", {}).items()
        if LEGACY_BANK_ALIAS_DEBT.get(raw) == canonical
    }
    print("Tag authority gate passed.")
    if remaining_alias_debt:
        print(f"Bounded legacy bank-alias debt remaining: {remaining_alias_debt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
