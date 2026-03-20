"""
Tests for the Surgical Rehab Integration Patch.

These regression tests verify that:
- Rehab drills are classified by function bucket.
- Drills serving the same function are deduplicated within a single call.
- Each drill output includes Purpose and Why-this-phase explanation text.
- Volume limits are respected (sparring day capped at 1 drill; others at 2).
- Phase context produces different rationale text across GPP / SPP / TAPER.
- Stage 2 rehab slots include rehab_function and rehab_function_label metadata.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.rehab_protocols import (
    REHAB_FUNCTION_BUCKETS,
    REHAB_QUALITY_CHECKS,
    classify_drill_function,
    generate_rehab_protocols,
    _format_rehab_drill,
    _PHASE_REHAB_WHY,
)
from fightcamp.stage2_payload import _serialize_rehab_option, _build_rehab_slots
from fightcamp.main import exercise_bank


# ---------------------------------------------------------------------------
# classify_drill_function
# ---------------------------------------------------------------------------


def test_classify_drill_function_returns_activation_for_banded():
    fn = classify_drill_function("Banded Clamshell", "Activate hip abductors")
    assert fn == "activation"


def test_classify_drill_function_returns_isometric_for_hold():
    fn = classify_drill_function("Isometric Split Squat Hold", "Static contraction")
    assert fn == "isometric_analgesia"


def test_classify_drill_function_returns_control_for_balance():
    fn = classify_drill_function("Single-Leg Balance", "proprioception on foam pad")
    assert fn == "control"


def test_classify_drill_function_returns_tendon_loading_for_eccentric():
    fn = classify_drill_function("Eccentric Calf Raise", "tendon loading protocol")
    assert fn == "tendon_loading"


def test_classify_drill_function_returns_mobility_for_stretch():
    fn = classify_drill_function("Hip Flexor Stretch", "improve range of motion")
    assert fn == "mobility"


def test_classify_drill_function_returns_recovery_for_foam_roll():
    fn = classify_drill_function("Foam Roll Quads", "post-session recovery")
    assert fn == "recovery_downregulation"


def test_classify_drill_function_fallback_is_control():
    fn = classify_drill_function("Unknown Drill", "")
    assert fn == "control"


# ---------------------------------------------------------------------------
# _format_rehab_drill
# ---------------------------------------------------------------------------


def test_format_rehab_drill_includes_function_label():
    headline, annotations = _format_rehab_drill("Banded External Rotation", "3×15", "SPP", "activation")
    assert "[Function: Activation]" in annotations[0]


def test_format_rehab_drill_includes_purpose():
    headline, annotations = _format_rehab_drill("Banded External Rotation", "3×15", "GPP", "activation")
    assert "Purpose:" in annotations[0]
    assert "underactive tissue" in annotations[0]


def test_format_rehab_drill_includes_why_this_phase():
    headline, annotations = _format_rehab_drill("Banded External Rotation", "3×15", "SPP", "activation")
    assert "Why this phase:" in annotations[1]
    assert _PHASE_REHAB_WHY["SPP"] in annotations[1]


def test_format_rehab_drill_phase_why_differs_across_phases():
    _, gpp_ann = _format_rehab_drill("Drill", "notes", "GPP", "control")
    _, spp_ann = _format_rehab_drill("Drill", "notes", "SPP", "control")
    _, taper_ann = _format_rehab_drill("Drill", "notes", "TAPER", "control")
    # All three should have distinct why-this-phase rationale
    assert gpp_ann[1] != spp_ann[1]
    assert spp_ann[1] != taper_ann[1]


# ---------------------------------------------------------------------------
# generate_rehab_protocols – output formatting
# ---------------------------------------------------------------------------


def test_generate_rehab_protocols_includes_function_label_in_output():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    # Should contain a [Function: ...] tag for at least one drill
    if "No rehab work required" not in result and "Consult with" not in result:
        assert "[Function:" in result, f"Expected function label in output, got:\n{result}"


def test_generate_rehab_protocols_includes_purpose_text():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="SPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        assert "Purpose:" in result, f"Expected Purpose in output, got:\n{result}"


def test_generate_rehab_protocols_includes_why_this_phase():
    result, _ = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        assert "Why this phase:" in result, f"Expected why-this-phase in output, got:\n{result}"


# ---------------------------------------------------------------------------
# generate_rehab_protocols – volume limits
# ---------------------------------------------------------------------------


def _count_drill_items(text: str) -> int:
    """Count drill bullet items in rehab output.

    Only lines that start with '  •' (two spaces then bullet) and are NOT
    4-space-indented annotation lines are counted as actual drill entries.
    """
    count = 0
    for line in text.splitlines():
        # Annotation lines are indented with 4 spaces; drill bullets use 2 spaces + '•'
        if line.startswith("  •") and not line.startswith("    "):
            count += 1
    return count


def test_sparring_day_limits_to_one_drill():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="SPP",
        day_type="sparring",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        count = _count_drill_items(result)
        assert count <= 1, f"Sparring day should produce at most 1 drill, got {count}:\n{result}"


def test_strength_day_limits_to_two_drills():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
        day_type="strength",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        count = _count_drill_items(result)
        assert count <= 2, f"Strength day should produce at most 2 drills, got {count}:\n{result}"


def test_default_day_type_limits_to_two_drills():
    result, _ = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        count = _count_drill_items(result)
        assert count <= 2, f"Default should produce at most 2 drills, got {count}:\n{result}"


# ---------------------------------------------------------------------------
# generate_rehab_protocols – function deduplication
# ---------------------------------------------------------------------------


def test_same_function_not_stacked_in_one_call():
    """Two drills from the same injury should not both have the same function bucket."""
    result, _ = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    if "No rehab work required" in result or "Consult with" in result:
        return  # nothing to check

    # Extract function labels from output
    function_labels = [
        line.split("[Function:")[1].split("]")[0].strip()
        for line in result.splitlines()
        if "[Function:" in line
    ]
    # Duplicates indicate same-function stacking
    assert len(function_labels) == len(set(function_labels)), (
        f"Duplicate function buckets found in single-injury output: {function_labels}\n{result}"
    )


# ---------------------------------------------------------------------------
# generate_rehab_protocols – cross-phase deduplication via seen_drills
# ---------------------------------------------------------------------------


def test_seen_drills_prevents_cross_phase_repetition():
    """The same drill key (name + phase-specific notes) should not appear in both GPP and SPP."""
    result_gpp, seen = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
        seen_drills=set(),
    )
    result_spp, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="SPP",
        seen_drills=seen,
    )

    # Extract full drill entries from bullet lines (skip annotation lines indented with 4 spaces)
    def _extract_drill_entries(text: str) -> set[str]:
        entries: set[str] = set()
        for line in text.splitlines():
            if line.startswith("  •") and not line.startswith("    "):
                entries.add(line.strip("  •").strip())
        return entries

    gpp_entries = _extract_drill_entries(result_gpp)
    spp_entries = _extract_drill_entries(result_spp)

    overlap = gpp_entries & spp_entries
    assert not overlap, (
        f"Same drill entries appeared in both GPP and SPP: {overlap}"
    )


# ---------------------------------------------------------------------------
# Stage 2 slot metadata
# ---------------------------------------------------------------------------


def test_serialize_rehab_option_includes_function_fields():
    slot = _serialize_rehab_option(
        "Banded Clamshell – Activate hip abductors",
        role="rehab_hip_strain",
        source="rehab_block",
        why="phase-specific rehab support",
    )
    assert "rehab_function" in slot
    assert "rehab_function_label" in slot
    assert slot["rehab_function"] in REHAB_FUNCTION_BUCKETS


def test_build_rehab_slots_includes_function_metadata():
    rehab_block = (
        "- Shoulder (Strain):\n"
        "  • Banded External Rotation – Restore rotator cuff control\n"
        "    [Function: Activation] Purpose: wake up underactive tissue.\n"
        "    Why this phase: establishes baseline control.\n"
    )
    slots = _build_rehab_slots(rehab_block, "GPP")
    assert slots, "Expected at least one slot from valid rehab block"
    slot = slots[0]
    assert "rehab_function" in slot, f"Missing rehab_function in slot: {slot}"
    assert "rehab_function_label" in slot, f"Missing rehab_function_label in slot: {slot}"
    assert slot["rehab_function"] in REHAB_FUNCTION_BUCKETS, (
        f"rehab_function {slot['rehab_function']!r} not in known buckets"
    )


def test_build_rehab_slots_alternates_prefer_different_functions():
    """Alternates should not all share the same function bucket as the selected drill."""
    rehab_block = (
        "- Ankle (Sprain):\n"
        "  • Single-Leg Balance on Foam Pad – Rebuild proprioception\n"
        "    [Function: Control] Purpose: improve joint position.\n"
        "    Why this phase: establishes baseline control.\n"
    )
    slots = _build_rehab_slots(rehab_block, "GPP")
    if not slots:
        return
    slot = slots[0]
    alternates = slot.get("alternates", [])
    if len(alternates) > 1:
        alt_functions = [a.get("rehab_function") for a in alternates]
        # Not all alternates should repeat the same function
        assert len(set(alt_functions)) > 1 or alt_functions[0] != slot.get("rehab_function"), (
            "All alternates share the selected slot's function bucket — diversity expected."
        )


# ---------------------------------------------------------------------------
# REHAB_QUALITY_CHECKS constant
# ---------------------------------------------------------------------------


def test_rehab_quality_checks_has_five_items():
    assert len(REHAB_QUALITY_CHECKS) == 5


def test_rehab_quality_checks_covers_key_questions():
    combined = " ".join(REHAB_QUALITY_CHECKS).lower()
    assert "exact issue" in combined
    assert "duplicate" in combined
    assert "lowest effective dose" in combined or "lowest" in combined
