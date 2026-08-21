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

from fightcamp.config import PHASE_TAG_BOOST  # noqa: E402
from fightcamp.priority_clarification_tags import (  # noqa: E402
    CLARIFICATION_DETAIL_TAG_MAP,
    _GENERIC_OVERALL_BY_ENTRY_TAG,
)
from fightcamp.tag_maps import GOAL_TAG_MAP, STYLE_TAG_MAP, WEAKNESS_TAG_MAP  # noqa: E402
from fightcamp.tag_vocabulary import read_tag_vocabulary_items  # noqa: E402
from fightcamp.tagging import TAG_SYNONYMS, normalize_tag  # noqa: E402
from tools.validate_banks import discover_banks  # noqa: E402


# Only constants that are actually interpreted as bank tags at runtime belong
# here. This explicit contract avoids mistaking HTML tags, injury text tokens,
# equipment names, or other unrelated string constants for bank-tag controls.
RUNTIME_BANK_TAG_CONSTANTS: dict[str, set[str]] = {
    "bank_schema.py": {
        "BALLISTIC_TAGS",
        "PRIMER_ONLY_TAGS",
        "STRENGTH_FULFILLMENT_TAGS",
    },
    "conditioning.py": {
        "TAPER_AVOID_TAGS",
        "LATE_CONDITIONING_SAFE_TAGS",
        "_GAS_TANK_SAFE_TAGS",
    },
    "strength.py": {
        "LATE_STRENGTH_SAFE_TAGS",
        "STRENGTH_MAINTENANCE_INTENT_TAGS",
        "STRENGTH_MAINTENANCE_MATCH_TAGS",
        "PRIMER_ONLY_STRENGTH_TOUCH_TAGS",
        "STRENGTH_MAINTENANCE_SUPPORT_TAGS",
        "LATE_SAFE_STRENGTH_FIELDS",
    },
    "strength_session_quality.py": {
        "_LOWER_BODY_JUMP_TAGS",
        "_LOWER_BODY_HIP_BALLISTIC_TAGS",
        "_ROTATIONAL_POWER_TAGS",
        "_UPPER_BODY_BALLISTIC_TAGS",
        "_CORE_BALANCE_SUPPORT_TAGS",
    },
}

# Some runtime tag contracts are encoded as the first element of a tuple where
# the remaining values are text-matching hints rather than tags.
RUNTIME_FIRST_TUPLE_TAG_CONSTANTS: dict[str, set[str]] = {
    "injury_filtering.py": {"MECH_KEYWORDS"},
}

RUNTIME_TAG_SOURCE_FILES = set(RUNTIME_BANK_TAG_CONSTANTS) | set(RUNTIME_FIRST_TUPLE_TAG_CONSTANTS)
BANK_TAG_COLLECTION_NAMES = {
    "tags",
    "tags_lower",
    "exercise_tags",
    "item_tags",
    "normalized_tags",
}


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


def _phase_scoring_tags() -> set[str]:
    tags: set[str] = set()
    for values in PHASE_TAG_BOOST.values():
        if not isinstance(values, dict):
            continue
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
        "clarification_detail": _mapping_tags(CLARIFICATION_DETAIL_TAG_MAP),
        "clarification_generic": _mapping_tags(_GENERIC_OVERALL_BY_ENTRY_TAG),
        "phase": _phase_scoring_tags(),
    }


def _literal_strings(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    values: set[str] = set()
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        for child in node.elts:
            values.update(_literal_strings(child))
    elif isinstance(node, ast.Call) and node.args:
        # Support frozenset({...}) and set({...}) without recursively walking
        # unrelated call arguments.
        func_name = node.func.id if isinstance(node.func, ast.Name) else ""
        if func_name in {"set", "frozenset", "list", "tuple"}:
            values.update(_literal_strings(node.args[0]))
    return values


def _first_tuple_strings(node: ast.AST | None) -> set[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return set()
    values: set[str] = set()
    for child in node.elts:
        if not isinstance(child, (ast.List, ast.Tuple)) or not child.elts:
            continue
        first = child.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            values.add(first.value)
    return values


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _expr_is_tag_collection(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in BANK_TAG_COLLECTION_NAMES
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name == "normalize_tags":
            return True
        if name == "get" and node.args:
            first = node.args[0]
            return isinstance(first, ast.Constant) and first.value == "tags"
        if name in {"set", "list", "tuple", "frozenset"} and node.args:
            return _expr_is_tag_collection(node.args[0])
    return False


class RuntimeTagVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        allowed_constants: set[str],
        first_tuple_constants: set[str],
    ) -> None:
        self.tags: set[str] = set()
        self.allowed_constants = allowed_constants
        self.first_tuple_constants = first_tuple_constants
        self.constant_values: dict[str, set[str]] = {}

    def _add(self, values: Iterable[str]) -> None:
        for value in values:
            canonical = _canonical(value)
            if canonical:
                self.tags.add(canonical)

    def _values_for_expr(self, node: ast.AST | None) -> set[str]:
        if isinstance(node, ast.Name) and node.id in self.constant_values:
            return set(self.constant_values[node.id])
        return _literal_strings(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        for name in names:
            if name in self.allowed_constants:
                values = _literal_strings(node.value)
                self.constant_values[name] = values
                self._add(values)
            elif name in self.first_tuple_constants:
                values = _first_tuple_strings(node.value)
                self.constant_values[name] = values
                self._add(values)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            name = node.target.id
            if name in self.allowed_constants:
                values = _literal_strings(node.value)
                self.constant_values[name] = values
                self._add(values)
            elif name in self.first_tuple_constants:
                values = _first_tuple_strings(node.value)
                self.constant_values[name] = values
                self._add(values)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        left = node.left
        for op, right in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)):
                if _expr_is_tag_collection(right):
                    self._add(self._values_for_expr(left))
                if _expr_is_tag_collection(left):
                    self._add(self._values_for_expr(right))
            left = right
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            if _expr_is_tag_collection(node.left):
                self._add(self._values_for_expr(node.right))
            if _expr_is_tag_collection(node.right):
                self._add(self._values_for_expr(node.left))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"intersection", "issubset", "isdisjoint"}
            and _expr_is_tag_collection(node.func.value)
        ):
            for arg in node.args:
                self._add(self._values_for_expr(arg))
        self.generic_visit(node)


def collect_runtime_control_tags(source_dir: Path = FIGHTCAMP_DIR) -> dict[str, set[str]]:
    tags_by_file: dict[str, set[str]] = {}
    for filename in sorted(RUNTIME_TAG_SOURCE_FILES):
        path = source_dir / filename
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        visitor = RuntimeTagVisitor(
            allowed_constants=RUNTIME_BANK_TAG_CONSTANTS.get(filename, set()),
            first_tuple_constants=RUNTIME_FIRST_TUPLE_TAG_CONSTANTS.get(filename, set()),
        )
        visitor.visit(tree)
        if visitor.tags:
            tags_by_file[filename] = visitor.tags
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
    code_owned_missing = sorted((scoring_tags | runtime_tags) - canonical_vocab)
    unknown_bank_only = sorted((bank_tags - canonical_vocab) - scoring_tags - runtime_tags)
    scoring_zero_bank_coverage = sorted(scoring_tags - bank_tags)
    runtime_zero_bank_coverage = sorted(runtime_tags - bank_tags)
    vocab_unused = sorted(canonical_vocab - bank_tags - scoring_tags - runtime_tags)

    runtime_files_by_tag: dict[str, list[str]] = {}
    for tag in sorted(runtime_tags):
        runtime_files_by_tag[tag] = sorted(
            filename for filename, tags in runtime_by_file.items() if tag in tags
        )

    scoring_sources_by_tag: dict[str, list[str]] = {}
    for tag in sorted(scoring_tags):
        scoring_sources_by_tag[tag] = [
            source for source, tags in scoring_by_source.items() if tag in tags
        ]

    bank_tag_details = {
        tag: {
            "occurrences": int(bank["canonical_counts"].get(tag, 0)),
            "banks": sorted(bank["files_by_tag"].get(tag, set())),
            "raw_forms": sorted(bank["raw_forms_by_canonical"].get(tag, set())),
        }
        for tag in sorted(bank_tags)
    }

    coverage = []
    for tag in sorted(scoring_tags):
        coverage.append(
            {
                "tag": tag,
                "bank_occurrences": int(bank["canonical_counts"].get(tag, 0)),
                "banks": sorted(bank["files_by_tag"].get(tag, set())),
                "in_vocabulary": tag in canonical_vocab,
                "sources": scoring_sources_by_tag[tag],
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
        "runtime_zero_bank_coverage": runtime_zero_bank_coverage,
        "vocab_unused": vocab_unused,
        "coverage": coverage,
        "bank_tag_details": bank_tag_details,
        "runtime_files_by_tag": runtime_files_by_tag,
        "scoring_sources_by_tag": scoring_sources_by_tag,
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


def _emit_tag_details(
    title: str,
    tags: Iterable[str],
    *,
    report: dict[str, Any],
    emit=print,
) -> None:
    tags = list(tags)
    emit(f"\n{title}: {len(tags)}")
    for tag in tags:
        bank = report["bank_tag_details"].get(tag, {})
        scoring = ",".join(report["scoring_sources_by_tag"].get(tag, [])) or "-"
        runtime = ",".join(report["runtime_files_by_tag"].get(tag, [])) or "-"
        banks = ",".join(bank.get("banks", [])) or "-"
        occurrences = bank.get("occurrences", 0)
        emit(
            f"  - {tag}: occurrences={occurrences} banks={banks} "
            f"scoring={scoring} runtime={runtime}"
        )


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
    _emit_tag_details(
        "Code-owned tags missing from vocabulary",
        report["code_owned_missing"],
        report=report,
        emit=emit,
    )
    _emit_tag_details(
        "Scoring tags missing from vocabulary",
        report["scoring_missing_vocab"],
        report=report,
        emit=emit,
    )
    _emit_tag_details(
        "Runtime control tags missing from vocabulary",
        report["runtime_missing_vocab"],
        report=report,
        emit=emit,
    )
    _emit_tag_details(
        "Bank tags missing from vocabulary",
        report["bank_missing_vocab"],
        report=report,
        emit=emit,
    )
    _emit_tag_details(
        "Unknown bank-only tags requiring review",
        report["unknown_bank_only"],
        report=report,
        emit=emit,
    )
    _emit_tag_details(
        "Scoring tags with zero bank coverage",
        report["scoring_zero_bank_coverage"],
        report=report,
        emit=emit,
    )
    _emit_tag_details(
        "Runtime control tags with zero bank coverage",
        report["runtime_zero_bank_coverage"],
        report=report,
        emit=emit,
    )
    _emit_list("Vocabulary tags unused by banks/scoring/runtime", report["vocab_unused"], emit=emit)

    emit("\nSCORING COVERAGE")
    for row in report["coverage"]:
        sources = ",".join(row["sources"]) or "-"
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
