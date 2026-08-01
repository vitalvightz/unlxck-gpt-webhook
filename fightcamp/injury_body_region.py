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
    "pelvis": "spine_pelvis",
    "pelvic": "spine_pelvis",
    "coccyx": "spine_pelvis",
    "tailbone": "spine_pelvis",
    "head": "head_face",
    "skull": "head_face",
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
_GENERIC_HEAD_NECK = re.compile(
    r"\b(?:brain|skull)\b|"
    r"(?<!long\s)(?<!short\s)(?<!femoral\s)(?<!radial\s)(?<!humeral\s)"
    r"\bhead\b(?!\s+of\b)",
    re.I,
)
_SPINE_PELVIS_PRIMARY = re.compile(r"\b(?:pelvis|pelvic|coccyx|tailbone)\b", re.I)
_BICEPS_FEMORIS = re.compile(r"\bbiceps\s+femoris\b", re.I)


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
    if _GENERIC_HEAD_NECK.search(text):
        return "head_neck"
    if _GENERIC_TRUNK_SPINE.search(text) or _GENERIC_BACK.search(text):
        return "trunk_spine"
    return "unknown"


def _context_from_text(text: str) -> InjuryBodyRegionContext:
    """Resolve one already-selected injury field without borrowing other anatomy."""
    from .injury_negation import remove_negated_phrases
    from .injury_scoring import score_injury_phrase
    from .injury_synonyms import canonicalize_location

    cleaned = remove_negated_phrases(text or "").strip()
    if not cleaned:
        return {
            "canonical_location": None,
            "region_group": "unknown",
            "body_region": "unknown",
        }

    # Preserve anatomical phrases the legacy location parser intentionally folds
    # into a nearby training region but that Today must route more conservatively.
    if _BICEPS_FEMORIS.search(cleaned):
        canonical = "hamstring"
    elif _SPINE_PELVIS_PRIMARY.search(cleaned):
        match = _SPINE_PELVIS_PRIMARY.search(cleaned)
        canonical = str(match.group(0)).lower() if match else "pelvis"
    elif re.search(r"\bback\s+of\s+(?:the\s+)?(?:head|skull)\b", cleaned, re.I):
        canonical = "head"
    else:
        direct = canonicalize_location(cleaned)
        canonical = " ".join(
            str(direct or "").replace("_", " ").lower().split()
        )

    region_group = region_group_for_canonical_location(canonical)
    body_region = _BODY_REGION_BY_GROUP.get(region_group, "unknown")

    if body_region == "unknown":
        score = score_injury_phrase(cleaned) or {}
        scored_location = " ".join(
            str(score.get("location") or "").replace("_", " ").lower().split()
        )
        scored_group = region_group_for_canonical_location(scored_location)
        if scored_group != "unknown":
            canonical = scored_location
            region_group = scored_group
            body_region = _BODY_REGION_BY_GROUP[region_group]
        else:
            # ``raw_text`` is the scorer's post-negation text. Generic fallback
            # must never rescan the uncleaned athlete wording.
            generic_text = str(score.get("raw_text") or cleaned)
            body_region = _generic_body_region(generic_text)
            region_group = _FALLBACK_GROUP_BY_REGION[body_region]

    return {
        "canonical_location": (
            canonical if canonical and canonical != "unspecified" else None
        ),
        "region_group": region_group,
        "body_region": body_region,
    }


def injury_body_region_context(
    body_area: object,
    description: object,
) -> InjuryBodyRegionContext:
    """Resolve ``body_area`` first; use description only when it has no location."""
    primary = _context_from_text(str(body_area or "").strip())
    if primary["body_region"] != "unknown":
        return primary
    return _context_from_text(str(description or "").strip())
