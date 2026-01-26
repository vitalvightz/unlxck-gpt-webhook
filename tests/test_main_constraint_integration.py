"""Test that main.py properly handles constraint parsing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Test the parsing logic directly
from fightcamp.injury_formatting import parse_injuries_and_restrictions, format_restriction_summary

def test_main_parsing_logic():
    """Test the parsing logic used in main.py."""
    injury_text = "mild right shoulder impingement; avoid deep knee flexion under load; heavy overhead pressing"
    
    # Parse using the same logic as main.py
    parsed_injuries, parsed_constraints = parse_injuries_and_restrictions(injury_text)
    
    print(f"Parsed {len(parsed_injuries)} injuries:")
    for inj in parsed_injuries:
        print(f"  - {inj}")
    
    print(f"\nParsed {len(parsed_constraints)} constraints:")
    for constraint in parsed_constraints:
        summary = format_restriction_summary(constraint)
        print(f"  - {summary}")
    
    # Create raw injury list (same as main.py)
    raw_injury_list = []
    if parsed_injuries:
        raw_injury_list = [
            f"{inj.get('side', '')} {inj.get('canonical_location', '')} {inj.get('injury_type', '')}".strip().lower()
            for inj in parsed_injuries
            if inj.get('canonical_location')
        ]
    
    print(f"\nRaw injury list for injury_guard: {raw_injury_list}")
    
    # Verify
    assert len(parsed_injuries) == 1, f"Expected 1 injury, got {len(parsed_injuries)}"
    assert len(parsed_constraints) == 2, f"Expected 2 constraints, got {len(parsed_constraints)}"
    assert len(raw_injury_list) == 1, f"Expected 1 raw injury, got {len(raw_injury_list)}"
    assert "shoulder" in raw_injury_list[0], f"Expected shoulder in raw injury: {raw_injury_list[0]}"
    assert "knee" not in str(raw_injury_list), f"Knee should not be in raw injury list: {raw_injury_list}"
    
    print("\n✅ Main parsing logic test passed!")


def test_constraint_logging():
    """Test that constraint logging works as expected."""
    injury_text = "left knee pain; avoid running"
    
    parsed_injuries, parsed_constraints = parse_injuries_and_restrictions(injury_text)
    
    # Simulate logging
    if parsed_constraints:
        print(f"[constraint-parse] Parsed {len(parsed_constraints)} constraints:")
        for constraint in parsed_constraints:
            summary = format_restriction_summary(constraint)
            print(f"[constraint-parse]   - {summary}")
    
    assert len(parsed_constraints) > 0, "Expected at least 1 constraint"
    print("\n✅ Constraint logging test passed!")


if __name__ == "__main__":
    test_main_parsing_logic()
    test_constraint_logging()
    print("\n✅ All main.py integration tests passed!")
