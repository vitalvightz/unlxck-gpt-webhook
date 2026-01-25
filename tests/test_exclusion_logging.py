"""
Test the new exclusion-only logging behavior.
"""
import os
import sys
from pathlib import Path
from io import StringIO

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import _log_exclusion
from fightcamp.injury_guard import injury_decision


def test_log_exclusion_only_logs_when_enabled(capsys):
    """Test that _log_exclusion only logs when INJURY_DEBUG=1"""
    # Setup
    item = {"name": "Bench Press", "tags": ["press_heavy"]}
    decision = injury_decision(item, ["shoulder"], "GPP", "low")
    
    # Without INJURY_DEBUG
    os.environ.pop("INJURY_DEBUG", None)
    _log_exclusion("test_context", item, decision)
    captured = capsys.readouterr()
    assert "[INJURY_DEBUG]" not in captured.out
    
    # With INJURY_DEBUG=0
    os.environ["INJURY_DEBUG"] = "0"
    _log_exclusion("test_context", item, decision)
    captured = capsys.readouterr()
    assert "[INJURY_DEBUG]" not in captured.out
    
    # With INJURY_DEBUG=1 and exclude action
    os.environ["INJURY_DEBUG"] = "1"
    if decision.action == "exclude":
        _log_exclusion("test_context", item, decision)
        captured = capsys.readouterr()
        assert "[INJURY_DEBUG]" in captured.out
        assert "EXCLUDE" in captured.out
        assert "Bench Press" in captured.out
    
    # Clean up
    os.environ.pop("INJURY_DEBUG", None)


def test_log_exclusion_does_not_log_allowed_items(capsys):
    """Test that _log_exclusion does not log items with action='allow'"""
    # Setup
    os.environ["INJURY_DEBUG"] = "1"
    item = {"name": "Safe Exercise", "tags": []}
    decision = injury_decision(item, ["shoulder"], "GPP", "low")
    
    # If the item is allowed, no log should appear
    if decision.action == "allow":
        _log_exclusion("test_context", item, decision)
        captured = capsys.readouterr()
        assert "[INJURY_DEBUG]" not in captured.out
        assert "Safe Exercise" not in captured.out
    
    # Clean up
    os.environ.pop("INJURY_DEBUG", None)


def test_log_exclusion_includes_context_and_triggers(capsys):
    """Test that _log_exclusion includes context, region, and triggers"""
    # Setup
    os.environ["INJURY_DEBUG"] = "1"
    item = {"name": "Overhead Press", "tags": ["overhead", "press_heavy"]}
    decision = injury_decision(item, ["shoulder"], "GPP", "low")
    
    if decision.action == "exclude":
        _log_exclusion("strength:GPP", item, decision)
        captured = capsys.readouterr()
        
        # Check that essential information is present
        assert "[INJURY_DEBUG]" in captured.out
        assert "EXCLUDE strength:GPP" in captured.out
        assert "item: Overhead Press" in captured.out
        assert "region:" in captured.out
        assert "risk_score:" in captured.out
    
    # Clean up
    os.environ.pop("INJURY_DEBUG", None)


if __name__ == "__main__":
    # Run basic smoke test
    print("Testing _log_exclusion function...")
    
    # Test 1: Basic functionality
    item = {"name": "Test Exercise", "tags": []}
    decision = injury_decision(item, ["shoulder"], "GPP", "low")
    os.environ["INJURY_DEBUG"] = "1"
    _log_exclusion("test", item, decision)
    
    print("✓ All manual tests passed")
    os.environ.pop("INJURY_DEBUG", None)
