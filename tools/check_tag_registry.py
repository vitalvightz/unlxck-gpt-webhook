#!/usr/bin/env python3
"""Blocking authority gate for canonical bank/scoring/safety tags."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.tag_vocabulary import read_tag_vocabulary_items  # noqa: E402
from tools.audit_tag_registry import DATA_DIR, audit_registry  # noqa: E402
from tools.injury_tag_authority import collect_generated_injury_tags  # noqa: E402

FIELD_ONLY_TOKENS = {"late_windows", "cut_buckets_allowed"}
REVIEW_PATH = DATA_DIR / "tag_registry_review.json"
VALID_REVIEW_DECISIONS = {"allow_canonical", "remove_from_tags"}


def load_review_decisions(path: Path = REVIEW_PATH) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    decisions = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(decisions, dict) or not decisions:
        raise ValueError("tag_registry_review.json must contain non-empty decisions")
    return decisions


def authority_failures(
    report: dict,
    vocabulary: set[str],
    *,
    generated_injury_tags: set[str] | None = None,
    review_decisions: dict[str, dict] | None = None,
) -> list[str]:
    failures: list[str] = []

    for key in (
        "aliases_in_vocabulary",
        "vocabulary_collisions",
        "bank_aliases",
        "bank_missing_vocab",
        "scoring_missing_vocab",
        "runtime_missing_vocab",
        "scoring_zero_bank_coverage",
    ):
        if report.get(key):
            failures.append(f"{key}: {report[key]}")

    missing_synonym_targets = sorted(set(report.get("synonym_canonicals", [])) - vocabulary)
    if missing_synonym_targets:
        failures.append(f"synonym_targets_missing_from_vocabulary: {missing_synonym_targets}")

    field_tokens_in_vocab = sorted(FIELD_ONLY_TOKENS & vocabulary)
    if field_tokens_in_vocab:
        failures.append(f"metadata_field_names_in_vocabulary: {field_tokens_in_vocab}")

    injury_tags = generated_injury_tags or set()
    missing_injury_tags = sorted(injury_tags - vocabulary)
    if missing_injury_tags:
        failures.append(f"generated_injury_tags_missing_from_vocabulary: {missing_injury_tags}")

    decisions = review_decisions or {}
    bank_tags = set(report.get("bank_tag_details", {}))
    for tag, row in sorted(decisions.items()):
        if not isinstance(row, dict):
            failures.append(f"invalid_review_decision:{tag}")
            continue
        decision = row.get("decision")
        category = str(row.get("category") or "").strip()
        rationale = str(row.get("rationale") or "").strip()
        if decision not in VALID_REVIEW_DECISIONS or not category or not rationale:
            failures.append(f"invalid_review_decision:{tag}")
            continue
        if decision == "allow_canonical":
            if tag not in vocabulary or tag not in bank_tags:
                failures.append(f"reviewed_canonical_tag_not_live:{tag}")
        elif decision == "remove_from_tags":
            if tag in vocabulary or tag in bank_tags:
                failures.append(f"reviewed_removed_tag_still_live:{tag}")

    return failures


def main() -> int:
    report = audit_registry()
    vocabulary = set(read_tag_vocabulary_items(DATA_DIR / "tag_vocabulary.json"))
    injury_tags = collect_generated_injury_tags()
    review_decisions = load_review_decisions()
    failures = authority_failures(
        report,
        vocabulary,
        generated_injury_tags=injury_tags,
        review_decisions=review_decisions,
    )
    if failures:
        print("Tag authority gate failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("Tag authority gate passed.")
    print(f"Generated injury/safety tags covered: {len(injury_tags)}")
    print(f"Reviewed bank-only decisions enforced: {len(review_decisions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
