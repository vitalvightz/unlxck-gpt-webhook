"""Reproduce source vocabulary counts and the bounded fighter-query review."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.services.training_library import LibraryCache, search  # noqa: E402
from api.services.training_library_vocabulary import CONCEPTS  # noqa: E402
from fightcamp.training_catalogue import strings  # noqa: E402

FIELDS = ("tags", "qualities", "goals", "movement", "method", "system", "modality", "tactical_function", "body_region", "weaknesses", "category")


def audit() -> dict:
    index = LibraryCache().get()
    training = [record for record in index.records if record["summary"]["category"] == "training"]
    cases = json.loads((ROOT / "tools/training_library_search_cases.json").read_text(encoding="utf-8"))
    vocabulary = {}
    for field in FIELDS:
        counts = Counter(token for record in training for token in strings(record["entry"]["raw"].get(field)))
        mapped = {token for rule in CONCEPTS for group in rule.groups for source, tokens in group if source == field for token in tokens}
        vocabulary[field] = {
            "entries": sum(bool(strings(record["entry"]["raw"].get(field))) for record in training),
            "distinct": len(counts), "frequencies": dict(sorted(counts.items())),
            "tokens_mentioned_by_rules": sorted(set(counts).intersection(mapped)),
            "unmapped_tokens": sorted(set(counts) - mapped),
        }
    queries = []
    for case in cases["cases"]:
        result = search(index, q=case["query"], limit=3000)
        names = [entry["name"] for entry in result["entries"]]
        ranks = {name: names.index(name) + 1 for name in case["relevant"] if name in names}
        queries.append({**case, "total": result["total"], "anchor_ranks": ranks,
                        "missed": sorted(set(case["relevant"]) - set(names)),
                        "excluded_found": sorted(set(case["exclude"]).intersection(names)),
                        "top_five": [{key: entry[key] for key in ("name", "discovery_match")} for entry in result["entries"][:5]]})
    non_equipment = {rule for rule in CONCEPTS if rule.label not in {"Medicine ball", "Bodyweight", "Bands", "Kettlebells"}}
    return {
        "scope": cases["scope"], "training_entries": len(training),
        "baseline_commit": cases["baseline_commit"],
        "baseline_anchors_found": sum(len(case["baseline_anchors_found"]) for case in cases["cases"]),
        "baseline_exclusions_found": sum(len(case["baseline_exclusions_found"]) for case in cases["cases"]),
        "source_revisions": dict(sorted({record["entry"]["source"]: record["entry"]["source_sha256"] for record in training}.items())),
        "concepts": len(CONCEPTS), "phrases": len({phrase for rule in CONCEPTS for phrase in rule.phrases}),
        "entries_with_any_discovery_rule": sum(bool(record["discovery"]) for record in training),
        "entries_with_non_equipment_rule": sum(bool(non_equipment.intersection(record["discovery"])) for record in training),
        "unmapped_entry_names": [record["summary"]["name"] for record in training if not record["discovery"]],
        "goal_filter_entries": sum(bool(record["facets"]["goal"]) for record in training),
        "vocabulary": vocabulary, "queries": queries,
        "anchors_found": sum(len(query["anchor_ranks"]) for query in queries),
        "anchors_total": sum(len(query["relevant"]) for query in queries),
        "exclusions_found": sum(len(query["excluded_found"]) for query in queries),
        "exclusions_total": sum(len(query["exclude"]) for query in queries),
    }


def markdown(report: dict) -> str:
    lines = ["# Training library search review", "", report["scope"], "",
             f"The audit covers **{report['training_entries']} Training entries**, **{report['concepts']} reviewed concepts** and **{report['phrases']} distinct phrases**. "
             f"{report['entries_with_any_discovery_rule']} entries satisfy at least one rule; {report['entries_with_non_equipment_rule']} satisfy a non-equipment rule. "
             "These are vocabulary reach counts, not proof of relevant effects or complete intent coverage.", "",
             f"Goal-filter coverage remains **{report['goal_filter_entries']}/1,010**. Discovery synonyms do not add Goal values, change original tags, or grant prescription permission.", "",
             "## Source vocabulary", "", "Full token frequencies and unmapped tokens are in `training-library-search-audit.json`.", "",
             "| Field | Entries | Distinct values | Values mentioned by rules |",
             "| --- | ---: | ---: | ---: |"]
    for field, values in report["vocabulary"].items():
        lines.append(f"| {field} | {values['entries']} | {values['distinct']} | {len(values['tokens_mentioned_by_rules'])} |")
    lines += ["", "A token being mentioned is not enough when its rule requires combined evidence. Risk/loading tokens, sport/style identifiers, phase restrictions and injury-prevention promises are not converted wholesale into fighter goals. Free-text modality values remain directly searchable; selected exact values and source names support the taxonomy.", "",
              "## Query checks", "",
              f"**{report['anchors_found']}/{report['anchors_total']} reviewed positive anchors found; {report['exclusions_found']}/{report['exclusions_total']} exclusion controls returned.** "
              f"The initial PR implementation found {report['baseline_anchors_found']}/{report['anchors_total']} anchors and returned {report['baseline_exclusions_found']}/{report['exclusions_total']} exclusions against the same current sources. "
              "Anchor recall measures this finite review set, not exhaustive recall or precision across every result. Anchor ranks and the first five actual results are recorded in the JSON for review.", "",
              "| Fighter query | Before → now | Reviewed relevant examples | Missed anchors |",
              "| --- | ---: | --- | --- |"]
    for query in report["queries"]:
        examples = "; ".join(f"{name} (#{rank})" for name, rank in query["anchor_ranks"].items())
        lines.append(f"| {query['query']} | {query['baseline_total']} → {query['total']} | {examples} | {'; '.join(query['missed']) or 'None'} |")
    lines += ["", "## Gaps and decisions", "",
              "- The initial library returned four `punching power` matches. The revised results retain the two reviewed Goal aliases first, then punch-specific power, then labelled related rotational/upper-body power. Generic rotation, leg power and rebound risk alone do not qualify.",
              "- Review exposed false positives from combining words across aliases, row/foot speed appearing for hand speed, neck work appearing for grip endurance, and mobility work appearing for neck strength. Intent phrases are now evaluated as complete evidence groups, with explicit exclusion controls.",
              "- Some searches intentionally became smaller: `core stability` and `reaction speed` no longer accept unrelated mechanical-risk words scattered across source fields. Higher counts are not the acceptance target.",
              "- Broad conditioning intents such as gas tank still span several modalities and energy systems. Filters narrow discovery; these results are not equivalent doses or interchangeable prescriptions.",
              "- Source-body mobility records can cover several regions at once. Hip/ankle searches require both mobility and explicit regional evidence, but the source may still describe a combined support drill.",
              "- Goal labels are source-backed discovery metadata, not scientific effect certification. Expanded search phrases are deliberately separate. No missing goal/anatomy/sport is inferred.",
              "- Pain, injury clearance, concussion prevention and guaranteed performance outcomes are not assigned synonyms. Rehab remains a separate category requiring its pathway/stage and clinical rules.",
              "- The review set does not establish complete relevance across all 1,010 records. Remaining unmatched tokens and unmapped entries are listed in the JSON for future reviewed additions.", "",
              "## Reproduce", "", "`python tools/audit_training_library_search.py`", "",
              "`python -m pytest tests/test_training_library.py -q`", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = audit()
    outputs = {
        ROOT / "docs/training-library-search-audit.json": json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        ROOT / "docs/training-library-search-review.md": markdown(report),
    }
    for path, content in outputs.items():
        if args.check:
            if path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Search audit is stale: {path.name}")
        else:
            path.write_text(content, encoding="utf-8")
    print(f"{report['anchors_found']}/{report['anchors_total']} anchors; {report['exclusions_found']}/{report['exclusions_total']} exclusions returned")
