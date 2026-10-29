"""Contracts for the read-only strength pool depth audit.

The cell counts are a snapshot of the bank, not a source of truth; these tests
pin that the audit uses the selector's own eligibility and never mutates the
cached bank it reads.
"""
from __future__ import annotations

import copy

from fightcamp import strength
from fightcamp.strength_session_quality import classify_strength_item
from tools import audit_strength_pool_depth as audit


def test_static_audit_never_mutates_the_cached_bank():
    before = copy.deepcopy(strength.get_exercise_bank())
    audit.static_audit()
    assert strength.get_exercise_bank() == before


def test_cells_cover_every_phase_and_equipment_tier():
    report = audit.static_audit()
    assert set(report["cells"]) == {
        f"{phase}/{tier}" for phase in audit.PHASES for tier in audit.EQUIPMENT_TIERS
    }
    for cell in report["cells"].values():
        assert cell["eligible_anchors"] <= cell["eligible"]
        assert set(cell["required_category_anchors"]) == set(audit.REQUIRED_CATEGORIES)


def test_review_candidates_only_lack_the_phase_tag():
    report = audit.static_audit()
    bank = {row["name"]: row for row in audit._steady_state_bank()}
    for key, entry in report["thin_required_category_review"].items():
        phase, tier, category = key.split("/")
        for candidate in entry["phase_tag_candidates"]:
            row = bank[candidate["name"]]
            profile = classify_strength_item(row)
            assert phase not in row["phases"]
            assert audit._equipment_ok(row, audit.EQUIPMENT_TIERS[tier])
            assert not strength._exercise_late_windows(row)
            assert not audit._banned(row)
            assert audit._phase_gate_ok(row, phase)
            assert profile["anchor_capable"]
            assert category in profile["base_categories"]


def test_movement_normalization_flips_are_reported():
    flips = {row["name"]: row for row in audit.static_audit()["movement_normalization_classification_flips"]}
    assert flips
    for name, row in flips.items():
        assert row["movement"][0] != row["movement"][1], name
        assert (
            row["quality_class"][0] != row["quality_class"][1]
            or row["categories_gained"]
            or row["categories_lost"]
        ), name


def test_isometric_gates_match_the_selector():
    bank = audit._steady_state_bank()
    for row in bank:
        if strength._is_supra_max_isometric(row):
            assert not audit._phase_gate_ok(row, "GPP")
        if strength._is_over_100_percent_isometric(row):
            assert not audit._phase_gate_ok(row, "SPP")
