#!/usr/bin/env python3
"""Audit canonical bank tags, scoring coverage, aliases, and runtime tag controls."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
FIGHTCAMP_DIR = REPO_ROOT / "fightcamp"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.tag_maps import GOAL_TAG_MAP, STYLE_TAG_MAP, WEAKNESS_TAG_MAP  # noqa: E402
from fightcamp.tag_vocabulary import read_tag_vocabulary_items  # noqa: E402
from fightcamp.tagging import TAG_SYNONYMS, normalize_tag  # noqa: E402
from tools.validate_banks import discover_banks  # noqa: E402


SKIP_RUNTIME_SCAN = {
    "tag_maps.py",
    "tag_vocabulary.py",
    "tagging.py",
}


def _is_tag_constant_name(name: str) -> bool:
    upper = name.upper()
    return (
        upper == "TAGS"
        or upper.endswith("_TAG")
        or upper.endswith("_TAGS")
        or "_TAG_" in upper
    )


def _canonical(value: str) -> str:
    return normalize_tag(value) or ""


def _iter_tag_lists(value: Any) -> Iterable[list[str]]:
    if isinstance(value, dict):
        tags = value.get("tags")
        if isinstance(tags, list):
            yield [tag for tag in tags if isinstance(tag, str)]
        for key, child in value.items():
            if key != "tags":
                yield from _iter_tag_lists(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_tag_lists(child)


def collect_bank_tags(paths: Iterable[Path]) -> dict[str, Any]:
    raw_counts: Counter[str] = Counter()
    canonical_counts: Counter[str] = Counter()
    files_by_tag: dict[str, set[str]] = defaultdict(set)
    raw_forms_by_canonical: dict[str, set[str]] = defaultdict(set)

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for tags in _iter_tag_lists(data):
            for raw in tags:
                stripped = raw.strip()
                canonical = _canonical(stripped)
                if not stripped or not canonical:
                    continue
                raw_counts[stripped] += 1
                canonical_counts[canonical] += 1
                files_by_tag[canonical].add(path.name)
                raw_forms_by_canonical[canonical].add(stripped)

    aliases = {
        raw: _canonical(raw)
        for raw in sorted(raw_counts)
        if _canonical(raw) and _canonical(raw) != raw
    }
    return {
        "raw_counts": raw_counts,
        "canonical_counts": canonical_counts,
        "files_by_tag": files_by_tag,
        "raw_forms_by_canonical": raw_forms_by_canonical,
        "aliases": aliases,
    }


def _mapping_tags(mapping: dict[str, list[str]]) -> set[str]:
    tags: set[str] = set()
    for values in mapping.values():
        for value in values:
            canonical = _canonical(value)
            if canonical:
                tags.add(canonical)
    return tags


def collect_scoring_tags() -> dict[str, set[str]]:
    return {
        "goal": _mapping_tags(GOAL_TAG_MAP),
        "weakness": _mapping_tags(WEAKNESS_TAG_MAP),
        "style": _mapping_tags(STYLE_TAG_MAP),
    }


def _literal_strings(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    values: set[str] = set()
    for child in ast.iter_child_nodes(node):
        values.update(_literal_strings(child))
    return values


def _expr_mentions_tags(node: ast.AST | None) -> bool:
    if node is None:
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and "tag" in child.id.lower():
            return True
        if isinstance(child, ast.Attribute) and "tag" in child.attr.lower():
            return True
    return False


class RuntimeTagVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.tags: set[str] = set()

    def _add(self, values: Iterable[str]) -> None:
        for value in values:
            canonical = _canonical(value)
            if canonical:
                self.tags.add(canonical)

    def visit_Assign(self, node: ast.Assign) -> None:
        names = [
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        ]
        if any(_is_tag_constant_name(name) for name in names):
            self._add(_literal_strings(node.value))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and _is_tag_constant_name(node.target.id):
            self._add(_literal_strings(node.value))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        left = node.left
        comparators = node.comparators
        for op, right in zip(node.ops, comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                if _expr_mentions_tags(right):
                    self._add(_literal_strings(left))
                if _expr_mentions_tags(left):
                    self._add(_literal_strings(right))
            left = right
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            if _expr_mentions_tags(node.left):
                self._add(_literal_strings(node.right))
            if _expr_mentions_tags(node.right):
                self._add(_literal_strings(node.left))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"intersection", "issubset", "isdisjoint"}
            and _expr_mentions_tags(node.func.value)
        ):
            for arg in node.args:
                self._add(_literal_strings(arg))
        self.generic_visit(node)


def collect_runtime_control_tags(source_dir: Path = FIGHTCAMP_DIR) -> dict[str, set[str]]:
    tags_by_file: dict[str, set[str]] = {}
    for path in sorted(source_dir.glob("*.py")):
        if path.name in SKIP_RUNTIME_SCAN:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        visitor = RuntimeTagVisitor()
        visitor.visit(tree)
        if visitor.tags:
            tags_by_file[path.name] = visitor.tags
    return tags_by_file


def audit_registry(data_dir: Path = DATA_DIR) -> dict[str, Any]:
    vocab_path = data_dir / "tag_vocabulary.json"
    raw_vocab = read_tag_vocabulary_items(vocab_path)
    canonical_vocab = {_canonical(tag) for tag in raw_vocab if _canonical(tag)}

    aliases_in_vocabulary = {
        raw: _canonical(raw)
        for raw in raw_vocab
        if _canonical(raw) and _canonical(raw) != raw
    }

    raw_vocab_by_canonical: dict[str, set[str]] = defaultdict(set)
    for raw in raw_vocab:
        canonical = _canonical(raw)
        if canonical:
            raw_vocab_by_canonical[canonical].add(raw)
    vocabulary_collisions = {
        canonical: sorted(raws)
        for canonical, raws in raw_vocab_by_canonical.items()
        if len(raws) > 1
    }

    bank_paths = discover_banks(data_dir)
    bank = collect_bank_tags(bank_paths)
    bank_tags = set(bank["canonical_counts"])

    scoring_by_source = collect_scoring_tags()
    scoring_tags = set().union(*scoring_by_source.values())

    runtime_by_file = collect_runtime_control_tags()
    runtime_tags = set().union(*runtime_by_file.values()) if runtime_by_file else set()

    scoring_missing_vocab = sorted(scoring_tags - canonical_vocab)
    runtime_missing_vocab = sorted(runtime_tags - canonical_vocab)
    bank_missing_vocab = sorted(bank_tags - canonical_vocab)
    code_owned_missing = sorted(
        (scoring_tags | runtime_tags) - canonical_vocab
    )
    unknown_bank_only = sorted(
        (bank_tags - canonical_vocab) - scoring_tags - runtime_tags
    )
    scoring_zero_bank_coverage = sorted(scoring_tags - bank_tags)
    vocab_unused = sorted(canonical_vocab - bank_tags - scoring_tags - runtime_tags)

    coverage = []
    for tag in sorted(scoring_tags):
        coverage.append(
            {
                "tag": tag,
                "bank_occurrences": int(bank["canonical_counts"].get(tag, 0)),
                "banks": sorted(bank["files_by_tag"].get(tag, set())),
                "in_vocabulary": tag in canonical_vocab,
                "goal": tag in scoring_by_source["goal"],
                "weakness": tag in scoring_by_source["weakness"],
                "style": tag in scoring_by_source["style"],
            }
        )

    return {
        "vocabulary_raw_count": len(raw_vocab),
        "vocabulary_canonical_count": len(canonical_vocab),
        "bank_file_count": len(bank_paths),
        "bank_unique_tag_count": len(bank_tags),
        "scoring_unique_tag_count": len(scoring_tags),
        "runtime_unique_tag_count": len(runtime_tags),
        "aliases_in_vocabulary": aliases_in_vocabulary,
        "vocabulary_collisions": vocabulary_collisions,
        "bank_aliases": bank["aliases"],
        "bank_missing_vocab": bank_missing_vocab,
        "scoring_missing_vocab": scoring_missing_vocab,
        "runtime_missing_vocab": runtime_missing_vocab,
        "code_owned_missing": code_owned_missing,
        "unknown_bank_only": unknown_bank_only,
        "scoring_zero_bank_coverage": scoring_zero_bank_coverage,
        "vocab_unused": vocab_unused,
        "coverage": coverage,
        "runtime_by_file": {
            name: sorted(tags) for name, tags in sorted(runtime_by_file.items())
        },
        "synonym_canonicals": sorted(
            {
                canonical
                for canonical in (_canonical(value) for value in TAG_SYNONYMS.values())
                if canonical
            }
        ),
    }


def _emit_list(title: str, values: Iterable[str], *, emit=print) -> None:
    values = list(values)
    emit(f"\n{title}: {len(values)}")
    for value in values:
        emit(f"  - {value}")


def _emit_mapping(title: str, mapping: dict[str, Any], *, emit=print) -> None:
    emit(f"\n{title}: {len(mapping)}")
    for key in sorted(mapping):
        emit(f"  - {key} -> {mapping[key]}")


def print_report(report: dict[str, Any], *, emit=print) -> None:
    emit("=" * 48)
    emit("TAG REGISTRY AUDIT")
    emit("=" * 48)
    emit(
        "Vocabulary: "
        f"raw={report['vocabulary_raw_count']} "
        f"canonical={report['vocabulary_canonical_count']}"
    )
    emit(
        "Coverage: "
        f"banks={report['bank_file_count']} "
        f"bank_tags={report['bank_unique_tag_count']} "
        f"scoring_tags={report['scoring_unique_tag_count']} "
        f"runtime_tags={report['runtime_unique_tag_count']}"
    )

    _emit_mapping("Aliases in vocabulary", report["aliases_in_vocabulary"], emit=emit)
    _emit_mapping("Vocabulary normalization collisions", report["vocabulary_collisions"], emit=emit)
    _emit_mapping("Non-canonical aliases used in banks", report["bank_aliases"], emit=emit)
    _emit_list("Code-owned tags missing from vocabulary", report["code_owned_missing"], emit=emit)
    _emit_list("Scoring tags missing from vocabulary", report["scoring_missing_vocab"], emit=emit)
    _emit_list("Runtime control tags missing from vocabulary", report["runtime_missing_vocab"], emit=emit)
    _emit_list("Bank tags missing from vocabulary", report["bank_missing_vocab"], emit=emit)
    _emit_list("Unknown bank-only tags requiring review", report["unknown_bank_only"], emit=emit)
    _emit_list("Scoring tags with zero bank coverage", report["scoring_zero_bank_coverage"], emit=emit)
    _emit_list("Vocabulary tags unused by banks/scoring/runtime", report["vocab_unused"], emit=emit)

    emit("\nSCORING COVERAGE")
    for row in report["coverage"]:
        sources = ",".join(
            source
            for source in ("goal", "weakness", "style")
            if row[source]
        )
        banks = ",".join(row["banks"]) or "-"
        emit(
            f"  - {row['tag']}: occurrences={row['bank_occurrences']} "
            f"banks={banks} sources={sources} "
            f"vocab={'yes' if row['in_vocabulary'] else 'NO'}"
        )


def check_failures(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    checks = {
        "aliases_in_vocabulary": report["aliases_in_vocabulary"],
        "vocabulary_collisions": report["vocabulary_collisions"],
        "bank_aliases": report["bank_aliases"],
        "bank_missing_vocab": report["bank_missing_vocab"],
        "scoring_missing_vocab": report["scoring_missing_vocab"],
        "runtime_missing_vocab": report["runtime_missing_vocab"],
        "scoring_zero_bank_coverage": report["scoring_zero_bank_coverage"],
    }
    for name, values in checks.items():
        if values:
            failures.append(name)
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="directory containing tag_vocabulary.json and training banks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the complete audit report as JSON",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when tag-authority invariants are violated",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_registry(args.data_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_report(report)

    if args.check:
        failures = check_failures(report)
        if failures:
            print("\nTag registry check failed: " + ", ".join(failures))
            return 1
        print("\nTag registry check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
