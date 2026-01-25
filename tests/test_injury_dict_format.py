"""
Tests for injury_decision function with dictionary format injuries.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_guard import injury_decision


def test_injury_decision_with_dict_format():
    """Test that injury_decision works with dictionary format injuries."""
    # Test with low severity
    injury_dict = {"region": "shoulder", "severity": "low"}
    decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        [injury_dict], 
        "GPP", 
        "low"
    )
    assert decision.action in {"exclude", "modify", "allow"}
    assert decision.reason["region"] == "shoulder"
    assert decision.reason["severity"] == "low"


def test_injury_decision_with_dict_format_high():
    """Test that injury_decision correctly handles high injuries."""
    injury_dict = {"region": "shoulder", "severity": "high"}
    decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        [injury_dict], 
        "GPP", 
        "low"
    )
    # Should be excluded due to high shoulder injury
    assert decision.action == "exclude"
    assert decision.reason["region"] == "shoulder"
    assert decision.reason["severity"] == "high"


def test_injury_decision_with_dict_format_moderate():
    """Test that injury_decision correctly handles moderate injuries."""
    injury_dict = {"region": "knee", "severity": "moderate"}
    decision = injury_decision(
        {"name": "Box Jump", "tags": []}, 
        [injury_dict], 
        "GPP", 
        "low"
    )
    # Should be restricted due to knee injury
    assert decision.action in {"exclude", "modify"}
    assert decision.reason["region"] == "knee"
    assert decision.reason["severity"] == "moderate"


def test_injury_decision_with_multiple_dict_injuries():
    """Test that injury_decision works with multiple dictionary injuries."""
    injuries = [
        {"region": "shoulder", "severity": "moderate"},
        {"region": "knee", "severity": "moderate"}
    ]
    
    # Test shoulder exercise
    shoulder_decision = injury_decision(
        {"name": "Overhead Press", "tags": []}, 
        injuries, 
        "GPP", 
        "low"
    )
    assert shoulder_decision.action in {"exclude", "modify"}
    
    # Test knee exercise
    knee_decision = injury_decision(
        {"name": "Box Jump", "tags": []}, 
        injuries, 
        "GPP", 
        "low"
    )
    assert knee_decision.action in {"exclude", "modify"}


def test_injury_decision_with_mixed_format():
    """Test that injury_decision works with mixed string and dict format."""
    injuries = [
        {"region": "shoulder", "severity": "moderate"},
        "knee pain"
    ]
    
    # Test shoulder exercise
    decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        injuries, 
        "GPP", 
        "low"
    )
    assert decision.action in {"exclude", "modify"}
    assert decision.reason["region"] == "shoulder"


def test_injury_decision_dict_vs_string_consistency():
    """Test that dict and string formats produce similar results."""
    # Dictionary format
    dict_injury = [{"region": "shoulder", "severity": "moderate"}]
    dict_decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        dict_injury, 
        "GPP", 
        "low"
    )
    
    # String format
    string_injury = ["shoulder"]
    string_decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        string_injury, 
        "GPP", 
        "low"
    )
    
    # Both should be restricted
    assert dict_decision.action in {"exclude", "modify"}
    assert string_decision.action in {"exclude", "modify"}


def test_injury_decision_with_single_dict():
    """Test that injury_decision works with a single dictionary (not in a list)."""
    injury_dict = {"region": "shoulder", "severity": "moderate"}
    decision = injury_decision(
        {"name": "Overhead Carry", "tags": []}, 
        injury_dict, 
        "GPP", 
        "low"
    )
    assert decision.action in {"exclude", "modify"}
    assert decision.reason["region"] == "shoulder"


def test_injury_decision_backward_compatibility():
    """Test that string format still works (backward compatibility)."""
    # Original string format should still work
    decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        ["shoulder injury"], 
        "GPP", 
        "low"
    )
    assert decision.action in {"exclude", "modify"}
    
    # Multiple string injuries
    decision2 = injury_decision(
        {"name": "Box Jump", "tags": []}, 
        ["knee pain", "ankle soreness"], 
        "GPP", 
        "low"
    )
    assert decision2.action in {"exclude", "modify"}


def test_injury_decision_no_match_with_dict():
    """Test that exercises not affected by injury are allowed."""
    injury_dict = {"region": "shoulder", "severity": "high"}
    decision = injury_decision(
        {"name": "Bike Tempo Ride", "tags": []}, 
        [injury_dict], 
        "GPP", 
        "low"
    )
    # Cycling shouldn't be affected by shoulder injury
    assert decision.action == "allow"


def test_injury_decision_severity_levels():
    """Test that different severity levels produce different risk scores."""
    exercise = {"name": "Overhead Press", "tags": []}
    
    low_decision = injury_decision(
        exercise, 
        [{"region": "shoulder", "severity": "low"}], 
        "GPP", 
        "low"
    )
    
    moderate_decision = injury_decision(
        exercise, 
        [{"region": "shoulder", "severity": "moderate"}], 
        "GPP", 
        "low"
    )
    
    high_decision = injury_decision(
        exercise, 
        [{"region": "shoulder", "severity": "high"}], 
        "GPP", 
        "low"
    )
    
    # Risk scores should increase with severity
    assert low_decision.risk_score <= moderate_decision.risk_score
    assert moderate_decision.risk_score <= high_decision.risk_score


def test_injury_decision_invalid_severity_defaults_to_moderate():
    """Test that invalid severity values default to moderate."""
    injury_dict = {"region": "shoulder", "severity": "unknown"}
    decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        [injury_dict], 
        "GPP", 
        "low"
    )
    # Should still work, defaulting to moderate
    assert decision.action in {"exclude", "modify"}
    assert decision.reason["severity"] == "moderate"


def test_injury_decision_missing_severity_defaults_to_moderate():
    """Test that missing severity defaults to moderate."""
    injury_dict = {"region": "shoulder"}
    decision = injury_decision(
        {"name": "Bench Press", "tags": []}, 
        [injury_dict], 
        "GPP", 
        "low"
    )
    # Should still work, defaulting to moderate
    assert decision.action in {"exclude", "modify"}
    assert decision.reason["severity"] == "moderate"
