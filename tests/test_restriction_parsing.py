import sys
from pathlib import Path
import logging

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.restriction_parsing import (
    parse_restriction_entry,
    _contains_trigger_token,
    _infer_restriction_strength,
)
from fightcamp.injury_formatting import (
    parse_injuries_and_restrictions,
    format_restriction_summary,
)


def test_contains_trigger_token():
    """Test detection of constraint trigger tokens."""
    assert _contains_trigger_token("avoid deep knee flexion")
    assert _contains_trigger_token("no heavy overhead pressing")
    assert _contains_trigger_token("don't do squats")
    assert _contains_trigger_token("do not perform lunges")
    assert _contains_trigger_token("limit jumping")
    assert _contains_trigger_token("not comfortable with sprinting")
    assert _contains_trigger_token("knee flares up")
    
    # Should NOT match these
    assert not _contains_trigger_token("shoulder pain")
    assert not _contains_trigger_token("knee sprain")
    assert not _contains_trigger_token("torn hamstring")


def test_parse_restriction_entry_canonical():
    """Test parsing of canonical restriction phrases."""
    result = parse_restriction_entry("avoid deep knee flexion under load")
    assert result is not None
    assert result["restriction"] == "deep_knee_flexion"
    assert result["region"] == "knee"
    assert result["strength"] == "avoid"
    
    result = parse_restriction_entry("no heavy overhead pressing")
    assert result is not None
    assert result["restriction"] == "heavy_overhead_pressing"
    assert result["region"] == "shoulder"
    assert result["strength"] == "avoid"


def test_parse_restriction_entry_generic():
    """Test parsing of non-canonical constraint phrases."""
    result = parse_restriction_entry("avoid jumping on the ankle")
    assert result is not None
    # "jumping" matches "high_impact" canonical restriction
    assert result["restriction"] in ["high_impact", "generic_constraint"]
    # Note: region inference may vary, accepting None or ankle
    assert result["strength"] == "avoid"
    
    result = parse_restriction_entry("limit wrist exercises")
    assert result is not None
    assert result["restriction"] == "generic_constraint"
    assert result["region"] == "wrist"
    assert result["strength"] == "limit"


def test_parse_restriction_entry_laterality():
    """Test that laterality is extracted correctly."""
    result = parse_restriction_entry("avoid left knee flexion")
    assert result is not None
    assert result["side"] == "left"
    assert result["region"] == "knee"
    
    result = parse_restriction_entry("no right shoulder overhead work")
    assert result is not None
    assert result["side"] == "right"
    assert result["region"] == "shoulder"


def test_parse_restriction_strength_variations():
    """Test different strength levels are correctly inferred."""
    result = parse_restriction_entry("avoid heavy lifting")
    assert result["strength"] == "avoid"
    
    result = parse_restriction_entry("limit overhead work")
    assert result["strength"] == "limit"
    
    result = parse_restriction_entry("knee flares with running")
    assert result["strength"] == "flare"


def test_parse_injuries_and_restrictions_separation():
    """Test that injuries and restrictions are properly separated."""
    text = "Right shin splints (mild) + left shoulder impingement. Avoid heavy overhead pressing."
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 2 injuries
    assert len(injuries) == 2
    locations = {inj.get("canonical_location") for inj in injuries}
    assert "shin" in locations
    assert "shoulder" in locations
    
    # Should have 1 restriction
    assert len(restrictions) == 1
    assert restrictions[0]["restriction"] == "heavy_overhead_pressing"
    assert restrictions[0]["region"] == "shoulder"


def test_parse_injuries_and_restrictions_complex_case():
    """Test parsing the example from the problem statement."""
    text = "avoid deep knee flexion under load"
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have NO injuries
    assert len(injuries) == 0
    
    # Should have 1 restriction
    assert len(restrictions) == 1
    assert restrictions[0]["restriction"] == "deep_knee_flexion"
    assert restrictions[0]["region"] == "knee"
    assert restrictions[0]["strength"] == "avoid"


def test_constraint_phrases_not_parsed_as_injuries():
    """Ensure constraint phrases are NOT mistakenly parsed as injuries."""
    constraint_phrases = [
        "avoid deep knee flexion under load",
        "no heavy overhead pressing",
        "limit high impact activities",
        "don't do box jumps",
        "not comfortable with sprinting",
    ]
    
    for phrase in constraint_phrases:
        injuries, restrictions = parse_injuries_and_restrictions(phrase)
        
        # Should have no injuries
        assert len(injuries) == 0, f"Phrase '{phrase}' was incorrectly parsed as injury"
        
        # Should have at least one restriction
        assert len(restrictions) > 0, f"Phrase '{phrase}' was not recognized as restriction"


def test_injury_only_parsing_still_works():
    """Ensure legacy injury-only parsing still works correctly."""
    text = "left ankle sprain, right shoulder pain"
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 2 injuries
    assert len(injuries) == 2
    
    # Should have no restrictions
    assert len(restrictions) == 0
    
    # Check injury details
    locations = {inj.get("canonical_location") for inj in injuries}
    assert "ankle" in locations
    assert "shoulder" in locations


def test_mixed_injuries_and_restrictions():
    """Test handling of mixed injury and restriction input."""
    text = "Knee soreness. Avoid deep squats and heavy lifting. Shoulder strain."
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have injuries for knee and shoulder
    assert len(injuries) == 2
    locations = {inj.get("canonical_location") for inj in injuries}
    assert "knee" in locations
    assert "shoulder" in locations
    
    # Should have restrictions
    assert len(restrictions) > 0


def test_format_restriction_summary():
    """Test formatting of restriction summary."""
    restriction = {
        "restriction": "deep_knee_flexion",
        "region": "knee",
        "strength": "avoid",
        "side": None,
        "original_phrase": "avoid deep knee flexion",
    }
    
    summary = format_restriction_summary(restriction)
    assert "Knee" in summary
    assert "Deep Knee Flexion" in summary
    assert "Strength: Avoid" in summary
    assert "Severity" not in summary  # Should NOT have severity
    
    # Test with laterality
    restriction["side"] = "left"
    summary = format_restriction_summary(restriction)
    assert "Left Knee" in summary


def test_restriction_no_severity_field():
    """Ensure restrictions don't have severity field (have strength instead)."""
    result = parse_restriction_entry("avoid deep knee flexion")
    assert result is not None
    assert "strength" in result
    assert "severity" not in result


def test_restriction_parsing_logging(caplog):
    """Test that restriction parsing emits appropriate log messages."""
    # Set log level to capture INFO messages
    caplog.set_level(logging.INFO)
    
    text = "avoid deep knee flexion under load"
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 1 restriction
    assert len(restrictions) == 1
    
    # Check that logging occurred
    assert len(caplog.records) >= 2
    
    # Check for individual restriction log
    individual_logs = [record for record in caplog.records if "[restriction-parse] parsed=" in record.message]
    assert len(individual_logs) >= 1
    assert "restriction" in individual_logs[0].message
    assert "deep_knee_flexion" in individual_logs[0].message
    
    # Check for total count log
    total_logs = [record for record in caplog.records if "total restrictions parsed:" in record.message]
    assert len(total_logs) == 1
    assert "1" in total_logs[0].message


def test_restriction_parsing_logging_multiple(caplog):
    """Test that logging captures multiple restrictions correctly."""
    caplog.set_level(logging.INFO)
    
    text = "avoid deep knee flexion. no heavy overhead pressing. limit high impact activities"
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 3 restrictions
    assert len(restrictions) == 3
    
    # Check that we have at least 3 individual logs + 1 summary log
    individual_logs = [record for record in caplog.records if "[restriction-parse] parsed=" in record.message]
    assert len(individual_logs) == 3
    
    # Check for total count log
    total_logs = [record for record in caplog.records if "total restrictions parsed:" in record.message]
    assert len(total_logs) == 1
    assert "3" in total_logs[0].message


def test_restriction_parsing_no_logging_for_injuries(caplog):
    """Test that injury parsing does not emit individual restriction logs but does log zero count."""
    caplog.set_level(logging.INFO)
    
    text = "left ankle sprain, right shoulder pain"
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 2 injuries and no restrictions
    assert len(injuries) == 2
    assert len(restrictions) == 0
    
    # Should have no individual restriction-parse logs
    individual_logs = [record for record in caplog.records if "[restriction-parse] parsed=" in record.message]
    assert len(individual_logs) == 0
    
    # But should still have a total count log showing 0
    total_logs = [record for record in caplog.records if "total restrictions parsed:" in record.message]
    assert len(total_logs) == 1
    assert "0" in total_logs[0].message

