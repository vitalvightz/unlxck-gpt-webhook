from pathlib import Path
import json
from .injury_exclusion_rules import INJURY_RULES, INJURY_REGION_KEYWORDS
from .injury_synonyms import parse_injury_phrase
from .injury_tagging import infer_tags_from_name


DATA_DIR = Path(__file__).resolve().parents[1] / "data"

LOCATION_REGION_MAP = {
    "toe": "toe",
    "foot": "foot",
    "heel": "foot",
    "ankle": "ankle",
    "achilles": "achilles",
    "calf": "calf",
    "shin": "shin",
    "knee": "knee",
    "quad": "quad",
    "hamstring": "hamstring",
    "hip flexor": "hip_flexor",
    "hip_flexor": "hip_flexor",
    "glutes": "glute",
    "glute": "glute",
    "groin": "groin",
    "hip": "hip",
    "si joint": "si_joint",
    "si_joint": "si_joint",
    "lower back": "lower_back",
    "lower_back": "lower_back",
    "upper back": "upper_back",
    "upper_back": "upper_back",
    "neck": "neck",
    "shoulder": "shoulder",
    "biceps": "shoulder",
    "chest": "chest",
    "elbow": "elbow",
    "forearm": "forearm",
    "wrist": "wrist",
    "hand": "hand",
    "fingers": "hand",
    "face": "head",
    "jaw": "head",
    "eye": "head",
    "head": "head",
}


def _load_injury_exclusion_map() -> dict:
    path = DATA_DIR / "injury_exclusion_map.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


INJURY_EXCLUSION_MAP = _load_injury_exclusion_map()


def normalize_injury_regions(injuries: list[str]) -> set[str]:
    regions = set()
    for injury in injuries or []:
        if not injury:
            continue
        text = injury.lower()
        if text in INJURY_RULES:
            regions.add(text)
            continue
        injury_type, location = parse_injury_phrase(text)
        found_region = False
        if location:
            mapped = LOCATION_REGION_MAP.get(location, location)
            if mapped in INJURY_RULES:
                regions.add(mapped)
                found_region = True
        if not found_region:
            for region, keywords in INJURY_REGION_KEYWORDS.items():
                if any(keyword in text for keyword in keywords):
                    regions.add(region)
                    found_region = True
                    break
        if injury_type == "unspecified" and location and not found_region:
            mapped = LOCATION_REGION_MAP.get(location, location)
            if mapped in INJURY_RULES:
                regions.add(mapped)
    return regions


def get_excluded_names(injury_regions: set[str]) -> set[str]:
    excluded = set()
    for region in injury_regions:
        excluded.update(INJURY_EXCLUSION_MAP.get(region, []))
    return excluded


def is_item_excluded(
    name: str,
    tags: list[str],
    injuries: list[str] | None = None,
    injury_regions: set[str] | None = None,
    excluded_names: set[str] | None = None,
) -> bool:
    if injuries is None and injury_regions is None:
        return False
    regions = injury_regions or normalize_injury_regions(injuries or [])
    if not regions:
        return False
    if excluded_names is None:
        excluded_names = get_excluded_names(regions)
    if name in excluded_names:
        return True
    tags_set = {t.lower() for t in tags} | set(infer_tags_from_name(name))
    name_lower = name.lower()
    for region in regions:
        rule = INJURY_RULES.get(region)
        if not rule:
            continue
        if any(keyword in name_lower for keyword in rule.get("ban_keywords", [])):
            return True
        if tags_set & set(rule.get("ban_tags", [])):
            return True
    return False


def filter_items(
    items: list[dict],
    injuries: list[str] | None,
    *,
    name_key: str = "name",
    tags_key: str = "tags",
) -> list[dict]:
    injury_regions = normalize_injury_regions(injuries or [])
    excluded_names = get_excluded_names(injury_regions)
    filtered = []
    for item in items:
        name = item.get(name_key, "")
        tags = item.get(tags_key, [])
        if is_item_excluded(
            name,
            tags,
            injury_regions=injury_regions,
            excluded_names=excluded_names,
        ):
            continue
        filtered.append(item)
    return filtered


def validate_injury_filter(selected_names: list[str], injuries: list[str]) -> None:
    regions = normalize_injury_regions(injuries)
    violations = []
    lowered = [name.lower() for name in selected_names]
    if "shoulder" in regions:
        shoulder_keywords = ["bench", "overhead", "press", "dip"]
        for name, lower in zip(selected_names, lowered):
            if any(keyword in lower for keyword in shoulder_keywords):
                violations.append(f"shoulder exclusion hit: {name}")
    if "achilles" in regions:
        achilles_keywords = ["depth jump", "drop jump", "max sprint"]
        for name, lower in zip(selected_names, lowered):
            if any(keyword in lower for keyword in achilles_keywords):
                violations.append(f"achilles exclusion hit: {name}")
    if violations:
        print("Injury filter violations detected:")
        for violation in violations:
            print(f"- {violation}")
        raise ValueError("Injury filter validation failed.")
