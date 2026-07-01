"""
Tests that surface/skin injuries (cut, abrasion, laceration, graze, blister)
get dedicated wound-care protocols — and never musculoskeletal loading rehab.

Surface injuries are integumentary, not structural/soft-tissue. They now have
their own wound-care entries in the rehab bank (keyed by surface type x body
location, covering all camp phases). Before this, they had no entries and fell
through to the location's "unspecified" loading drills (isometrics, eccentrics,
balance work) — clinically wrong for a skin wound and potentially harmful.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_registry import SURFACE_TISSUE_TYPES
from fightcamp.rehab_protocols import (
    SURFACE_MINOR_TRAIN_THROUGH_NOTE,
    SURFACE_WOUND_CARE_NOTE,
    _collect_surface_drills,
    _is_surface_type,
    _rehab_drills_for_phase,
    build_coach_review_entries,
    format_injury_guardrails,
    generate_rehab_protocols,
    get_rehab_bank,
    normalize_rehab_location,
)
from fightcamp.coach_review import build_coach_review_notes

# Structural region-guardrail phrasing that must never attach to a surface
# injury. These are the spine/pelvis Do/Avoid strings that were leaking onto a
# lower-back graze and driving trunk/anti-rotation "rehab" every session.
STRUCTURAL_GUARDRAIL_TERMS = (
    "trunk endurance",
    "hinge/squat",
    "loaded flexion",
    "graded exposure",
    "hip capacity",
)

PHASES = ("GPP", "SPP", "TAPER")
LOADING_TERMS = ("isometric", "eccentric", "spanish squat", "heel walk", "nordic", "pogo", "plyo")


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


def test_bank_has_surface_coverage_across_phases():
    bank = get_rehab_bank()
    surface_entries = [e for e in bank if str(e.get("type") or "").lower() in SURFACE_TISSUE_TYPES]
    assert len(surface_entries) >= 50, len(surface_entries)
    # Every surface type resolves wound-care drills in every phase (via the
    # unspecified-location fallback at minimum).
    for injury_type in SURFACE_TISSUE_TYPES:
        for phase in PHASES:
            drills = _collect_surface_drills(injury_type, normalize_rehab_location("shoulder"), phase)
            assert drills, (injury_type, phase)


def test_surface_injury_gets_wound_care_not_loading_drills():
    for injury_type in SURFACE_TISSUE_TYPES:
        for phase in PHASES:
            block, _ = generate_rehab_protocols(
                injury_string=f"{injury_type} on knee",
                exercise_data=[],
                current_phase=phase,
                parsed_entries=[_surface_entry(injury_type)],
            )
            # Surface injuries surface as a single note — the wound-care note
            # (cut/laceration or high severity) or the calm train-through note
            # (minor graze/abrasion/blister) — never musculoskeletal loading
            # drills and never a wound-care drill list.
            has_wound_guidance = (
                SURFACE_WOUND_CARE_NOTE in block or SURFACE_MINOR_TRAIN_THROUGH_NOTE in block
            )
            assert "[Wound care]" not in block, (injury_type, phase)
            assert has_wound_guidance, (injury_type, phase)
            lowered = block.lower()
            for loading_term in LOADING_TERMS:
                assert loading_term not in lowered, (injury_type, phase, loading_term)


def test_minor_surface_injury_collapses_to_single_calm_note():
    # A minor graze/abrasion/blister trains through: one calm coach-facing note,
    # no wound-care drill list, and no per-drill warning repeated every session.
    for injury_type in ("graze", "abrasion", "blister"):
        for phase in PHASES:
            block, _ = generate_rehab_protocols(
                injury_string=f"{injury_type} on lower back",
                exercise_data=[],
                current_phase=phase,
                parsed_entries=[_surface_entry(injury_type, location="lower back", severity="mild")],
            )
            assert SURFACE_MINOR_TRAIN_THROUGH_NOTE in block, (injury_type, phase)
            assert "[Wound care]" not in block, (injury_type, phase)
            # Coach language, not medical panic.
            assert "clinician" not in block.lower(), (injury_type, phase)


def test_non_minor_surface_collapses_to_single_wound_care_note():
    # A laceration is a surface/skin injury: it surfaces as the single wound-care
    # note only — no drill list and no "[Wound care]" drill caveat.
    block, _ = generate_rehab_protocols(
        injury_string="laceration on shin",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_surface_entry("laceration", location="shin", severity="moderate")],
    )
    assert block.count(SURFACE_WOUND_CARE_NOTE) == 1
    assert "[Wound care]" not in block


def test_rehab_drills_for_phase_returns_surface_wound_care_only():
    for injury_type in SURFACE_TISSUE_TYPES:
        drills = _rehab_drills_for_phase(injury_type, "knee", "GPP", limit=6)
        assert drills, injury_type
        joined = " ".join(drills).lower()
        for loading_term in LOADING_TERMS:
            assert loading_term not in joined, (injury_type, loading_term)
    # Non-surface types still resolve loading drills.
    assert _rehab_drills_for_phase("sprain", "knee", "GPP", limit=6)


def test_guardrails_surface_priority_shows_wound_care():
    block = format_injury_guardrails("GPP", "laceration on shin")
    assert "**Rehab Priority**" in block
    assert "No rehab drills available" not in block
    # Surface injuries render as the wound-care note only — no structural
    # region Do/Avoid guidance and no loading drills.
    assert SURFACE_WOUND_CARE_NOTE in block
    lowered = block.lower()
    for loading_term in LOADING_TERMS:
        assert loading_term not in lowered, loading_term


def test_unknown_surface_location_falls_back_to_note():
    # A surface injury with no resolvable bank match still yields wound-care
    # guidance rather than silence or loading drills.
    block, _ = generate_rehab_protocols(
        injury_string="cut",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_surface_entry("cut", location="")],
    )
    assert SURFACE_WOUND_CARE_NOTE in block or "[Wound care]" in block


def test_surface_avoid_does_not_create_blocking_restriction():
    # A surface injury's "avoid" is wound-care guidance, not a training-load
    # restriction. Promoting it to a restriction lets the Stage-2 validator
    # flag the plan's own wound-care references and falsely hold the plan.
    from fightcamp.input_parsing import GuidedInjury, _parse_guided_injury

    guided = GuidedInjury(
        area="knee",
        injury_type="surface_injury",
        surface_type="laceration",
        avoid="friction on the wound",
    )
    _injuries, restrictions = _parse_guided_injury(guided)
    assert restrictions == []


def test_non_surface_avoid_still_creates_restriction():
    from fightcamp.input_parsing import GuidedInjury, _parse_guided_injury

    guided = GuidedInjury(area="knee", avoid="deep squats")
    _injuries, restrictions = _parse_guided_injury(guided)
    assert any(r.get("restriction") for r in restrictions)


def test_surface_rehab_is_not_promoted_to_stage2_slots():
    # Wound-care guidance must not become a prescriptive Stage-2 rehab slot
    # (which the finalizer would expand into plan content that collides with
    # friction/contact restrictions).
    from fightcamp.stage2_payload import _build_rehab_slots

    block, _ = generate_rehab_protocols(
        injury_string="knee laceration",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_surface_entry("laceration", severity="moderate")],
    )
    assert _build_rehab_slots(block, "GPP") == []
    # A real (non-surface) injury still produces rehab slots.
    sprain_block, _ = generate_rehab_protocols(
        injury_string="knee sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_surface_entry("sprain", severity="moderate")],
    )
    assert _build_rehab_slots(sprain_block, "GPP")


def test_mixed_location_keeps_loading_rehab_for_structural_injury():
    # A sprain at the same region must still receive normal loading rehab; the
    # surface path only applies when the injury is purely surface.
    block, _ = generate_rehab_protocols(
        injury_string="knee sprain",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[_surface_entry("sprain", severity="moderate")],
    )
    assert "[Function:" in block
    assert "[Wound care]" not in block


def _lower_back_graze_entry(severity: str = "moderate") -> dict:
    return {
        "injury_type": "graze",
        "rehab_type": "graze",
        "canonical_location": "lower_back",
        "location": "lower back",
        "display_location": "lower back",
        "severity": severity,
        "flags": [],
    }


def test_surface_injury_gets_no_structural_region_guardrail():
    # Regression: a moderate lower-back graze was pulling the spine/pelvis
    # REGION_GUARDRAILS Do/Avoid ruleset (trunk endurance, hinge/squat, loaded
    # flexion/rotation) and rendering it as structural "rehab focus". A surface
    # injury must surface only its wound-care/train-through note.
    for phase in PHASES:
        block = format_injury_guardrails(
            phase, "moderate lower-back graze", parsed_entries=[_lower_back_graze_entry()]
        )
        assert SURFACE_MINOR_TRAIN_THROUGH_NOTE in block, phase
        lowered = block.lower()
        for term in STRUCTURAL_GUARDRAIL_TERMS:
            assert term not in lowered, (phase, term)


def test_surface_injury_produces_no_coach_review_entry():
    # A surface injury must not generate a coach-review safety entry (region
    # Do/Avoid guidance, rehab-priority drills, or exercise substitutions).
    for severity in ("moderate", "severe"):
        entries = build_coach_review_entries(
            "lower-back graze", "GPP", parsed_entries=[_lower_back_graze_entry(severity)]
        )
        assert entries == [], severity
    notes = build_coach_review_notes(
        build_coach_review_entries(
            "lower-back graze", "GPP", parsed_entries=[_lower_back_graze_entry()]
        ),
        [],
    )
    assert notes == ""
    # A real structural injury still produces a coach-review entry.
    assert build_coach_review_entries(
        "moderate lower-back sprain",
        "GPP",
        parsed_entries=[
            {
                "injury_type": "sprain",
                "canonical_location": "lower_back",
                "location": "lower back",
                "severity": "moderate",
                "flags": [],
            }
        ],
    )
