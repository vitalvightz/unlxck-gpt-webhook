from fightcamp.injury_location import get_injury_location


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
    assert get_injury_location({"area": " Left Rib "}) == "left rib"
