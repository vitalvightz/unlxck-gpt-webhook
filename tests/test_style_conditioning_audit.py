from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp.bank_schema import D21_TO_D14, is_late_fight_metadata_safe
from tools import audit_style_conditioning_bank as audit

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLE_CONDITIONING_BANK_PATH = REPO_ROOT / "data" / "style_conditioning_bank.json"
PREPURGE_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "style_conditioning_prepurge_names.json"
RETIREMENT_CONTRACT_PATH = REPO_ROOT / "tests" / "fixtures" / "style_conditioning_retirement_contract.json"

BATCH_1_CLEANED_NAMES = [
    "Clinch Hold & Knee Complex",
    "Max Knee & Sprawl Complex",
    "Band-Resisted Whizzer & Sprawl Complex",
    "Intercept & Counter Mitts",
    "Ezekiel Finishing Drill",
    "Calf Slicer Pressure Drill",
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_style_conditioning_bank() -> list[dict]:
    return _load_json(STYLE_CONDITIONING_BANK_PATH)


def _load_prepurge_baseline_payload() -> dict:
    return _load_json(PREPURGE_BASELINE_PATH)


def _load_retirement_contract() -> dict:
    return _load_json(RETIREMENT_CONTRACT_PATH)


def _batch_1_entries() -> list[dict]:
    bank = _load_style_conditioning_bank()
    by_name = {entry["name"]: entry for entry in bank}
    missing = [name for name in BATCH_1_CLEANED_NAMES if name not in by_name]
    assert not missing, f"Batch 1 cleaned entries missing from bank: {missing}"
    return [by_name[name] for name in BATCH_1_CLEANED_NAMES]


def _style_entry(**overrides):
    entry = {
        "name": "Clean Rhythm Reset",
        "system": "aerobic",
        "phases": ["TAPER"],
        "tags": ["conditioning", "style_specific"],
        "rpe": 5,
        "intensity": "low",
        "lactate_load": "low",
        "movement_cost": "low",
        "impact_cost": "low",
        "late_windows": ["d21_to_d14"],
        "duration": "6 min",
        "notes": "Controlled technical rhythm.",
    }
    entry.update(overrides)
    return entry


def test_rpe_9_style_entry_is_flagged():
    row = audit.style_conditioning_audit_row(_style_entry(rpe=9))
    assert row["late_fight_risk_flag"] is True
    assert row["dose_risk_flag"] is True
    assert "high_rpe" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "redose"
    assert row["late_fight_action"] == "late_blocked"


@pytest.mark.parametrize("intensity", ["high", "max", "very high", "very-high"])
def test_high_intensity_variants_are_flagged(intensity):
    row = audit.style_conditioning_audit_row(_style_entry(intensity=intensity))
    assert row["late_fight_risk_flag"] is True
    assert "high_intensity" in row["quarantine_reason_codes"]


def test_aggressive_movie_style_notes_are_flagged():
    row = audit.style_conditioning_audit_row(
        _style_entry(notes="Make this feel like a movie scene: no mercy, destroy the round.")
    )
    assert row["aggressive_notes_flag"] is True
    assert "aggressive_notes" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "delete_or_rebuild"
    assert row["late_fight_action"] == "late_blocked"


def test_missing_late_windows_is_flagged_without_forcing_camp_cleanup():
    entry = _style_entry(phases=["GPP", "SPP"], rpe=5, intensity="moderate")
    entry.pop("late_windows")
    row = audit.style_conditioning_audit_row(entry)
    assert "missing_late_windows" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "keep"
    assert row["late_fight_action"] == "not_late_eligible"


def test_report_outputs_include_action_summaries(tmp_path):
    rows = audit.audit_style_conditioning_entries([_style_entry(rpe=9)])
    markdown_report = audit.render_markdown_report(rows)
    assert "camp_action" in markdown_report
    assert "late_fight_action" in markdown_report
    assert "### Camp Actions" in markdown_report
    assert "### Late-Fight Actions" in markdown_report

    payload = json.loads(audit.render_json_report(rows))
    assert payload["summary"]["entries_audited"] == 1
    assert payload["summary"]["camp_action_counts"]["redose"] == 1
    assert payload["summary"]["late_fight_action_counts"]["late_blocked"] == 1

    path = tmp_path / "style_conditioning_audit.json"
    audit.write_report(rows, path, output_format="json")
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["rows"][0]["camp_action"] == "redose"


@pytest.mark.parametrize(
    ("name", "rpe", "expected_action"),
    [
        ("Warrior Reset", 5, "rename"),
        ("Warrior Reset", 9, "rename_and_redose"),
        ("Kill Mode Circuit", 9, "delete_or_rebuild"),
    ],
)
def test_overstyled_names_route_to_expected_cleanup(name, rpe, expected_action):
    row = audit.style_conditioning_audit_row(_style_entry(name=name, rpe=rpe))
    assert row["camp_action"] == expected_action


def test_low_rpe_cognitive_drill_can_be_late_support_candidate():
    row = audit.style_conditioning_audit_row(
        _style_entry(
            name="Tactical Cue Reset",
            system="cognitive",
            tags=["conditioning", "tactical", "cue"],
            rpe=3,
            notes="Low arousal tactical breathing cue reset.",
        )
    )
    assert row["camp_action"] == "keep"
    assert row["late_fight_action"] == "late_support_candidate"


def test_empty_tuple_dose_metadata_is_missing():
    row = audit.style_conditioning_audit_row(_style_entry(duration=()))
    assert "missing_dose_metadata" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "manual_review"


def test_load_entries_rejects_malformed_entries(tmp_path):
    path = tmp_path / "style_conditioning_bank.json"
    path.write_text(json.dumps([_style_entry(), "not an object"]), encoding="utf-8")
    with pytest.raises(ValueError, match="malformed indexes: 1"):
        audit._load_entries(path)


def test_quarantined_style_entry_cannot_pass_late_fight_eligibility():
    safety = is_late_fight_metadata_safe(
        _style_entry(rpe=9),
        "style_conditioning_bank.json",
        D21_TO_D14,
    )
    assert safety["severity"] == "blocked"
    assert "late_block_style_conditioning_quarantine" in safety["block_codes"]
    assert "late_block_style_conditioning_high_rpe" in safety["block_codes"]


def test_batch_1_cleaned_entries_stay_clean_and_keep_original_intent():
    for entry in _batch_1_entries():
        row = audit.style_conditioning_audit_row(entry)
        assert row["overstyled_name_flag"] is False, entry["name"]
        assert row["aggressive_notes_flag"] is False, entry["name"]
        assert "violent_wording" not in row["quarantine_reason_codes"], entry["name"]
        assert row["camp_action"] in {"keep", "redose"}, entry["name"]
        assert row["late_fight_action"] in {"late_blocked", "not_late_eligible"}, entry["name"]
        assert entry.get("phases"), entry["name"]
        assert entry.get("system"), entry["name"]


@pytest.mark.parametrize(
    ("modality", "expected_codes"),
    [
        ("prison rules", {"overstyled_name", "aggressive_notes", "violent_wording"}),
        ("neck torture", {"overstyled_name", "aggressive_notes", "violent_wording"}),
        ("clinch hell", {"overstyled_name", "aggressive_notes", "violent_wording"}),
        ("rotational annihilation", {"aggressive_notes", "violent_wording"}),
    ],
)
def test_modality_scanning_flags_gimmick_terms(modality, expected_codes):
    row = audit.style_conditioning_audit_row(_style_entry(modality=modality))
    assert expected_codes.issubset(set(row["quarantine_reason_codes"]))
    assert row["camp_action"] == "delete_or_rebuild"
    assert row["late_fight_action"] == "late_blocked"


@pytest.mark.parametrize("rest_sec, should_flag", [(None, True), (90, False)])
def test_atp_pcr_classification_requires_rest_proof(rest_sec, should_flag):
    kwargs = {
        "system": "ATP-PCr",
        "duration": "10 hammer strikes -> 5 tire jumps -> x5 rounds",
        "rpe": 9,
        "intensity": "max",
    }
    if rest_sec is not None:
        kwargs["rest_sec"] = rest_sec
    row = audit.style_conditioning_audit_row(_style_entry(**kwargs))
    flagged = "questionable_atp_pcr_classification" in row["quarantine_reason_codes"]
    assert flagged is should_flag


def test_retired_style_entries_cannot_reappear_in_active_bank():
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}
    contract = _load_retirement_contract()
    retired = set(contract["batch2_archived"]) | set(contract["batch3_purged"])
    overlap = active_names & retired
    assert not overlap, f"Retired style-conditioning entries reappeared: {sorted(overlap)}"


def test_hammer_strike_sprawl_jump_complex_remains_retired():
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}
    assert "Hammer Strike & Sprawl Jump Complex" not in active_names


def test_prepurge_baseline_matches_recorded_retirement_contract():
    baseline = _load_prepurge_baseline_payload()
    baseline_names = set(baseline["names"])
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}
    contract = _load_retirement_contract()

    removed = baseline_names - active_names
    expected_removed = set(contract["batch3_purged"]) | set(contract["post_purge_replaced"])
    assert removed == expected_removed, {
        "removed_but_not_listed": sorted(removed - expected_removed),
        "listed_but_not_removed": sorted(expected_removed - removed),
    }


def test_retirement_contract_and_baseline_fixtures_are_well_formed():
    baseline = _load_prepurge_baseline_payload()
    assert len(baseline["names"]) == baseline["count"]
    assert len(set(baseline["names"])) == len(baseline["names"])

    contract = _load_retirement_contract()
    assert len(contract["batch2_archived"]) == 9
    assert len(contract["batch3_purged"]) == 132
    assert len(contract["post_purge_replaced"]) == 53
    for key, names in contract.items():
        assert len(names) == len(set(names)), f"{key} contains duplicate names"
