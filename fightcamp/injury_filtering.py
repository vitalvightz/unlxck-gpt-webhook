from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Iterable

from .injury_exclusion_rules import INJURY_REGION_KEYWORDS, INJURY_RULES

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

INFERRED_TAG_RULES = [
    {"keywords": ["bench", "floor press"], "tags": ["upper_push", "horizontal_push"]},
    {"keywords": ["overhead", "push press", "strict press", "military press"], "tags": ["overhead", "upper_push"]},
    {"keywords": ["snatch", "jerk"], "tags": ["overhead", "shoulder_heavy"]},
    {"keywords": ["dip"], "tags": ["upper_push", "elbow_extension_heavy"]},
    {"keywords": ["handstand"], "tags": ["overhead", "wrist_loaded_extension"]},
    {"keywords": ["push-up", "pushup"], "tags": ["upper_push", "wrist_loaded_extension"]},
    {"keywords": ["front rack"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {"keywords": ["clean"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {"keywords": ["deadlift", "rdl", "good morning", "jefferson curl"], "tags": ["hinge_heavy", "axial_heavy"]},
    {"keywords": ["back squat", "front squat", "heavy squat"], "tags": ["knee_dominant_heavy", "axial_heavy"]},
    {"keywords": ["deep squat", "pistol", "cossack"], "tags": ["deep_flexion", "hip_irritant"]},
    {"keywords": ["lateral lunge", "adductor"], "tags": ["adductor_load_high"]},
    {"keywords": ["nordic", "ham curl"], "tags": ["hamstring_eccentric_high"]},
    {"keywords": ["sprint", "max sprint"], "tags": ["max_velocity"]},
    {"keywords": ["jump", "plyo", "depth jump", "drop jump", "bounds", "hops", "pogo"], "tags": ["high_impact_plyo"]},
    {"keywords": ["jump rope"], "tags": ["impact_rebound_high", "foot_impact_high"]},
    {"keywords": ["bear crawl"], "tags": ["wrist_loaded_extension"]},
    {"keywords": ["rope climb", "towel", "thick grip", "plate pinch", "farmer", "dead hang"], "tags": ["grip_max", "hand_crush"]},
    {"keywords": ["bridges", "wrestler bridge"], "tags": ["neck_loaded"]},
    {"keywords": ["lateral bounds", "hard cuts"], "tags": ["ankle_lateral_impact_high"]},
    {"keywords": ["barefoot sprint"], "tags": ["foot_impact_high"]},
    {"keywords": ["contact", "sparring"], "tags": ["contact"]},
]


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def infer_tags_from_name(name: str) -> set[str]:
    normalized = _normalize_text(name)
    inferred: set[str] = set()
    for rule in INFERRED_TAG_RULES:
        normalized_keywords = [_normalize_text(keyword) for keyword in rule["keywords"]]
        if any(keyword in normalized for keyword in normalized_keywords):
            inferred.update(rule["tags"])
    return inferred


def normalize_injury_regions(injuries: Iterable[str]) -> set[str]:
    regions: set[str] = set()
    for injury in injuries:
        if not injury:
            continue
        normalized = _normalize_text(injury)
        direct_key = normalized.replace(" ", "_")
        if direct_key in INJURY_RULES:
            regions.add(direct_key)
            continue
        matched = False
        for region, keywords in INJURY_REGION_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                regions.add(region)
                matched = True
        if not matched:
            regions.add("unspecified")
    return regions


def injury_violation_reasons(item: dict, injuries: Iterable[str]) -> list[str]:
    if not injuries:
        return []
    name = item.get("name", "")
    name_lower = name.lower()
    tags = {t.lower() for t in item.get("tags", [])}
    inferred = infer_tags_from_name(name)
    all_tags = tags | inferred
    reasons: list[str] = []

    for region in normalize_injury_regions(injuries):
        rules = INJURY_RULES.get(region, {})
        ban_keywords = [kw.lower() for kw in rules.get("ban_keywords", [])]
        ban_tags = {t.lower() for t in rules.get("ban_tags", [])}
        for keyword in ban_keywords:
            if keyword in name_lower:
                reasons.append(f"{region}:keyword:{keyword}")
        for tag in sorted(all_tags & ban_tags):
            reasons.append(f"{region}:tag:{tag}")
    return reasons


def is_injury_safe(item: dict, injuries: Iterable[str]) -> bool:
    return not injury_violation_reasons(item, injuries)


def filter_items_for_injuries(items: Iterable[dict], injuries: Iterable[str]) -> list[dict]:
    return [item for item in items if is_injury_safe(item, injuries)]


def _load_style_specific_exercises() -> list[dict]:
    source = DATA_DIR / "style_specific_exercises"
    text = source.read_text()
    start = text.find("[")
    end = text.rfind("}")
    snippet = text[start : end + 1] + "]" if start != -1 and end != -1 else "[]"
    try:
        return ast.literal_eval(snippet)
    except Exception:
        return []


def collect_banks() -> dict[str, list[dict]]:
    banks: dict[str, list[dict]] = {}
    banks["exercise_bank"] = json.loads((DATA_DIR / "exercise_bank.json").read_text())
    banks["conditioning_bank"] = json.loads(
        (DATA_DIR / "conditioning_bank.json").read_text()
    )
    banks["style_conditioning_bank"] = json.loads(
        (DATA_DIR / "style_conditioning_bank.json").read_text()
    )
    banks["universal_gpp_strength"] = json.loads(
        (DATA_DIR / "universal_gpp_strength.json").read_text()
    )
    banks["universal_gpp_conditioning"] = json.loads(
        (DATA_DIR / "universal_gpp_conditioning.json").read_text()
    )
    banks["style_taper_conditioning"] = json.loads(
        (DATA_DIR / "style_taper_conditioning.json").read_text()
    )
    banks["style_specific_exercises"] = _load_style_specific_exercises()

    coord_data = json.loads((DATA_DIR / "coordination_bank.json").read_text())
    coordination_bank: list[dict] = []
    if isinstance(coord_data, list):
        coordination_bank.extend(coord_data)
    elif isinstance(coord_data, dict):
        for val in coord_data.values():
            if isinstance(val, list):
                coordination_bank.extend(val)
    banks["coordination_bank"] = coordination_bank

    return banks


def build_bank_inferred_tags() -> list[dict]:
    entries: list[dict] = []
    for bank_name, items in collect_banks().items():
        for item in items:
            name = item.get("name", "")
            item_id = f"{bank_name}:{name}"
            explicit_tags = [t.lower() for t in item.get("tags", [])]
            inferred_tags = sorted(infer_tags_from_name(name))
            entries.append(
                {
                    "item_id": item_id,
                    "bank": bank_name,
                    "name": name,
                    "explicit_tags": explicit_tags,
                    "inferred_tags": inferred_tags,
                }
            )
    return entries


def build_injury_exclusion_map() -> dict[str, list[str]]:
    exclusions = {region: [] for region in INJURY_RULES}
    for bank_name, items in collect_banks().items():
        for item in items:
            name = item.get("name", "")
            item_id = f"{bank_name}:{name}"
            name_lower = name.lower()
            tags = {t.lower() for t in item.get("tags", [])}
            tags |= infer_tags_from_name(name)
            for region, rule in INJURY_RULES.items():
                ban_keywords = [kw.lower() for kw in rule.get("ban_keywords", [])]
                ban_tags = {t.lower() for t in rule.get("ban_tags", [])}
                if any(keyword in name_lower for keyword in ban_keywords) or tags & ban_tags:
                    exclusions[region].append(item_id)
    for region in exclusions:
        exclusions[region] = sorted(set(exclusions[region]))
    return exclusions


def write_injury_exclusion_files(output_dir: Path | None = None) -> None:
    output_dir = output_dir or DATA_DIR
    inferred_path = output_dir / "bank_inferred_tags.json"
    exclusion_path = output_dir / "injury_exclusion_map.json"

    inferred = build_bank_inferred_tags()
    exclusion_map = build_injury_exclusion_map()

    inferred_path.write_text(json.dumps(inferred, indent=2, sort_keys=True))
    exclusion_path.write_text(json.dumps(exclusion_map, indent=2, sort_keys=True))


def log_injury_debug(items: Iterable[dict], injuries: Iterable[str], *, label: str) -> None:
    normalized = sorted(normalize_injury_regions(injuries))
    print(f"[injury-debug] {label} normalized_injuries={normalized}")
    for item in items:
        name = item.get("name", "Unnamed")
        reasons = injury_violation_reasons(item, injuries)
        if reasons:
            print(f"[injury-debug] {label} item={name} allowed=False reasons={reasons}")
        else:
            print(f"[injury-debug] {label} item={name} allowed=True")
