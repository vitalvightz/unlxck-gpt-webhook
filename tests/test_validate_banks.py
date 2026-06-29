from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.bank_schema import is_late_fight_metadata_safe, validate_training_item
from fightcamp.late_selector_windows import D1, D6_TO_D5, D7, D13_TO_D8, D21_TO_D14
from tools import validate_banks


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_fixture_banks(data_dir: Path) -> None:
    _write_json(
        data_dir / "tag_vocabulary.json",
        ["aerobic", "conditioning", "coordination", "high_impact", "speed"],
    )
    _write_json(
        data_dir / "injury_exclusion_map.json",
        {"knee": ["conditioning_bank:Bad Sprint"]},
    )
    _write_json(
        data_dir / "exercise_bank.json",
        [
            {
                "name": "Primer Push",
                "tags": ["speed"],
                "phases": ["TAPER"],
                "late_windows": ["d6_to_d5"],
                "impact_cost": "low",
                "movement_cost": "low",
                "cns_load": "low",
                "eccentric_cost": "low",
                "landing_cost": "low",
                "soreness_risk": "low",
                "stress_class": "support",
                "cost_class": "low",
                "support_only": True,
                "meaningful_stress": False,
            }
        ],
    )
    _write_json(
        data_dir / "conditioning_bank.json",
        [
            {
                "name": "Bad Sprint",
                "tags": ["conditioning", "high_impact"],
                "system": "mystery",
                "impact_cost": "high",
                "movement_cost": "high",
                "lactate_load": "high",
                "rpe": 9,
            }
        ],
    )
    _write_json(
        data_dir / "style_conditioning_bank.json",
        [
            {
                "name": "Alias Drill",
                "tags": ["conditioning"],
                "phases": ["SPP"],
                "late_windows": ["d13_to_d8"],
                "system": "atp-pcr",
                "impact_cost": "low",
                "movement_cost": "low",
                "lactate_load": "low",
                "rpe_max": 6,
                "stress_class": "support",
                "cost_class": "low",
                "support_only": True,
                "meaningful_stress": False,
            }
        ],
    )
    _write_json(
        data_dir / "coordination_bank.json",
        {"general": [{"name": "Balance Reset", "tags": ["coordination"], "phases": ["TAPER"]}]},
    )
    _write_json(
        data_dir / "rehab_bank.json",
        [{"location": "ankle", "type": "sprain", "drills": [{"name": "Band Circles"}]}],
    )


def test_validator_discovery_includes_previously_skipped_banks():
    discovered_names = {path.name for path in validate_banks.discover_banks()}

    assert "coordination_bank.json" in discovered_names
    assert "rehab_bank.json" in discovered_names
    assert "style_conditioning_bank.json" in discovered_names
    assert "regex_patterns.json" not in discovered_names


def test_validator_audit_reports_required_groups_without_failing(tmp_path: Path):
    _write_fixture_banks(tmp_path)
    output: list[str] = []

    exit_code = validate_banks.run_validation("audit", tmp_path, emit=output.append)
    text = "\n".join(output)

    assert exit_code == 0
    assert "missing phases:" in text
    assert "not late-fight eligible" in text
    assert "unknown conditioning system:" in text
    assert "mystery -> mystery" in text
    assert "alias-only conditioning system:" in text
    assert "atp-pcr -> alactic" in text
    assert "coordination_bank.json" in text
    assert "rehab_bank.json" in text


def test_validator_strict_fails_on_required_field_issues(tmp_path: Path):
    _write_fixture_banks(tmp_path)

    exit_code = validate_banks.run_validation("strict", tmp_path, emit=lambda _message: None)

    assert exit_code == 1


def test_runtime_missing_late_windows_blocks_late_fight_selection():
    item = validate_training_item(
        {"name": "Easy Bike", "tags": ["aerobic"], "phases": ["TAPER"], "system": "aerobic"},
        source="conditioning_bank.json",
        mode="runtime",
    )

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D6_TO_D5,
        bridge_rules={},
    )

    assert item["_schema_safety"]["late_fight_eligible"] is False
    assert result["blocked"] is True
    assert "late_block_missing_late_windows" in result["block_codes"]


def _safe_conditioning(**overrides) -> dict:
    item = {
        "name": "Safe Rhythm",
        "tags": ["conditioning"],
        "phases": ["TAPER"],
        "system": "aerobic",
        "late_windows": [D21_TO_D14, D13_TO_D8, D7, D6_TO_D5, D1],
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "rpe": 5,
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
    }
    item.update(overrides)
    return item


def _safe_strength(**overrides) -> dict:
    item = {
        "name": "Safe Strength Touch",
        "tags": ["strength"],
        "phases": ["TAPER"],
        "late_windows": [D21_TO_D14, D13_TO_D8, D7, D6_TO_D5, D1],
        "impact_cost": "low",
        "movement_cost": "low",
        "cns_load": "low",
        "soreness_risk": "low",
        "eccentric_cost": "low",
        "landing_cost": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "equipment": [],
    }
    item.update(overrides)
    return item


def test_runtime_missing_cost_metadata_blocks_late_fight_selection():
    safety = is_late_fight_metadata_safe(
        _safe_conditioning(impact_cost=""),
        "conditioning_bank.json",
        D21_TO_D14,
    )

    assert safety["safe"] is False
    assert "late_block_missing_cost_metadata" in safety["block_codes"]


def test_runtime_unknown_conditioning_system_blocks_late_fight_selection():
    safety = is_late_fight_metadata_safe(
        _safe_conditioning(system="mystery"),
        "conditioning_bank.json",
        D21_TO_D14,
    )

    assert safety["safe"] is False
    assert "late_block_unknown_system" in safety["block_codes"]


def test_support_alias_system_does_not_become_meaningful_stress_by_default():
    safety = is_late_fight_metadata_safe(
        _safe_conditioning(system="skill", support_only=False, stress_class="meaningful_stress"),
        "style_conditioning_bank.json",
        D21_TO_D14,
    )

    assert safety["safe"] is False
    assert "late_block_alias_system_without_meaningful_stress" in safety["block_codes"]


def test_runtime_high_intensity_gates_use_countdown_windows():
    assert "late_block_high_rpe" in is_late_fight_metadata_safe(
        _safe_conditioning(rpe=8),
        "conditioning_bank.json",
        D7,
    )["block_codes"]
    assert "late_block_high_lactate" in is_late_fight_metadata_safe(
        _safe_conditioning(lactate_load="high"),
        "conditioning_bank.json",
        D13_TO_D8,
    )["block_codes"]
    assert "late_block_high_movement_cost" in is_late_fight_metadata_safe(
        _safe_conditioning(movement_cost="high"),
        "conditioning_bank.json",
        D13_TO_D8,
    )["block_codes"]


def test_runtime_d1_blocks_forbidden_modalities_without_final_day_policy():
    safety = is_late_fight_metadata_safe(
        _safe_strength(equipment=["bands"], tags=["strength", "ballistic"]),
        "exercise_bank.json",
        D1,
    )

    assert safety["safe"] is False
    assert "late_block_d1_forbidden_modality" in safety["block_codes"]


def test_runtime_primer_only_cannot_satisfy_strength_maintenance():
    safety = is_late_fight_metadata_safe(
        _safe_strength(tags=["strength", "neural_primer", "late_strength_touch"], primer_only=True),
        "exercise_bank.json",
        D21_TO_D14,
    )

    assert safety["safe"] is False
    assert "late_block_primer_only_strength_fulfillment" in safety["block_codes"]


def test_support_only_false_stress_cannot_satisfy_anchor_requirements():
    strength_safety = is_late_fight_metadata_safe(
        _safe_strength(tags=["strength", "maximal_strength_maintenance"]),
        "exercise_bank.json",
        D21_TO_D14,
    )
    conditioning_safety = is_late_fight_metadata_safe(
        _safe_conditioning(stress_class="meaningful_stress"),
        "conditioning_bank.json",
        D21_TO_D14,
    )

    assert "late_block_support_only_anchor_fulfillment" in strength_safety["block_codes"]
    assert "late_block_support_only_anchor_fulfillment" in conditioning_safety["block_codes"]
