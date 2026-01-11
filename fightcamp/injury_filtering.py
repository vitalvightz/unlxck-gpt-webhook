from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Iterable

from .injury_exclusion_rules import INJURY_REGION_KEYWORDS, INJURY_RULES
from .injury_synonyms import parse_injury_phrase, split_injury_text

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
INJURY_MATCH_ALLOWLIST: list[str] = [
    "pressure fighter",
    "pressure cooker",
    "sandbox jumper",
    "ship hinge",
    "stomach ache",
]
GENERIC_SINGLE_WORD_PATTERNS = {"press", "overhead", "bench"}

INFERRED_TAG_RULES = [
    {"keywords": ["bench press", "floor press"], "tags": ["upper_push", "horizontal_push"]},
    {
        "keywords": ["overhead press", "push press", "strict press", "military press"],
        "tags": ["overhead", "upper_push"],
    },
    {"keywords": ["snatch", "jerk"], "tags": ["overhead", "shoulder_heavy"]},
    {"keywords": ["ring dip", "bench dip", "parallel bar dip", "bar dip"], "tags": ["upper_push", "elbow_extension_heavy"]},
    {"keywords": ["handstand"], "tags": ["overhead", "wrist_loaded_extension"]},
    {"keywords": ["push-up", "pushup"], "tags": ["upper_push", "wrist_loaded_extension"]},
    {"keywords": ["front rack"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {"keywords": ["clean"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {"keywords": ["deadlift", "rdl", "good morning", "jefferson curl"], "tags": ["hinge_heavy", "axial_heavy"]},
    {"keywords": ["back squat", "front squat", "heavy squat"], "tags": ["knee_dominant_heavy", "axial_heavy"]},
    {"keywords": ["deep squat", "pistol", "cossack"], "tags": ["deep_flexion", "hip_irritant"]},
    {"keywords": ["lateral lunge", "adductor"], "tags": ["adductor_load_high"]},
    {"keywords": ["nordic", "ham curl"], "tags": ["hamstring_eccentric_high"]},
    {"keywords": ["sprint", "sprints", "max sprint", "acceleration", "accelerations"], "tags": ["max_velocity"]},
    {"keywords": ["jump", "plyo", "depth jump", "drop jump", "bounds", "hops", "pogo"], "tags": ["high_impact_plyo"]},
    {"keywords": ["jump rope"], "tags": ["impact_rebound_high", "foot_impact_high"]},
    {"keywords": ["bear crawl"], "tags": ["wrist_loaded_extension"]},
    {"keywords": ["rope climb", "towel", "thick grip", "plate pinch", "farmer", "dead hang"], "tags": ["grip_max", "hand_crush"]},
    {"keywords": ["bridges", "wrestler bridge"], "tags": ["neck_loaded"]},
    {"keywords": ["lateral bounds", "hard cuts"], "tags": ["ankle_lateral_impact_high"]},
    {"keywords": ["barefoot sprint"], "tags": ["foot_impact_high"]},
    {"keywords": ["contact", "sparring"], "tags": ["contact"]},
]

AUTO_TAG_RULES = [
    {
        "keywords": ["assault bike", "air bike", "bike", "cycle", "spin bike"],
        "tags": ["aerobic", "low_impact"],
    },
    {
        "keywords": ["row", "rower", "erg", "ski erg", "ski-erg"],
        "tags": ["aerobic", "low_impact"],
    },
    {"keywords": ["treadmill", "run", "running", "jog"], "tags": ["aerobic"]},
    {"keywords": ["mobility", "stretch", "recovery", "breathing"], "tags": ["mobility", "recovery"]},
]


def _normalize_text(text: str) -> str:
    cleaned = text.lower().replace("-", " ").replace("_", " ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def _phrase_in_tokens(tokens: list[str], phrase_tokens: list[str]) -> bool:
    if not phrase_tokens or len(phrase_tokens) > len(tokens):
        return False
    window = len(phrase_tokens)
    for idx in range(len(tokens) - window + 1):
        if tokens[idx : idx + window] == phrase_tokens:
            return True
    return False


def _build_phrase_regex(phrase: str) -> re.Pattern[str] | None:
    normalized = _normalize_text(phrase)
    if not normalized:
        return None
    tokens = normalized.split()
    if len(tokens) == 1 and tokens[0] in GENERIC_SINGLE_WORD_PATTERNS:
        return None
    escaped = [re.escape(token) for token in tokens]
    pattern = r"\b" + r"\s+".join(escaped) + r"\b"
    return re.compile(pattern)


def match_forbidden(text: str, patterns: Iterable[str], *, allowlist: Iterable[str] | None = None) -> list[str]:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return []
    allowlist = allowlist or []
    for phrase in allowlist:
        phrase_regex = _build_phrase_regex(phrase)
        if phrase_regex and phrase_regex.search(normalized_text):
            return []
    matches: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        phrase_regex = _build_phrase_regex(pattern)
        if not phrase_regex:
            continue
        if phrase_regex.search(normalized_text):
            if pattern not in seen:
                matches.append(pattern)
                seen.add(pattern)
    return matches


def infer_tags_from_name(name: str) -> set[str]:
    inferred: set[str] = set()
    for rule in INFERRED_TAG_RULES:
        if match_forbidden(name, rule["keywords"], allowlist=INJURY_MATCH_ALLOWLIST):
            inferred.update(rule["tags"])
    return inferred


def auto_tag(item: dict) -> set[str]:
    name = str(item.get("name", "") or "")
    purpose = str(item.get("purpose", "") or "")
    equipment = item.get("equipment", "")
    if isinstance(equipment, (list, tuple, set)):
        equipment_text = " ".join(str(e) for e in equipment if e)
    else:
        equipment_text = str(equipment or "")
    fields_text = " ".join([name, purpose, equipment_text])
    tags: set[str] = set(infer_tags_from_name(name))
    for rule in AUTO_TAG_RULES:
        if match_forbidden(fields_text, rule["keywords"], allowlist=INJURY_MATCH_ALLOWLIST):
            tags.update(rule["tags"])
    return {tag.lower() for tag in tags if tag}


def ensure_tags(item: dict) -> list[str]:
    raw_tags = [t for t in item.get("tags", []) if t]
    if raw_tags:
        return [t.lower() for t in raw_tags]
    inferred = sorted(auto_tag(item))
    if not inferred:
        inferred = ["untagged"]
    item["tags"] = inferred
    return inferred


def _map_text_to_region(text: str) -> str | None:
    for region, keywords in INJURY_REGION_KEYWORDS.items():
        if match_forbidden(text, keywords, allowlist=INJURY_MATCH_ALLOWLIST):
            return region
    return None


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
        for phrase in split_injury_text(injury):
            injury_type, location = parse_injury_phrase(phrase)
            for candidate in (location, injury_type, phrase):
                if not candidate:
                    continue
                region = _map_text_to_region(candidate)
                if region:
                    regions.add(region)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            region = _map_text_to_region(injury)
            if region:
                regions.add(region)
            else:
                regions.add("unspecified")
    return regions


def injury_violation_reasons(item: dict, injuries: Iterable[str]) -> list[str]:
    reasons: set[str] = set()
    for detail in injury_match_details(item, injuries, risk_levels=("exclude",)):
        region = detail["region"]
        for keyword in detail["patterns"]:
            reasons.add(f"{region}:keyword:{_normalize_text(keyword)}")
        for tag in detail["tags"]:
            reasons.add(f"{region}:tag:{tag}")
    return sorted(reasons)


def is_injury_safe(item: dict, injuries: Iterable[str]) -> bool:
    return not injury_violation_reasons(item, injuries)


def injury_violation_reasons_with_fields(
    item: dict,
    injuries: Iterable[str],
    *,
    fields: Iterable[str] | None = None,
) -> list[str]:
    reasons: set[str] = set()
    for detail in injury_match_details(item, injuries, fields=fields, risk_levels=("exclude",)):
        region = detail["region"]
        for keyword in detail["patterns"]:
            reasons.add(f"{region}:keyword:{_normalize_text(keyword)}")
        for tag in detail["tags"]:
            reasons.add(f"{region}:tag:{tag}")
    return sorted(reasons)


def injury_flag_reasons(item: dict, injuries: Iterable[str]) -> list[str]:
    reasons: set[str] = set()
    for detail in injury_match_details(item, injuries, risk_levels=("flag",)):
        region = detail["region"]
        for keyword in detail["patterns"]:
            reasons.add(f"{region}:keyword:{_normalize_text(keyword)}")
        for tag in detail["tags"]:
            reasons.add(f"{region}:tag:{tag}")
    return sorted(reasons)


def is_injury_safe_with_fields(
    item: dict,
    injuries: Iterable[str],
    *,
    fields: Iterable[str] | None = None,
) -> bool:
    return not injury_violation_reasons_with_fields(
        item, injuries, fields=fields
    )


def filter_items_for_injuries(items: Iterable[dict], injuries: Iterable[str]) -> list[dict]:
    return [item for item in items if is_injury_safe(item, injuries)]


def injury_match_details(
    item: dict,
    injuries: Iterable[str],
    *,
    fields: Iterable[str] | None = None,
    risk_levels: Iterable[str] | None = None,
) -> list[dict]:
    if not injuries:
        return []
    fields = fields or ("name",)
    risk_levels = set(risk_levels or ("exclude",))
    field_values = {field: str(item.get(field, "") or "") for field in fields}
    name = field_values.get("name", "")
    tags = set(ensure_tags(item))
    tags |= infer_tags_from_name(name)
    reasons: list[dict] = []
    for region in normalize_injury_regions(injuries):
        rules = INJURY_RULES.get(region, {})
        for risk_level in ("exclude", "flag"):
            if risk_level not in risk_levels:
                continue
            patterns = rules.get(f"{risk_level}_keywords", rules.get("ban_keywords", []) if risk_level == "exclude" else [])
            risk_tags = {t.lower() for t in rules.get(f"{risk_level}_tags", rules.get("ban_tags", []) if risk_level == "exclude" else [])}
            tag_hits = sorted(tags & risk_tags)
            field_hits: dict[str, list[str]] = {}
            matched_patterns: set[str] = set()
            if not tag_hits:
                for field_name, value in field_values.items():
                    matches = match_forbidden(value, patterns, allowlist=INJURY_MATCH_ALLOWLIST)
                    if matches:
                        field_hits[field_name] = matches
                        matched_patterns.update(matches)
            if field_hits or tag_hits:
                reasons.append(
                    {
                        "region": region,
                        "fields": sorted(field_hits),
                        "patterns": sorted(matched_patterns),
                        "tags": tag_hits,
                        "risk_level": risk_level,
                    }
                )
    return reasons


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
            explicit_tags = [t.lower() for t in item.get("tags", []) if t]
            normalized_tags = ensure_tags(item)
            inferred_tags = sorted(infer_tags_from_name(name))
            entries.append(
                {
                    "item_id": item_id,
                    "bank": bank_name,
                    "name": name,
                    "explicit_tags": explicit_tags or normalized_tags,
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
            tags = set(ensure_tags(item))
            tags |= infer_tags_from_name(name)
            for region, rule in INJURY_RULES.items():
                ban_keywords = rule.get("exclude_keywords", rule.get("ban_keywords", []))
                ban_tags = {t.lower() for t in rule.get("exclude_tags", rule.get("ban_tags", []))}
                if match_forbidden(name, ban_keywords, allowlist=INJURY_MATCH_ALLOWLIST) or tags & ban_tags:
                    exclusions[region].append(item_id)
    for region in exclusions:
        exclusions[region] = sorted(set(exclusions[region]))
    return exclusions


def audit_missing_tags() -> dict[str, int]:
    counts: dict[str, int] = {}
    total = 0
    for bank_name, items in collect_banks().items():
        missing = 0
        for item in items:
            raw_tags = [t for t in item.get("tags", []) if t]
            if not raw_tags:
                missing += 1
                total += 1
        counts[bank_name] = missing
    counts["total"] = total
    return counts


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
