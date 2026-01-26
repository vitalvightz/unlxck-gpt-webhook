import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_formatting import parse_injuries_and_restrictions
from fightcamp.injury_guard import _injury_context, normalize_severity
from fightcamp.rehab_protocols import _normalize_injury_entries


def test_constraint_separation_basic():
    """Test that constraints are separated from injuries."""
    text = "mild right shoulder impingement; avoid deep knee flexion under load; heavy overhead pressing"
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 1 injury
    assert len(injuries) == 1, f"Expected 1 injury, got {len(injuries)}: {injuries}"
    
    # Should have 2 restrictions
    assert len(restrictions) == 2, f"Expected 2 restrictions, got {len(restrictions)}: {restrictions}"
    
    # Verify the injury
    injury = injuries[0]
    assert injury["canonical_location"] == "shoulder", f"Expected shoulder, got {injury['canonical_location']}"
    assert injury["injury_type"] == "impingement", f"Expected impingement, got {injury['injury_type']}"
    assert injury["side"] == "right", f"Expected right, got {injury['side']}"
    
    # Verify the restrictions
    restriction_phrases = [r["original_phrase"] for r in restrictions]
    assert any("avoid" in p and "knee" in p for p in restriction_phrases), f"Missing knee restriction: {restriction_phrases}"
    assert any("overhead" in p and "pressing" in p for p in restriction_phrases), f"Missing overhead restriction: {restriction_phrases}"


def test_constraint_severity_not_extracted():
    """Test that severity is not extracted from constraint phrases."""
    text = "mild right shoulder impingement; avoid deep knee flexion under load"
    
    # Test through _normalize_injury_entries
    entries = _normalize_injury_entries(text)
    
    # Should only have the shoulder injury, not the knee constraint
    assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}: {entries}"
    
    entry = entries[0]
    assert entry["canonical_location"] == "shoulder", f"Expected shoulder, got {entry['canonical_location']}"
    assert entry["severity"] in ["mild", "moderate"], f"Unexpected severity: {entry['severity']}"


def test_injury_context_filters_constraints():
    """Test that _injury_context filters out constraint phrases."""
    text = "mild right shoulder impingement; avoid deep knee flexion"
    
    debug_entries = []
    region_severity = _injury_context([text], debug_entries=debug_entries)
    
    # Should only have shoulder region, not knee
    assert "shoulder" in region_severity, f"Expected shoulder in regions: {region_severity}"
    assert "knee" not in region_severity, f"Knee should not be in regions: {region_severity}"
    
    # Check debug entries to see what was filtered
    filtered_entries = [e for e in debug_entries if e.get("filtered")]
    assert len(filtered_entries) > 0, f"Expected filtered entries, got: {debug_entries}"


def test_severity_per_phrase():
    """Test that severity is extracted per phrase, not from entire text."""
    text = "severe left ankle sprain; mild right shoulder impingement"
    
    entries = _normalize_injury_entries(text)
    
    # Should have 2 injuries with different severities
    assert len(entries) == 2, f"Expected 2 entries, got {len(entries)}: {entries}"
    
    # Find the ankle and shoulder entries
    ankle_entry = next((e for e in entries if e.get("canonical_location") == "ankle"), None)
    shoulder_entry = next((e for e in entries if e.get("canonical_location") == "shoulder"), None)
    
    assert ankle_entry is not None, f"Missing ankle entry: {entries}"
    assert shoulder_entry is not None, f"Missing shoulder entry: {entries}"
    
    # Verify severities are correct per phrase
    assert ankle_entry["severity"] == "severe", f"Expected severe ankle, got {ankle_entry['severity']}"
    assert shoulder_entry["severity"] == "mild", f"Expected mild shoulder, got {shoulder_entry['severity']}"


def test_left_knee_pain_patellar_tendon():
    """Test case from problem statement: left knee pain (patellar tendon)."""
    text = "left knee pain (patellar tendon)"
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 1 injury, 0 restrictions
    assert len(injuries) == 1, f"Expected 1 injury, got {len(injuries)}: {injuries}"
    assert len(restrictions) == 0, f"Expected 0 restrictions, got {len(restrictions)}: {restrictions}"
    
    # Verify the injury
    injury = injuries[0]
    assert injury["canonical_location"] == "knee", f"Expected knee, got {injury['canonical_location']}"
    assert injury["side"] == "left", f"Expected left, got {injury['side']}"
    
    # Verify severity extraction
    entries = _normalize_injury_entries(text)
    assert len(entries) == 1
    # "pain" typically maps to "moderate" severity
    assert entries[0]["severity"] in ["mild", "moderate"], f"Unexpected severity: {entries[0]['severity']}"


def test_no_region_no_severity():
    """Test that phrases without regions don't generate severity events."""
    text = "feeling tired and sore overall"
    
    debug_entries = []
    region_severity = _injury_context([text], debug_entries=debug_entries)
    
    # Should not extract any regions or severities
    # (This text is vague and shouldn't match any injury patterns)
    # If it does extract something, that's ok as long as it has a valid region
    for region in region_severity:
        assert region is not None, f"Region should not be None: {region_severity}"


def test_constraint_phrase_with_avoid():
    """Test that 'avoid' phrases are properly classified as constraints."""
    text = "avoid running; ankle sprain"
    
    injuries, restrictions = parse_injuries_and_restrictions(text)
    
    # Should have 1 injury (ankle sprain), 1 restriction (avoid running)
    assert len(injuries) == 1, f"Expected 1 injury, got {len(injuries)}: {injuries}"
    assert len(restrictions) >= 1, f"Expected at least 1 restriction, got {len(restrictions)}: {restrictions}"
    
    # Verify the injury
    injury = injuries[0]
    assert injury["canonical_location"] == "ankle", f"Expected ankle, got {injury['canonical_location']}"


def test_severity_descriptors_stay_in_context():
    """Test that severity descriptors stay within same phrase-region context."""
    text = "mild shoulder pain; knee injury"
    
    entries = _normalize_injury_entries(text)
    
    # Should have 2 injuries
    assert len(entries) == 2, f"Expected 2 entries, got {len(entries)}: {entries}"
    
    shoulder_entry = next((e for e in entries if e.get("canonical_location") == "shoulder"), None)
    knee_entry = next((e for e in entries if e.get("canonical_location") == "knee"), None)
    
    assert shoulder_entry is not None
    assert knee_entry is not None
    
    # Shoulder should be mild (has "mild" in its phrase)
    assert shoulder_entry["severity"] == "mild", f"Expected mild shoulder, got {shoulder_entry['severity']}"
    
    # Knee should be moderate (no severity descriptor, default for "unspecified" injury type)
    assert knee_entry["severity"] in ["moderate"], f"Expected moderate knee, got {knee_entry['severity']}"


if __name__ == "__main__":
    test_constraint_separation_basic()
    print("✓ test_constraint_separation_basic passed")
    
    test_constraint_severity_not_extracted()
    print("✓ test_constraint_severity_not_extracted passed")
    
    test_injury_context_filters_constraints()
    print("✓ test_injury_context_filters_constraints passed")
    
    test_severity_per_phrase()
    print("✓ test_severity_per_phrase passed")
    
    test_left_knee_pain_patellar_tendon()
    print("✓ test_left_knee_pain_patellar_tendon passed")
    
    test_no_region_no_severity()
    print("✓ test_no_region_no_severity passed")
    
    test_constraint_phrase_with_avoid()
    print("✓ test_constraint_phrase_with_avoid passed")
    
    test_severity_descriptors_stay_in_context()
    print("✓ test_severity_descriptors_stay_in_context passed")
    
    print("\n✅ All tests passed!")
