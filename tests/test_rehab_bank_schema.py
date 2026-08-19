"""Rehab-bank data contract: schema helpers and strict validation.

The validator is the CI gate for ``data/rehab_bank.json``. These lock in what it
must reject, and — just as importantly — that it never repairs a finding by
guessing: an unrecognised function class stays an error instead of quietly
becoming ``"control"``.
"""

from __future__ import annotations

import json

import pytest

from fightcamp import rehab_schema
from fightcamp.rehab_protocols import REHAB_FUNCTION_BUCKETS, _FUNCTION_LABELS, _FUNCTION_PURPOSES
from tools import validate_rehab_bank as validator

ERROR = validator.ERROR
INFO = validator.INFO


def _msk_drill(**overrides) -> dict:
    """A fully migrated musculoskeletal drill."""
    drill = {
        "id": "ankle_sprain_single_leg_balance_on_foam_pad",
        "name": "Single-Leg Balance on Foam Pad",
        "notes": "GPP: Rebuild proprioception",
        "rehab_stage": "restore",
        "function": "control",
        "equipment": ["foam_pad"],
        "dose": {"sets": 3, "reps": None, "duration_seconds": 30},
        "impact": "none",
        "load": "low",
        "velocity": "low",
        "pain_ceiling": 3,
        "allowed_severities": ["low", "moderate"],
        "progress_when": ["30s hold is steady and pain-free"],
        "regress_when": ["symptoms flare the morning after"],
        "stop_when": ["sharp pain at the joint line"],
    }
    drill.update(overrides)
    return drill


def _msk_entry(*drills, **overrides) -> dict:
    entry = {
        "location": "ankle",
        "type": "sprain",
        "phase_progression": "GPP → SPP",
        "drills": list(drills) or [_msk_drill()],
    }
    entry.update(overrides)
    return entry


def _wound_drill(**overrides) -> dict:
    drill = {
        "id": "knee_cut_no_reopen_protection",
        "name": "No-Reopen Protection",
        "notes": "GPP: Avoid friction or contact directly over the wound",
    }
    drill.update(overrides)
    return drill


def _wound_entry(*drills, **overrides) -> dict:
    entry = {
        "location": "knee",
        "type": "cut",
        "phase_progression": "GPP → SPP → TAPER",
        "drills": list(drills) or [_wound_drill()],
    }
    entry.update(overrides)
    return entry


def _codes(issues, severity: str | None = None) -> set[str]:
    return {issue.code for issue in issues if severity is None or issue.severity == severity}


def _errors(bank, **kwargs) -> list:
    """Errors under the strict reading: no duplicate is grandfathered."""
    return [issue for issue in validator.validate_rehab_bank(bank, **kwargs) if issue.severity == ERROR]


def _shipped_bank() -> list[dict]:
    from fightcamp.config import DATA_DIR

    return json.loads((DATA_DIR / "rehab_bank.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Enum ownership
# ---------------------------------------------------------------------------


def test_function_buckets_are_keyed_by_the_schema_enum():
    """rehab_schema owns the function enum; the keyword buckets must match it."""
    assert set(REHAB_FUNCTION_BUCKETS) == set(rehab_schema.REHAB_FUNCTIONS)
    assert set(_FUNCTION_LABELS) == set(rehab_schema.REHAB_FUNCTIONS)
    assert set(_FUNCTION_PURPOSES) == set(rehab_schema.REHAB_FUNCTIONS)


def test_rehab_stages_are_the_five_declared_stages():
    assert rehab_schema.REHAB_STAGES == ("calm", "restore", "load", "dynamic", "return")


def test_schema_borrows_injury_types_from_the_taxonomy():
    from fightcamp.injury_registry import REHAB_BLOCKED_TYPES, REHAB_SAFE_TYPES

    assert rehab_schema.canonical_rehab_types() == REHAB_SAFE_TYPES
    # Types held for clinical clearance never own bank entries.
    assert not rehab_schema.canonical_rehab_types() & REHAB_BLOCKED_TYPES


def test_schema_borrows_locations_from_the_parser_and_location_registry():
    from fightcamp.injury_location_registry import LOCATION_REGISTRY

    locations = rehab_schema.canonical_rehab_locations()
    assert "unspecified" in locations
    assert {"ankle", "shoulder", "lower_back"} <= locations
    for data in LOCATION_REGISTRY.values():
        assert set(data.get("rehab_locations", [])) <= locations


# ---------------------------------------------------------------------------
# A valid bank passes
# ---------------------------------------------------------------------------


def test_valid_bank_passes():
    assert _errors([_msk_entry(), _wound_entry()]) == []


def test_fully_migrated_drill_reports_nothing_pending():
    issues = validator.validate_rehab_bank([_msk_entry()])
    assert _codes(issues) == set()
    assert rehab_schema.is_migration_complete(_msk_drill())


def test_shipped_rehab_bank_passes_validation():
    bank = _shipped_bank()
    issues = validator.validate_rehab_bank(bank, duplicate_debt=validator.load_duplicate_debt())
    assert [issue for issue in issues if issue.severity == ERROR] == []


def test_shipped_rehab_bank_matches_its_deterministic_migration():
    from tools.migrate_rehab_bank_schema import main as migrate_main

    assert migrate_main(["--check"]) == 0


# ---------------------------------------------------------------------------
# Structural failures
# ---------------------------------------------------------------------------


def test_non_list_root_fails():
    assert _codes(validator.validate_rehab_bank({"drills": []}), ERROR) == {"invalid_root"}


def test_duplicate_drill_ids_fail():
    bank = [
        _msk_entry(_msk_drill()),
        _msk_entry(_msk_drill(name="Banded Ankle Circles", notes="Other note"), type="strain"),
    ]
    issues = validator.validate_rehab_bank(bank)
    assert "duplicate_drill_id" in _codes(issues, ERROR)


def test_invalid_drill_id_shape_fails():
    issues = validator.validate_rehab_bank([_msk_entry(_msk_drill(id="Ankle Sprain!"))])
    assert "invalid_drill_id" in _codes(issues, ERROR)


def test_missing_drill_id_fails():
    drill = _msk_drill()
    del drill["id"]
    assert "missing_drill_id" in _codes(validator.validate_rehab_bank([_msk_entry(drill)]), ERROR)


def test_missing_drill_name_fails():
    assert "missing_drill_name" in _codes(validator.validate_rehab_bank([_msk_entry(_msk_drill(name=" "))]), ERROR)


def test_entry_without_drills_fails():
    assert "missing_drills" in _codes(validator.validate_rehab_bank([_msk_entry(drills=[])]), ERROR)


def test_exact_duplicate_location_type_stage_drill_combination_fails():
    bank = [_msk_entry(_msk_drill(), _msk_drill(id="ankle_sprain_single_leg_balance_on_foam_pad_2"))]
    assert "duplicate_drill_combination" in _codes(validator.validate_rehab_bank(bank), ERROR)


def test_same_drill_name_in_a_different_stage_is_not_a_duplicate():
    bank = [
        _msk_entry(
            _msk_drill(),
            _msk_drill(id="ankle_sprain_single_leg_balance_on_foam_pad_2", rehab_stage="load"),
        )
    ]
    assert "duplicate_drill_combination" not in _codes(validator.validate_rehab_bank(bank), ERROR)


# ---------------------------------------------------------------------------
# Canonical registry failures
# ---------------------------------------------------------------------------


def test_invalid_location_fails():
    issues = validator.validate_rehab_bank([_msk_entry(location="left_kneecap_area")])
    assert "unknown_location" in _codes(issues, ERROR)
    assert any("left_kneecap_area" in issue.detail for issue in issues)


def test_invalid_injury_type_fails():
    assert "unknown_type" in _codes(validator.validate_rehab_bank([_msk_entry(type="mystery_ache")]), ERROR)


def test_clinically_blocked_injury_type_cannot_own_bank_entries():
    """Fractures and the like route to the red-flag path, never to rehab drills."""
    assert "unknown_type" in _codes(validator.validate_rehab_bank([_msk_entry(type="fracture")]), ERROR)


@pytest.mark.parametrize(
    "progression",
    ["", "   ", "GPP → PEAK", "DELOAD", "GPP → GPP", None, 5],
)
def test_malformed_phase_progression_fails(progression):
    issues = validator.validate_rehab_bank([_msk_entry(phase_progression=progression)])
    assert "malformed_phase_progression" in _codes(issues, ERROR)


def test_well_formed_phase_progressions_pass():
    for progression in ("GPP", "SPP → TAPER", "GPP → SPP → TAPER"):
        assert _errors([_msk_entry(phase_progression=progression)]) == []


# ---------------------------------------------------------------------------
# Finite-value failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["rebuild", "RESTORE", "", 2, ["restore"]])
def test_invalid_rehab_stage_fails(stage):
    assert "invalid_rehab_stage" in _codes(validator.validate_rehab_bank([_msk_entry(_msk_drill(rehab_stage=stage))]), ERROR)


@pytest.mark.parametrize("stage", list(rehab_schema.REHAB_STAGES) + [None])
def test_declared_rehab_stages_pass(stage):
    assert _errors([_msk_entry(_msk_drill(rehab_stage=stage))]) == []


@pytest.mark.parametrize(
    "field,bad,good",
    [
        ("impact", "explosive", "none"),
        ("impact", "minimal", "high"),
        ("load", "none", "minimal"),
        ("velocity", "none", "low"),
        ("velocity", "ballistic", "high"),
    ],
)
def test_invalid_impact_load_velocity_fail(field, bad, good):
    bad_issues = validator.validate_rehab_bank([_msk_entry(_msk_drill(**{field: bad}))])
    assert f"invalid_{field}" in _codes(bad_issues, ERROR)
    assert _errors([_msk_entry(_msk_drill(**{field: good}))]) == []


@pytest.mark.parametrize(
    "dose",
    [
        {"sets": 0},
        {"sets": -1, "reps": None, "duration_seconds": None},
        {"sets": "3", "reps": None, "duration_seconds": None},
        {"tempo": "3-1-3"},
        [3, 10],
        "3x10",
    ],
)
def test_malformed_dose_fails(dose):
    assert "invalid_dose" in _codes(validator.validate_rehab_bank([_msk_entry(_msk_drill(dose=dose))]), ERROR)


def test_dose_with_declared_structure_and_unprescribed_slots_passes():
    dose = {"sets": None, "reps": None, "duration_seconds": None}
    assert _errors([_msk_entry(_msk_drill(dose=dose))]) == []


@pytest.mark.parametrize("ceiling", [-1, 11, "3", "none", [3], True])
def test_invalid_pain_ceiling_fails(ceiling):
    assert "invalid_pain_ceiling" in _codes(validator.validate_rehab_bank([_msk_entry(_msk_drill(pain_ceiling=ceiling))]), ERROR)


@pytest.mark.parametrize("ceiling", [0, 3, 10, 4.5, rehab_schema.PAIN_CEILING_UNRESTRICTED, None])
def test_valid_pain_ceilings_pass(ceiling):
    assert _errors([_msk_entry(_msk_drill(pain_ceiling=ceiling))]) == []


@pytest.mark.parametrize(
    "severities",
    [[], ["mild"], ["low", "low"], "low", ["severe"], [None]],
)
def test_invalid_severity_values_fail(severities):
    issues = validator.validate_rehab_bank([_msk_entry(_msk_drill(allowed_severities=severities))])
    assert "invalid_allowed_severities" in _codes(issues, ERROR)


def test_declared_severity_values_pass():
    assert _errors([_msk_entry(_msk_drill(allowed_severities=list(rehab_schema.SEVERITY_VALUES)))]) == []


@pytest.mark.parametrize("field", ["progress_when", "regress_when", "stop_when"])
@pytest.mark.parametrize("value", ["pain settles", [""], [3], {"when": "pain settles"}])
def test_malformed_progression_regression_stop_rules_fail(field, value):
    issues = validator.validate_rehab_bank([_msk_entry(_msk_drill(**{field: value}))])
    assert f"invalid_{field}" in _codes(issues, ERROR)


@pytest.mark.parametrize("field", ["progress_when", "regress_when", "stop_when"])
def test_empty_rule_list_is_a_deliberate_no_criteria_value(field):
    assert _errors([_msk_entry(_msk_drill(**{field: []}))]) == []


@pytest.mark.parametrize("equipment", ["foam_pad", [""], [None], {"foam_pad": True}])
def test_malformed_equipment_fails(equipment):
    assert "invalid_equipment" in _codes(validator.validate_rehab_bank([_msk_entry(_msk_drill(equipment=equipment))]), ERROR)


def test_empty_equipment_list_means_needs_nothing():
    assert _errors([_msk_entry(_msk_drill(equipment=[]))]) == []


# ---------------------------------------------------------------------------
# Function metadata is never guessed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("function", ["wobble", "Control", "balance", 7, ["control"]])
def test_invalid_function_fails(function):
    issues = validator.validate_rehab_bank([_msk_entry(_msk_drill(function=function))])
    assert "invalid_function" in _codes(issues, ERROR)


def test_missing_function_metadata_is_identified():
    drill = _msk_drill()
    del drill["function"]
    codes = _codes(validator.validate_rehab_bank([_msk_entry(drill)]), ERROR)
    assert "missing_function" in codes
    assert "missing_contract_field" in codes


def test_unknown_function_does_not_silently_become_control():
    """An unrecognised class stays an error; nothing coerces it to a valid one."""
    drill = _msk_drill(function="proprioceptive_wobble")
    issues = validator.validate_rehab_bank([_msk_entry(drill)])

    assert "invalid_function" in _codes(issues, ERROR)
    # The drill dict is never rewritten, and the declared-function reader
    # refuses to report an unknown value as a real class.
    assert drill["function"] == "proprioceptive_wobble"
    assert rehab_schema.get_declared_function(drill) is None
    assert rehab_schema.resolve_drill_function(drill, "mobility") == "mobility"


def test_validation_never_consults_the_keyword_classifier(monkeypatch):
    """The legacy 'control' default is a runtime fallback, not a validation crutch."""
    import fightcamp.rehab_protocols as rehab_protocols

    def _boom(*_args, **_kwargs):
        raise AssertionError("validation must not classify drills by keyword")

    monkeypatch.setattr(rehab_protocols, "classify_drill_function", _boom)
    monkeypatch.setattr(rehab_protocols, "match_drill_function", _boom)

    assert validator.validate_rehab_bank([_msk_entry(_msk_drill(function=None))]) is not None


def test_unmigrated_function_is_reported_as_pending_not_as_an_error():
    issues = validator.validate_rehab_bank([_msk_entry(_msk_drill(function=None))])
    assert _codes(issues, ERROR) == set()
    assert "unmigrated_function" in _codes(issues, INFO)


# ---------------------------------------------------------------------------
# Unknown vs. deliberately unrestricted
# ---------------------------------------------------------------------------


def test_null_marks_a_field_as_not_yet_migrated():
    drill = _msk_drill(pain_ceiling=None, stop_when=None, equipment=None)
    assert rehab_schema.unmigrated_fields(drill) == ["equipment", "pain_ceiling", "stop_when"]
    assert not rehab_schema.is_migration_complete(drill)


def test_deliberately_unrestricted_values_are_not_reported_as_unmigrated():
    drill = _msk_drill(
        pain_ceiling=rehab_schema.PAIN_CEILING_UNRESTRICTED,
        equipment=[],
        stop_when=[],
        progress_when=[],
        regress_when=[],
    )
    assert rehab_schema.unmigrated_fields(drill) == []
    assert _errors([_msk_entry(drill)]) == []


def test_pending_migration_is_reported_per_drill():
    drill = _msk_drill(rehab_stage=None, impact=None)
    issues = [issue for issue in validator.validate_rehab_bank([_msk_entry(drill)]) if issue.code == "pending_migration"]
    assert len(issues) == 1
    assert "rehab_stage" in issues[0].detail and "impact" in issues[0].detail


def test_strict_migration_mode_fails_on_not_yet_migrated_fields(tmp_path):
    bank = tmp_path / "rehab_bank.json"
    bank.write_text(json.dumps([_msk_entry(_msk_drill(rehab_stage=None))]), encoding="utf-8")

    assert validator.run_validation(bank, emit=lambda _m: None) == 0
    assert validator.run_validation(bank, emit=lambda _m: None, strict_migration=True) == 1


# ---------------------------------------------------------------------------
# Surface injuries stay out of the musculoskeletal schema
# ---------------------------------------------------------------------------


def test_surface_entries_are_classified_as_wound_care():
    for injury_type in ("cut", "laceration", "abrasion", "graze", "blister"):
        assert rehab_schema.care_type_for_injury_type(injury_type) == rehab_schema.CARE_TYPE_WOUND_CARE
    for injury_type in ("sprain", "strain", "tendonitis", "unspecified"):
        assert rehab_schema.care_type_for_injury_type(injury_type) == rehab_schema.CARE_TYPE_MUSCULOSKELETAL


def test_wound_care_drills_are_not_required_to_carry_loading_metadata():
    assert _errors([_wound_entry()]) == []
    assert rehab_schema.unmigrated_fields(_wound_drill(), care_type=rehab_schema.CARE_TYPE_WOUND_CARE) == []


@pytest.mark.parametrize("field,value", [("load", "high"), ("rehab_stage", "load"), ("function", "tendon_loading")])
def test_wound_care_drill_declaring_loading_metadata_fails(field, value):
    issues = validator.validate_rehab_bank([_wound_entry(_wound_drill(**{field: value}))])
    assert "wound_care_loading_metadata" in _codes(issues, ERROR)
    assert any(field in issue.detail for issue in issues)


def test_shipped_surface_entries_carry_no_loading_metadata():
    bank = _shipped_bank()
    surface_drills = [
        drill
        for entry in bank
        if rehab_schema.is_surface_injury_type(entry.get("type"))
        for drill in entry.get("drills", [])
    ]
    assert surface_drills
    for drill in surface_drills:
        assert not set(drill) & set(rehab_schema.MSK_DRILL_FIELDS)


# ---------------------------------------------------------------------------
# Declared duplicate debt
# ---------------------------------------------------------------------------


def _duplicated_bank() -> list[dict]:
    """Two groups carrying the same drill — the pre-schema duplication pattern."""
    return [_msk_entry(_msk_drill()), _msk_entry(_msk_drill(id="ankle_sprain_single_leg_balance_on_foam_pad_2"))]


def _debt(copies: int = 1, **overrides) -> dict:
    row = {
        "location": "ankle",
        "type": "sprain",
        # Matches _msk_drill(); the ledger keys on the drill's declared stage.
        "rehab_stage": "restore",
        "name": "Single-Leg Balance on Foam Pad",
        "grandfathered_copies": copies,
    }
    row.update(overrides)
    return {"duplicates": [row]}


def _debt_map(payload: dict, tmp_path) -> dict:
    ledger = tmp_path / "rehab_bank_duplicate_debt.json"
    ledger.write_text(json.dumps(payload), encoding="utf-8")
    return validator.load_duplicate_debt(ledger)


def test_undeclared_duplicate_fails():
    assert "duplicate_drill_combination" in _codes(validator.validate_rehab_bank(_duplicated_bank()), ERROR)


def test_declared_duplicate_is_reported_as_debt_not_as_an_error(tmp_path):
    issues = validator.validate_rehab_bank(_duplicated_bank(), duplicate_debt=_debt_map(_debt(), tmp_path))

    assert _codes(issues, ERROR) == set()
    assert "grandfathered_duplicate" in _codes(issues, INFO)


def test_declared_duplicate_is_never_reported_silently(tmp_path):
    issues = validator.validate_rehab_bank(_duplicated_bank(), duplicate_debt=_debt_map(_debt(), tmp_path))
    reported = [issue for issue in issues if issue.code == "grandfathered_duplicate"]

    assert len(reported) == 1
    assert "Single-Leg Balance on Foam Pad" in reported[0].detail
    assert "rehab_bank_duplicate_debt.json" in reported[0].detail


def test_extra_copy_beyond_the_declared_count_still_fails(tmp_path):
    bank = [
        *_duplicated_bank(),
        _msk_entry(_msk_drill(id="ankle_sprain_single_leg_balance_on_foam_pad_3")),
    ]
    issues = validator.validate_rehab_bank(bank, duplicate_debt=_debt_map(_debt(), tmp_path))

    assert "duplicate_drill_combination" in _codes(issues, ERROR)
    assert any("not covered by" in issue.detail for issue in issues if issue.severity == ERROR)


def test_debt_does_not_grandfather_a_different_drill(tmp_path):
    debt = _debt_map(_debt(name="Some Other Drill"), tmp_path)
    issues = validator.validate_rehab_bank(_duplicated_bank(), duplicate_debt=debt)
    assert "duplicate_drill_combination" in _codes(issues, ERROR)


def test_a_resolved_duplicate_leaves_a_stale_ledger_row_without_failing(tmp_path):
    issues = validator.validate_rehab_bank([_msk_entry()], duplicate_debt=_debt_map(_debt(), tmp_path))

    assert _codes(issues, ERROR) == set()
    assert "resolved_duplicate_debt" in _codes(issues, INFO)


def test_missing_ledger_means_nothing_is_grandfathered(tmp_path):
    assert validator.load_duplicate_debt(tmp_path / "absent.json") == {}
    assert validator.load_duplicate_debt(None) == {}


def test_shipped_ledger_declares_exactly_the_duplicates_the_bank_still_has():
    """No stale rows, and no duplicate the ledger forgot to declare."""
    issues = validator.validate_rehab_bank(_shipped_bank(), duplicate_debt=validator.load_duplicate_debt())
    codes = _codes(issues)

    assert "duplicate_drill_combination" not in codes
    assert "resolved_duplicate_debt" not in codes
    assert "grandfathered_duplicate" in codes


def test_shipped_ledger_only_declares_duplicates_never_new_drills():
    """Every ledger row must name a drill the bank actually carries."""
    bank_names = {
        (entry["location"], entry["type"], drill.get("name"))
        for entry in _shipped_bank()
        for drill in entry.get("drills", [])
    }
    from fightcamp.config import DATA_DIR

    ledger = json.loads((DATA_DIR / "rehab_bank_duplicate_debt.json").read_text(encoding="utf-8"))
    assert ledger["duplicates"]
    for row in ledger["duplicates"]:
        assert (row["location"], row["type"], row["name"]) in bank_names
        assert row["grandfathered_copies"] >= 1


def test_strict_migration_mode_fails_while_duplicate_debt_remains(tmp_path):
    bank = tmp_path / "rehab_bank.json"
    bank.write_text(json.dumps(_duplicated_bank()), encoding="utf-8")
    ledger = tmp_path / "rehab_bank_duplicate_debt.json"
    ledger.write_text(json.dumps(_debt()), encoding="utf-8")

    assert validator.run_validation(bank, emit=lambda _m: None, duplicate_debt_path=ledger) == 0
    assert (
        validator.run_validation(bank, emit=lambda _m: None, duplicate_debt_path=ledger, strict_migration=True) == 1
    )


def test_migration_removes_no_group_record():
    """PR1 adds fields. It never drops, merges or reorders a group."""
    from tools.migrate_rehab_bank_schema import migrate_entries

    original = [
        {
            "location": "ankle",
            "type": "sprain",
            "phase_progression": "GPP → SPP",
            "drills": [{"name": "Single-Leg Balance on Foam Pad", "notes": "GPP: Rebuild proprioception"}],
        }
    ]
    duplicated = [*original, json.loads(json.dumps(original[0]))]
    migrated = migrate_entries(duplicated)

    assert len(migrated) == 2
    assert [entry["location"] for entry in migrated] == ["ankle", "ankle"]
    assert [drill["name"] for entry in migrated for drill in entry["drills"]] == [
        "Single-Leg Balance on Foam Pad",
        "Single-Leg Balance on Foam Pad",
    ]
    # Ids still have to be unique, so the second copy is suffixed.
    ids = [drill["id"] for entry in migrated for drill in entry["drills"]]
    assert len(set(ids)) == 2


def test_duplicate_debt_ledger_is_not_treated_as_a_training_bank():
    from tools import validate_banks

    discovered = {path.name for path in validate_banks.discover_validation_targets()}
    assert "rehab_bank.json" in discovered
    assert "rehab_bank_duplicate_debt.json" not in discovered


# ---------------------------------------------------------------------------
# CLI / CI wiring
# ---------------------------------------------------------------------------


def test_cli_returns_non_zero_on_a_malformed_bank(tmp_path):
    bank = tmp_path / "rehab_bank.json"
    bank.write_text(json.dumps([_msk_entry(_msk_drill(function="wobble"))]), encoding="utf-8")

    assert validator.main(["--bank", str(bank)]) == 1


def test_cli_returns_zero_on_a_valid_bank(tmp_path):
    bank = tmp_path / "rehab_bank.json"
    bank.write_text(json.dumps([_msk_entry(), _wound_entry()]), encoding="utf-8")

    assert validator.main(["--bank", str(bank)]) == 0


def test_cli_returns_non_zero_on_an_undeclared_duplicate(tmp_path):
    bank = tmp_path / "rehab_bank.json"
    bank.write_text(json.dumps(_duplicated_bank()), encoding="utf-8")

    assert validator.main(["--bank", str(bank), "--duplicate-debt", str(tmp_path / "absent.json")]) == 1


def test_cli_accepts_the_repo_bank_and_ledger():
    assert validator.main([]) == 0


def test_cli_returns_non_zero_on_invalid_json(tmp_path):
    bank = tmp_path / "rehab_bank.json"
    bank.write_text("[{", encoding="utf-8")

    assert validator.run_validation(bank, emit=lambda _m: None) == 1


def test_issues_identify_the_exact_offending_drill():
    bank = [_msk_entry(), _msk_entry(_msk_drill(id="knee_pain_bad", name="Bad Drill", impact="explosive"), type="pain", location="knee")]
    issues = [issue for issue in validator.validate_rehab_bank(bank) if issue.severity == ERROR]

    assert len(issues) == 1
    assert "entry[1]" in issues[0].locator
    assert "knee/pain" in issues[0].locator
    assert "Bad Drill" in issues[0].locator
    assert "knee_pain_bad" in issues[0].locator


def test_shared_bank_validator_reports_rehab_schema_errors(tmp_path):
    from tools import validate_banks

    bank = tmp_path / "rehab_bank.json"
    bank.write_text(json.dumps([_msk_entry(_msk_drill(function="wobble"))]), encoding="utf-8")

    issues = validate_banks.rehab_schema_issues(bank, emit=lambda _m: None)

    assert issues
    assert all(issue.group == validate_banks.REHAB_SCHEMA_GROUP for issue in issues)
    assert any("invalid_function" in issue.detail for issue in issues)
    # Not-yet-migrated findings stay out of the cross-bank report.
    assert all(issue.severity != "info" for issue in issues)


def test_shared_bank_validator_fails_strict_mode_on_rehab_schema_errors(tmp_path):
    from tools import validate_banks

    (tmp_path / "tag_vocabulary.json").write_text(json.dumps(["aerobic"]), encoding="utf-8")
    (tmp_path / "rehab_bank.json").write_text(
        json.dumps([_msk_entry(_msk_drill(function="wobble"))]), encoding="utf-8"
    )

    assert validate_banks.run_validation("strict", tmp_path, emit=lambda _m: None) == 1
