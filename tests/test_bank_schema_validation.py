from __future__ import annotations

import pytest

from fightcamp import bank_schema


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
