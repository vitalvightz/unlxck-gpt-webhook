from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable

from .injury_exclusion_rules import INJURY_REGION_KEYWORDS, INJURY_RULES
from .injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
from .bank_schema import validate_training_item
from .tagging import normalize_item_tags, normalize_tags

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
INJURY_MATCH_ALLOWLIST: list[str] = [
    "pressure fighter",
    "pressure cooker",
    "sandbox jumper",
    "ship hinge",
    "stomach ache",
]
GENERIC_SINGLE_WORD_PATTERNS = {"press", "overhead", "bench"}
MAX_VELOCITY_EXCLUDE_KEYWORDS = [
    "assault bike",
    "echo bike",
    "air bike",
    "rower",
    "ski erg",
    "ski-erg",
    "battle rope",
    "rope wave",
]
MAX_VELOCITY_RUNNING_KEYWORDS = [
    "sprint",
    "sprints",
    "sprint start",
    "acceleration",
    "accelerations",
    "hill sprint",
    "treadmill sprint",
    "10m",
    "20m",
    "30m",
    "track",
    "shuttle sprint",
    "shuttle run",
]

INFERRED_TAG_RULES = [
    {"keywords": ["bench press", "floor press"], "tags": ["upper_push", "horizontal_push", "press_heavy"]},
    {
        "keywords": ["overhead press", "push press", "strict press", "military press"],
        "tags": ["overhead", "upper_push", "dynamic_overhead", "press_heavy"],
    },
    {"keywords": ["snatch", "jerk"], "tags": ["overhead", "shoulder_heavy", "dynamic_overhead"]},
    {
        "keywords": ["ring dip", "bench dip", "parallel bar dip", "bar dip", "dip"],
        "tags": ["upper_push", "elbow_extension_heavy", "dip_loaded"],
    },
    {"keywords": ["handstand"], "tags": ["overhead", "wrist_loaded_extension"]},
    {"keywords": ["push-up", "pushup"], "tags": ["upper_push", "wrist_loaded_extension"]},
    {"keywords": ["front rack"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {"keywords": ["clean"], "tags": ["front_rack", "wrist_loaded_extension"]},
    {
        "keywords": ["deadlift", "rdl", "good morning", "jefferson curl"],
        "tags": ["hinge_heavy", "axial_heavy", "lumbar_loaded", "posterior_chain_heavy"],
    },
    {"keywords": ["back squat", "front squat", "heavy squat"], "tags": ["knee_dominant_heavy", "axial_heavy"]},
    {"keywords": ["deep squat", "pistol", "cossack"], "tags": ["deep_flexion", "hip_irritant"]},
    {"keywords": ["lateral lunge", "adductor"], "tags": ["adductor_load_high"]},
    {"keywords": ["nordic", "ham curl"], "tags": ["hamstring_eccentric_high"]},
    {"keywords": ["sprint", "sprints", "max sprint", "acceleration", "accelerations"], "tags": ["max_velocity"]},
    {
        "keywords": ["jump", "plyo", "depth jump", "drop jump", "bounds", "hops", "pogo"],
        "tags": [
            "high_impact_plyo",
            "landing_stress_high",
            "reactive_rebound_high",
            "calf_rebound_high",
            "forefoot_load_high",
            "toe_extension_high",
        ],
    },
    {"keywords": ["jump rope"], "tags": ["impact_rebound_high", "foot_impact_high"]},
    {"keywords": ["bear crawl"], "tags": ["wrist_loaded_extension"]},
    {
        "keywords": ["rope climb", "towel", "thick grip", "plate pinch", "farmer", "dead hang"],
        "tags": ["grip_max", "hand_crush", "pinch_grip_high"],
    },
    {"keywords": ["bridges", "wrestler bridge"], "tags": ["neck_loaded"]},
    {"keywords": ["lateral bounds", "hard cuts"], "tags": ["ankle_lateral_impact_high"]},
    {"keywords": ["barefoot sprint"], "tags": ["foot_impact_high"]},
    {"keywords": ["contact", "sparring"], "tags": ["contact"]},
    {"keywords": ["carry", "yoke", "farmer", "suitcase carry"], "tags": ["carry_heavy"]},
    {"keywords": ["row", "seal row", "t bar row", "t-bar row", "meadows row"], "tags": ["row_heavy", "upper_back_loaded"]},
    {"keywords": ["back extension", "reverse hyper", "reverse hyperextension"], "tags": ["spine_extension_loaded", "lumbar_loaded"]},
    {"keywords": ["jefferson curl"], "tags": ["spine_flexion_loaded", "lumbar_loaded"]},
    {
        "keywords": ["run", "running", "roadwork", "jog", "treadmill"],
        "tags": ["running_volume_high", "shin_splints_risk", "calf_volume_high"],
    },
    {
        "keywords": ["agility", "shuffle", "change of direction", "cut", "decel", "deceleration"],
        "tags": ["cod_high", "decel_high"],
    },
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

INJURY_TAG_ALIASES = {
    "adductors": {"long_lever_adductor", "wide_stance_adductor_high"},
    "aerobic": set(),
    "agility": {"cod_high", "decel_high"},
    "boxing": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "clinch": {"contact", "sparring", "head_impact", "striking_contact"},
    "core": {"hip_flexion_loaded", "hip_flexor_strain_risk"},
    "deadlift": {"posterior_chain_heavy", "lumbar_loaded"},
    "endurance": set(),
    "explosive": {"explosive_upper_push"},
    "grappling": {"contact", "sparring", "head_impact"},
    "grip": {
        "finger_flexor_high",
        "forearm_load_high",
        "wrist_flexor_high",
        "wrist_compression_high",
        "finger_load_high",
        "pinch_grip_high",
    },
    "hamstring": {"posterior_chain_eccentric_high"},
    "high_cns": set(),
    "hip_dominant": {
        "hip_impingement_risk",
        "hip_internal_rotation_stress",
        "hip_extension_heavy",
        "glute_load_high",
        "pelvic_shear_risk",
    },
    "kickboxing": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "lateral": {"cod_high", "decel_high"},
    "mma": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "muay_thai": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "neck": {"cervical_load", "cervical_extension_loaded", "cervical_flexion_loaded", "neck_bridge"},
    "overhead": {"dynamic_overhead", "press_heavy", "wrist_extension_high"},
    "plyometric": {"landing_stress_high", "reactive_rebound_high", "achilles_high_risk_impact", "forefoot_load_high"},
    "posterior_chain": {"posterior_chain_heavy", "lumbar_loaded", "glute_load_high", "hip_extension_heavy"},
    "pull": {"row_heavy", "deep_elbow_flexion_loaded"},
    "push": {"press_heavy", "pec_loaded", "explosive_upper_push", "wrist_extension_high"},
    "quad_dominant": {"quad_dominant_heavy", "deep_knee_flexion_loaded"},
    "reactive": {"reactive_rebound_high", "achilles_high_risk_impact", "forefoot_load_high"},
    "shoulders": {"press_heavy", "dynamic_overhead"},
    "speed": {"max_velocity", "decel_high"},
    "striking": {"contact", "sparring", "head_impact", "striking_contact", "hard_contact", "live_rounds"},
    "triceps": {"triceps_tendon_heavy"},
    "unilateral": {"asym_load_high"},
    "upper_back": {"upper_back_loaded"},
    "upper_body": {"pec_loaded"},
    "wrestling": {"contact", "sparring", "head_impact"},
}

logger = logging.getLogger(__name__)


def expand_injury_tags(tags: Iterable[str]) -> set[str]:
    expanded: set[str] = set()
    for tag in tags:
        expanded.update(INJURY_TAG_ALIASES.get(tag, ()))
    return expanded


def _normalize_text(text: str) -> str:
    cleaned = text.lower().replace("-", " ").replace("_", " ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return " ".join(cleaned.split())


def _phrase_in_tokens(text: str, phrase_tokens: list[str]) -> bool:
    if not phrase_tokens:
        return False
    phrase_pattern = r"\b" + r"\s+".join(re.escape(token) for token in phrase_tokens) + r"\b"
    return re.search(phrase_pattern, text) is not None


def match_forbidden(text: str, patterns: Iterable[str], *, allowlist: Iterable[str] | None = None) -> list[str]:
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return []
    allowlist = allowlist or []
    for phrase in allowlist:
        phrase_tokens = _normalize_text(phrase).split()
        if phrase_tokens and _phrase_in_tokens(normalized_text, phrase_tokens):
            return []
    matches: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        normalized_pattern = _normalize_text(pattern)
        if not normalized_pattern:
            continue
        phrase_tokens = normalized_pattern.split()
        if len(phrase_tokens) == 1 and phrase_tokens[0] in GENERIC_SINGLE_WORD_PATTERNS:
            continue
        if _phrase_in_tokens(normalized_text, phrase_tokens):
            if pattern not in seen:
                matches.append(pattern)
                seen.add(pattern)
    return matches


def _infer_item_module(item: dict) -> str:
    if item.get("bank_type"):
        return str(item["bank_type"])
    if item.get("system") or item.get("modality") or item.get("placement") == "conditioning":
        return "conditioning"
    return "strength"


def infer_tags_from_name(name: str) -> set[str]:
    inferred: set[str] = set()
    for rule in INFERRED_TAG_RULES:
        if match_forbidden(name, rule["keywords"], allowlist=INJURY_MATCH_ALLOWLIST):
            if "max_velocity" in rule["tags"] and not _should_apply_max_velocity(name):
                continue
            inferred.update(rule["tags"])
    return {t for t in normalize_tags(inferred) if t}


def _should_apply_max_velocity(name: str) -> bool:
    if match_forbidden(name, MAX_VELOCITY_EXCLUDE_KEYWORDS, allowlist=INJURY_MATCH_ALLOWLIST):
        return False
    return bool(match_forbidden(name, MAX_VELOCITY_RUNNING_KEYWORDS, allowlist=INJURY_MATCH_ALLOWLIST))


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
    return {tag for tag in normalize_tags(tags) if tag}


def ensure_tags(item: dict) -> list[str]:
    raw_tags = normalize_tags([t for t in item.get("tags", []) if t])
    if raw_tags:
        item["tags"] = raw_tags
        return raw_tags
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
        non_negated_phrases: list[str] = []
        for phrase in split_injury_text(injury):
            cleaned = remove_negated_phrases(phrase)
            if not cleaned:
                continue
            non_negated_phrases.append(phrase)
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
        if not matched and non_negated_phrases:
            for phrase in non_negated_phrases:
                region = _map_text_to_region(phrase)
                if region:
                    regions.add(region)
                    matched = True
                    break
        if not matched and non_negated_phrases:
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
    module: str | None = None,
) -> list[dict]:
    if not injuries:
        return []
    fields = ("name",)
    risk_levels = set(risk_levels or ("exclude",))
    field_values = {"name": str(item.get("name", "") or "")}
    name = field_values["name"]
    item_module = _infer_item_module(item)
    if module and module != item_module:
        return []
    tags = set(ensure_tags(item))
    tags |= infer_tags_from_name(name)
    tags |= expand_injury_tags(tags)
    if "low_impact" in tags:
        tags.discard("running_volume_high")
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
    paths = [
        DATA_DIR / "style_specific_exercises.json",
        DATA_DIR / "style_specific_exercises",
    ]
    for path in paths:
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(
                "style_specific_exercises JSON error in "
                f"{path}: line {exc.lineno} column {exc.colno} ({exc.msg})"
            ) from exc
        if not isinstance(items, list):
            raise ValueError(
                "style_specific_exercises must be a JSON list of exercise objects. "
                f"Check {path}."
            )
        for item in items:
            validate_training_item(item, source=str(path), require_phases=True)
            normalize_item_tags(item)
        return items
    logger.warning(
        "[bank] style_specific_exercises missing. Add data/style_specific_exercises.json "
        "or data/style_specific_exercises to enable style-specific lifts."
    )
    return []


def _load_bank_items(filename: str) -> list[dict]:
    items = json.loads((DATA_DIR / filename).read_text())
    for item in items:
        validate_training_item(item, source=filename, require_phases=True)
        normalize_item_tags(item)
    return items


def collect_banks() -> dict[str, list[dict]]:
    banks: dict[str, list[dict]] = {}
    banks["exercise_bank"] = _load_bank_items("exercise_bank.json")
    banks["conditioning_bank"] = _load_bank_items("conditioning_bank.json")
    banks["style_conditioning_bank"] = _load_bank_items("style_conditioning_bank.json")
    banks["universal_gpp_strength"] = _load_bank_items("universal_gpp_strength.json")
    banks["universal_gpp_conditioning"] = _load_bank_items("universal_gpp_conditioning.json")
    banks["style_taper_conditioning"] = _load_bank_items("style_taper_conditioning.json")
    banks["style_specific_exercises"] = _load_style_specific_exercises()

    coord_data = json.loads((DATA_DIR / "coordination_bank.json").read_text())
    coordination_bank: list[dict] = []
    if isinstance(coord_data, list):
        for item in coord_data:
            validate_training_item(item, source="coordination_bank.json", require_phases=True)
            normalize_item_tags(item)
            coordination_bank.append(item)
    elif isinstance(coord_data, dict):
        for val in coord_data.values():
            if isinstance(val, list):
                for item in val:
                    validate_training_item(item, source="coordination_bank.json", require_phases=True)
                    normalize_item_tags(item)
                    coordination_bank.append(item)
    banks["coordination_bank"] = coordination_bank

    return banks


def build_bank_inferred_tags() -> list[dict]:
    entries: list[dict] = []
    for bank_name, items in collect_banks().items():
        for item in items:
            name = item.get("name", "")
            item_id = f"{bank_name}:{name}"
            explicit_tags = normalize_tags(item.get("tags", []))
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
            tags |= expand_injury_tags(tags)
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
    logger.info("[injury-debug] %s normalized_injuries=%s", label, normalized)
    for item in items:
        name = item.get("name", "Unnamed")
        reasons = injury_violation_reasons(item, injuries)
        if reasons:
            logger.info(
                "[injury-debug] %s item=%s allowed=False reasons=%s",
                label,
                name,
                reasons,
            )
        else:
            logger.info("[injury-debug] %s item=%s allowed=True", label, name)
