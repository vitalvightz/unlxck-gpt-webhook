"""Read-only source catalogue. Discovery never grants training permission.

No planner imports this adapter. Raw fields are not normalised by runtime bank
loaders, which may infer tags/defaults unsuitable as search evidence.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from .config import DATA_DIR
from .exercise_identity import normalize_exercise_key
from .injury_registry import SURFACE_TISSUE_TYPES
from .sports import SUPPORTED_SPORTS

# Explicit live inventory shared with the #2816 audit; never glob archives.
SOURCE_CLASSES = {
    "exercise_bank.json": "strength_power",
    "conditioning_bank.json": "conditioning",
    "style_conditioning_bank.json": "conditioning",
    "style_taper_conditioning.json": "conditioning",
    "technical_footwork_bank.json": "technical_coordination",
    "coordination_bank.json": "technical_coordination",
    **{f"coordination/{name}.json": "technical_coordination" for name in (
        "universal", "striking", "kicks", "mma_transitions", "grappling",
    )},
    "rehab_bank.json": "rehabilitation",
    "tactical_watch_bank.json": "tactical_educational",
    "fight_visualization_bank.json": "visualisation",
}
MANIFEST_FILE = "training_catalogue_ids.json"
ALIASES_FILE = "training_catalogue_aliases.json"
PHYSICAL_CLASSES = frozenset({"strength_power", "conditioning", "technical_coordination"})
UNKNOWN_VALUES = frozenset({"unknown", "unreviewed", "unspecified"})
SEARCH_FIELDS = (
    "name", "description", "notes", "cue", "instructions", "why", "pro_tip",
    "combat_carryover", "category", "tags", "sports", "equipment", "movement",
    "qualities", "goals", "weaknesses", "method", "system", "modality",
    "function", "tactical_function", "body_region", "target_regions",
)
METADATA_FIELDS = tuple(dict.fromkeys((*SEARCH_FIELDS,
    "difficulty", "phases", "styles", "tactical_styles", "sport_specific",
    "contraindications", "avoid_if", "mechanical_risk_tags", "rehab_stage",
    "allowed_severities", "pain_ceiling", "dose", "progress_when",
    "regress_when", "stop_when", "quality_stop_rule", "contact_level",
    "late_windows", "block_if_fight_within_days", "cut_buckets_allowed",
)))
VALIDATION_AUTHORITIES = {
    "training": [
        "fightcamp.injury_guard.injury_decision",
        "fightcamp.strength", "fightcamp.conditioning",
        "fightcamp.coordination_support_library",
    ],
    "rehabilitation": [
        "fightcamp.rehab_clinical.validate_clinical_bank",
        "fightcamp.rehab_selector.filter_rehab_candidates",
        "api.contracts.injury_policy",
    ],
}


def content_hash(value: object) -> str:
    """Row binding, NOT its permanent identity. Match regardless of JSON layout."""
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    ).encode()).hexdigest()


def source_hash(raw: bytes) -> str:
    """Source revision with CRLF normalised to LF, independent of Git checkout.

    Preserve all other bytes. This is not a raw on-disk byte digest; row bindings
    still use canonical JSON content hashes independently of source formatting.
    """
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def metadata_state(row: dict, field: str) -> str:
    """Do not confuse absent/null/unknown with explicit empty/no equipment."""
    if field not in row:
        return "absent"
    value = row[field]
    if value is None:
        return "null"
    if value == []:
        return "known" if field == "equipment" else "empty"
    if value == {} or (isinstance(value, str) and not value.strip()):
        return "empty"
    values = strings(value)
    unknown = [v for v in values if v.casefold() in UNKNOWN_VALUES]
    if unknown:
        return "unknown" if len(unknown) == len(values) else "ambiguous"
    if field == "equipment" and (
        not values or not isinstance(value, (str, list))
        or (isinstance(value, list) and len(values) != len(value))
    ):
        return "ambiguous"
    return "known"


def iter_source_rows(source: str, payload: Any) -> Iterator[tuple[dict, dict | None, str]]:
    """Pointers describe current provenance only; never use them as identity."""
    if source == "rehab_bank.json":
        for group_index, group in enumerate(payload):
            context = {key: value for key, value in group.items() if key != "drills"}
            for drill_index, row in enumerate(group["drills"]):
                yield row, context, f"/{group_index}/drills/{drill_index}"
        return
    if source == "coordination_bank.json" and isinstance(payload, dict):
        for key, rows in payload.items():
            if isinstance(rows, list):
                escaped = key.replace("~", "~0").replace("/", "~1")
                for index, row in enumerate(rows):
                    yield row, None, f"/{escaped}/{index}"
        return
    if not isinstance(payload, list):
        raise ValueError(f"Unexpected bank shape: {source}")
    for index, row in enumerate(payload):
        yield row, None, f"/{index}"


def classify(source: str, group: dict | None) -> str:
    if source == "rehab_bank.json" and (group or {}).get("type") in SURFACE_TISSUE_TYPES:
        return "care_instruction"
    return SOURCE_CLASSES[source]


def selection_boundary(content_class: str, has_identity: bool) -> dict:
    physical = content_class in PHYSICAL_CLASSES
    if not has_identity:
        boundary, reason = "excluded", "missing_stable_identity"
    elif physical:
        boundary, reason = "training_validation_required", "athlete_context_not_evaluated"
    elif content_class == "rehabilitation":
        boundary, reason = "rehab_pathway_only", "pathway_stage_and_clearance_required"
    else:
        boundary, reason = "excluded", "non_workout_content"
    return {
        "physical_candidate": physical and has_identity,
        "normal_workout_candidate": physical and has_identity,
        "prescription_allowed": False,
        "boundary": boundary, "reason": reason,
        "validation_authorities": deepcopy(VALIDATION_AUTHORITIES.get(
            "training" if physical else content_class, [],
        )),
    }


def search_aliases(entry: dict, rules: dict) -> list[dict]:
    """Exact reviewed tokens and explicit entry overrides, never name heuristics."""
    if entry["content_class"] not in PHYSICAL_CLASSES:
        return []
    aliases = []
    for rule in rules["token_aliases"]:
        field = rule["field"]
        if entry["metadata"][field]["state"] != "known":
            continue
        if rule["token"] in strings(entry["raw"].get(field)):
            aliases.append({"label": rule["label"], "evidence": {
                "field": field, "token": rule["token"],
                "source": entry["source"], "row_sha256": entry["row_sha256"],
                "rules_source": ALIASES_FILE, "rationale": rule["rationale"],
            }})
    override = rules["entry_aliases"].get(entry["catalogue_id"])
    if override and override["row_sha256"] == entry["row_sha256"]:
        aliases.append({"label": override["label"], "evidence": {
            "source": entry["source"], "row_sha256": entry["row_sha256"],
            "rules_source": ALIASES_FILE, "rationale": override["rationale"],
        }})
    return aliases


def build_catalogue(data_dir: Path = DATA_DIR, *, strict: bool = True) -> list[dict]:
    """Fresh owned records; no mutation of cached planner data or source banks.

    Strict mode fails on identity drift. Report mode accounts for unresolved rows
    with no permission to select them. IDs are explicitly pinned in the manifest.
    """
    manifest = json.loads((data_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    rules = json.loads((data_dir / ALIASES_FILE).read_text(encoding="utf-8"))
    if manifest["schema_version"] != 1 or rules["schema_version"] != 1:
        raise ValueError("Unsupported catalogue manifest/alias schema")
    entries, used_bindings = [], set()
    for source in SOURCE_CLASSES:
        raw_bytes = (data_dir / source).read_bytes()
        source_sha = source_hash(raw_bytes)
        for row, group, pointer in iter_source_rows(source, json.loads(raw_bytes)):
            if not isinstance(row, dict) or not strings(row.get("name")):
                raise ValueError(f"Unnamed or malformed catalogue row: {source}{pointer}")
            row_sha = content_hash(row)
            explicit_field = next((field for field in ("id", "key") if strings(row.get(field))), None)
            binding = manifest["sources"].get(source, {}).get(row_sha)
            local_id = row[explicit_field] if explicit_field else (binding or {}).get("id")
            if binding and not explicit_field:
                used_bindings.add((source, row_sha))
            if not isinstance(local_id, str) or not local_id.strip():
                local_id = None
                if strict:
                    raise ValueError(f"Missing stable identity: {source}{pointer}; review manifest binding")
            entry = {
                "catalogue_id": f"{source}:{local_id}" if local_id else None,
                "source_id": local_id,
                "identity_origin": explicit_field or ("manifest" if local_id else "missing"),
                "source": source, "source_sha256": source_sha, "row_sha256": row_sha,
                "source_pointer": pointer, "name": row["name"],
                "content_class": classify(source, group),
                "classification_provenance": {"source": source, "group": group},
                "raw": deepcopy(row), "raw_group": deepcopy(group),
                "metadata": {field: {
                    "state": metadata_state(row, field),
                    **({"value": deepcopy(row[field]), "provenance": {
                        "source": source, "source_sha256": source_sha,
                        "row_sha256": row_sha, "pointer": f"{pointer}/{field}",
                    }} if field in row else {}),
                } for field in dict.fromkeys((*METADATA_FIELDS, *row))},
            }
            entry["eligibility"] = selection_boundary(entry["content_class"], bool(local_id))
            entry["exercise_key"] = (
                normalize_exercise_key(row["name"])
                if entry["content_class"] in PHYSICAL_CLASSES else None
            )
            entry["aliases"] = search_aliases(entry, rules)
            # Every indexed piece retains the original field and its evidence.
            entry["search_evidence"] = [
                {"text": text, "field": field, "provenance": entry["metadata"][field]["provenance"]}
                for field in SEARCH_FIELDS if entry["metadata"][field]["state"] == "known"
                for text in strings(row.get(field))
            ]
            sport_evidence = [
                {"value": sport, "field": field, "provenance": entry["metadata"][field]["provenance"]}
                for field in ("sports", "tags") if entry["metadata"][field]["state"] == "known"
                for sport in strings(row.get(field))
                if sport in SUPPORTED_SPORTS or (field == "sports" and sport == "universal")
            ]
            entry["sport_evidence"] = sport_evidence
            entries.append(entry)
    counts = Counter(entry["catalogue_id"] for entry in entries if entry["catalogue_id"])
    if any(count > 1 for count in counts.values()):
        raise ValueError("Ambiguous stable catalogue identity; never merge duplicate rows")
    expected_bindings = {(source, digest) for source, rows in manifest["sources"].items() for digest in rows}
    if strict and expected_bindings != used_bindings:
        raise ValueError("Stale catalogue manifest bindings; review changed or removed rows")
    return sorted(entries, key=lambda entry: (entry["source"], entry["catalogue_id"] or entry["source_pointer"]))
