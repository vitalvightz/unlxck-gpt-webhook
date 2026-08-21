"""Fail-closed regression coverage for the rehab metadata review validator."""

from __future__ import annotations

import copy

import pytest

from fightcamp.rehab_schema import REHAB_FUNCTIONS
from tools.apply_rehab_metadata_review import apply_reviews
from tools.generate_rehab_metadata_review import build_ledger
from tools.rehab_metadata_review_lib import (
    FLAG_VARIABLE_DEMAND,
    LEDGER_VERSION,
    REVIEW_FIELDS,
    REVIEW_STATE_REVIEWED,
)
from tools.validate_rehab_bank import ERROR, validate_rehab_bank
from tools.validate_rehab_metadata_review import validate


def _drill() -> dict:
    """Minimal canonical MSK drill that remains valid with unmigrated fields."""
    return {
        "id": "ankle_sprain_iso_hold",
        "name": "Isometric Ankle Hold",
        "notes": "Controlled ankle isometric hold",
        "rehab_stage": None,
        "function": REHAB_FUNCTIONS[0],
        "equipment": None,
        "dose": None,
        "impact": None,
        "load": None,
        "velocity": None,
        "pain_ceiling": None,
        "allowed_severities": None,
        "progress_when": None,
        "regress_when": None,
        "stop_when": None,
        "target_regions": ["ankle"],
        "laterality_applicability": "unknown",
        "target_tissues": None,
        "contraction_type": "unknown",
        "sport_specificity": "unknown",
        "contact_level": "unknown",
        "evidence_notes": None,
    }


def _entries() -> list[dict]:
    return [
        {
            "location": "ankle",
            "type": "sprain",
            "phase_progression": "GPP",
            "drills": [_drill()],
        }
    ]


def _reviewed(entries: list[dict] | None = None) -> list[dict]:
    entries = entries or _entries()
    ledger = build_ledger(entries)
    ledger[0]["review_state"] = REVIEW_STATE_REVIEWED
    return ledger


def _errors_for_proposed(field: str, value) -> list[str]:
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["proposed"][field] = value
    return validate(entries, ledger)


@pytest.mark.parametrize("value", [[], [""], ["   "]])
def test_target_regions_must_be_non_empty_text_list(value):
    errors = _errors_for_proposed("target_regions", value)
    assert any("proposed.target_regions" in error for error in errors)


def test_target_regions_must_use_canonical_location():
    errors = _errors_for_proposed("target_regions", ["not_a_real_region"])
    assert any("not in location registry" in error for error in errors)


@pytest.mark.parametrize("value", [[""], ["   "], "bands"])
def test_equipment_rejects_blank_or_malformed_values(value):
    errors = _errors_for_proposed("equipment", value)
    assert any("proposed.equipment" in error for error in errors)


def test_equipment_empty_list_is_valid_canonical_no_equipment_state():
    assert _errors_for_proposed("equipment", []) == []


@pytest.mark.parametrize("value", [[""], ["   "], "tendon"])
def test_target_tissues_rejects_blank_or_malformed_values(value):
    errors = _errors_for_proposed("target_tissues", value)
    assert any("proposed.target_tissues" in error for error in errors)


def test_target_tissues_empty_list_matches_canonical_text_list_semantics():
    assert _errors_for_proposed("target_tissues", []) == []


@pytest.mark.parametrize("value", ["", "   ", []])
def test_evidence_notes_must_be_non_empty_text_or_null(value):
    errors = _errors_for_proposed("evidence_notes", value)
    assert any("proposed.evidence_notes" in error for error in errors)


@pytest.mark.parametrize("value", [None, LEDGER_VERSION + 1, str(LEDGER_VERSION), True])
def test_review_version_must_match_exact_integer_contract(value):
    entries = _entries()
    ledger = _reviewed(entries)
    if value is None:
        ledger[0].pop("review_version")
    else:
        ledger[0]["review_version"] = value
    errors = validate(entries, ledger)
    assert any("review_version" in error for error in errors)


def test_flags_must_be_list_not_string():
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["flags"] = FLAG_VARIABLE_DEMAND
    errors = validate(entries, ledger)
    assert any("flags must be a list" in error for error in errors)


def test_flags_reject_unknown_value():
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["flags"] = ["NOT_A_REAL_FLAG"]
    errors = validate(entries, ledger)
    assert any("unknown flag" in error for error in errors)


def test_flags_reject_non_string_value():
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["flags"] = [123]
    errors = validate(entries, ledger)
    assert any("must be a string" in error for error in errors)


def test_flags_reject_duplicates():
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["flags"] = [FLAG_VARIABLE_DEMAND, FLAG_VARIABLE_DEMAND]
    errors = validate(entries, ledger)
    assert any("duplicate flag" in error for error in errors)


def test_validator_rejects_malformed_proposed_object():
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["proposed"] = []
    errors = validate(entries, ledger)
    assert any("proposed must be an object" in error for error in errors)


def test_reviewed_source_hash_change_is_stale():
    entries = _entries()
    ledger = _reviewed(entries)
    changed = copy.deepcopy(entries)
    changed[0]["drills"][0]["notes"] = "Changed after clinical review"
    errors = validate(changed, ledger)
    assert any("STALE_SOURCE_HASH" in error for error in errors)


def test_surface_record_returns_specific_msk_exclusion_error():
    surface = [
        {
            "location": "cheek",
            "type": "laceration",
            "phase_progression": "GPP",
            "drills": [
                {
                    "id": "cheek_laceration_clean",
                    "name": "Clean and dress",
                    "notes": "Wound care",
                }
            ],
        }
    ]
    bad = [
        {
            "drill_id": "cheek_laceration_clean",
            "source_hash": "0" * 64,
            "location": "cheek",
            "injury_type": "laceration",
            "name": "Clean and dress",
            "notes": "Wound care",
            "movement_archetype": "unknown",
            "proposed": {field: None for field in REVIEW_FIELDS},
            "flags": [],
            "review_state": "needs_review",
            "review_version": LEDGER_VERSION,
        }
    ]
    errors = validate(surface, bad)
    assert any(
        "must not receive MSK review metadata" in error
        for error in errors
    )


def test_accepted_review_cannot_create_canonical_bank_validation_error():
    """Ledger acceptance must imply structural validity after application."""
    entries = _entries()
    ledger = _reviewed(entries)
    ledger[0]["proposed"].update(
        {
            "target_regions": ["ankle"],
            "target_tissues": [],
            "equipment": [],
            "impact": "none",
            "load": "low",
            "velocity": "low",
            "evidence_notes": "Reviewed mechanical classification.",
        }
    )

    assert validate(entries, ledger) == []
    applied, applied_ids, stale_ids = apply_reviews(entries, ledger)
    assert applied_ids == ["ankle_sprain_iso_hold"]
    assert stale_ids == []

    canonical_issues = validate_rehab_bank(applied, duplicate_debt={})
    errors = [issue for issue in canonical_issues if issue.severity == ERROR]
    assert errors == []
