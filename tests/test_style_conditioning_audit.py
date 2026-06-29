from __future__ import annotations

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
    assert "high_rpe" in row["quarantine_reason_codes"]
    assert row["recommended_action"] == "redose"


def test_high_or_max_intensity_style_entry_is_flagged():
    row = audit.style_conditioning_audit_row(_style_entry(intensity="max"))

    assert row["late_fight_risk_flag"] is True
    assert "high_intensity" in row["quarantine_reason_codes"]


def test_aggressive_movie_style_notes_are_flagged():
    row = audit.style_conditioning_audit_row(
        _style_entry(notes="Make this feel like a movie scene: no mercy, destroy the round.")
    )

    assert row["aggressive_notes_flag"] is True
    assert "aggressive_notes" in row["quarantine_reason_codes"]
    assert row["recommended_action"] == "manual_review"


def test_missing_late_windows_is_flagged():
    entry = _style_entry()
    entry.pop("late_windows")

    row = audit.style_conditioning_audit_row(entry)

    assert row["late_fight_risk_flag"] is True
    assert "missing_late_windows" in row["quarantine_reason_codes"]


def test_report_includes_recommended_action():
    rows = audit.audit_style_conditioning_entries([_style_entry(rpe=9)])
    report = audit.render_markdown_report(rows)

    assert "recommended_action" in report
    assert "redose" in report


def test_quarantined_style_entry_cannot_pass_late_fight_eligibility():
    safety = is_late_fight_metadata_safe(
        _style_entry(rpe=9),
        "style_conditioning_bank.json",
        D21_TO_D14,
    )

    assert safety["severity"] == "blocked"
    assert "late_block_style_conditioning_quarantine" in safety["block_codes"]
    assert "late_block_style_conditioning_high_rpe" in safety["block_codes"]
