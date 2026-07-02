from __future__ import annotations

import json
from pathlib import Path

from fightcamp import conditioning
from fightcamp.bank_schema import is_late_fight_metadata_safe, validate_training_item
from fightcamp.late_selector_windows import D1, D4_TO_D2, D6_TO_D5, D7, D13_TO_D8, D21_TO_D14
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


def test_validator_extracts_rehab_drills_without_training_metadata_requirements(tmp_path: Path):
    _write_json(
        tmp_path / "rehab_bank.json",
        [{"location": "ankle", "type": "sprain", "drills": [{"name": "Band Circles"}]}],
    )

    success, entry_count, _tags_seen, issues = validate_banks.validate_bank(
        tmp_path / "rehab_bank.json",
        set(),
    )
    issue_groups = {issue.group for issue in issues}

    assert success is True
    assert entry_count == 1
    assert "missing names" not in issue_groups
    assert "missing tags" not in issue_groups
    assert "missing phases" not in issue_groups
    assert "missing/empty late_windows" not in issue_groups
    assert "missing cost fields" not in issue_groups


def test_validator_empty_tag_vocabulary_flags_all_seen_tags(tmp_path: Path):
    _write_json(
        tmp_path / "exercise_bank.json",
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

    success, _entry_count, _tags_seen, issues = validate_banks.validate_bank(
        tmp_path / "exercise_bank.json",
        set(),
    )

    assert success is False
    assert any(issue.group == "tags not in tag_vocabulary" and issue.detail == "speed" for issue in issues)


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


def test_runtime_fallback_missing_late_windows_blocks_all_late_windows():
    item = _safe_conditioning(late_windows=[])

    for window in (D21_TO_D14, D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1):
        result = conditioning._evaluate_conditioning_late_window(
            item,
            system="aerobic",
            window=window,
            bridge_rules={},
            source="runtime_fallback",
        )

        assert result["blocked"] is True
        assert "late_block_missing_late_windows" in result["block_codes"]


def test_runtime_fallback_missing_rpe_and_cost_metadata_blocks_late_selection():
    item = _safe_conditioning(
        impact_cost="",
        movement_cost="",
        lactate_load="",
        stress_class="",
        cost_class="",
        support_only=None,
        meaningful_stress=None,
    )
    item.pop("rpe")

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D21_TO_D14,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is True
    assert "late_block_missing_cost_metadata" in result["block_codes"]
    assert "late_penalty_missing_rpe" in result["penalty_codes"]


def test_missing_governance_metadata_does_not_hard_block_d21_low_risk_support():
    item = _safe_conditioning(
        system="skill",
        tags=["tactical", "cue_card"],
        rpe=3,
        stress_class="",
        cost_class="",
        support_only=None,
        meaningful_stress=None,
    )

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D21_TO_D14,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is False
    assert result["severity"] == "penalty"
    assert "late_penalty_missing_governance_metadata" in result["penalty_codes"]


def test_missing_governance_metadata_cannot_satisfy_strength_maintenance():
    safety = is_late_fight_metadata_safe(
        _safe_strength(
            tags=["strength", "maximal_strength_maintenance"],
            stress_class="",
            cost_class="",
            support_only=None,
            meaningful_stress=None,
        ),
        "exercise_bank.json",
        D21_TO_D14,
    )

    assert safety["severity"] == "blocked"
    assert "late_block_support_only_anchor_fulfillment" in safety["block_codes"]


def test_missing_governance_metadata_cannot_satisfy_conditioning_anchor():
    safety = is_late_fight_metadata_safe(
        _safe_conditioning(
            stress_class="anchor",
            cost_class="",
            support_only=None,
            meaningful_stress=None,
        ),
        "conditioning_bank.json",
        D21_TO_D14,
    )

    assert safety["severity"] == "blocked"
    assert "late_block_support_only_anchor_fulfillment" in safety["block_codes"]


def test_missing_cost_metadata_penalizes_d21_low_risk_support_without_blocking():
    item = _safe_conditioning(
        system="skill",
        tags=["breathing", "reset"],
        rpe=3,
        impact_cost="",
        movement_cost="",
        lactate_load="",
    )

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D21_TO_D14,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is False
    assert result["severity"] == "penalty"
    assert "late_penalty_missing_cost_metadata" in result["penalty_codes"]


def test_missing_cost_metadata_blocks_physical_work_d7_onward():
    item = _safe_conditioning(
        tags=["conditioning", "ballistic"],
        impact_cost="",
        movement_cost="",
        lactate_load="",
        rpe=4,
    )

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D7,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is True
    assert "late_block_missing_cost_metadata" in result["block_codes"]


def test_missing_rpe_blocks_fight_pace_glycolytic_d13_onward():
    item = _safe_conditioning(system="glycolytic", tags=["glycolytic"], load="fight-pace rhythm")
    item.pop("rpe")

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="glycolytic",
        window=D13_TO_D8,
        bridge_rules={"glycolytic_touch_max": 1},
        source="runtime_fallback",
    )

    assert result["blocked"] is True
    assert "late_block_missing_rpe" in result["block_codes"]


def test_missing_rpe_does_not_block_tactical_breathing_support():
    item = _safe_conditioning(system="skill", tags=["breathing", "visualization", "tactical"])
    item.pop("rpe")

    result = conditioning._evaluate_conditioning_late_window(
        item,
        system="aerobic",
        window=D7,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is False
    assert "late_penalty_missing_rpe" in result["penalty_codes"]


def test_runtime_fallback_unknown_system_blocks_late_selection():
    result = conditioning._evaluate_conditioning_late_window(
        _safe_conditioning(system="mystery"),
        system="mystery",
        window=D21_TO_D14,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is True
    assert "late_block_unknown_system" in result["block_codes"]


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


def test_runtime_fallback_support_alias_cannot_claim_meaningful_stress():
    result = conditioning._evaluate_conditioning_late_window(
        _safe_conditioning(system="skill", support_only=False, stress_class="meaningful_stress"),
        system="skill",
        window=D21_TO_D14,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is True
    assert "late_block_alias_system_without_meaningful_stress" in result["block_codes"]


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


def test_runtime_fallback_high_lactate_blocks_d13_onward():
    for window in (D13_TO_D8, D7, D6_TO_D5, D4_TO_D2, D1):
        result = conditioning._evaluate_conditioning_late_window(
            _safe_conditioning(lactate_load="high"),
            system="glycolytic",
            window=window,
            bridge_rules={"glycolytic_touch_max": 1},
            source="runtime_fallback",
        )

        assert result["blocked"] is True
        assert "late_block_high_lactate" in result["block_codes"]


def test_runtime_d1_blocks_forbidden_modalities_without_final_day_policy():
    safety = is_late_fight_metadata_safe(
        _safe_strength(equipment=["bands"], tags=["strength", "ballistic"]),
        "exercise_bank.json",
        D1,
    )

    assert safety["safe"] is False
    assert "late_block_d1_forbidden_modality" in safety["block_codes"]


def test_runtime_d1_blocks_any_equipment_even_with_final_day_policy():
    # No equipment of any kind is allowed on d1; d1_ok cannot override it.
    for equipment in (["double_end_bag"], ["reaction_ball"], ["pad"], ["focus_mitts"]):
        safety = is_late_fight_metadata_safe(
            _safe_strength(equipment=equipment, tags=["strength", "d1_ok"]),
            "exercise_bank.json",
            D1,
        )

        assert safety["safe"] is False, equipment
        assert "late_block_d1_equipment" in safety["block_codes"], equipment


def test_runtime_d1_allows_bodyweight_only_items():
    safety = is_late_fight_metadata_safe(
        _safe_strength(equipment=["bodyweight"], tags=["strength", "d1_ok"]),
        "exercise_bank.json",
        D1,
    )

    assert "late_block_d1_equipment" not in safety["block_codes"]


def test_runtime_d1_mat_and_space_descriptors_are_not_equipment():
    # Surface descriptors like "Mat Space" tokenize into multiple tokens;
    # none of them may trip the d1 equipment block.
    for equipment in (["mat"], "Mat Space", "Open Space", ["mat", "bodyweight"]):
        safety = is_late_fight_metadata_safe(
            _safe_strength(equipment=equipment, tags=["strength", "d1_ok"]),
            "exercise_bank.json",
            D1,
        )

        assert "late_block_d1_equipment" not in safety["block_codes"], equipment


def test_runtime_d1_equipment_block_outside_d1_window_does_not_apply():
    safety = is_late_fight_metadata_safe(
        _safe_strength(equipment=["double_end_bag"], tags=["strength"]),
        "exercise_bank.json",
        D4_TO_D2,
    )

    assert "late_block_d1_equipment" not in safety["block_codes"]


def test_runtime_fallback_d1_blocks_forbidden_conditioning_modality():
    result = conditioning._evaluate_conditioning_late_window(
        _safe_conditioning(equipment=["bands"]),
        system="aerobic",
        window=D1,
        bridge_rules={},
        source="runtime_fallback",
    )

    assert result["blocked"] is True
    assert "late_block_d1_forbidden_modality" in result["block_codes"]


def test_runtime_fallback_d1_blocks_all_forbidden_modality_signals():
    variants = [
        _safe_conditioning(equipment=["bands"]),
        _safe_conditioning(equipment=["medicine_ball"]),
        _safe_conditioning(equipment=["dumbbell"]),
        _safe_conditioning(equipment=[], required_equipment=["dumbbell"]),
        _safe_conditioning(method="isometric"),
        _safe_conditioning(tags=["conditioning", "ballistic"]),
        _safe_conditioning(tags=["conditioning", "max_intent"]),
        _safe_conditioning(rpe=8),
    ]

    for item in variants:
        safety = is_late_fight_metadata_safe(
            item,
            "runtime_fallback",
            D1,
            source_kind="conditioning",
        )

        assert safety["severity"] == "blocked"
        assert "late_block_d1_forbidden_modality" in safety["block_codes"]


def test_runtime_fallback_complete_safe_metadata_can_still_be_selected():
    fallback = conditioning._bridge_glycolytic_touch_fallback()

    result = conditioning._evaluate_conditioning_late_window(
        fallback,
        system="glycolytic",
        window=D21_TO_D14,
        bridge_rules={"glycolytic_touch_max": 1},
        source="runtime_fallback",
    )

    assert result["blocked"] is False


def test_conditioning_reservoir_reports_blocked_and_penalized_metadata_entries(monkeypatch):
    penalized = validate_training_item(
        {
            "name": "Tactical Cue Reset",
            "tags": ["tactical", "cue_card"],
            "phases": ["TAPER"],
            "system": "skill",
            "late_windows": [D21_TO_D14],
            "rpe": 3,
            "equipment": [],
            "required_equipment": [],
        },
        source="conditioning_bank.json",
        require_system=True,
        mode="runtime",
    )
    blocked = validate_training_item(
        {
            "name": "Physical Drill Missing Window",
            "tags": ["conditioning"],
            "phases": ["TAPER"],
            "system": "aerobic",
            "rpe": 5,
            "impact_cost": "low",
            "movement_cost": "low",
            "lactate_load": "low",
            "equipment": [],
            "required_equipment": [],
        },
        source="conditioning_bank.json",
        require_system=True,
        mode="runtime",
    )
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [penalized, blocked])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [])

    *_prefix, candidate_reservoir = conditioning.generate_conditioning_block(
        {
            "phase": "TAPER",
            "fatigue": "low",
            "style_technical": ["boxing"],
            "style_tactical": ["out-boxer"],
            "sport": "boxing",
            "key_goals": ["conditioning"],
            "weaknesses": ["sharpness"],
            "injuries": [],
            "restrictions": [],
            "equipment": ["bodyweight"],
            "training_frequency": 4,
            "days_available": 4,
            "days_until_fight": 18,
            "time_to_fight_days": 18,
        }
    )

    diagnostics = candidate_reservoir["__late_window__"]
    blocked_by_name = {entry["name"]: entry for entry in diagnostics["blocked"]}
    penalized_by_name = {entry["name"]: entry for entry in diagnostics["penalized"]}

    assert "Physical Drill Missing Window" in blocked_by_name
    assert "late_block_missing_late_windows" in blocked_by_name["Physical Drill Missing Window"]["reason_codes"]
    assert "Tactical Cue Reset" in penalized_by_name
    assert "late_penalty_missing_cost_metadata" in penalized_by_name["Tactical Cue Reset"]["penalty_codes"]


def test_runtime_primer_only_cannot_satisfy_strength_maintenance():
    safety = is_late_fight_metadata_safe(
        _safe_strength(tags=["strength", "neural_primer", "maximal_strength_maintenance"], primer_only=True),
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
