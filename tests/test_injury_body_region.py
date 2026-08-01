from __future__ import annotations

import pytest

from api.contracts.injury_checkin import injury_consequence_tier
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
        ("biceps femoris tear", "hamstring", "lower_limb"),
        ("pelvis fracture", "pelvis", "trunk_spine"),
        ("coccyx fracture", "coccyx", "trunk_spine"),
        ("back of head injury", "head", "head_neck"),
        ("back of skull injury", "head", "head_neck"),
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


def test_body_area_wins_over_unrelated_or_negated_description_anatomy() -> None:
    assert injury_body_region_context(
        "upper arm", "pain after kicking with the leg"
    )["body_region"] == "upper_limb"
    assert injury_body_region_context(
        "shoulder", "no leg injury, shoulder tear"
    )["body_region"] == "upper_limb"


def test_avulsion_is_a_structural_consequence() -> None:
    [row] = _with_safe_session_context(
        [
            {
                "body_area": "ankle",
                "description": "ankle avulsion",
                "severity": "moderate",
                "status": "open",
            }
        ]
    )
    assert row["body_region"] == "lower_limb"
    assert row["consequence"] == "structural"


@pytest.mark.parametrize(
    "description",
    ["soleus tear", "ankle fractures", "hip dislocations", "achilles ruptures"],
)
def test_structural_word_forms_are_classified(description: str) -> None:
    assert injury_consequence_tier("ankle", description) == "structural"


@pytest.mark.parametrize(
    "description",
    [
        "no fracture, mild ankle soreness",
        "no fracture or tear, mild ankle soreness",
        "nothing is ruptured, mild ankle soreness",
    ],
)
def test_negated_structural_wording_does_not_escalate(description: str) -> None:
    assert injury_consequence_tier("ankle", description) != "structural"


def test_safe_session_enrichment_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("classifier unavailable")

    monkeypatch.setattr("api.services.today_service.injury_body_region_context", fail)
    [row] = _with_safe_session_context(
        [{"body_area": "ankle", "description": "ankle fracture", "severity": "moderate"}]
    )
    assert row["body_region"] == "unknown"
    assert row["consequence"] == "structural"
