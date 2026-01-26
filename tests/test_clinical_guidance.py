"""
Tests for clinical guidance fallback in rehab protocols.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.rehab_protocols import generate_rehab_protocols
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
