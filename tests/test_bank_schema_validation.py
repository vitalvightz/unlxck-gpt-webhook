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
        bank_schema.validate_training_item({}, source="unit")

    with pytest.raises(ValueError, match="Missing required 'name'"):
        bank_schema.validate_training_item({}, source="unit")

    assert len(warnings) == 1
    assert "Missing required 'name'" in warnings[0]


def test_validate_training_item_defaults_tags_and_phases_and_deduplicates_warnings(monkeypatch: pytest.MonkeyPatch):
    warnings: list[str] = []
    monkeypatch.setattr(bank_schema.logger, "warning", warnings.append)

    item = bank_schema.validate_training_item({"name": "Band Circuit"}, source="unit")
    repeated = bank_schema.validate_training_item({"name": "Band Circuit"}, source="unit")

    assert item["tags"] == []
    assert item["phases"] == bank_schema.DEFAULT_PHASES
    assert repeated["tags"] == []
    assert repeated["phases"] == bank_schema.DEFAULT_PHASES
    assert len(warnings) == 2
    assert "defaulting to []." in warnings[0]
    assert "defaulting to" in warnings[1]


def test_validate_training_item_requires_system_when_requested(monkeypatch: pytest.MonkeyPatch):
    warnings: list[str] = []
    monkeypatch.setattr(bank_schema.logger, "warning", warnings.append)

    with pytest.raises(ValueError, match="Missing required 'system'"):
        bank_schema.validate_training_item(
            {"name": "Sprint Circuit", "tags": [], "phases": ["SPP"]},
            source="conditioning",
            require_system=True,
        )

    assert len(warnings) == 1
    assert "Missing required 'system'" in warnings[0]

def test_validate_training_item_backfills_exercise_bank_schema_defaults():
    item = bank_schema.validate_training_item(
        {"name": "Tempo Goblet Squat", "tags": ["strength"], "phases": ["GPP"]},
        source="exercise_bank.json",
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
    )

    assert item["late_windows"] == []
    assert item["work_sec"] is None
    assert item["rest_sec"] is None
    assert item["rounds"] is None
    assert item["total_minutes"] is None
    assert item["rpe"] is None
    assert item["lactate_load"] == ""
