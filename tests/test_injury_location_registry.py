from fightcamp.injury_exclusion_rules import INJURY_RULES
from fightcamp.injury_exclusion_rules import get_exclusion_regions
from fightcamp.injury_filtering import normalize_injury_regions
from fightcamp.injury_location import canonicalize_location
from fightcamp.injury_location_registry import LOCATION_REGISTRY, canonicalize_location_from_registry
from fightcamp.rehab_protocols import LOCATION_REGION_MAP, generate_rehab_protocols, get_rehab_locations


def test_every_location_synonym_resolves():
    for canonical, data in LOCATION_REGISTRY.items():
        for synonym in data["synonyms"]:
            assert canonicalize_location_from_registry(synonym) == canonical


def test_every_location_has_exclusion_route():
    for _location, data in LOCATION_REGISTRY.items():
        assert data.get("exclusion_region") or data.get("no_exclusion_required") is True


def test_exclusion_regions_exist_in_injury_rules():
    for _location, data in LOCATION_REGISTRY.items():
        regions = [data.get("exclusion_region")]
        regions += data.get("secondary_exclusion_regions", [])
        for region in filter(None, regions):
            assert region in INJURY_RULES


def test_rehab_locations_exist_or_fallback():
    rehab_locations = get_rehab_locations()
    for _location, data in LOCATION_REGISTRY.items():
        candidates = data.get("rehab_locations", [])
        assert candidates or data.get("allow_unspecified_rehab") is True
        for candidate in candidates:
            assert candidate in rehab_locations or candidate == "unspecified"


def test_registry_bridge_preserves_existing_canonical_locations():
    legacy_locations = [
        "shoulder", "ankle", "wrist", "foot", "toe",
        "achilles", "calf", "shin", "neck", "elbow",
        "hand", "chest", "hip", "groin", "triceps",
    ]
    for location in legacy_locations:
        assert canonicalize_location(location) == location


def test_location_region_map_preserves_legacy_guardrails():
    assert LOCATION_REGION_MAP["shoulder"] == "upper_limb"
    assert LOCATION_REGION_MAP["ankle"] == "lower_leg_foot"
    assert LOCATION_REGION_MAP["wrist"] == "upper_limb"
    assert LOCATION_REGION_MAP["achilles"] == "lower_leg_foot"


def test_rehab_still_handles_legacy_locations():
    for injury in ["shoulder pain", "ankle sprain", "wrist pain", "achilles tightness"]:
        text, _ = generate_rehab_protocols(
            injury_string=injury,
            exercise_data=[],
            current_phase="GPP",
        )
        assert "No rehab options" not in text
        assert "Unspecified Location" not in text


def test_registry_exclusion_routing():
    assert get_exclusion_regions("biceps") == ["elbow", "shoulder"]
    assert get_exclusion_regions("jaw") == ["head"]
    assert get_exclusion_regions("heel") == ["foot", "achilles"]
    assert get_exclusion_regions("quad") == ["quad", "knee"]
    assert get_exclusion_regions("glute") == ["glute", "hip"]
    assert get_exclusion_regions("hip flexor") == ["hip_flexor", "hip"]
    assert get_exclusion_regions("si joint") == ["si_joint", "lower_back"]


def test_legacy_exclusion_location_fallback():
    assert get_exclusion_regions("ankle") == ["ankle"]
    assert get_exclusion_regions("shoulder") == ["shoulder"]
    assert get_exclusion_regions("wrist") == ["wrist"]
    assert get_exclusion_regions("achilles") == ["achilles"]


def test_normalize_injury_regions_uses_legacy_location_fallback():
    assert normalize_injury_regions(["ankle sprain"]) == {"ankle"}
    assert normalize_injury_regions(["shoulder pain"]) == {"shoulder"}
    # hip_flexor is not a distinct exclusion region; it rolls up to "hip".
    assert "hip" in normalize_injury_regions(["hip flexor strain"])
    assert "si_joint" in normalize_injury_regions(["si joint pain"])
