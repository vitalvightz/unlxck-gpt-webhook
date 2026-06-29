#!/usr/bin/env python3
"""Audit and strictly validate training-bank metadata without mutating banks."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
TAG_VOCAB_FILE = DATA_DIR / "tag_vocabulary.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.bank_schema import KNOWN_SYSTEMS, SYSTEM_ALIASES  # noqa: E402
from fightcamp.tagging import normalize_tag  # noqa: E402


VALIDATION_MODES = {"audit", "strict", "runtime"}
OLD_VALIDATOR_SKIPPED = {
    "coordination_bank.json",
    "injury_exclusion_map.json",
    "rehab_bank.json",
    "tag_vocabulary.json",
}
NON_BANK_JSON = {
    "bank_inferred_tags.json",
    "regex_patterns.json",
}
CONFIG_TARGETS = {
    "injury_exclusion_map.json",
    "tag_vocabulary.json",
}
AUDIT_GROUP_ORDER = [
    "missing names",
    "missing tags",
    "missing phases",
    "missing/empty late_windows",
    "missing cost fields",
    "missing rpe/rpe_max",
    "missing stress_class/cost_class/support_only/meaningful_stress",
    "high intensity marked late-safe",
    "unknown conditioning system",
    "alias-only conditioning system",
    "entries skipped by the old validator",
    "duplicate names",
    "tags not in tag_vocabulary",
    "config schema issues",
]
STRICT_ERROR_GROUPS = {
    "missing names",
    "missing tags",
    "missing phases",
    "missing/empty late_windows",
    "missing cost fields",
    "missing rpe/rpe_max",
    "missing stress_class/cost_class/support_only/meaningful_stress",
    "unknown conditioning system",
    "tags not in tag_vocabulary",
    "config schema issues",
}
CONDITIONING_BANK_NAMES = {
    "conditioning_bank.json",
    "coordination_bank.json",
    "footwork_conditioning_bank.json",
    "style_conditioning_bank.json",
    "style_taper_conditioning.json",
    "universal_gpp_conditioning.json",
}
EXERCISE_BANK_NAMES = {
    "exercise_bank.json",
    "universal_gpp_strength.json",
}
CONDITIONING_COST_FIELDS = ("impact_cost", "movement_cost", "lactate_load")
EXERCISE_COST_FIELDS = (
    "impact_cost",
    "movement_cost",
    "cns_load",
    "eccentric_cost",
    "landing_cost",
    "soreness_risk",
)
LATE_GOVERNANCE_FIELDS = ("stress_class", "cost_class", "support_only", "meaningful_stress")
HIGH_LEVELS = {"high", "very_high", "max"}
HIGH_INTENSITY_TAGS = {
    "glycolytic",
    "high_impact",
    "mech_cns_high",
    "mech_landing_impact",
    "work_capacity",
}


@dataclass(frozen=True)
class BankIssue:
    group: str
    file: str
    entry: str
    detail: str
    severity: str = "error"


def configure_utf8_output() -> None:
    """Prefer UTF-8 console output when the host stream supports it."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _is_non_bank_json(filename: str) -> bool:
    return filename in NON_BANK_JSON or filename.startswith("format_")


def discover_banks(data_dir: Path = DATA_DIR) -> list[Path]:
    """Return raw training-bank JSON targets, including rehab and coordination banks."""
    banks: list[Path] = []
    for file_path in sorted(data_dir.glob("*.json")):
        filename = file_path.name.lower()
        if _is_non_bank_json(filename) or filename in CONFIG_TARGETS:
            continue
        banks.append(file_path)
    return banks


def discover_validation_targets(data_dir: Path = DATA_DIR) -> list[Path]:
    """Return all validator targets, including config files that shape bank safety."""
    targets = discover_banks(data_dir)
    for filename in sorted(CONFIG_TARGETS):
        path = data_dir / filename
        if path.exists():
            targets.append(path)
    return sorted(targets, key=lambda path: path.name)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _clean_tag(value: Any) -> str | None:
    return normalize_tag(str(value)) if isinstance(value, str) else None


def load_tag_vocabulary(data_dir: Path = DATA_DIR, *, emit=print) -> set[str]:
    """Load normalized tag vocabulary from tag_vocabulary.json."""
    path = data_dir / "tag_vocabulary.json"
    emit(f"Loading tag vocabulary from {path}...")
    data = _load_json(path)
    if isinstance(data, list):
        tags = {_clean_tag(tag) for tag in data}
        normalized = {tag for tag in tags if tag}
        emit(f"Tag vocabulary loaded: {len(normalized)} tags (list schema)\n")
        return normalized
    if isinstance(data, dict):
        for key in ("items", "data"):
            if isinstance(data.get(key), list):
                tags = {_clean_tag(tag) for tag in data[key]}
                normalized = {tag for tag in tags if tag}
                emit(f"Tag vocabulary loaded: {len(normalized)} tags (object schema with '{key}')\n")
                return normalized
    raise ValueError(f"Unrecognized tag vocabulary schema in {path}")


def load_injury_rules() -> dict[str, dict[str, list[str]]]:
    """Load runtime injury exclusion rules for compatibility with older callers."""
    from fightcamp.injury_exclusion_rules import INJURY_RULES

    return INJURY_RULES


def parse_bank_schema(data: Any) -> tuple[list[dict], str]:
    """Parse common bank schemas into a flat entry list."""
    if isinstance(data, list):
        return data, f"root list with {len(data)} entries"
    if isinstance(data, dict):
        for key in ("items", "data"):
            if isinstance(data.get(key), list):
                entries = data[key]
                return entries, f"object with '{key}' array containing {len(entries)} entries"
        flattened: list[dict] = []
        list_keys = 0
        for value in data.values():
            if isinstance(value, list):
                list_keys += 1
                flattened.extend(item for item in value if isinstance(item, dict))
        if list_keys:
            return flattened, f"object with {list_keys} list groups containing {len(flattened)} entries"
    raise ValueError("Unrecognized bank schema structure. Expected list or object with list values.")


def duplicate_name_counts(entries: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}
    for entry in entries:
        raw_name = entry.get("name")
        if not raw_name:
            continue
        key = str(raw_name).strip().casefold()
        if not key:
            continue
        counts[key] += 1
        display_names.setdefault(key, str(raw_name).strip())
    return {
        display_names[key]: count
        for key, count in sorted(counts.items(), key=lambda item: display_names[item[0]].lower())
        if count > 1
    }


def _entry_label(entry: dict, index: int) -> str:
    name = str(entry.get("name") or "").strip()
    if name:
        return name
    location = str(entry.get("location") or "").strip()
    injury_type = str(entry.get("type") or "").strip()
    if location or injury_type:
        return ":".join(part for part in (location, injury_type) if part)
    return f"index {index}"


def _tags_for_entry(entry: dict) -> list[str]:
    tags = entry.get("tags")
    if not isinstance(tags, list):
        return []
    normalized: list[str] = []
    for tag in tags:
        cleaned = _clean_tag(tag)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _system_issue(raw_system: Any) -> tuple[str, str] | None:
    system = str(raw_system or "").strip().lower()
    if not system:
        return ("unknown", "missing")
    normalized = SYSTEM_ALIASES.get(system, system)
    if normalized in KNOWN_SYSTEMS:
        if system != normalized:
            return ("alias", f"{system} -> {normalized}")
        return None
    return ("unknown", f"{system} -> {normalized}")


def _has_late_windows(entry: dict) -> bool:
    late_windows = entry.get("late_windows")
    return isinstance(late_windows, list) and bool(late_windows)


def _is_missing_value(value: Any) -> bool:
    return value is None or value == "" or value == []


def _missing_fields(entry: dict, fields: Iterable[str]) -> list[str]:
    return [field for field in fields if field not in entry or _is_missing_value(entry.get(field))]


def _number(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _high_intensity_late_safe(entry: dict, tags: list[str]) -> bool:
    if not _has_late_windows(entry):
        return False
    if HIGH_INTENSITY_TAGS.intersection(tags):
        return True
    system = str(entry.get("system") or "").strip().lower()
    if SYSTEM_ALIASES.get(system, system) == "glycolytic":
        return True
    for field in (*CONDITIONING_COST_FIELDS, *EXERCISE_COST_FIELDS):
        if str(entry.get(field) or "").strip().lower() in HIGH_LEVELS:
            return True
    rpe = _number(entry.get("rpe"))
    rpe_max = _number(entry.get("rpe_max"))
    return bool((rpe is not None and rpe >= 8) or (rpe_max is not None and rpe_max >= 8))


def _add_issue(
    issues: list[BankIssue],
    group: str,
    path: Path,
    entry: str,
    detail: str,
    *,
    severity: str | None = None,
) -> None:
    issues.append(
        BankIssue(
            group=group,
            file=path.name,
            entry=entry,
            detail=detail,
            severity=severity or ("error" if group in STRICT_ERROR_GROUPS else "warning"),
        )
    )


def validate_config_target(path: Path) -> list[BankIssue]:
    issues: list[BankIssue] = []
    data = _load_json(path)
    if path.name in OLD_VALIDATOR_SKIPPED:
        _add_issue(
            issues,
            "entries skipped by the old validator",
            path,
            path.name,
            "config target is now included in audit coverage",
            severity="info",
        )
    if path.name == "tag_vocabulary.json":
        if not isinstance(data, list) or any(not isinstance(tag, str) or not tag.strip() for tag in data):
            _add_issue(issues, "config schema issues", path, path.name, "expected a non-empty list of tag strings")
    elif path.name == "injury_exclusion_map.json":
        if not isinstance(data, dict):
            _add_issue(issues, "config schema issues", path, path.name, "expected an object keyed by injury region")
        else:
            for region, references in data.items():
                if not isinstance(references, list) or any(not isinstance(ref, str) for ref in references):
                    _add_issue(
                        issues,
                        "config schema issues",
                        path,
                        str(region),
                        "expected each region to map to a list of bank entry references",
                    )
    return issues


def validate_bank(path: Path, tag_vocab: set[str]) -> tuple[bool, int, set[str], list[BankIssue]]:
    """Validate one raw training bank and return compatibility summary data."""
    issues: list[BankIssue] = []
    all_tags: set[str] = set()
    data = _load_json(path)
    entries, _schema_desc = parse_bank_schema(data)

    if path.name in OLD_VALIDATOR_SKIPPED:
        _add_issue(
            issues,
            "entries skipped by the old validator",
            path,
            path.name,
            f"{len(entries)} entries are now included in audit coverage",
            severity="info",
        )

    name_counter: Counter[str] = Counter()
    display_names: dict[str, str] = {}
    bank_name = path.name.lower()
    cost_fields = CONDITIONING_COST_FIELDS if bank_name in CONDITIONING_BANK_NAMES else EXERCISE_COST_FIELDS
    requires_conditioning_system = bank_name in CONDITIONING_BANK_NAMES
    requires_rpe = bank_name in CONDITIONING_BANK_NAMES
    requires_governance = bank_name in CONDITIONING_BANK_NAMES or bank_name in EXERCISE_BANK_NAMES

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _add_issue(issues, "config schema issues", path, f"index {index}", "entry is not an object")
            continue

        label = _entry_label(entry, index)
        raw_name = str(entry.get("name") or "").strip()
        if raw_name:
            key = raw_name.casefold()
            name_counter[key] += 1
            display_names.setdefault(key, raw_name)
        else:
            _add_issue(issues, "missing names", path, label, "missing or empty name")

        tags_value = entry.get("tags")
        if not isinstance(tags_value, list) or not tags_value:
            _add_issue(issues, "missing tags", path, label, "missing, empty, or non-list tags")
        tags = _tags_for_entry(entry)
        all_tags.update(tags)
        for tag in tags:
            if tag_vocab and tag not in tag_vocab:
                _add_issue(issues, "tags not in tag_vocabulary", path, label, tag)

        phases = entry.get("phases")
        if not isinstance(phases, list) or not phases:
            _add_issue(issues, "missing phases", path, label, "missing, empty, or non-list phases")

        if not _has_late_windows(entry):
            _add_issue(
                issues,
                "missing/empty late_windows",
                path,
                label,
                "not late-fight eligible until explicit late_windows are supplied",
            )

        missing_cost = _missing_fields(entry, cost_fields)
        if missing_cost:
            _add_issue(issues, "missing cost fields", path, label, ", ".join(missing_cost))

        if requires_rpe and _number(entry.get("rpe")) is None and _number(entry.get("rpe_max")) is None:
            _add_issue(issues, "missing rpe/rpe_max", path, label, "missing numeric rpe or rpe_max")

        if requires_governance:
            missing_governance = _missing_fields(entry, LATE_GOVERNANCE_FIELDS)
            if missing_governance:
                _add_issue(
                    issues,
                    "missing stress_class/cost_class/support_only/meaningful_stress",
                    path,
                    label,
                    ", ".join(missing_governance),
                )

        if _high_intensity_late_safe(entry, tags):
            _add_issue(
                issues,
                "high intensity marked late-safe",
                path,
                label,
                "late_windows present alongside high-intensity system, tags, costs, or RPE",
                severity="warning",
            )

        if requires_conditioning_system:
            system_issue = _system_issue(entry.get("system"))
            if system_issue:
                group_type, detail = system_issue
                group = "alias-only conditioning system" if group_type == "alias" else "unknown conditioning system"
                _add_issue(issues, group, path, label, detail, severity="warning" if group_type == "alias" else None)

    for key, count in sorted(name_counter.items(), key=lambda item: display_names[item[0]].lower()):
        if count > 1:
            _add_issue(
                issues,
                "duplicate names",
                path,
                display_names[key],
                f"{count} entries share this name",
                severity="warning",
            )

    has_errors = any(issue.severity == "error" for issue in issues)
    return not has_errors, len(entries), all_tags, issues


def _print_issue_report(grouped: dict[str, list[BankIssue]], *, emit=print) -> None:
    emit("=" * 40)
    emit("BANK AUDIT REPORT")
    emit("=" * 40)
    for group in AUDIT_GROUP_ORDER:
        issues = grouped.get(group, [])
        emit(f"\n{group}: {len(issues)}")
        for issue in issues[:25]:
            emit(f"  - {issue.file} :: {issue.entry} :: {issue.detail}")
        if len(issues) > 25:
            emit(f"  ... {len(issues) - 25} more")
    extra_groups = sorted(set(grouped) - set(AUDIT_GROUP_ORDER))
    for group in extra_groups:
        issues = grouped[group]
        emit(f"\n{group}: {len(issues)}")
        for issue in issues[:25]:
            emit(f"  - {issue.file} :: {issue.entry} :: {issue.detail}")


def run_validation(mode: str = "audit", data_dir: Path = DATA_DIR, *, emit=print) -> int:
    if mode not in VALIDATION_MODES:
        raise ValueError(f"Unknown validation mode '{mode}'. Expected one of {sorted(VALIDATION_MODES)}.")

    emit(f"Discovering validation targets in {data_dir}...")
    targets = discover_validation_targets(data_dir)
    emit(f"Found {len(targets)} targets to inspect.\n")
    if not targets:
        emit("No validation targets found.")
        return 0

    try:
        tag_vocab = load_tag_vocabulary(data_dir, emit=emit)
    except Exception as exc:
        emit(f"ERROR loading tag vocabulary: {exc}")
        return 1

    total_entries = 0
    all_issues: list[BankIssue] = []
    all_tags_seen: set[str] = set()

    for target in targets:
        emit("=" * 40)
        emit(f"Inspecting: {target.name}")
        emit("=" * 40)
        try:
            if target.name in CONFIG_TARGETS:
                issues = validate_config_target(target)
                all_issues.extend(issues)
                emit(f"Config target inspected with {len(issues)} issue(s).\n")
                continue
            success, entry_count, tags_seen, issues = validate_bank(target, tag_vocab)
            total_entries += entry_count
            all_tags_seen.update(tags_seen)
            all_issues.extend(issues)
            status = "passed" if success else "issues found"
            emit(f"Entries inspected: {entry_count}; {status}; issues={len(issues)}\n")
        except Exception as exc:
            all_issues.append(
                BankIssue(
                    group="config schema issues",
                    file=target.name,
                    entry=target.name,
                    detail=str(exc),
                    severity="error",
                )
            )
            emit(f"ERROR inspecting {target.name}: {exc}\n")

    grouped: dict[str, list[BankIssue]] = defaultdict(list)
    for issue in all_issues:
        grouped[issue.group].append(issue)
    _print_issue_report(grouped, emit=emit)

    error_count = sum(1 for issue in all_issues if issue.severity == "error")
    warning_count = sum(1 for issue in all_issues if issue.severity == "warning")
    info_count = sum(1 for issue in all_issues if issue.severity == "info")

    emit("\n" + "=" * 40)
    emit("VALIDATION SUMMARY")
    emit("=" * 40)
    emit(f"Mode: {mode}")
    emit(f"Total targets inspected: {len(targets)}")
    emit(f"Total entries inspected: {total_entries}")
    emit(f"Unique tags seen: {len(all_tags_seen)}")
    emit(f"Issues: errors={error_count} warnings={warning_count} info={info_count}")

    if mode == "audit":
        emit("Audit mode completed successfully; issues are reported for follow-up.")
        return 0
    if error_count:
        emit(f"{mode} mode failed on required-field issues.")
        return 1
    emit(f"{mode} mode passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=sorted(VALIDATION_MODES),
        default="audit",
        help="audit reports issues with exit 0; strict/runtime fail on required-field issues",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="directory containing bank JSON files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    return run_validation(args.mode, args.data_dir)


if __name__ == "__main__":
    sys.exit(main())
