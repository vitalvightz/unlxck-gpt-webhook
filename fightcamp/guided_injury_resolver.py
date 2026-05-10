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
}

RUPTURE_EVIDENCE_PATTERN = re.compile(
    r"\b(?:rupture|ruptured|avulsion|detached|complete tear|full tear|confirmed tear|confirmed rupture|deformity|cannot bear weight|cannot walk)\b",
    re.IGNORECASE,
)


def _normalize_guided_value(value: Any) -> str:
    return str(value or "").strip().lower()


def resolve_guided_injury_entry(guided_injury: Any, parsed_entry: dict[str, Any]) -> dict[str, Any]:
    area = str(getattr(guided_injury, "area", "") or "").strip()
    notes = str(getattr(guided_injury, "notes", "") or "").strip()
    avoid = str(getattr(guided_injury, "avoid", "") or "").strip()

    injury_evidence_text = ". ".join(part for part in [area, notes] if part)
    rupture_evidence_text = ". ".join(part for part in [injury_evidence_text, avoid] if part)

    parser_entry = parse_injury_entry(injury_evidence_text) if injury_evidence_text else None
    parser_type = str((parser_entry or {}).get("injury_type") or "").strip().lower()
    parser_location = (parser_entry or {}).get("canonical_location")

    guided_type = _normalize_guided_value(getattr(guided_injury, "injury_type", ""))
    surface_type = _normalize_guided_value(getattr(guided_injury, "surface_type", ""))
    mapped_surface_type = SURFACE_TYPE_TO_INJURY_TYPE.get(surface_type)

    final_type = ""
    source = "fallback"

    if parser_type and parser_type != "unspecified":
        final_type = parser_type
        source = "parser"
    elif mapped_surface_type:
        final_type = mapped_surface_type
        source = "surface_type"
    elif guided_type in SERIOUS_GUIDED_TYPES:
        final_type = guided_type
        source = "guided_serious_type"
    elif guided_type == "tendon_ligament":
        if RUPTURE_EVIDENCE_PATTERN.search(rupture_evidence_text):
            final_type = "tendon_rupture_or_avulsion"
        else:
            final_type = "soft_tissue_joint_issue"
        source = "guided_tendon_ligament"
    elif guided_type and guided_type not in {"unspecified", "surface_injury"}:
        final_type = guided_type
        source = "guided_type"
    else:
        final_type = str(parsed_entry.get("injury_type") or "unspecified").strip().lower() or "unspecified"
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

    if final_type not in SPECIFIC_PARSER_TYPES and source == "parser":
        # parser still has precedence for any explicit parse result
        resolved["injury_type_source"] = "parser"

    if not resolved.get("injury_type"):
        resolved["injury_type"] = "unspecified"

    return resolved
