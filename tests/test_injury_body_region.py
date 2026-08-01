from __future__ import annotations

import pytest

from api.services.today_service import _with_safe_session_context
from fightcamp.injury_body_region import (
    body_region_for_canonical_location,
    injury_body_region_context,
    region_group_for_canonical_location,
)
from fightcamp.injury_synonyms import LOCATION_MAP


@pytest.mark.parametrize(
    ("phrase", "canonical", "region"),
    [
        ("soleus tear", "calf", "lower_limb"),
        ("metatarsal fracture", "foot", "lower_limb"),
        ("humerus fracture", "biceps", "upper_limb"),
        ("adductors tear", "groin", "lower_limb"),
        ("forehead cut", "face", "head_neck"),
        ("sternum fracture", "chest", "trunk_spine"),
        ("long head of biceps tear", "biceps", "upper_limb"),
        ("back of knee tear", "knee", "lower_limb"),
    ],
)
def test_existing_synonyms_resolve_to_broad_regions(
    phrase: str, canonical: str, region: str
) -> None:
    context = injury_body_region_context(phrase, phrase)
    assert context["canonical_location"] == canonical
    assert context["body_region"] == region


@pytest.mark.parametrize(
    ("phrase", "region"),
    [
        ("femur fracture", "lower_limb"),
        ("leg fracture", "lower_limb"),
        ("arm fracture", "upper_limb"),
        ("spine fracture", "trunk_spine"),
        ("head injury", "head_neck"),
    ],
)
def test_generic_backend_locations_receive_conservative_regions(
    phrase: str, region: str
) -> None:
    assert injury_body_region_context(phrase, phrase)["body_region"] == region


def test_every_canonical_location_from_existing_synonym_map_is_grouped() -> None:
    canonicals = {
        " ".join(str(location).replace("_", " ").lower().split())
        for location in LOCATION_MAP.values()
        if str(location).strip() and str(location).strip() != "unspecified"
    }
    missing = {
        location
        for location in canonicals
        if region_group_for_canonical_location(location) == "unknown"
        or body_region_for_canonical_location(location) == "unknown"
    }
    assert missing == set()


def test_today_payload_enrichment_uses_backend_region_and_consequence() -> None:
    [row] = _with_safe_session_context(
        [
            {
                "id": "inj-1",
                "body_area": "soleus",
                "description": "soleus tear",
                "severity": "moderate",
                "status": "open",
            }
        ]
    )
    assert row["canonical_location"] == "calf"
    assert row["region_group"] == "lower_leg_foot"
    assert row["body_region"] == "lower_limb"
    assert row["consequence"] == "structural"
