"""
Tests that surface/skin injuries (cut, abrasion, laceration, graze, blister)
are NOT prescribed musculoskeletal loading rehab.

Surface injuries are integumentary, not structural/soft-tissue. The rehab bank
has no surface-type entries, so before this guard these injuries fell through to
the location's "unspecified" loading drills (isometrics, eccentrics, balance
work) — clinically wrong for a skin wound and potentially harmful (friction /
reopening / infection). The correct prescription is wound care only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_registry import SURFACE_TISSUE_TYPES
from fightcamp.rehab_protocols import (
    SURFACE_WOUND_CARE_NOTE,
    _is_surface_type,
    _rehab_drills_for_phase,
    format_injury_guardrails,
    generate_rehab_protocols,
)


def _surface_entry(injury_type: str, location: str = "knee", severity: str = "mild") -> dict:
    return {
        "injury_type": injury_type,
        "rehab_type": injury_type,
        "canonical_location": location,
        "location": location,
        "severity": severity,
        "flags": [],
    }


def test_surface_types_classified():
    assert SURFACE_TISSUE_TYPES == {"abrasion", "cut", "graze", "blister", "laceration"}
    for injury_type in SURFACE_TISSUE_TYPES:
        assert _is_surface_type(injury_type)
    assert not _is_surface_type("sprain")
    assert not _is_surface_type("strain")


def test_surface_injury_gets_wound_care_not_loading_drills():
    for injury_type in SURFACE_TISSUE_TYPES:
        block, _ = generate_rehab_protocols(
            injury_string=f"{injury_type} on knee",
            exercise_data=[],
            current_phase="GPP",
            parsed_entries=[_surface_entry(injury_type)],
        )
        assert SURFACE_WOUND_CARE_NOTE in block, injury_type
        # No indented drill bullets (the loading-rehab format) should appear.
        assert "\n  •" not in block, injury_type
        lowered = block.lower()
        for loading_term in ("isometric", "eccentric", "spanish squat", "heel walk", "nordic"):
            assert loading_term not in lowered, (injury_type, loading_term)


def test_rehab_drills_for_phase_empty_for_surface_types():
    for injury_type in SURFACE_TISSUE_TYPES:
        assert _rehab_drills_for_phase(injury_type, "knee", "GPP", limit=6) == []
    # Non-surface types still resolve loading drills.
    assert _rehab_drills_for_phase("sprain", "knee", "GPP", limit=6)


def test_guardrails_surface_priority_shows_wound_care():
    block = format_injury_guardrails("GPP", "laceration on shin")
    assert "**Rehab Priority**" in block
    assert SURFACE_WOUND_CARE_NOTE in block
    assert "No rehab drills available" not in block


def test_mixed_location_keeps_loading_rehab_for_structural_injury():
    # A sprain at the same region must still receive normal loading rehab; the
    # surface guard only suppresses drills when the injury is purely surface.
    block, _ = generate_rehab_protocols(
        injury_string="knee sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_surface_entry("sprain", severity="moderate")],
    )
    assert "\n  •" in block
    assert SURFACE_WOUND_CARE_NOTE not in block
