from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.bank_schema import validate_training_item
from fightcamp.late_selector_windows import D6_TO_D5
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
    )

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D6_TO_D5,
        bridge_rules={},
    )

    assert item["_schema_safety"]["late_fight_eligible"] is False
    assert result["blocked"] is True
    assert "late_conditioning_block_missing_late_windows" in result["block_codes"]
