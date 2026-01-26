"""End-to-end test for the problem statement examples."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_formatting import parse_injuries_and_restrictions
from fightcamp.injury_guard import _injury_context
from fightcamp.rehab_protocols import _normalize_injury_entries


def test_problem_statement_case_1():
    """
    Test case 1 from problem statement:
    Input: "mild right shoulder impingement; avoid deep knee flexion under load; heavy overhead pressing"
    Expected:
      - Injuries: [{severity: "low", region: "shoulder", condition: "impingement"}]
      - Constraints: ["avoid deep knee flexion under load", "heavy overhead pressing"]
      - Ensure severity is only extracted from injuries, not constraints.
    """
    text = "mild right shoulder impingement; avoid deep knee flexion under load; heavy overhead pressing"
    
    print("=== Test Case 1 ===")
    print(f"Input: {text}")
    print()
    
    # Parse
    injuries, constraints = parse_injuries_and_restrictions(text)
    
    print(f"Parsed {len(injuries)} injury(ies):")
    for inj in injuries:
        print(f"  - Region: {inj.get('canonical_location')}, Type: {inj.get('injury_type')}, Side: {inj.get('side')}")
    
    print(f"\nParsed {len(constraints)} constraint(s):")
    for con in constraints:
        print(f"  - {con.get('original_phrase')} (region: {con.get('region')})")
    
    # Verify injuries
    assert len(injuries) == 1, f"Expected 1 injury, got {len(injuries)}"
    assert injuries[0]['canonical_location'] == 'shoulder'
    assert injuries[0]['injury_type'] == 'impingement'
    assert injuries[0]['side'] == 'right'
    
    # Verify constraints
    assert len(constraints) == 2, f"Expected 2 constraints, got {len(constraints)}"
    
    # Test severity extraction through _normalize_injury_entries
    entries = _normalize_injury_entries(text)
    print(f"\nNormalized entries: {entries}")
    
    assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"
    assert entries[0]['canonical_location'] == 'shoulder'
    assert entries[0]['severity'] in ['mild', 'moderate'], f"Unexpected severity: {entries[0]['severity']}"
    
    # Test injury_context to ensure knee doesn't get severity
    debug_entries = []
    region_severity = _injury_context([text], debug_entries=debug_entries)
    
    print(f"\nRegion severities: {region_severity}")
    print(f"Debug entries:")
    for entry in debug_entries:
        print(f"  - {entry}")
    
    assert 'shoulder' in region_severity, f"Expected shoulder in regions: {region_severity}"
    assert 'knee' not in region_severity, f"Knee should NOT be in regions: {region_severity}"
    
    print("\n✅ Test case 1 passed!")


def test_problem_statement_case_2():
    """
    Test case 2 from problem statement:
    Input: "left knee pain (patellar tendon)"
    Expected:
      - Injuries: [{severity: "moderate", region: "knee", condition: "tendonitis"}]
      - Constraints: []
    """
    text = "left knee pain (patellar tendon)"
    
    print("\n=== Test Case 2 ===")
    print(f"Input: {text}")
    print()
    
    # Parse
    injuries, constraints = parse_injuries_and_restrictions(text)
    
    print(f"Parsed {len(injuries)} injury(ies):")
    for inj in injuries:
        print(f"  - Region: {inj.get('canonical_location')}, Type: {inj.get('injury_type')}, Side: {inj.get('side')}")
    
    print(f"\nParsed {len(constraints)} constraint(s):")
    for con in constraints:
        print(f"  - {con.get('original_phrase')}")
    
    # Verify
    assert len(injuries) == 1, f"Expected 1 injury, got {len(injuries)}"
    assert len(constraints) == 0, f"Expected 0 constraints, got {len(constraints)}"
    
    assert injuries[0]['canonical_location'] == 'knee'
    assert injuries[0]['injury_type'] == 'tendonitis'
    assert injuries[0]['side'] == 'left'
    
    # Test severity extraction
    entries = _normalize_injury_entries(text)
    print(f"\nNormalized entries: {entries}")
    
    assert len(entries) == 1
    assert entries[0]['canonical_location'] == 'knee'
    assert entries[0]['severity'] in ['mild', 'moderate'], f"Unexpected severity: {entries[0]['severity']}"
    
    print("\n✅ Test case 2 passed!")


def test_no_false_positives_for_constraint_severities():
    """Test that severity from constraint phrases doesn't leak to injuries."""
    text = "ankle sprain; avoid severe impact"
    
    print("\n=== Test Case: No False Positives ===")
    print(f"Input: {text}")
    print()
    
    injuries, constraints = parse_injuries_and_restrictions(text)
    
    print(f"Parsed {len(injuries)} injury(ies):")
    for inj in injuries:
        print(f"  - {inj}")
    
    print(f"\nParsed {len(constraints)} constraint(s):")
    for con in constraints:
        print(f"  - {con}")
    
    # The word "severe" appears in the constraint "avoid severe impact"
    # but it should NOT affect the ankle sprain severity
    entries = _normalize_injury_entries(text)
    print(f"\nNormalized entries: {entries}")
    
    assert len(entries) == 1
    ankle_entry = entries[0]
    
    # Ankle sprain should have default severity for sprain (moderate), 
    # NOT "severe" from the constraint phrase
    assert ankle_entry['severity'] in ['moderate'], f"Severity incorrectly influenced by constraint: {ankle_entry['severity']}"
    
    print("\n✅ No false positive test passed!")


if __name__ == "__main__":
    test_problem_statement_case_1()
    test_problem_statement_case_2()
    test_no_false_positives_for_constraint_severities()
    print("\n" + "="*50)
    print("✅ ALL PROBLEM STATEMENT TESTS PASSED!")
    print("="*50)
