"""
Test suite for Romanian Deadlift (RDL) injury exclusion logic.

This module tests that all variations of 'Romanian Deadlift' are properly excluded
for hamstring injuries, addressing the issue where insufficient normalization and
substring matching could allow RDL variations to appear in plans for users with
hamstring injuries.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import (
    match_forbidden,
    injury_violation_reasons,
    normalize_for_substring_match,
    _normalize_text,
)
from fightcamp.injury_exclusion_rules import INJURY_RULES


def test_normalization_function():
    """Test that the normalization functions work correctly."""
    # Test _normalize_text (for word-boundary matching)
    assert _normalize_text("Romanian Deadlift") == "romanian deadlift"
    assert _normalize_text("Romanian Deadlift (RDL)") == "romanian deadlift rdl"
    assert _normalize_text("RomanianDeadlift") == "romaniandeadlift"
    assert _normalize_text("DB-RDL") == "db rdl"
    
    # Test normalize_for_substring_match (removes all non-alphanumeric)
    assert normalize_for_substring_match("Romanian Deadlift") == "romaniandeadlift"
    assert normalize_for_substring_match("Romanian Deadlift (RDL)") == "romaniandeadliftrdl"
    assert normalize_for_substring_match("RomanianDeadlift") == "romaniandeadlift"
    assert normalize_for_substring_match("DB-RDL") == "dbrdl"
    
    print("✓ test_normalization_function PASSED")


def test_rdl_keyword_matching():
    """Test that RDL keywords match all variations."""
    hamstring_keywords = INJURY_RULES["hamstring"]["ban_keywords"]
    
    # Verify the ban_keywords include the required patterns
    assert "romanian deadlift" in hamstring_keywords
    assert "rdl" in hamstring_keywords
    
    # Test all RDL variations with match_forbidden
    test_cases = [
        ("Romanian Deadlift", True, "Standard capitalization with space"),
        ("Romanian Deadlift (RDL)", True, "With acronym in parentheses"),
        ("RomanianDeadlift", True, "Compound word without space"),
        ("RDL", True, "Acronym alone"),
        ("Single-Leg RDL", True, "With prefix"),
        ("DB-RDL", True, "With dumbbell prefix"),
        ("romanian deadlift", True, "Lowercase"),
        ("ROMANIAN DEADLIFT", True, "Uppercase"),
    ]
    
    for text, should_match, description in test_cases:
        matches = match_forbidden(text, hamstring_keywords)
        matched = bool(matches)
        assert matched == should_match, f"Failed: {description} - {text} -> {matches}"
        print(f"  ✓ {description}: '{text}' -> {matches}")
    
    print("✓ test_rdl_keyword_matching PASSED")


def test_rdl_end_to_end_exclusion():
    """Test end-to-end exclusion for hamstring injuries."""
    test_exercises = [
        {"name": "Romanian Deadlift", "tags": []},
        {"name": "Romanian Deadlift (RDL)", "tags": []},
        {"name": "RomanianDeadlift", "tags": []},
        {"name": "RDL", "tags": []},
        {"name": "Single-Leg RDL", "tags": []},
        {"name": "DB-RDL Tempo", "tags": []},
    ]
    
    for exercise in test_exercises:
        reasons = injury_violation_reasons(exercise, ["hamstring"])
        assert reasons, f"Exercise '{exercise['name']}' should be excluded for hamstring injury but was not"
        print(f"  ✓ '{exercise['name']}' excluded: {reasons[:2]}")
    
    print("✓ test_rdl_end_to_end_exclusion PASSED")


def test_false_positives_not_excluded():
    """Test that similar-looking exercises are NOT incorrectly excluded."""
    # These should NOT match RDL patterns
    test_cases = [
        "Dead Hang",  # Contains "dead" but not "deadlift"
        "Treadmill Sprint",  # Contains "dl" but not "rdl"
        "World Record Lift",  # Contains "rdl" letters separately but not as keyword
    ]
    
    hamstring_keywords = INJURY_RULES["hamstring"]["ban_keywords"]
    rdl_keywords = ["romanian deadlift", "rdl"]  # Just test these two
    
    for text in test_cases:
        matches = match_forbidden(text, rdl_keywords)
        assert not matches, f"False positive: '{text}' should not match RDL but got {matches}"
        print(f"  ✓ '{text}' correctly NOT matched")
    
    print("✓ test_false_positives_not_excluded PASSED")


def test_substring_matching_for_compound_words():
    """Test that substring matching works for compound words but not false positives."""
    # These should match via substring (compound words)
    compound_cases = [
        ("RomanianDeadlift", ["romanian deadlift"], True),
        ("Good Morning Drill", ["good morning"], True),
    ]
    
    for text, patterns, should_match in compound_cases:
        matches = match_forbidden(text, patterns)
        matched = bool(matches)
        assert matched == should_match, f"Compound word test failed: {text} with {patterns}"
        print(f"  ✓ Compound word: '{text}' -> {matches}")
    
    # These should NOT match (false positives)
    false_positive_cases = [
        ("skipping rope", ["kipping"], False),
        ("membership plan", ["hip"], False),
    ]
    
    for text, patterns, should_match in false_positive_cases:
        matches = match_forbidden(text, patterns)
        matched = bool(matches)
        assert matched == should_match, f"False positive test failed: {text} with {patterns}"
        print(f"  ✓ False positive check: '{text}' with {patterns} -> {matches}")
    
    print("✓ test_substring_matching_for_compound_words PASSED")


if __name__ == "__main__":
    print("Running Romanian Deadlift (RDL) exclusion tests...\n")
    
    test_normalization_function()
    test_rdl_keyword_matching()
    test_rdl_end_to_end_exclusion()
    test_false_positives_not_excluded()
    test_substring_matching_for_compound_words()
    
    print("\n" + "="*60)
    print("All RDL exclusion tests PASSED! ✓")
    print("="*60)
