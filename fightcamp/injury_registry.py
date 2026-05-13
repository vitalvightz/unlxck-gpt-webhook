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
