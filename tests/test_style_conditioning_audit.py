from __future__ import annotations

import json

import pytest

from fightcamp.bank_schema import D21_TO_D14, is_late_fight_metadata_safe
from tools import audit_style_conditioning_bank as audit


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


def test_high_or_max_intensity_style_entry_is_flagged():
    row = audit.style_conditioning_audit_row(_style_entry(intensity="max"))

    assert row["late_fight_risk_flag"] is True
    assert "high_intensity" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "redose"


def test_very_high_intensity_normalizes_spaces_and_hyphens():
    spaced = audit.style_conditioning_audit_row(_style_entry(intensity="very high"))
    hyphenated = audit.style_conditioning_audit_row(_style_entry(intensity="very-high"))

    assert "high_intensity" in spaced["quarantine_reason_codes"]
    assert "high_intensity" in hyphenated["quarantine_reason_codes"]


def test_aggressive_movie_style_notes_are_flagged():
    row = audit.style_conditioning_audit_row(
        _style_entry(notes="Make this feel like a movie scene: no mercy, destroy the round.")
    )

    assert row["aggressive_notes_flag"] is True
    assert "aggressive_notes" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "delete_or_rebuild"
    assert row["late_fight_action"] == "late_blocked"


def test_missing_late_windows_is_flagged():
    entry = _style_entry()
    entry.pop("late_windows")

    row = audit.style_conditioning_audit_row(entry)

def test_report_includes_action_summaries():
    rows = audit.audit_style_conditioning_entries([_style_entry(rpe=9)])

    markdown_report = audit.render_markdown_report(rows)
    assert "camp_action" in markdown_report
    assert "late_fight_action" in markdown_report
    assert "### Camp Actions" in markdown_report
    assert "### Late-Fight Actions" in markdown_report
    assert "### Grouped Review Queues" in markdown_report or "## Grouped Review Queues" in markdown_report
    assert "redose" in markdown_report
    assert "late_blocked" in markdown_report

    payload = json.loads(audit.render_json_report(rows))
    assert payload["summary"]["entries_audited"] == 1
    assert payload["summary"]["camp_action_counts"]["redose"] == 1
    assert payload["summary"]["late_fight_action_counts"]["late_blocked"] == 1
    assert payload["rows"][0]["camp_action"] == "redose"
    assert payload["rows"][0]["late_fight_action"] == "late_blocked"
    assert "missing_late_windows" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "keep"
    assert row["late_fight_action"] == "not_late_eligible"


def test_report_includes_action_summaries():
    rows = audit.audit_style_conditioning_entries([_style_entry(rpe=9)])
    report = audit.render_markdown_report(rows)

    assert "camp_action" in report
    assert "late_fight_action" in report
    assert "### Camp Actions" in report
    assert "### Late-Fight Actions" in report
    assert "redose" in report
    assert "late_blocked" in report


def test_overstyled_name_only_recommends_rename():
    row = audit.style_conditioning_audit_row(_style_entry(name="Warrior Reset"))

    assert row["camp_action"] == "rename"
    assert row["late_fight_action"] == "late_blocked"


def test_overstyled_name_with_dose_risk_recommends_rename_and_redose():
    row = audit.style_conditioning_audit_row(_style_entry(name="Warrior Reset", rpe=9))

    assert row["camp_action"] == "rename_and_redose"
    assert row["late_fight_action"] == "late_blocked"


def test_missing_late_windows_alone_does_not_force_camp_cleanup():
    entry = _style_entry(phases=["GPP", "SPP"], rpe=5, intensity="moderate")
    entry.pop("late_windows")

    row = audit.style_conditioning_audit_row(entry)

    assert row["camp_action"] == "keep"
    assert row["late_fight_action"] == "not_late_eligible"


def test_low_rpe_cognitive_drill_without_late_windows_remains_camp_keep():
    entry = _style_entry(
        name="Tactical Cue Reset",
        system="cognitive",
        tags=["conditioning", "tactical", "cue"],
        rpe=3,
        notes="Low arousal tactical breathing cue reset.",
    )
    entry.pop("late_windows")

    row = audit.style_conditioning_audit_row(entry)

    assert row["camp_action"] == "keep"
    assert row["late_fight_action"] in {"not_late_eligible", "late_support_candidate"}


def test_low_rpe_cognitive_drill_with_late_windows_is_support_candidate():
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


def test_aggressive_wording_plus_high_dose_recommends_delete_or_rebuild():
    row = audit.style_conditioning_audit_row(_style_entry(name="Kill Mode Circuit", rpe=9))

    assert "violent_wording" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "delete_or_rebuild"


def test_empty_tuple_dose_metadata_is_missing():
    row = audit.style_conditioning_audit_row(_style_entry(duration=()))

    assert "missing_dose_metadata" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "manual_review"


def test_json_report_output_is_valid(tmp_path):
    rows = audit.audit_style_conditioning_entries([_style_entry(rpe=9)])
    path = tmp_path / "style_conditioning_audit.json"

    audit.write_report(rows, path, output_format="json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["entries_audited"] == 1
    assert payload["rows"][0]["camp_action"] == "redose"
    assert payload["rows"][0]["late_fight_action"] == "late_blocked"


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
