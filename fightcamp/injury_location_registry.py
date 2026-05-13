from __future__ import annotations

from typing import Any

LOCATION_REGISTRY: dict[str, dict[str, Any]] = {
    "knee": {
        "synonyms": ["knee", "knees", "patellar", "patella", "acl", "mcl", "lcl", "pcl", "meniscus"],
        "exclusion_region": "knee",
        "rehab_locations": ["knee"],
        "region_group": "knee",
        "sensitive_contact_area": False,
    },
    "biceps": {
        "synonyms": ["bicep", "biceps", "upper arm biceps"],
        "exclusion_region": "elbow",
        "secondary_exclusion_regions": ["shoulder"],
        "rehab_locations": ["biceps", "bicep"],
        "region_group": "upper_limb",
        "sensitive_contact_area": False,
    },
    "jaw": {
        "synonyms": ["jaw", "jawbone", "mandible"],
        "exclusion_region": "head",
        "rehab_locations": ["face", "jaw"],
        "region_group": "head_face",
        "sensitive_contact_area": True,
    },
    "heel": {
        "synonyms": ["heel", "heel bone", "calcaneus", "heel pad"],
        "exclusion_region": "foot",
        "secondary_exclusion_regions": ["achilles"],
        "rehab_locations": ["heel", "foot"],
        "region_group": "lower_leg_foot",
        "sensitive_contact_area": False,
    },
    "hamstring": {
        "synonyms": ["hamstring", "hamstrings"],
        "exclusion_region": "hamstring",
        "rehab_locations": ["hamstring", "hamstrings"],
        "region_group": "lower_leg_foot",
        "sensitive_contact_area": False,
    },
    "quad": {
        "synonyms": ["quad", "quads"],
        "exclusion_region": "quad",
        "secondary_exclusion_regions": ["knee"],
        "rehab_locations": ["quad", "quads"],
        "region_group": "knee",
        "sensitive_contact_area": False,
    },
    "glute": {
        "synonyms": ["glute", "glutes"],
        "exclusion_region": "glute",
        "secondary_exclusion_regions": ["hip"],
        "rehab_locations": ["glute", "glutes"],
        "region_group": "hip_groin",
        "sensitive_contact_area": False,
    },
    "hip flexor": {
        "synonyms": ["hip flexor", "hip_flexor"],
        "exclusion_region": "hip_flexor",
        "secondary_exclusion_regions": ["hip"],
        "rehab_locations": ["hip flexor", "hip_flexor"],
        "region_group": "hip_groin",
        "sensitive_contact_area": False,
    },
    "lower back": {
        "synonyms": ["lower back", "lower_back"],
        "exclusion_region": "lower_back",
        "rehab_locations": ["lower back", "lower_back"],
        "region_group": "spine_pelvis",
        "sensitive_contact_area": False,
    },
    "upper back": {
        "synonyms": ["upper back", "upper_back"],
        "exclusion_region": "upper_back",
        "rehab_locations": ["upper back", "upper_back"],
        "region_group": "spine_pelvis",
        "sensitive_contact_area": False,
    },
    "si joint": {
        "synonyms": ["si joint", "si_joint"],
        "exclusion_region": "si_joint",
        "secondary_exclusion_regions": ["lower_back"],
        "rehab_locations": ["si joint", "si_joint"],
        "region_group": "spine_pelvis",
        "sensitive_contact_area": False,
    },
}


def build_location_synonym_map() -> dict[str, str]:
    synonym_map: dict[str, str] = {}
    for canonical, data in LOCATION_REGISTRY.items():
        synonym_map[canonical] = canonical
        for synonym in data.get("synonyms", []):
            synonym_map[synonym] = canonical
    return synonym_map


def canonicalize_location_from_registry(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    cleaned = cleaned.replace("_", " ")
    for prefix in ("left ", "right ", "both "):
        if cleaned.startswith(prefix):
            cleaned = cleaned.removeprefix(prefix).strip()
            break
    if not cleaned:
        return None
    return build_location_synonym_map().get(cleaned, cleaned)


def build_location_region_map() -> dict[str, str]:
    return {location: data["region_group"] for location, data in LOCATION_REGISTRY.items() if data.get("region_group")}


def get_rehab_location_candidates(location: str) -> list[str]:
    entry = LOCATION_REGISTRY.get(location)
    if not entry:
        return [location, "unspecified"]
    return entry.get("rehab_locations", [location])
