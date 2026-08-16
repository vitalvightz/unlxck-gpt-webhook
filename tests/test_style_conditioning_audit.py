from __future__ import annotations

import json
from pathlib import Path

import pytest

from fightcamp.bank_schema import D21_TO_D14, is_late_fight_metadata_safe
from tools import audit_style_conditioning_bank as audit

REPO_ROOT = Path(__file__).resolve().parents[1]
STYLE_CONDITIONING_BANK_PATH = REPO_ROOT / "data" / "style_conditioning_bank.json"

# Batch 1 manual cleanup: names as they exist in the bank today, post-cleanup.
# Entries superseded by later style-bank rebuilds, or removed by the batch-3
# legacy purge (see BATCH_3_PURGED_NAMES), are intentionally absent from this
# regression list, which tracks batch-1 entries that remain active today.
BATCH_1_CLEANED_NAMES = [
    "Sprint, Sprawl & Knee Conditioning Complex",
    "Clinch Hold & Knee Complex",
    "Max Knee & Sprawl Complex",
    "Wall Pressure & Elbow Complex",
    "Clinch & Sprawl Reaction Complex",
    "Band-Resisted Whizzer & Sprawl Complex",
    "Intercept & Counter Mitts",
    "Frame & Counter Knee Complex",
    "Ezekiel Finishing Drill",
    "Ground-and-Pound Bursts",
    "Calf Slicer Pressure Drill",
]

STYLE_CONDITIONING_ARCHIVE_PATH = REPO_ROOT / "data" / "style_conditioning_bank_archive.json"

# Frozen snapshot of every entry name in the bank immediately BEFORE the batch-3
# legacy purge. Lets the deletion-only claim be verified against a real baseline
# instead of only against the purge list.
PREPURGE_BASELINE_PATH = REPO_ROOT / "tests" / "fixtures" / "style_conditioning_prepurge_names.json"

# Batch 2: archived (deleted from the active bank) as duplicates or
# fake-hard/cartoonish content surfaced once modality text was scanned.
BATCH_2_ARCHIVED_NAMES = [
    "Pavement Pounder",
    "Last Call Circuit",
    "Meat Locker",
    "Gutter Fight Finisher",
    "Backfist Brawler",
    "Last Man Standing",
    "Trench Warfare",
    "Pressure Cooker Deluxe",
    "Hammer & Tire Power Complex",
]

# Batch 2: renamed/rebuilt in place after modality scanning surfaced gimmick
# wording ("neck torture", "footwork torture", "annihilation") not caught by
# the original name-only/notes-only batch-1 pass.
#
# NOTE: both original batch-2 renamed entries ("Neck Bridge & Plate Rotation
# Complex" — barbell neck strength; "Backward Sled Drag & Slip Complex" — sled
# work) were subsequently removed outright by the batch-3 legacy purge because
# their primary identity is generic S&C rather than a style-specific behaviour.
# They now live in BATCH_3_PURGED_NAMES / the archive file, so this list is
# empty; it is retained as an anchor for the batch-2 regression tests below.
BATCH_2_RENAMED_NAMES: list[str] = []

# Batch 3 (legacy purge): removed outright from the active bank as clearly
# low-value legacy style-conditioning content. Grouped by deletion reason. This
# was a deletion-only cleanup pass ahead of a per-archetype re-audit -- no
# replacement drills were added. Every name here must be absent from the active
# bank and present in the archive file with an archived_reason and archived_date.
BATCH_3_PURGED_NAMES = [
    # generic_snc (33)
    "Alleyway Ambush",
    "Backward Lunge & Swing Complex",
    "Backward Sled Drag & Slip Complex",
    "Blackout Blitz",
    "Bouncer's Revenge",
    "Brick Fist Protocol",
    "Clinch Control 3.0",
    "Concrete Clinch",
    "Cross-Counter Plyo Pushups",
    "DB Uppercut & Med Ball Slam Complex",
    "Dirty Boxing Marathon",
    "Ditch Digger",
    "Dogfight Drill",
    "Hammer & Tire Jump Complex",
    "Hammer Strike & Sprawl Jump Complex",
    "Infighting Jump & Push-Up Complex",
    "Junkyard Judo",
    "Lateral Escape Plyo Pushoffs",
    "Liver Hunter",
    "Med Ball Slam & Wall Drive Complex",
    "Outdoor Tire Flip & Burpee Complex",
    "Piledriver Circuit",
    "Plumb Power Circuit",
    "Plumb Power Rotations",
    "Rooftop Rumble",
    "Sandbag Carry & Knee Complex",
    "Sandbag Carry & Sprawl Complex",
    "Sled Push & KB Swing Complex",
    "Sled Push & Knee Complex",
    "Sled Push & Punch Combo",
    "Smesh Prep Circuit",
    "Sprint, Burpee & Shadowbox Finisher",
    "Weighted Plank & Stand-Up Complex",
    # artificial_resistance (11)
    "Band-Resisted Knee Complex",
    "Band-Resisted Shoulder Roll & Counter Complex",
    "Banded Shadowboxing",
    "Barroom Brawl",
    "Check Hook Crucible",
    "Check Hook Matrix",
    "Ding-Dong Roundhouse",
    "Dive Bar Duelist",
    "Interception Drill",
    "Roll-Under Counter Complex",
    "Slipping Symphony",
    # reaction_gimmick (10)
    "Brawler's Puzzle Defense",
    "Clinch Auditory Triggers",
    "Hybrid's Stance-Switch Reaction",
    "Kick Pattern Recall",
    "Pressure Fighter's Shadowboxing Riddle",
    "Reaction Jab Matrix",
    "Reaction Overload",
    "Slip & Rip Protocol",
    "Takedown Dilemma",
    "Wrestling Chess",
    # arbitrary_volume (2)
    "Counter Uppercut Drill",
    "Pull-Back Sniper",
    # fatigue_before_skill (3)
    "Concrete Hands Circuit",
    "Counter Puncher's Gauntlet",
    "Ropes Pressure Hook & Uppercut Complex",
    # duplicate (4)
    "Lateral Plyo Pushoffs",
    "MMA Wall-Walk Conditioning",
    "Muay Thai Matrix",
    "Rolling Thunder",
    # wrong_bank (69)
    "Arch Walks (Barefoot Activation)",
    "Assisted Chinnups (Light Load)",
    "Assisted Dip Machine (Light Load)",
    "Assisted Pullup (Heavy Band)",
    "Assisted Squat (TRX)",
    "Banded Core Chop (Anti-Rotation)",
    "Banded External Rotation (Shoulder)",
    "Banded Face Pulls (Rear Delt)",
    "Banded Pull-Aparts (Light)",
    "Banded Sled Push (Light)",
    "Bike Sprints (Assault)",
    "Bike Sprints (Fixed Gear Recovery)",
    "Bike Steady-State (Easy Gear)",
    "Bird Dog Holds (Core Stability)",
    "Boxer's Clinch Control",
    "Cable Woodchops (Light Load)",
    "Chest-Supported Dumbbell Row",
    "Core Plank Progressions",
    "Dead Bug Progressions",
    "Dumbbell Bent-Row (Light Load)",
    "Dumbbell Turkish Get-Ups (Light)",
    "Elliptical Backward Movement",
    "Elliptical Machine Intervals",
    "Farmer Carry (Seated Starting Position)",
    "Foam Roll Hamstring (Seated)",
    "Glass Jaw Redemption",
    "Glute Bridge March (Isometric Base)",
    "Half-Kneeling Hip Flexor Stretch",
    "Half-Kneeling Landmine Press",
    "Hanging Leg Raise (Assisted)",
    "Headbutt Conditioning",
    "Incline Push-Up Progression",
    "Incline Treadmill Walk",
    "Junkyard Dog",
    "Kettle Bell Sumo Squat (Light Load)",
    "Knuckle Dragger",
    "Landmine Rotations (Light Load)",
    "Landmine Single-Arm Press (Light)",
    "Medicine Ball Chest Pass (Light Load)",
    "Medicine Ball Rotational Slam (Light)",
    "Neck Bridge & Plate Rotation Complex",
    "Neck Harness Isometric Complex",
    "Pallof Press (Anti-Rotation)",
    "Parallette Push-Ups (Low-Impact)",
    "Pillow Punch Combinations (Air Work)",
    "Pool Walking (Shallow End)",
    "Prone Superman Holds",
    "Push-Up Hold (Isometric Chest)",
    "Quad Foam Rolling (Active Recovery)",
    "Quadruped Shoulder Taps",
    "Resistance Band Chest Fly",
    "Reverse Sled Drag (Quad Emphasis)",
    "Rowing Machine Sprint Intervals",
    "Rowing Machine Steady State",
    "Side-Lying Leg Raise (Hip Stability)",
    "Side-Plank Hold (Core Lateral)",
    "Single-Leg Balance Series",
    "Sled Drag Low-Impact Intervals",
    "Sled Reverse Drag (Backward Walking)",
    "Stair Climbing (No Sprinting)",
    "Swimming Endurance Circuits",
    "Swimming Technique Drills",
    "Tall Kneeling Core Holds",
    "Tall-Kneeling Pallof Press",
    "Thai Skip Rope",
    "Upper Body Sled Push",
    "Wall Plank Hold",
    "Wall Sit Series (Isometric)",
    "Water Jogging (Deep End)",
]

# Protected rebuilt blocks: the Distance Striker (boxing / kickboxing-muay thai /
# MMA / cross-sport general), Kicker, and Pressure Fighter blocks were recently
# rebuilt from scratch. They are protected by default from cleanup passes and
# must remain present in the active bank. This list locks them against accidental
# deletion by future purges.
PROTECTED_REBUILT_NAMES = [
    "Anti-Fence Range Rounds",
    "Backstep Counter Reset",
    "Body-Head Pressure Intervals",
    "Body-Kick Repeatability",
    "Cage Cut & Re-Catch",
    "Cage Escape Intervals",
    "Cage-Aware Range Flow",
    "Check-Return Burst",
    "Check-Hook Pivot Burst",
    "Counter Quality Rounds",
    "Counter Shadow Flow",
    "Corner Trap Burst",
    "Cutoff-Reposition Intervals",
    "Dutch Target Call",
    "Defend-Counter-Exit Intervals",
    "Defensive Position Flow",
    "Entry-Exit Burst",
    "Entry-Score-Angle Burst",
    "Entry-Score-Exit Bursts",
    "Entry-and-Score Burst",
    "Escape-Recatch Burst",
    "Explosive Cutoff Burst",
    "Failed-Entry Reset Intervals",
    "Fence Escape Denial",
    "Fence-Escape Burst",
    "In-Out MMA Striking Rounds",
    "Intercept-Reposition Rounds",
    "Intercept-and-Exit Burst",
    "Intercepting Straight Burst",
    "Interception Kick Burst",
    "Jab Volume & Position",
    "Jab-Kick Entry Burst",
    "Jab-Teep Control Rounds",
    "Jab-to-Pressure Flow",
    "Kick & Exit Flow",
    "Kick Recoil Quality Rounds",
    "Kick-Exit Intervals",
    "Kick-Punch Reposition",
    "Kick-Reposition Rounds",
    "Kick-Step Pressure Rounds",
    "Kick-and-Exit Burst",
    "Kick-to-Pressure Flow",
    "Lateral Escape Burst",
    "Level-Change Respect Flow",
    "Level-Threat Pressure Reset",
    "Long Combination Rounds",
    "Long-Range Decision Rounds",
    "Long-Range MMA Decision Rounds",
    "Long-Range Movement Flow",
    "Long-Weapon Exit Flow",
    "Long-to-Clinch Transition",
    "Low-High Decision Rounds",
    "Low-Kick Exit Burst",
    "Low-Kick Re-Catch Intervals",
    "Max-Power Bag Burst",
    "Movement Economy Rounds",
    "Open-Space Movement Flow",
    "Pocket Repeatability Rounds",
    "Parry-Return Intervals",
    "Precision Under Pace",
    "Pull-Straight Burst",
    "Random Attack Counter Rounds",
    "Reactive Counter Choice",
    "Read & Counter Flow",
    "Pressure Combination Rounds",
    "Pressure Decision Rounds",
    "Pressure Escape and Reset",
    "Pressure Footwork Flow",
    "Pressure Reset Intervals",
    "Pressure-Escape Distance Rounds",
    "Pressure-Kicker Rounds",
    "Pressure-to-Clinch Transition",
    "Punch-Clinch Reentry",
    "Punch-Slide Repeatability",
    "Range Intercept Burst",
    "Range Movement Flow",
    "Range Recovery Intervals",
    "Range Recovery Under Pressure",
    "Range Reset Flow",
    "Range Reset Intervals",
    "Range-Recovery Intervals",
    "Reactive Body-Kick Burst",
    "Reactive Distance Rounds",
    "Reactive Long-Weapon Burst",
    "Reactive Range Decision Burst",
    "Rear-Kick Power Singles",
    "Rear-Kick Reposition Burst",
    "Ring Escape Flow",
    "Ring Generalship Rounds",
    "Ring Perimeter Flow",
    "Ring-Cut Flow",
    "Ring-Cutting Intervals",
    "Slip-Cross Burst",
    "Rope/Corner Pressure Rounds",
    "Score-Reposition Rounds",
    "Straight-Shot Re-Angle",
    "Strike-Level-Change Decision Rounds",
    "Strike-Sprawl-Reset Burst",
    "Strike-to-Fence Pressure",
    "Switch-Kick Repeatability",
    "Switch-Side Rhythm",
    "Teep Intercept Burst",
    "Teep Range Reset",
    "Teep Range-Control Flow",
    "Teep Volume & Position",
    "Teep Walk-Down Reset",
]

# Legacy entries deliberately superseded after the deletion-only purge by the
# focused Boxing Counter Striker rebuild. Shared Distance Striker, Kickboxing,
# and MMA entries remain active and are therefore not listed here.
POST_PURGE_REPLACED_NAMES = {
    "Pull Counter Matrix",
    "Sniper's Timing",
    "Counter Striker's Shell Defense Drill",
    "Pull-Counter Springs",
    "Counter Striker's Retreat Drill",
    "Counter Striker's Parry Drill",
    "Tempo Shadowboxing (Slow Reps)",
}


def _load_style_conditioning_bank() -> list[dict]:
    return json.loads(STYLE_CONDITIONING_BANK_PATH.read_text(encoding="utf-8"))


def _load_style_conditioning_archive() -> list[dict]:
    return json.loads(STYLE_CONDITIONING_ARCHIVE_PATH.read_text(encoding="utf-8"))


def _load_prepurge_baseline_payload() -> dict:
    return json.loads(PREPURGE_BASELINE_PATH.read_text(encoding="utf-8"))


def _load_prepurge_baseline_names() -> list[str]:
    return _load_prepurge_baseline_payload()["names"]


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

    assert "missing_late_windows" in row["quarantine_reason_codes"]
    assert row["camp_action"] == "keep"
    assert row["late_fight_action"] == "not_late_eligible"


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


def test_batch_1_cleaned_entries_are_no_longer_overstyled_or_aggressive():
    for entry in _batch_1_entries():
        row = audit.style_conditioning_audit_row(entry)
        assert row["overstyled_name_flag"] is False, entry["name"]
        assert row["aggressive_notes_flag"] is False, entry["name"]
        assert "violent_wording" not in row["quarantine_reason_codes"], entry["name"]


def test_batch_1_cleaned_entries_preserve_appropriate_camp_action():
    for entry in _batch_1_entries():
        row = audit.style_conditioning_audit_row(entry)
        # Wording is clean now, so these should no longer sit in the
        # delete_or_rebuild / rename / rename_and_redose cleanup queues.
        assert row["camp_action"] in {"keep", "redose"}, (entry["name"], row["camp_action"])


def test_batch_1_hard_camp_work_is_not_automatically_late_eligible():
    for entry in _batch_1_entries():
        row = audit.style_conditioning_audit_row(entry)
        assert row["late_fight_action"] in {"late_blocked", "not_late_eligible"}, (
            entry["name"],
            row["late_fight_action"],
        )


def test_batch_1_entries_approved_late_satisfy_low_risk_metadata():
    low_risk_actions = {"late_support_candidate", "late_technical_candidate", "late_conditioning_candidate"}
    for entry in _batch_1_entries():
        row = audit.style_conditioning_audit_row(entry)
        if row["late_fight_action"] not in low_risk_actions:
            continue
        max_rpe = 4 if row["late_fight_action"] == "late_support_candidate" else 6
        assert row["rpe"] <= max_rpe, entry["name"]
        assert row["lactate_load"] == "low", entry["name"]
        assert row["movement_cost"] == "low", entry["name"]
        assert row["impact_cost"] == "low", entry["name"]


def test_batch_1_entries_preserve_phases_and_system():
    """Cleanup should only touch wording/dose fields, not the underlying GPP/SPP intent."""
    bank = _load_style_conditioning_bank()
    by_name = {entry["name"]: entry for entry in bank}
    for name in BATCH_1_CLEANED_NAMES:
        entry = by_name[name]
        assert entry.get("phases"), name
        assert entry.get("system"), name


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

    assert expected_codes.issubset(set(row["quarantine_reason_codes"])), (modality, row["quarantine_reason_codes"])
    assert row["camp_action"] == "delete_or_rebuild", (modality, row["camp_action"])
    assert row["late_fight_action"] == "late_blocked", (modality, row["late_fight_action"])


def test_batch_2_archived_entries_are_removed_from_active_bank():
    bank = _load_style_conditioning_bank()
    active_names = {entry["name"] for entry in bank}
    still_active = active_names & set(BATCH_2_ARCHIVED_NAMES)
    assert not still_active, f"Archived entries still present in active bank: {sorted(still_active)}"


def test_batch_2_archived_entries_are_present_in_archive_file():
    archive = _load_style_conditioning_archive()
    archived_by_name = {entry["name"]: entry for entry in archive}
    missing = [name for name in BATCH_2_ARCHIVED_NAMES if name not in archived_by_name]
    assert not missing, f"Archived entries missing from archive file: {missing}"
    for name in BATCH_2_ARCHIVED_NAMES:
        entry = archived_by_name[name]
        assert entry.get("archived_reason"), name
        assert entry.get("archived_date"), name


def test_batch_2_renamed_entries_are_clean():
    bank = _load_style_conditioning_bank()
    by_name = {entry["name"]: entry for entry in bank}
    missing = [name for name in BATCH_2_RENAMED_NAMES if name not in by_name]
    assert not missing, f"Batch 2 renamed entries missing from bank: {missing}"
    for name in BATCH_2_RENAMED_NAMES:
        row = audit.style_conditioning_audit_row(by_name[name])
        assert row["overstyled_name_flag"] is False, name
        assert row["aggressive_notes_flag"] is False, name
        assert "violent_wording" not in row["quarantine_reason_codes"], name


def test_batch_2_renamed_entries_are_not_late_eligible():
    bank = _load_style_conditioning_bank()
    by_name = {entry["name"]: entry for entry in bank}
    for name in BATCH_2_RENAMED_NAMES:
        row = audit.style_conditioning_audit_row(by_name[name])
        assert row["late_fight_action"] in {"late_blocked", "not_late_eligible"}, (name, row["late_fight_action"])


def test_batch_2_system_fix_entry_was_purged_in_batch_3():
    """"Hammer Strike & Sprawl Jump Complex" was a batch-2 system fix, but the
    batch-3 legacy purge removed it outright as generic S&C (sledgehammer strikes
    + sprawl jumps). It must be gone from the active bank and archived with a
    reason rather than lingering as low-value style conditioning."""
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}
    assert "Hammer Strike & Sprawl Jump Complex" not in active_names
    archived_by_name = {entry["name"]: entry for entry in _load_style_conditioning_archive()}
    assert "Hammer Strike & Sprawl Jump Complex" in archived_by_name
    assert archived_by_name["Hammer Strike & Sprawl Jump Complex"].get("archived_reason")


def test_questionable_atp_pcr_classification_is_flagged_without_rest_proof():
    row = audit.style_conditioning_audit_row(
        _style_entry(
            system="ATP-PCr",
            duration="10 hammer strikes -> 5 tire jumps -> x5 rounds",
            rpe=9,
            intensity="max",
        )
    )

    assert "questionable_atp_pcr_classification" in row["quarantine_reason_codes"]


def test_questionable_atp_pcr_classification_is_not_flagged_with_explicit_rest():
    row = audit.style_conditioning_audit_row(
        _style_entry(
            system="ATP-PCr",
            duration="10 hammer strikes -> 5 tire jumps -> x5 rounds",
            rest_sec=90,
            rpe=9,
            intensity="max",
        )
    )

    assert "questionable_atp_pcr_classification" not in row["quarantine_reason_codes"]


def test_no_entries_were_newly_approved_for_late_fight_in_batch_2():
    bank = _load_style_conditioning_bank()
    # The batch-2-touched entries were all removed by the batch-3 legacy purge, so
    # only entries that are still active are checked here. None of the surviving
    # batch-2 renamed entries (currently none) may have become late-fight eligible.
    by_name = {entry["name"]: entry for entry in bank}
    newly_touched_names = {name for name in BATCH_2_RENAMED_NAMES if name in by_name}
    late_eligible_actions = {"late_support_candidate", "late_technical_candidate", "late_conditioning_candidate"}
    for name in newly_touched_names:
        row = audit.style_conditioning_audit_row(by_name[name])
        assert row["late_fight_action"] not in late_eligible_actions, (name, row["late_fight_action"])


def test_batch_3_purged_entries_removed_from_active_bank():
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}
    still_active = active_names & set(BATCH_3_PURGED_NAMES)
    assert not still_active, f"Purged entries still present in active bank: {sorted(still_active)}"


def test_batch_3_purged_entries_present_in_archive_file():
    archive = _load_style_conditioning_archive()
    archived_by_name = {entry["name"]: entry for entry in archive}
    missing = [name for name in BATCH_3_PURGED_NAMES if name not in archived_by_name]
    assert not missing, f"Purged entries missing from archive file: {missing}"
    for name in BATCH_3_PURGED_NAMES:
        entry = archived_by_name[name]
        assert entry.get("archived_reason"), name
        assert entry.get("archived_date"), name


def test_batch_3_purge_baseline_accounts_for_later_protected_rebuilds():
    """The legacy purge is deletion-only, checked against the frozen pre-purge
    baseline rather than against the purge list itself.

    Comparing the active bank only to BATCH_3_PURGED_NAMES would not prove
    anything about additions: a brand-new drill invented during the purge would
    trivially satisfy "does not collide with a purged name". The real invariant
    needs the pre-purge name set, so it is frozen in a fixture and asserted here:

      1. active names are a subset of the baseline  (nothing new was added)
      2. baseline - active == the purge list        (exactly the intended removals)
    """
    baseline_names = set(_load_prepurge_baseline_names())
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}

    # Later approved style rebuilds may add protected drills. Anything else is
    # still an unexpected addition against the frozen purge baseline.
    added = sorted((active_names - baseline_names) - set(PROTECTED_REBUILT_NAMES))
    assert not added, f"Purge must not add drills, but these are new since the baseline: {added}"

    removed = baseline_names - active_names
    expected_removed = set(BATCH_3_PURGED_NAMES) | POST_PURGE_REPLACED_NAMES
    assert removed == expected_removed, {
        "removed_but_not_listed": sorted(removed - expected_removed),
        "listed_but_not_removed": sorted(expected_removed - removed),
    }

    # The purge removals are archived. Later purpose-built replacements are
    # tracked above rather than being misrepresented as part of that purge.
    archived_names = {entry["name"] for entry in _load_style_conditioning_archive()}
    assert set(BATCH_3_PURGED_NAMES) <= archived_names


def test_prepurge_baseline_fixture_matches_recorded_count():
    """Guard the baseline itself: if someone edits the fixture, the count must move
    with it, so a silent append cannot weaken the no-new-drills check above."""
    payload = _load_prepurge_baseline_payload()
    names = payload["names"]
    assert len(names) == payload["count"]
    assert len(set(names)) == len(names), "baseline fixture contains duplicate names"


def test_protected_rebuilt_blocks_remain_present():
    """Regression lock: the recently rebuilt Distance Striker, Kicker, and Pressure
    Fighter blocks are protected from cleanup passes and must never be deleted by a
    purge. If a future edit removes one of these, this test fails loudly."""
    active_names = {entry["name"] for entry in _load_style_conditioning_bank()}
    missing = [name for name in PROTECTED_REBUILT_NAMES if name not in active_names]
    assert not missing, f"Protected rebuilt entries missing from active bank: {missing}"


def test_protected_rebuilt_blocks_were_not_purged():
    """The protected rebuilt blocks and the purge list must be disjoint."""
    overlap = set(PROTECTED_REBUILT_NAMES) & set(BATCH_3_PURGED_NAMES)
    assert not overlap, f"Protected entries wrongly listed for purge: {sorted(overlap)}"
