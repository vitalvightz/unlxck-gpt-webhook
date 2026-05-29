from __future__ import annotations

import re
from typing import Any

from .injury_formatting import parse_injury_entry

SPECIFIC_PARSER_TYPES = {
    "hyperextension",
    "sprain",
    "strain",
    "tendonitis",
    "impingement",
    "instability",
    "stiffness",
    "tightness",
    "swelling",
    "soreness",
    "pain",
    "contusion",
    "cut",
    "laceration",
    "abrasion",
    "graze",
    "blister",
}

SERIOUS_GUIDED_TYPES = {
    "fracture",
    "dislocation",
    "post_surgery",
}

SURFACE_TYPE_TO_INJURY_TYPE = {
    "bruise": "contusion",
    "cut": "cut",
    "laceration": "laceration",
    "abrasion": "abrasion",
    "graze": "graze",
    "blister": "blister",
    "skin_irritation": "abrasion",
}

ALLOWED_GUIDED_SUBTYPE_TOKENS = SPECIFIC_PARSER_TYPES | {"surface_injury"}
ALLOWED_GUIDED_SURFACE_SUBTYPE_TOKENS = set(SURFACE_TYPE_TO_INJURY_TYPE.keys())
VAGUE_GUIDED_TYPES = {"", "unspecified", "pain", "soreness", "tightness", "stiffness", "surface_injury"}

RUPTURE_EVIDENCE_PATTERN = re.compile(
    r"\b(?:rupture|ruptured|avulsion|detached|complete tear|full tear|confirmed tear|confirmed rupture)\b",
    re.IGNORECASE,
)
RUPTURE_NEGATION_PATTERN = re.compile(r"\b(?:no|not|without|denies)\s+(?:\w+\s+){0,3}?(?:rupture|tear|avulsion)\b", re.IGNORECASE)


def _normalize_guided_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _specific_parser_type(entry: dict[str, Any] | None) -> str:
    return str((entry or {}).get("injury_type") or "").strip().lower()


def _guided_primary_subtype(guided_injury: Any) -> tuple[str, str]:
    raw_subtypes = getattr(guided_injury, "injury_subtypes", None)
    if not isinstance(raw_subtypes, list):
        return "", ""

    normalized = [str(value).strip().lower() for value in raw_subtypes if str(value).strip()]
    if len(normalized) != 1:
        return "", ""

    token = normalized[0]
    if ":" in token:
        primary, secondary = token.split(":", 1)
        normalized_primary = primary.strip()
        normalized_secondary = secondary.strip()
        if (
            normalized_primary in ALLOWED_GUIDED_SUBTYPE_TOKENS
            and normalized_primary == "surface_injury"
            and normalized_secondary in ALLOWED_GUIDED_SURFACE_SUBTYPE_TOKENS
        ):
            return normalized_primary, normalized_secondary
        return "", ""
    return (token, "") if token in ALLOWED_GUIDED_SUBTYPE_TOKENS else ("", "")


def _has_rupture_evidence(text: str) -> bool:
    if not text:
        return False
    if RUPTURE_NEGATION_PATTERN.search(text):
        return False
    return bool(RUPTURE_EVIDENCE_PATTERN.search(text))


def _is_vague_guided_type(guided_type: str) -> bool:
    return guided_type in VAGUE_GUIDED_TYPES


def resolve_guided_injury_entry(guided_injury: Any, parsed_entry: dict[str, Any]) -> dict[str, Any]:
    area = str(getattr(guided_injury, "area", "") or "").strip()
    notes = str(getattr(guided_injury, "notes", "") or "").strip()
    avoid = str(getattr(guided_injury, "avoid", "") or "").strip()

    area_entry = parse_injury_entry(area) if area else None
    area_type = _specific_parser_type(area_entry)

    parser_entry = area_entry
    combined_text = " ".join(part for part in [area, notes] if part)
    combined_entry = None
    if not area_type or area_type == "unspecified":
        combined_entry = parse_injury_entry(combined_text) if combined_text else None
        parser_entry = combined_entry or area_entry

        combined_type = _specific_parser_type(combined_entry)
        if area_entry and combined_entry and combined_type and (combined_type != "unspecified" or not combined_entry.get("canonical_location")):
            parser_entry = dict(combined_entry)
            parser_entry["canonical_location"] = area_entry.get("canonical_location")
            parser_entry["side"] = area_entry.get("side")
            parser_entry["laterality"] = area_entry.get("laterality")
            # Use the user-facing area string here, not combined_text. Otherwise
            # internal notes (passed to the parser only to improve type detection)
            # leak into downstream surfaces like injuries_only_text.
            parser_entry["original_phrase"] = area

    parser_type = _specific_parser_type(parser_entry)
    parser_location = (parser_entry or {}).get("canonical_location")

    guided_type = _normalize_guided_value(getattr(guided_injury, "injury_type", ""))
    surface_type = _normalize_guided_value(getattr(guided_injury, "surface_type", ""))
    subtype_type, subtype_surface = _guided_primary_subtype(guided_injury)
    mapped_surface_type = SURFACE_TYPE_TO_INJURY_TYPE.get(surface_type)

    rupture_evidence_text = ". ".join(part for part in [area, notes, avoid] if part)

    if parser_type in SPECIFIC_PARSER_TYPES:
        final_type = parser_type
        source = "parser"
    elif mapped_surface_type:
        final_type = mapped_surface_type
        source = "surface_type"
    elif guided_type in SERIOUS_GUIDED_TYPES:
        final_type = guided_type
        source = "guided_serious_type"
    elif guided_type == "tendon_ligament":
        final_type = "tendon_rupture_or_avulsion" if _has_rupture_evidence(rupture_evidence_text) else "soft_tissue_joint_issue"
        source = "guided_tendon_ligament"
    elif (
        _is_vague_guided_type(guided_type)
        and subtype_type == "surface_injury"
        and subtype_surface
    ):
        mapped_subtype_surface = SURFACE_TYPE_TO_INJURY_TYPE.get(subtype_surface)
        if mapped_subtype_surface:
            final_type = mapped_subtype_surface
            source = "guided_subtype"
        else:
            final_type = _specific_parser_type(parsed_entry) or "unspecified"
            source = "fallback"
    elif (
        _is_vague_guided_type(guided_type)
        and subtype_type
        and subtype_type not in {"surface_injury", "unspecified"}
    ):
        final_type = subtype_type
        source = "guided_subtype"
    elif guided_type and guided_type not in {"unspecified", "surface_injury"}:
        final_type = guided_type
        source = "guided_type"
    else:
        final_type = _specific_parser_type(parsed_entry) or "unspecified"
        source = "fallback"

    resolved = dict(parsed_entry)
    resolved["injury_type"] = final_type

    if parser_location:
        resolved["canonical_location"] = parser_location
        parser_side = (parser_entry or {}).get("side")
        parser_laterality = (parser_entry or {}).get("laterality")
        if parser_side:
            resolved["side"] = parser_side
        if parser_laterality:
            resolved["laterality"] = parser_laterality

    resolved["injury_type_source"] = source
    resolved["parser_injury_type"] = parser_type or None
    resolved["guided_injury_type"] = guided_type or None
    resolved["guided_surface_type"] = surface_type or None

    if parser_entry and parser_entry.get("original_phrase"):
        resolved["original_phrase"] = parser_entry["original_phrase"]

    if not resolved.get("injury_type"):
        resolved["injury_type"] = "unspecified"

    return resolved
