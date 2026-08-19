#!/usr/bin/env python3
"""Strictly validate ``data/rehab_bank.json`` against the rehab data contract.

Validation only — nothing here selects, scores or renders a drill. The finite
value sets, the recognised locations and the recognised injury types all come
from :mod:`fightcamp.rehab_schema`, which in turn borrows the project's injury
taxonomy and location registry. No list is redefined here.

Two ideas drive the rules:

* **Unknown is never a classification.** A ``function`` this validator does not
  recognise is an error, and a missing one is an error. Nothing is silently
  read as ``"control"`` — the legacy keyword fallback is a *runtime* concern and
  is never consulted during validation.
* **Skin is not musculoskeletal.** Surface (wound-care) groups carry no loading
  metadata, and declaring any is an error rather than an omission.

Duplicate drills are an error, with one narrow exception: the combinations
listed in ``data/rehab_bank_duplicate_debt.json`` predate this schema and are
grandfathered as declared migration debt. They are reported on every run, never
silently, and the ledger only ever shrinks — a duplicate that is not listed, or
an extra copy beyond the declared count, still fails.

Exit codes: ``0`` when no errors were found, ``1`` otherwise, so CI can block a
malformed rehab-bank change.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp.rehab_schema import (  # noqa: E402
    CARE_TYPE_WOUND_CARE,
    DOSE_FIELDS,
    DRILL_ID_PATTERN,
    IMPACT_VALUES,
    LOAD_VALUES,
    MSK_DRILL_FIELDS,
    PAIN_CEILING_MAX,
    PAIN_CEILING_MIN,
    PAIN_CEILING_UNRESTRICTED,
    PHASE_TOKENS,
    REHAB_FUNCTIONS,
    REHAB_STAGES,
    RULE_LIST_FIELDS,
    SEVERITY_VALUES,
    VELOCITY_VALUES,
    canonical_rehab_locations,
    canonical_rehab_types,
    care_type_for_injury_type,
    split_phase_progression,
    unmigrated_fields,
)

DEFAULT_BANK = REPO_ROOT / "data" / "rehab_bank.json"
DEFAULT_DUPLICATE_DEBT = REPO_ROOT / "data" / "rehab_bank_duplicate_debt.json"

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class RehabBankIssue:
    """One validation finding, pinned to the exact entry or drill it came from."""

    code: str
    severity: str
    locator: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code} :: {self.locator} :: {self.detail}"


def entry_locator(index: int, entry: Any) -> str:
    if not isinstance(entry, dict):
        return f"entry[{index}]"
    location = str(entry.get("location") or "?")
    injury_type = str(entry.get("type") or "?")
    return f"entry[{index}] {location}/{injury_type}"


def drill_locator(index: int, entry: Any, drill_index: int, drill: Any) -> str:
    base = f"{entry_locator(index, entry)} drill[{drill_index}]"
    if not isinstance(drill, dict):
        return base
    name = str(drill.get("name") or "?")
    drill_id = str(drill.get("id") or "?")
    return f"{base} '{name}' (id={drill_id})"


def _issue(code: str, severity: str, locator: str, detail: str) -> RehabBankIssue:
    return RehabBankIssue(code=code, severity=severity, locator=locator, detail=detail)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_text_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _hashable(value: Any) -> str:
    """Return a stable key for a value that may be malformed (and unhashable)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=repr)


# ---------------------------------------------------------------------------
# Group-level rules
# ---------------------------------------------------------------------------


def validate_entry_identity(index: int, entry: dict) -> list[RehabBankIssue]:
    """Check the group's location, injury type and phase progression."""
    issues: list[RehabBankIssue] = []
    locator = entry_locator(index, entry)

    location = entry.get("location")
    if not isinstance(location, str) or not location.strip():
        issues.append(_issue("missing_location", ERROR, locator, "location must be a non-empty string"))
    elif location not in canonical_rehab_locations():
        issues.append(
            _issue("unknown_location", ERROR, locator, f"{location!r} is not a recognised injury location")
        )

    injury_type = entry.get("type")
    if not isinstance(injury_type, str) or not injury_type.strip():
        issues.append(_issue("missing_type", ERROR, locator, "type must be a non-empty string"))
    elif injury_type not in canonical_rehab_types():
        issues.append(
            _issue(
                "unknown_type",
                ERROR,
                locator,
                f"{injury_type!r} is not a rehab-eligible injury type in the taxonomy",
            )
        )

    issues.extend(validate_phase_progression(locator, entry.get("phase_progression")))
    return issues


def validate_phase_progression(locator: str, value: Any) -> list[RehabBankIssue]:
    """Check that the phase progression names known phases exactly once each."""
    if not isinstance(value, str) or not value.strip():
        return [
            _issue(
                "malformed_phase_progression",
                ERROR,
                locator,
                "phase_progression must be a non-empty string",
            )
        ]
    tokens = split_phase_progression(value)
    if not tokens:
        return [
            _issue("malformed_phase_progression", ERROR, locator, f"{value!r} names no phases")
        ]
    unknown = [token for token in tokens if token not in PHASE_TOKENS]
    if unknown:
        return [
            _issue(
                "malformed_phase_progression",
                ERROR,
                locator,
                f"unknown phase(s) {sorted(unknown)} in {value!r}",
            )
        ]
    duplicates = sorted({token for token, count in Counter(tokens).items() if count > 1})
    if duplicates:
        return [
            _issue(
                "malformed_phase_progression",
                ERROR,
                locator,
                f"phase(s) {duplicates} repeated in {value!r}",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Drill-level rules
# ---------------------------------------------------------------------------


def validate_drill_identity(locator: str, drill: dict) -> list[RehabBankIssue]:
    """Check the fields every drill carries, whatever its care pathway."""
    issues: list[RehabBankIssue] = []

    drill_id = drill.get("id")
    if not isinstance(drill_id, str) or not drill_id.strip():
        issues.append(_issue("missing_drill_id", ERROR, locator, "id must be a non-empty string"))
    elif not DRILL_ID_PATTERN.match(drill_id):
        issues.append(
            _issue("invalid_drill_id", ERROR, locator, f"id {drill_id!r} is not a lowercase a-z0-9_ slug")
        )

    name = drill.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append(_issue("missing_drill_name", ERROR, locator, "name must be a non-empty string"))

    if not isinstance(drill.get("notes", ""), str):
        issues.append(_issue("invalid_drill_notes", ERROR, locator, "notes must be a string"))

    return issues


def _validate_enum(locator: str, field: str, value: Any, allowed: tuple[str, ...]) -> list[RehabBankIssue]:
    if value is None or (isinstance(value, str) and value in allowed):
        return []
    return [
        _issue(
            f"invalid_{field}",
            ERROR,
            locator,
            f"{field}={value!r} is not one of {list(allowed)} (null means not migrated yet)",
        )
    ]


def validate_function(locator: str, drill: dict) -> list[RehabBankIssue]:
    """Check the explicit function classification.

    A value outside the six classes is an error. ``null`` is the not-migrated
    marker and is reported separately — never quietly read as ``"control"``.
    """
    if "function" not in drill:
        return [
            _issue(
                "missing_function",
                ERROR,
                locator,
                "function metadata is missing; declare one of "
                f"{list(REHAB_FUNCTIONS)} or null for not-yet-migrated",
            )
        ]
    value = drill.get("function")
    if value is None:
        return [
            _issue(
                "unmigrated_function",
                INFO,
                locator,
                "function is not migrated yet; runtime falls back to the keyword classifier",
            )
        ]
    if not isinstance(value, str) or value not in REHAB_FUNCTIONS:
        return [
            _issue(
                "invalid_function",
                ERROR,
                locator,
                f"function={value!r} is not one of {list(REHAB_FUNCTIONS)}",
            )
        ]
    return []


def validate_dose(locator: str, value: Any) -> list[RehabBankIssue]:
    """Check the structured dose object."""
    if value is None:
        return []
    if not isinstance(value, dict):
        return [_issue("invalid_dose", ERROR, locator, f"dose must be an object or null, got {type(value).__name__}")]
    unknown = sorted(set(value) - set(DOSE_FIELDS))
    if unknown:
        return [_issue("invalid_dose", ERROR, locator, f"dose has unknown field(s) {unknown}")]
    issues: list[RehabBankIssue] = []
    for field in DOSE_FIELDS:
        slot = value.get(field)
        if slot is None:
            continue
        if not _is_number(slot) or slot <= 0:
            issues.append(
                _issue("invalid_dose", ERROR, locator, f"dose.{field}={slot!r} must be a positive number or null")
            )
    return issues


def validate_equipment(locator: str, value: Any) -> list[RehabBankIssue]:
    """Check the equipment list. ``[]`` means "needs nothing"; null means unmigrated."""
    if value is None or _is_text_list(value):
        return []
    return [
        _issue(
            "invalid_equipment",
            ERROR,
            locator,
            f"equipment={value!r} must be a list of non-empty strings, [] or null",
        )
    ]


def validate_pain_ceiling(locator: str, value: Any) -> list[RehabBankIssue]:
    """Check the pain ceiling: null, the unrestricted sentinel, or 0-10."""
    if value is None or value == PAIN_CEILING_UNRESTRICTED:
        return []
    if _is_number(value) and PAIN_CEILING_MIN <= value <= PAIN_CEILING_MAX:
        return []
    return [
        _issue(
            "invalid_pain_ceiling",
            ERROR,
            locator,
            f"pain_ceiling={value!r} must be null, {PAIN_CEILING_UNRESTRICTED!r}, "
            f"or a number in {PAIN_CEILING_MIN}-{PAIN_CEILING_MAX}",
        )
    ]


def validate_allowed_severities(locator: str, value: Any) -> list[RehabBankIssue]:
    """Check the severity gate. Null means unmigrated; an empty list is meaningless."""
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        return [
            _issue(
                "invalid_allowed_severities",
                ERROR,
                locator,
                f"allowed_severities={value!r} must be a non-empty list or null",
            )
        ]
    unknown = [item for item in value if not isinstance(item, str) or item not in SEVERITY_VALUES]
    if unknown:
        return [
            _issue(
                "invalid_allowed_severities",
                ERROR,
                locator,
                f"unknown severity value(s) {unknown}; expected {list(SEVERITY_VALUES)}",
            )
        ]
    duplicates = sorted({item for item, count in Counter(value).items() if count > 1})
    if duplicates:
        return [
            _issue(
                "invalid_allowed_severities",
                ERROR,
                locator,
                f"duplicate severity value(s) {duplicates}",
            )
        ]
    return []


def validate_rule_list(locator: str, field: str, value: Any) -> list[RehabBankIssue]:
    """Check a progress/regress/stop rule list. ``[]`` is a deliberate "no criteria"."""
    if value is None or _is_text_list(value):
        return []
    return [
        _issue(
            f"invalid_{field}",
            ERROR,
            locator,
            f"{field}={value!r} must be a list of non-empty strings, [] or null",
        )
    ]


def validate_msk_drill(locator: str, drill: dict) -> list[RehabBankIssue]:
    """Check the musculoskeletal contract fields on one drill."""
    issues: list[RehabBankIssue] = []

    missing = [field for field in MSK_DRILL_FIELDS if field not in drill]
    if missing:
        issues.append(
            _issue(
                "missing_contract_field",
                ERROR,
                locator,
                f"contract field(s) {missing} absent; declare them, using null for not-yet-migrated",
            )
        )

    issues.extend(validate_function(locator, drill))
    issues.extend(_validate_enum(locator, "rehab_stage", drill.get("rehab_stage"), REHAB_STAGES))
    issues.extend(_validate_enum(locator, "impact", drill.get("impact"), IMPACT_VALUES))
    issues.extend(_validate_enum(locator, "load", drill.get("load"), LOAD_VALUES))
    issues.extend(_validate_enum(locator, "velocity", drill.get("velocity"), VELOCITY_VALUES))
    issues.extend(validate_dose(locator, drill.get("dose")))
    issues.extend(validate_equipment(locator, drill.get("equipment")))
    issues.extend(validate_pain_ceiling(locator, drill.get("pain_ceiling")))
    issues.extend(validate_allowed_severities(locator, drill.get("allowed_severities")))
    for field in RULE_LIST_FIELDS:
        issues.extend(validate_rule_list(locator, field, drill.get(field)))

    pending = unmigrated_fields(drill)
    if pending:
        issues.append(
            _issue("pending_migration", INFO, locator, f"awaiting clinical migration: {pending}")
        )
    return issues


def validate_wound_care_drill(locator: str, drill: dict) -> list[RehabBankIssue]:
    """Check a surface/skin drill.

    Skin injuries are integumentary. They carry wound-care instructions and must
    not be dressed up as loading rehab, so any musculoskeletal field is an error.
    """
    declared = [field for field in MSK_DRILL_FIELDS if field in drill]
    if not declared:
        return []
    return [
        _issue(
            "wound_care_loading_metadata",
            ERROR,
            locator,
            f"surface (wound-care) drill must not declare musculoskeletal field(s) {declared}",
        )
    ]


# ---------------------------------------------------------------------------
# Declared duplicate debt
# ---------------------------------------------------------------------------

#: Ledger key: the location/type/stage/drill-name a duplicate is grandfathered on.
DebtKey = tuple[str, str, str, str]


def _debt_key(location: Any, injury_type: Any, stage: Any, name: Any) -> DebtKey:
    return (_hashable(location), _hashable(injury_type), _hashable(stage), _hashable(name))


def load_duplicate_debt(path: Path | None = DEFAULT_DUPLICATE_DEBT) -> dict[DebtKey, int]:
    """Return the grandfathered duplicate counts keyed by location/type/stage/name.

    A missing path (or ``None``) means no duplicate is grandfathered, which is
    the strict reading used by unit tests.
    """
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    debt: dict[DebtKey, int] = {}
    for row in payload.get("duplicates", []):
        key = _debt_key(row.get("location"), row.get("type"), row.get("rehab_stage"), row.get("name"))
        debt[key] = debt.get(key, 0) + int(row.get("grandfathered_copies", 0))
    return debt


def _duplicate_issues(
    combination_locations: dict[tuple, list[str]],
    debt: dict[DebtKey, int],
) -> list[RehabBankIssue]:
    """Report duplicate drill combinations, spending the declared debt first."""
    issues: list[RehabBankIssue] = []
    remaining = dict(debt)

    for combination, locators in combination_locations.items():
        excess = len(locators) - 1
        if excess < 1:
            continue
        location, injury_type, stage, name, _notes = (json.loads(part) for part in combination)
        key = _debt_key(location, injury_type, stage, name)
        grandfathered = min(excess, remaining.get(key, 0))
        remaining[key] = remaining.get(key, 0) - grandfathered

        if grandfathered:
            issues.append(
                _issue(
                    "grandfathered_duplicate",
                    INFO,
                    locators[0],
                    f"{location}/{injury_type}/stage={stage} repeats drill {name!r} "
                    f"({grandfathered} declared copy/copies) — migration debt, see "
                    f"{DEFAULT_DUPLICATE_DEBT.name}",
                )
            )
        if excess > grandfathered:
            issues.append(
                _issue(
                    "duplicate_drill_combination",
                    ERROR,
                    locators[0],
                    f"{location}/{injury_type}/stage={stage} repeats drill {name!r} at: "
                    f"{locators[1:]} ({excess - grandfathered} copy/copies not covered "
                    f"by {DEFAULT_DUPLICATE_DEBT.name})",
                )
            )

    for key, unspent in sorted(remaining.items()):
        if unspent > 0:
            location, injury_type, stage, name = (json.loads(part) for part in key)
            issues.append(
                _issue(
                    "resolved_duplicate_debt",
                    INFO,
                    f"{DEFAULT_DUPLICATE_DEBT.name} {location}/{injury_type}",
                    f"{unspent} declared duplicate(s) of {name!r} no longer exist; "
                    "drop the row from the ledger",
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Whole-bank rules
# ---------------------------------------------------------------------------


def validate_rehab_bank(data: Any, *, duplicate_debt: dict[DebtKey, int] | None = None) -> list[RehabBankIssue]:
    """Validate a parsed rehab bank and return every finding.

    ``duplicate_debt`` grandfathers the duplicate combinations declared in the
    ledger. It defaults to none, so a caller that passes nothing gets the strict
    reading in which every duplicate is an error.
    """
    if not isinstance(data, list):
        return [
            _issue("invalid_root", ERROR, "rehab_bank", f"expected a list of groups, got {type(data).__name__}")
        ]

    issues: list[RehabBankIssue] = []
    id_locations: dict[str, list[str]] = defaultdict(list)
    combination_locations: dict[tuple, list[str]] = defaultdict(list)

    for index, entry in enumerate(data):
        locator = entry_locator(index, entry)
        if not isinstance(entry, dict):
            issues.append(_issue("invalid_entry", ERROR, locator, "group record must be an object"))
            continue

        issues.extend(validate_entry_identity(index, entry))

        drills = entry.get("drills")
        if not isinstance(drills, list) or not drills:
            issues.append(_issue("missing_drills", ERROR, locator, "drills must be a non-empty list"))
            continue

        care_type = care_type_for_injury_type(entry.get("type"))
        for drill_index, drill in enumerate(drills):
            drill_at = drill_locator(index, entry, drill_index, drill)
            if not isinstance(drill, dict):
                issues.append(_issue("invalid_drill", ERROR, drill_at, "drill must be an object"))
                continue

            issues.extend(validate_drill_identity(drill_at, drill))
            if care_type == CARE_TYPE_WOUND_CARE:
                issues.extend(validate_wound_care_drill(drill_at, drill))
            else:
                issues.extend(validate_msk_drill(drill_at, drill))

            drill_id = drill.get("id")
            if isinstance(drill_id, str) and drill_id.strip():
                id_locations[drill_id].append(drill_at)

            combination_locations[
                (
                    _hashable(entry.get("location")),
                    _hashable(entry.get("type")),
                    _hashable(drill.get("rehab_stage")),
                    _hashable(drill.get("name")),
                    _hashable(drill.get("notes")),
                )
            ].append(drill_at)

    for drill_id, locators in sorted(id_locations.items()):
        if len(locators) > 1:
            issues.append(
                _issue("duplicate_drill_id", ERROR, locators[0], f"id {drill_id!r} reused by: {locators[1:]}")
            )

    issues.extend(_duplicate_issues(combination_locations, duplicate_debt or {}))

    return issues


# ---------------------------------------------------------------------------
# Reporting / CLI
# ---------------------------------------------------------------------------


def count_by_severity(issues: list[RehabBankIssue]) -> dict[str, int]:
    counts = Counter(issue.severity for issue in issues)
    return {ERROR: counts[ERROR], WARNING: counts[WARNING], INFO: counts[INFO]}


def report(issues: list[RehabBankIssue], *, emit=print, max_per_code: int = 20) -> None:
    """Print findings grouped by code, most severe first."""
    grouped: dict[tuple[str, str], list[RehabBankIssue]] = defaultdict(list)
    for issue in issues:
        grouped[(issue.severity, issue.code)].append(issue)

    order = {ERROR: 0, WARNING: 1, INFO: 2}
    for severity, code in sorted(grouped, key=lambda key: (order.get(key[0], 3), key[1])):
        found = grouped[(severity, code)]
        emit(f"\n{severity}: {code} ({len(found)})")
        for issue in found[:max_per_code]:
            emit(f"  - {issue.locator} :: {issue.detail}")
        if len(found) > max_per_code:
            emit(f"  ... {len(found) - max_per_code} more")


def run_validation(
    bank_path: Path = DEFAULT_BANK,
    *,
    emit=print,
    strict_migration: bool = False,
    duplicate_debt_path: Path | None = DEFAULT_DUPLICATE_DEBT,
) -> int:
    """Validate the bank at ``bank_path``; return a process exit code."""
    emit(f"Validating rehab bank: {bank_path}")
    try:
        data = json.loads(bank_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        emit(f"ERROR: {bank_path} does not exist")
        return 1
    except json.JSONDecodeError as exc:
        emit(f"ERROR: {bank_path} is not valid JSON: {exc}")
        return 1

    try:
        debt = load_duplicate_debt(duplicate_debt_path)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        emit(f"ERROR: {duplicate_debt_path} is not a valid duplicate-debt ledger: {exc}")
        return 1

    issues = validate_rehab_bank(data, duplicate_debt=debt)
    report(issues, emit=emit)
    counts = count_by_severity(issues)

    emit("\n" + "=" * 40)
    emit("REHAB BANK VALIDATION SUMMARY")
    emit("=" * 40)
    emit(f"Groups: {len(data) if isinstance(data, list) else 0}")
    emit(f"Issues: errors={counts[ERROR]} warnings={counts[WARNING]} info={counts[INFO]}")

    failing = counts[ERROR]
    if strict_migration:
        pending = sum(
            1
            for issue in issues
            if issue.code in {"pending_migration", "unmigrated_function", "grandfathered_duplicate"}
        )
        failing += pending
        emit(f"strict-migration: {pending} outstanding migration-debt finding(s) treated as failures")

    if failing:
        emit("Rehab bank validation FAILED.")
        return 1
    emit("Rehab bank validation passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK, help="rehab bank JSON path")
    parser.add_argument(
        "--duplicate-debt",
        type=Path,
        default=DEFAULT_DUPLICATE_DEBT,
        help="ledger of grandfathered duplicate drill combinations",
    )
    parser.add_argument(
        "--strict-migration",
        action="store_true",
        help="also fail on fields still awaiting the PR3 clinical migration",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return run_validation(
        args.bank,
        strict_migration=args.strict_migration,
        duplicate_debt_path=args.duplicate_debt,
    )


if __name__ == "__main__":
    sys.exit(main())
