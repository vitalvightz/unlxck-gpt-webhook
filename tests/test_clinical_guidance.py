"""
Tests for clinical guidance fallback in rehab protocols.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.rehab_protocols import (
    classify_drill_function,
    generate_rehab_protocols,
    REHAB_FUNCTION_BUCKETS,
)
from fightcamp.stage2_payload import _build_rehab_slots, STAGE2_FINALIZER_PROMPT
from fightcamp.main import exercise_bank


def test_clinical_guidance_fallback_when_no_drills():
    """Test that clinical guidance message is shown when no rehab drills are available."""
    # Use an obscure injury that likely won't match any drills in the current phase
    injury_string = "nonexistent body part injury"
    current_phase = "TAPER"  # TAPER phase has fewer drills
    
    result, _ = generate_rehab_protocols(
        injury_string=injury_string,
        exercise_data=exercise_bank,
        current_phase=current_phase,
        seen_drills=set()
    )
    
    # Should contain clinical guidance when no drills are available
    # (Red flag detection would produce a different message)
    if "Red Flag" not in result:
        assert "Consult with a healthcare professional" in result, \
            f"Expected clinical guidance message, got: {result}"
    # Should NOT contain the old literal error
    assert "No rehab options for this phase" not in result


def test_no_injuries_shows_no_rehab_needed():
    """Test that no injuries shows appropriate message."""
    injury_string = ""
    current_phase = "GPP"
    
    result, _ = generate_rehab_protocols(
        injury_string=injury_string,
        exercise_data=exercise_bank,
        current_phase=current_phase,
        seen_drills=set()
    )
    
    # Empty injury should show "No rehab work required"
    assert "✅ No rehab work required" in result


def test_valid_injury_shows_drills():
    """Test that valid injuries show actual rehab drills, not fallback."""
    injury_string = "shoulder strain"
    current_phase = "GPP"
    
    result, seen = generate_rehab_protocols(
        injury_string=injury_string,
        exercise_data=exercise_bank,
        current_phase=current_phase,
        seen_drills=set()
    )
    
    # Should not be a fallback message
    assert "No rehab work required" not in result
    # Should contain actual drill information
    assert "Shoulder" in result or "shoulder" in result.lower()


# ---------------------------------------------------------------------------
# Additional tests for combined surgical rehab patch
# ---------------------------------------------------------------------------


def test_valid_injury_drills_include_function_tags():
    """Drills returned for a real injury should include [Function: ...] tags."""
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
        seen_drills=set()
    )
    if "Consult with a healthcare professional" not in result and "Red Flag" not in result:
        assert "[Function:" in result, (
            f"Expected function tags in drill output, got:\n{result}"
        )


def test_valid_injury_drills_include_why_today():
    """Drills returned for a real injury should include 'Why today:' annotation."""
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
        seen_drills=set()
    )
    if "Consult with a healthcare professional" not in result and "Red Flag" not in result:
        assert "Why today:" in result, (
            f"Expected 'Why today:' annotation in output, got:\n{result}"
        )


def test_classify_drill_function_activation():
    assert classify_drill_function("Banded Monster Walk", "") == "activation"
    assert classify_drill_function("Glute Bridge Activation", "") == "activation"


def test_classify_drill_function_control():
    assert classify_drill_function("Single-Leg Balance", "") == "control"
    assert classify_drill_function("Pallof Press", "") == "control"


def test_classify_drill_function_isometric():
    assert classify_drill_function("Isometric Hip Bridge Hold", "") == "isometric_analgesia"
    assert classify_drill_function("Spanish Squat", "") == "isometric_analgesia"


def test_classify_drill_function_mobility():
    assert classify_drill_function("Ankle Circle", "") == "mobility"
    assert classify_drill_function("Thoracic Rotation Stretch", "") == "mobility"


def test_classify_drill_function_recovery():
    assert classify_drill_function("Foam Roll Quads", "") == "recovery_downregulation"
    assert classify_drill_function("Soft Tissue Reset", "") == "recovery_downregulation"


def test_classify_drill_function_unknown_defaults_to_control():
    assert classify_drill_function("XYZ Unknown Drill", "") == "control"


def test_rehab_function_buckets_have_expected_keys():
    expected = {
        "activation",
        "control",
        "isometric_analgesia",
        "mobility",
        "tendon_loading",
        "recovery_downregulation",
    }
    assert expected == set(REHAB_FUNCTION_BUCKETS.keys())


def test_stage2_prompt_contains_rehab_rule():
    assert "SURGICAL REHAB" in STAGE2_FINALIZER_PROMPT, (
        "Expected RULE 12 - SURGICAL REHAB INTEGRATION in the finalizer prompt"
    )


def test_stage2_prompt_requires_why_today_format():
    assert "Why today" in STAGE2_FINALIZER_PROMPT, (
        "Expected 'Why today' format requirement in the finalizer prompt"
    )
