from __future__ import annotations

from types import MappingProxyType

from .injury_taxonomy import INJURY_TAXONOMY, derive_injury_type_severity_map


def _normalize_injury_type(injury_type: str | None) -> str:
    return str(injury_type or "").strip().lower().replace("-", "_").replace(" ", "_")


ALL_INJURY_TYPES = frozenset(INJURY_TAXONOMY.keys())
REHAB_SAFE_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if bool(rule.get("rehab_allowed", True)))
REHAB_BLOCKED_TYPES = frozenset(ALL_INJURY_TYPES - REHAB_SAFE_TYPES)
URGENT_INJURY_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if bool(rule.get("urgent")))
CLINICAL_CLEARANCE_TYPES = frozenset(
    k for k, rule in INJURY_TAXONOMY.items() if bool(rule.get("requires_clinical_clearance"))
)
STRUCTURAL_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "structural")
SYMPTOM_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "symptom")
UNKNOWN_TYPES = frozenset(k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "unknown")
SURFACE_TISSUE_TYPES = frozenset(
    k for k, rule in INJURY_TAXONOMY.items() if str(rule.get("category") or "") == "surface"
)
INJURY_TYPE_SEVERITY = MappingProxyType(derive_injury_type_severity_map())

# Surface *skin* injuries that train through as skin-level damage. Every member is
# a canonical taxonomy type with category="surface" (so ``_is_surface_type`` is
# True), which lets the rehab formatter collapse them to a single calm note
# instead of a wound-care drill list. ``cut``/``laceration`` are deliberately
# absent — they carry deep-wound/stitch risk and keep the detailed wound-care
# path. "scrape" is not here because it is not a canonical type: the parser
# canonicalizes scrapes to ``abrasion``. Bruises/contusions are also absent —
# they are soft-tissue, not skin wounds, and train through via normal full-plan
# routing and low-severity injury-guard handling instead.
MINOR_SURFACE_TRAIN_THROUGH_TYPES = frozenset(
    {"graze", "abrasion", "blister"}
)

# Calm, coach-facing note for a minor surface (skin) injury that trains through.
# This is deliberately NOT medical-panic language: it treats the athlete as fit
# to train and only asks for basic wound hygiene. Surfaced once by the rehab
# formatter in place of a wound-care drill list, not repeated per drill.
SURFACE_MINOR_TRAIN_THROUGH_NOTE = (
    "Minor surface injury: keep it covered and clean, avoid direct friction on the "
    "area, and stop if it opens, bleeds, or becomes infected. Train normally otherwise."
)


def is_known_injury_type(injury_type: str | None) -> bool:
    return _normalize_injury_type(injury_type) in ALL_INJURY_TYPES


def is_rehab_safe_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in REHAB_SAFE_TYPES


def is_rehab_blocked_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in REHAB_BLOCKED_TYPES


def is_urgent_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in URGENT_INJURY_TYPES


def requires_clinical_clearance_type(injury_type: str | None) -> bool:
    normalized = _normalize_injury_type(injury_type)
    return normalized in CLINICAL_CLEARANCE_TYPES


def get_registry_category(injury_type: str | None) -> str:
    rule = INJURY_TAXONOMY.get(_normalize_injury_type(injury_type)) or INJURY_TAXONOMY["unspecified"]
    return str(rule.get("category") or "unknown")


def get_registry_default_severity(injury_type: str | None) -> str:
    rule = INJURY_TAXONOMY.get(_normalize_injury_type(injury_type)) or INJURY_TAXONOMY["unspecified"]
    return str(rule.get("default_severity") or "moderate")
