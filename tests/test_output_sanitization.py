"""
Tests for output sanitization functions (_normalize_time_labels, _sanitize_stage_output).
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.main import _normalize_time_labels, _sanitize_stage_output


def test_normalize_time_labels_basic():
    """Test basic time label normalization."""
    text = "Week 1: Base Building\nDay 3: Heavy session"
    result = _normalize_time_labels(text)
    assert "**Week 1**" in result
    assert "**Day 3**" in result


def test_normalize_time_labels_already_bold():
    """Test that already bold time labels are not double-bolded."""
    text = "**Week 1**: Base Building\n**Day 3**: Heavy session"
    result = _normalize_time_labels(text)
    # Should not become ****Week 1****
    assert result.count("**Week 1**") == 1
    assert result.count("**Day 3**") == 1


def test_normalize_time_labels_empty():
    """Test that empty text is handled gracefully."""
    assert _normalize_time_labels("") == ""
    assert _normalize_time_labels(None) == None


def test_sanitize_stage_output_removes_excess_newlines():
    """Test that excessive blank lines are reduced."""
    text = "Section 1\n\n\n\nSection 2"
    result = _sanitize_stage_output(text)
    # Should have max 2 consecutive newlines
    assert "\n\n\n" not in result
    assert "Section 1\n\nSection 2" in result


def test_sanitize_stage_output_strips_trailing_whitespace():
    """Test that trailing whitespace on lines is removed."""
    text = "Line 1   \nLine 2  \n  Line 3   "
    result = _sanitize_stage_output(text)
    lines = result.split('\n')
    for line in lines:
        assert line == line.rstrip()


def test_sanitize_stage_output_normalizes_time_labels():
    """Test that sanitize_stage_output applies time label normalization."""
    text = "Week 1: Introduction\n\n\nDay 5: Recovery"
    result = _sanitize_stage_output(text)
    assert "**Week 1**" in result
    assert "**Day 5**" in result
    # Should also reduce excessive newlines
    assert "\n\n\n" not in result


def test_sanitize_stage_output_empty():
    """Test that empty text is handled gracefully."""
    assert _sanitize_stage_output("") == ""
    assert _sanitize_stage_output(None) == None


def test_sanitize_stage_output_full_integration():
    """Test a realistic block of phase output."""
    text = """
Week 1: Foundation Phase   

This is the introduction.   


Week 2: Building Phase

Day 1: Strength Training   
Day 2: Conditioning   


    """
    result = _sanitize_stage_output(text)
    # Check time labels are bold
    assert "**Week 1**" in result
    assert "**Week 2**" in result
    assert "**Day 1**" in result
    assert "**Day 2**" in result
    # Check excessive newlines are removed
    assert "\n\n\n" not in result
    # Check trailing spaces are removed
    for line in result.split('\n'):
        assert line == line.rstrip()
    # Check overall string is stripped
    assert result == result.strip()
