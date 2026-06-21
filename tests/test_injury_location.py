from fightcamp.injury_location import canonicalize_location, get_injury_location
from fightcamp.injury_guard import _injury_context
from fightcamp.rehab_protocols import generate_rehab_protocols


def test_get_injury_location_prefers_canonical_then_fallback_keys():
    entry = {
        "area": "Right Knee",
        "display_location": "Knee",
        "location": "leg",
        "region": "lower_limb",
        "canonical_location": "knee",
    }
    assert get_injury_location(entry) == "knee"


def test_get_injury_location_uses_area_when_only_area_available():
    assert get_injury_location({"area": " Left Rib "}) == "rib"


def test_get_injury_location_normalises_display_location_laterality_for_region_logic():
    assert get_injury_location({"display_location": "Left Knee"}) == "knee"


def test_canonicalize_location_covers_laterality_and_aliases():
    assert canonicalize_location("right knee") == "knee"
    assert canonicalize_location("left lower_back") == "lower back"
    assert canonicalize_location("upper_back") == "upper back"
    assert canonicalize_location("bicep") == "biceps"
    assert canonicalize_location("hamstrings") == "hamstring"
    assert canonicalize_location("quads") == "quads"
    assert canonicalize_location("glutes") == "glute"
    assert canonicalize_location("hip_flexor") == "hip flexor"
    assert canonicalize_location("si_joint") == "si joint"


def test_injury_guard_handles_canonical_location_only_as_knee_region():
    region_severity = _injury_context([{"canonical_location": "knee", "severity": "moderate"}])
    assert region_severity.get("knee") == "moderate"


def test_injury_guard_handles_region_only_as_knee_region():
    region_severity = _injury_context([{"region": "knee", "severity": "moderate"}])
    assert region_severity.get("knee") == "moderate"


def test_injury_guard_handles_display_location_only_as_knee_region():
    region_severity = _injury_context([{"display_location": "Left Knee", "severity": "moderate"}])
    assert region_severity.get("knee") == "moderate"


def test_rehab_protocols_prefers_structured_parsed_entries_over_raw_text():
    output, _ = generate_rehab_protocols(
        injury_string="right shoulder soreness",
        exercise_data=[],
        current_phase="GPP",
        parsed_entries=[{"canonical_location": "knee", "injury_type": "sprain", "severity": "moderate"}],
    )
    assert "Knee" in output


def test_generate_rehab_protocols_keeps_alias_lookup_for_lower_back_and_biceps():
    output, _ = generate_rehab_protocols(
        injury_string="lower back pain, bicep strain",
        exercise_data=[],
        current_phase="GPP",
    )
    assert "Lower Back" in output
    assert "Biceps" in output
