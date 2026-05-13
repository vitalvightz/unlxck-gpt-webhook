from __future__ import annotations

from fightcamp.injury_registry import (
    ALL_INJURY_TYPES,
    INJURY_TYPE_SEVERITY,
    REHAB_BLOCKED_TYPES,
    REHAB_SAFE_TYPES,
    SURFACE_TISSUE_TYPES,
    get_registry_category,
    is_known_injury_type,
    is_rehab_blocked_type,
)
from fightcamp.injury_taxonomy import INJURY_TAXONOMY, derive_injury_type_severity_map


def test_registry_contains_same_injury_keys_as_taxonomy() -> None:
    assert ALL_INJURY_TYPES == set(INJURY_TAXONOMY.keys())


def test_injury_type_severity_matches_taxonomy_derived_map() -> None:
    assert dict(INJURY_TYPE_SEVERITY) == derive_injury_type_severity_map()


def test_rehab_safe_types_include_existing_safe_types() -> None:
    for injury_type in {"sprain", "strain", "tightness", "pain", "soreness"}:
        assert injury_type in REHAB_SAFE_TYPES


def test_rehab_blocked_types_include_existing_blocked_types() -> None:
    for injury_type in {"fracture", "dislocation", "concussion", "tendon_rupture"}:
        assert injury_type in REHAB_BLOCKED_TYPES


def test_surface_tissue_types_match_expected_set() -> None:
    assert SURFACE_TISSUE_TYPES == {"abrasion", "cut", "graze", "blister", "laceration"}


def test_unknown_input_does_not_create_new_type() -> None:
    assert is_known_injury_type("made_up_injury") is False
    assert "made_up_injury" not in ALL_INJURY_TYPES
    assert is_rehab_blocked_type("made_up_injury") is False


def test_hyphen_and_space_normalisation_match_tendon_rupture() -> None:
    assert is_known_injury_type("tendon rupture") is True
    assert is_known_injury_type("tendon-rupture") is True
    assert is_rehab_blocked_type("tendon rupture") == is_rehab_blocked_type("tendon_rupture")
    assert get_registry_category("tendon-rupture") == get_registry_category("tendon_rupture")
