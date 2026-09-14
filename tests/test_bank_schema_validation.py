from __future__ import annotations

import pytest

from fightcamp import bank_schema, conditioning


@pytest.fixture(autouse=True)
def clear_schema_warning_cache():
    bank_schema._SCHEMA_WARNINGS_LOGGED.clear()
    yield
    bank_schema._SCHEMA_WARNINGS_LOGGED.clear()


def test_validate_training_item_rejects_missing_name_and_logs_once(monkeypatch: pytest.MonkeyPatch):
    warnings: list[str] = []
    monkeypatch.setattr(bank_schema.logger, "warning", warnings.append)

    with pytest.raises(ValueError, match="Missing required 'name'"):
        bank_schema.validate_training_item({}, source="unit", mode="runtime")

    with pytest.raises(ValueError, match="Missing required 'name'"):
        bank_schema.validate_training_item({}, source="unit", mode="runtime")

    assert len(warnings) == 1
    assert "Missing required 'name'" in warnings[0]


def test_validate_training_item_runtime_marks_missing_tags_and_phases_without_defaulting(monkeypatch: pytest.MonkeyPatch):
    warnings: list[str] = []
    monkeypatch.setattr(bank_schema.logger, "warning", warnings.append)

    item = bank_schema.validate_training_item({"name": "Band Circuit"}, source="unit", mode="runtime")
    repeated = bank_schema.validate_training_item({"name": "Band Circuit"}, source="unit", mode="runtime")

    assert "tags" not in item
    assert "phases" not in item
    assert "tags" not in repeated
    assert "phases" not in repeated
    assert item["_schema_issues"] == ["missing_tags", "missing_phases"]
    assert item["_schema_safety"]["late_fight_eligible"] is False
    assert len(warnings) == 2
    assert "Missing or invalid 'tags'" in warnings[0]
    assert "Missing or invalid 'phases'" in warnings[1]


def test_validate_training_item_audit_keeps_legacy_defaults_for_report_only_mode():
    item = bank_schema.validate_training_item({"name": "Band Circuit"}, source="unit", mode="audit")

    assert item["tags"] == []
    assert item["phases"] == bank_schema.DEFAULT_PHASES


def test_validate_training_item_strict_rejects_missing_phases():
    with pytest.raises(ValueError, match="Missing or invalid 'phases'"):
        bank_schema.validate_training_item(
            {"name": "Band Circuit", "tags": []},
            source="unit",
            mode="strict",
        )


def test_validate_training_item_requires_system_when_requested(monkeypatch: pytest.MonkeyPatch):
    warnings: list[str] = []
    monkeypatch.setattr(bank_schema.logger, "warning", warnings.append)

    with pytest.raises(ValueError, match="Missing required 'system'"):
        bank_schema.validate_training_item(
            {"name": "Sprint Circuit", "tags": [], "phases": ["SPP"]},
            source="conditioning",
            require_system=True,
            mode="runtime",
        )

    assert len(warnings) == 1
    assert "Missing required 'system'" in warnings[0]

def test_validate_training_item_backfills_exercise_bank_schema_defaults():
    item = bank_schema.validate_training_item(
        {"name": "Tempo Goblet Squat", "tags": ["strength"], "phases": ["GPP"]},
        source="exercise_bank.json",
        mode="audit",
    )

    assert item["late_windows"] == []
    assert item["impact_cost"] == ""
    assert item["movement_cost"] == ""
    assert item["cns_load"] == ""
    assert item["sport_specific"] is False


def test_validate_training_item_backfills_conditioning_bank_schema_defaults():
    item = bank_schema.validate_training_item(
        {"name": "Easy Bike", "tags": ["aerobic"], "phases": ["TAPER"], "system": "aerobic"},
        source="conditioning_bank.json",
        mode="audit",
    )

    assert item["late_windows"] == []
    assert item["work_sec"] is None
    assert item["rest_sec"] is None
    assert item["rounds"] is None
    assert item["total_minutes"] is None
    assert item["rpe"] is None
    assert item["lactate_load"] == ""


def test_conditioning_bank_membership_does_not_grant_primary_aerobic_authority():
    bank = conditioning.get_conditioning_bank()
    aerobic_names = {item["name"] for item in bank if item.get("system") == "aerobic"}
    by_name = {item["name"]: item for item in bank}

    assert {"Turkish Get-Up Skill Flow", "Wrist/Finger Activation Micro-Reset"}.isdisjoint(aerobic_names)
    assert "Bike Zone 2 (Nasal Only)" in aerobic_names
    assert "Agility Ladder (Recovery)" in aerobic_names
    assert not bank_schema.has_meaningful_fulfillment_authority(
        by_name["Agility Ladder (Recovery)"],
        source_kind="conditioning",
        source="conditioning_bank.json",
    )
    assert bank_schema.has_meaningful_fulfillment_authority(
        by_name["Bike Zone 2 (Nasal Only)"],
        source_kind="conditioning",
        source="conditioning_bank.json",
    )
    assert not {
        item.get("system") for item in bank
    }.intersection(bank_schema.SUPPORT_ONLY_SYSTEM_ALIASES)


def _governed_conditioning_item(**overrides):
    item = {
        "name": "Governed aerobic",
        "tags": ["aerobic"],
        "phases": ["GPP"],
        "system": "aerobic",
        "late_windows": [bank_schema.D21_TO_D14],
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "anchor",
        "cost_class": "low",
        "support_only": False,
        "meaningful_stress": True,
    }
    item.update(overrides)
    return item


@pytest.mark.parametrize("rpe_field", ["rpe", "rpe_max"])
def test_conditioning_rpe_contract_accepts_either_supported_shape(rpe_field):
    item = _governed_conditioning_item(total_minutes=20, **{rpe_field: 5})

    validated = bank_schema.validate_training_item(
        item, source="conditioning_bank.json", mode="runtime"
    )

    assert "missing_rpe" not in validated.get("_schema_issues", [])
    assert "missing_rpe_max" not in validated.get("_schema_issues", [])


@pytest.mark.parametrize(
    "dose",
    [
        {"total_minutes": 20},
        {"work_sec": 60, "rest_sec": 30, "rounds": 6},
    ],
)
def test_conditioning_dose_contract_accepts_continuous_or_interval_shape(dose):
    validated = bank_schema.validate_training_item(
        _governed_conditioning_item(rpe=5, **dose),
        source="conditioning_bank.json",
        mode="runtime",
    )

    assert "missing_conditioning_dose" not in validated.get("_schema_issues", [])


def test_conditioning_dose_contract_rejects_an_empty_dose():
    validated = bank_schema.validate_training_item(
        _governed_conditioning_item(rpe=5),
        source="conditioning_bank.json",
        mode="runtime",
    )

    assert "missing_conditioning_dose" in validated["_schema_issues"]
    assert not bank_schema.has_meaningful_fulfillment_authority(
        validated,
        source_kind="conditioning",
        source="conditioning_bank.json",
    )


def test_technical_footwork_quality_rep_dose_is_valid_without_fake_intervals():
    item = _governed_conditioning_item(
        name="Quality pivots",
        modality="technical_footwork",
        rpe_max=4,
        sets=3,
        reps_per_side=4,
        rest_sec=30,
        quality_stop_rule="Stop when balance degrades",
    )

    validated = bank_schema.validate_training_item(
        item, source="technical_footwork_bank.json", mode="runtime"
    )

    assert "missing_technical_footwork_dose" not in validated.get("_schema_issues", [])
    assert "missing_conditioning_dose" not in validated.get("_schema_issues", [])


def test_explicit_support_governance_wins_over_system_and_dose():
    item = _governed_conditioning_item(
        total_minutes=45,
        rpe=4,
        stress_class="support",
        support_only=True,
        meaningful_stress=False,
    )

    assert not bank_schema.has_meaningful_fulfillment_authority(
        item,
        source_kind="conditioning",
        source="conditioning_bank.json",
    )


def test_validate_training_item_classifies_loaded_bank_source_names_by_family():
    strength_item = bank_schema.validate_training_item(
        {"name": "Style Lift", "tags": ["strength"], "phases": ["SPP"]},
        source="exercise_bank.json",
        mode="audit",
    )
    conditioning_item = bank_schema.validate_training_item(
        {"name": "Footwork Reset", "tags": ["coordination"], "phases": ["TAPER"], "system": "aerobic"},
        source="technical_footwork_bank.json",
        mode="audit",
    )

    assert strength_item["cns_load"] == ""
    assert strength_item["soreness_risk"] == ""
    assert conditioning_item["rpe"] is None
    assert conditioning_item["lactate_load"] == ""


def test_required_equipment_contributes_to_late_modality_gate():
    item = {
        "name": "Loaded Reset",
        "tags": ["conditioning"],
        "phases": ["TAPER"],
        "late_windows": [bank_schema.D1],
        "system": "aerobic",
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "rpe": 4,
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "required_equipment": ["dumbbell"],
    }

    safety = bank_schema.is_late_fight_metadata_safe(
        item,
        "runtime_fallback",
        bank_schema.D1,
        source_kind="conditioning",
    )

    assert safety["severity"] == "blocked"
    assert "late_block_d1_forbidden_modality" in safety["block_codes"]


def test_validate_training_item_runtime_exposes_missing_late_window_state():
    item = bank_schema.validate_training_item(
        {"name": "Easy Bike", "tags": ["aerobic"], "phases": ["TAPER"], "system": "aerobic"},
        source="conditioning_bank.json",
        mode="runtime",
    )

    assert "late_windows" not in item
    assert "missing_late_windows" in item["_schema_issues"]
    assert item["_schema_safety"]["late_fight_eligible"] is False
