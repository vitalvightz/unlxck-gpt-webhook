"""Broad body-region classification built on the existing injury parser.

The injury system already owns the large synonym vocabulary in
``fightcamp.injury_synonyms.LOCATION_MAP``. This module deliberately does not
repeat those synonyms. It groups the parser's small set of canonical locations
into the broad loading regions consumed by Today.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from .injury_location_registry import build_location_region_map

BodyRegion = Literal[
    "lower_limb",
    "upper_limb",
    "trunk_spine",
    "head_neck",
    "unknown",
]

RegionGroup = Literal[
    "lower_leg_foot",
    "knee",
    "hip_groin",
    "upper_limb",
    "spine_pelvis",
    "head_face",
    "lower_limb",
    "unknown",
]


class InjuryBodyRegionContext(TypedDict):
    canonical_location: str | None
    region_group: RegionGroup
    body_region: BodyRegion


# Canonical locations only — never athlete-entered synonyms. Synonym
# recognition remains owned by LOCATION_MAP/canonicalize_location.
_CANONICAL_REGION_GROUP: dict[str, RegionGroup] = {
    "toe": "lower_leg_foot",
    "foot": "lower_leg_foot",
    "heel": "lower_leg_foot",
    "ankle": "lower_leg_foot",
    "achilles": "lower_leg_foot",
    "calf": "lower_leg_foot",
    "shin": "lower_leg_foot",
    "hamstring": "lower_leg_foot",
    "quads": "knee",
    "knee": "knee",
    "hip": "hip_groin",
    "hip flexor": "hip_groin",
    "groin": "hip_groin",
    "glute": "hip_groin",
    "glutes": "hip_groin",
    "biceps": "upper_limb",
    "triceps": "upper_limb",
    "shoulder": "upper_limb",
    "elbow": "upper_limb",
    "forearm": "upper_limb",
    "wrist": "upper_limb",
    "hand": "upper_limb",
    "fingers": "upper_limb",
    "chest": "spine_pelvis",
    "core": "spine_pelvis",
    "obliques": "spine_pelvis",
    "upper back": "spine_pelvis",
    "lower back": "spine_pelvis",
    "si joint": "spine_pelvis",
    "neck": "head_face",
    "jaw": "head_face",
    "face": "head_face",
    "eye": "head_face",
}

_BODY_REGION_BY_GROUP: dict[str, BodyRegion] = {
    "lower_leg_foot": "lower_limb",
    "knee": "lower_limb",
    "hip_groin": "lower_limb",
    "lower_limb": "lower_limb",
    "upper_limb": "upper_limb",
    "spine_pelvis": "trunk_spine",
    "head_face": "head_neck",
}

_FALLBACK_GROUP_BY_REGION: dict[BodyRegion, RegionGroup] = {
    "lower_limb": "lower_limb",
    "upper_limb": "upper_limb",
    "trunk_spine": "spine_pelvis",
    "head_neck": "head_face",
    "unknown": "unknown",
}

# Broad anatomical words whose legacy canonical location is intentionally
# ``unspecified``. These are fallbacks, not a second synonym bank.
_GENERIC_LOWER_LIMB = re.compile(
    r"\b(?:leg|legs|lower\s+leg|lower\s+legs|femur|thigh\s+bone)\b", re.I
)
_GENERIC_UPPER_LIMB = re.compile(
    r"\b(?:arm|arms|upper\s+arm|upper\s+arms)\b", re.I
)
_GENERIC_TRUNK_SPINE = re.compile(
    r"\b(?:torso|trunk|spine|spinal|pelvis|pelvic|coccyx|tailbone|ribs?|ribcage|sternum)\b",
    re.I,
)
_GENERIC_BACK = re.compile(
    r"\bback\b(?!\s+of\s+(?:leg|thigh|knee|calf|arm|shoulder))", re.I
)
_GENERIC_HEAD_NECK = re.compile(r"\b(?:head|brain|skull)\b", re.I)


def region_group_for_canonical_location(location: object) -> RegionGroup:
    """Return the existing detailed group for one canonical location."""
    normalized = " ".join(
        str(location or "").replace("_", " ").lower().split()
    )
    if not normalized or normalized == "unspecified":
        return "unknown"
    registry_group = build_location_region_map().get(normalized)
    group = registry_group or _CANONICAL_REGION_GROUP.get(normalized)
    if group in _BODY_REGION_BY_GROUP:
        return group  # type: ignore[return-value]
    return "unknown"


def body_region_for_canonical_location(location: object) -> BodyRegion:
    return _BODY_REGION_BY_GROUP.get(
        region_group_for_canonical_location(location), "unknown"
    )


def _generic_body_region(text: str) -> BodyRegion:
    if _GENERIC_LOWER_LIMB.search(text):
        return "lower_limb"
    if _GENERIC_UPPER_LIMB.search(text):
        return "upper_limb"
    if _GENERIC_TRUNK_SPINE.search(text) or _GENERIC_BACK.search(text):
        return "trunk_spine"
    if _GENERIC_HEAD_NECK.search(text):
        return "head_neck"
    return "unknown"


def injury_body_region_context(
    body_area: object,
    description: object,
) -> InjuryBodyRegionContext:
    """Resolve an injury through the shared scorer, then group its location."""
    from .injury_scoring import score_injury_phrase
    from .injury_synonyms import canonicalize_location

    text = " ".join(
        part
        for part in (
            str(body_area or "").strip(),
            str(description or "").strip(),
        )
        if part
    )
    score = score_injury_phrase(text) or {}
    canonical = " ".join(
        str(score.get("location") or "").replace("_", " ").lower().split()
    )
    if not canonical or canonical == "unspecified":
        fallback = canonicalize_location(text) if text else None
        canonical = " ".join(
            str(fallback or "").replace("_", " ").lower().split()
        )

    region_group = region_group_for_canonical_location(canonical)
    body_region = _BODY_REGION_BY_GROUP.get(region_group, "unknown")
    canonical_location = (
        canonical if canonical and canonical != "unspecified" else None
    )

    if body_region == "unknown":
        body_region = _generic_body_region(text)
        region_group = _FALLBACK_GROUP_BY_REGION[body_region]

    return {
        "canonical_location": canonical_location,
        "region_group": region_group,
        "body_region": body_region,
    }
