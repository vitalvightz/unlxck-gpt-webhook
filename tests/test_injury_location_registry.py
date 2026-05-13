from fightcamp.injury_exclusion_rules import INJURY_RULES
from fightcamp.injury_location_registry import LOCATION_REGISTRY, canonicalize_location_from_registry
from fightcamp.rehab_protocols import get_rehab_locations


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
