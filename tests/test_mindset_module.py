import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.main import _filter_mindset_blocks
from fightcamp.mindset_module import classify_mental_block, get_mindset_by_phase


def test_kickboxing_mindset_excludes_grappling_cues():
    blocks = _filter_mindset_blocks(["fear of takedowns"], ["kickboxing"], [])
    mindset = get_mindset_by_phase("GPP", {"mental_block": blocks})
    lowered = mindset.lower()
    for banned in ["takedown", "sprawl", "wrestling", "grappling", "wall wrestling"]:
        assert banned not in lowered


def test_classify_rushing_behavior():
    """Test detection of rushing behavior patterns."""
    text = "after taking a clean shot, he rushes exchanges to 'get it back' instead of resetting"
    blocks = classify_mental_block(text)
    assert "rushing" in blocks


def test_classify_breath_control_issues():
    """Test detection of breath control problems."""
    text = "loses breath control during intense exchanges"
    blocks = classify_mental_block(text)
    assert "breath control" in blocks


def test_classify_composure_loss():
    """Test detection of composure issues."""
    text = "loses composure when pressured"
    blocks = classify_mental_block(text)
    assert "composure" in blocks


def test_classify_compound_behavioral_description():
    """Test classification of compound behavioral descriptions from problem statement."""
    text = "after taking a clean shot, he rushes exchanges to 'get it back' instead of resetting; loses breath control and composure"
    blocks = classify_mental_block(text)
    
    # Should detect multiple specific blocks
    assert len(blocks) >= 2
    assert "rushing" in blocks
    # Should detect either breath control or composure (or both)
    assert any(block in blocks for block in ["breath control", "composure"])


def test_rushing_advice_is_actionable():
    """Test that rushing block provides specific, actionable advice."""
    mindset = get_mindset_by_phase("SPP", {"mental_block": ["rushing"]})
    lowered = mindset.lower()
    
    # Should contain specific coaching interventions
    assert "reset" in lowered
    # Should not be generic
    assert "generic" not in mindset


def test_breath_control_advice_is_actionable():
    """Test that breath control block provides specific, actionable advice."""
    mindset = get_mindset_by_phase("GPP", {"mental_block": ["breath control"]})
    lowered = mindset.lower()
    
    # Should contain breathing-specific advice
    assert "breath" in lowered or "exhale" in lowered or "nasal" in lowered
    # Should not be generic
    assert "generic" not in mindset


def test_composure_advice_is_actionable():
    """Test that composure block provides specific, actionable advice."""
    mindset = get_mindset_by_phase("TAPER", {"mental_block": ["composure"]})
    lowered = mindset.lower()
    
    # Should contain composure-specific advice
    assert any(word in lowered for word in ["calm", "composure", "reset", "ritual"])
    # Should not be generic
    assert "generic" not in mindset


def test_multiple_specific_blocks_no_generic():
    """Test that specific blocks don't fall back to generic advice."""
    mindset = get_mindset_by_phase("SPP", {"mental_block": ["rushing", "breath control"]})
    
    # Should contain advice for both blocks
    assert "Rushing:" in mindset or "rushing" in mindset.lower()
    assert "Breath Control:" in mindset or "breath" in mindset.lower()
    # Should not contain generic advice when specific blocks are detected
    assert "Generic:" not in mindset


def test_get_it_back_pattern():
    """Test detection of 'get it back' mentality pattern."""
    text = "trying to get it back after losing the first round"
    blocks = classify_mental_block(text)
    assert "rushing" in blocks


def test_chasing_pattern():
    """Test detection of chasing behavior."""
    text = "chasing opponent instead of staying composed"
    blocks = classify_mental_block(text)
    # Should detect rushing (chasing behavior)
    assert "rushing" in blocks or "composure" in blocks


def test_shallow_breathing_pattern():
    """Test detection of breathing quality issues."""
    text = "shallow breathing under pressure"
    blocks = classify_mental_block(text)
    assert "breath control" in blocks


def test_loses_breath_pattern():
    """Test detection of 'loses breath' pattern."""
    text = "loses breath when the pace picks up"
    blocks = classify_mental_block(text)
    assert "breath control" in blocks


def test_rattled_composure_pattern():
    """Test detection of emotional control issues."""
    text = "gets rattled and flustered when opponent scores"
    blocks = classify_mental_block(text)
    assert "composure" in blocks


def test_overwhelmed_pattern():
    """Test detection of being overwhelmed."""
    text = "feels overwhelmed in high-pressure situations"
    blocks = classify_mental_block(text)
    # Should detect composure or pressure
    assert any(block in blocks for block in ["composure", "pressure"])
