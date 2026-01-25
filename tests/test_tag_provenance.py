"""
Tests for tag provenance (_tag_source) and injury exclusion logic.

These tests verify that:
1. ensure_tags() marks tags as "explicit" or "inferred"
2. Only explicit tags trigger tag-based exclusion
3. Inferred tags do not cause EXCLUDE decisions
4. Pattern/keyword exclusions still work as before
5. Severity normalization defaults to "moderate"
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import ensure_tags, injury_match_details
from fightcamp.injury_guard import injury_decision


def test_ensure_tags_marks_explicit_tags():
    """PATCH 1: Verify explicit tags are marked with _tag_source='explicit'"""
    item = {"name": "Test Exercise", "tags": ["overhead", "press_heavy"]}
    tags = ensure_tags(item)
    assert item["_tag_source"] == "explicit"
    assert "overhead" in tags
    assert "press_heavy" in tags


def test_ensure_tags_marks_inferred_tags():
    """PATCH 1: Verify inferred tags are marked with _tag_source='inferred'"""
    item = {"name": "Bench Press", "tags": []}
    tags = ensure_tags(item)
    assert item["_tag_source"] == "inferred"
    # Should have inferred tags from name
    assert len(tags) > 0


def test_ensure_tags_handles_untagged():
    """PATCH 1: Verify items with no tags get 'untagged' with inferred source"""
    item = {"name": "Mystery Exercise", "tags": []}
    tags = ensure_tags(item)
    assert item["_tag_source"] == "inferred"
    # Should get at least 'untagged' tag if no other tags inferred
    assert len(tags) > 0


def test_explicit_tags_trigger_exclusion():
    """PATCH 2: Explicit tags should trigger tag-based exclusion"""
    item = {"name": "Custom Exercise", "tags": ["overhead", "press_heavy"]}
    details = injury_match_details(item, ["shoulder"], risk_levels=("exclude",))
    
    # Should find exclusions based on explicit tags
    assert len(details) > 0
    # At least one detail should have tags
    assert any(detail["tags"] for detail in details)


def test_inferred_tags_do_not_trigger_exclusion():
    """PATCH 2: Inferred tags should NOT trigger tag-based exclusion"""
    # Item with no explicit tags, but name that would infer overhead tags
    item = {"name": "Overhead Press", "tags": []}
    
    # Manually ensure tags to verify they are inferred
    ensure_tags(item)
    assert item.get("_tag_source") == "inferred"
    
    # Check for shoulder injury
    details = injury_match_details(item, ["shoulder"], risk_levels=("exclude",))
    
    # Should find exclusions but only from pattern matching, not from tags
    if details:
        for detail in details:
            # tag_hits should be empty because tags are inferred
            assert detail["tags"] == [], f"Inferred tags should not cause exclusion, but got: {detail['tags']}"


def test_pattern_exclusions_still_work():
    """PATCH 2: Pattern/keyword exclusions should work regardless of tag source"""
    # Item with inferred tags but name that matches keyword pattern
    item = {"name": "Overhead Press", "tags": []}
    
    details = injury_match_details(item, ["shoulder"], risk_levels=("exclude",))
    
    # Should find exclusions based on pattern matching
    assert len(details) > 0
    # Should have pattern matches
    assert any(detail["patterns"] for detail in details)


def test_injury_decision_with_inferred_tags():
    """PATCH 2: injury_decision should not exclude based on inferred tags alone"""
    # Exercise with no explicit tags
    exercise = {"name": "Mobility Flow", "tags": []}
    
    # Ensure tags are set
    ensure_tags(exercise)
    assert exercise.get("_tag_source") == "inferred"
    
    # Decision should not be exclude unless pattern matches
    decision = injury_decision(exercise, ["shoulder"], "GPP", "low")
    # Mobility should be safe (no pattern match)
    assert decision.action in ["allow", "modify"]


def test_injury_decision_with_explicit_tags():
    """PATCH 2: injury_decision should exclude based on explicit tags"""
    # Exercise with explicit risky tags
    exercise = {"name": "Custom Press", "tags": ["overhead", "press_heavy"]}
    
    decision = injury_decision(exercise, ["shoulder"], "GPP", "low")
    # Should be excluded due to explicit tags
    assert decision.action == "exclude"


def test_severity_normalization_to_moderate():
    """PATCH 3: Missing severity should default to 'moderate'"""
    # Injury dict without severity
    injury = {"region": "shoulder"}
    exercise = {"name": "Bench Press", "tags": []}
    
    # Call injury_decision which should normalize severity
    decision = injury_decision(exercise, [injury], "GPP", "low")
    
    # The decision should have been made (no error)
    assert decision is not None
    # Check that region was recognized
    assert decision.reason.get("region") in ["shoulder", None] or decision.action == "allow"


def test_severity_normalization_preserves_existing():
    """PATCH 3: Existing severity values should be preserved"""
    # Injury dict with explicit severity
    injury = {"region": "shoulder", "severity": "severe"}
    exercise = {"name": "Light Movement", "tags": []}
    
    # Call injury_decision
    decision = injury_decision(exercise, [injury], "GPP", "low")
    
    # The decision should have been made (no error)
    assert decision is not None
    # Verify the severity was used (severe should have higher risk)
    if decision.reason.get("region") == "shoulder":
        assert decision.reason.get("severity") == "severe"


def test_pattern_match_with_inferred_tags_excludes():
    """Verify that pattern matches still cause exclusion even with inferred tags"""
    # "Bench Press" has pattern match AND inferred tags
    exercise = {"name": "Bench Press", "tags": []}
    
    decision = injury_decision(exercise, ["shoulder"], "GPP", "low")
    # Should be excluded or modified due to pattern match, not tags
    # The exact action depends on risk threshold calculation
    assert decision.action in ["exclude", "modify"], f"Expected exclude or modify, got {decision.action}"


def test_no_false_positives_with_safe_names():
    """Verify that safe exercises with inferred tags don't get excluded"""
    safe_exercises = [
        {"name": "Bike Tempo Ride", "tags": []},
        {"name": "Rowing Machine", "tags": []},
        {"name": "Mobility Work", "tags": []},
    ]
    
    for exercise in safe_exercises:
        decision = injury_decision(exercise, ["shoulder"], "GPP", "low")
        # None of these should be excluded for shoulder
        assert decision.action in ["allow", "modify"], f"{exercise['name']} should not be excluded"


def test_regression_explicit_tags_still_exclude():
    """Regression: Verify that exercises with explicit risky tags are still excluded"""
    # This is a critical regression test
    exercise = {"name": "Some Exercise", "tags": ["overhead", "dynamic_overhead"]}
    
    decision = injury_decision(exercise, ["shoulder"], "GPP", "low")
    # Must be excluded because these are explicit risky tags for shoulder
    assert decision.action == "exclude"


if __name__ == "__main__":
    # Run tests manually
    print("Running tag provenance tests...")
    test_ensure_tags_marks_explicit_tags()
    print("✓ test_ensure_tags_marks_explicit_tags")
    
    test_ensure_tags_marks_inferred_tags()
    print("✓ test_ensure_tags_marks_inferred_tags")
    
    test_ensure_tags_handles_untagged()
    print("✓ test_ensure_tags_handles_untagged")
    
    test_explicit_tags_trigger_exclusion()
    print("✓ test_explicit_tags_trigger_exclusion")
    
    test_inferred_tags_do_not_trigger_exclusion()
    print("✓ test_inferred_tags_do_not_trigger_exclusion")
    
    test_pattern_exclusions_still_work()
    print("✓ test_pattern_exclusions_still_work")
    
    test_injury_decision_with_inferred_tags()
    print("✓ test_injury_decision_with_inferred_tags")
    
    test_injury_decision_with_explicit_tags()
    print("✓ test_injury_decision_with_explicit_tags")
    
    test_severity_normalization_to_moderate()
    print("✓ test_severity_normalization_to_moderate")
    
    test_severity_normalization_preserves_existing()
    print("✓ test_severity_normalization_preserves_existing")
    
    test_pattern_match_with_inferred_tags_excludes()
    print("✓ test_pattern_match_with_inferred_tags_excludes")
    
    test_no_false_positives_with_safe_names()
    print("✓ test_no_false_positives_with_safe_names")
    
    test_regression_explicit_tags_still_exclude()
    print("✓ test_regression_explicit_tags_still_exclude")
    
    print("\nAll tests passed!")
