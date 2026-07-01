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

# Flag markers that pull a surface injury back onto the existing danger gates
# (infection, uncontrolled bleeding, needs-review, worsening, clinical clearance,
# any red flag). If a parsed surface injury carries one of these, it is NOT a
# train-through skin constraint and must keep its normal urgent/red-flag routing.
_SURFACE_TRAIN_THROUGH_RED_FLAG_MARKERS = (
    "red_flag",
    "urgent",
    "review",
    "clearance",
    "infection",
    "infected",
    "suspected",
    "bleed",
    "stitch",
    "worsen",
)


def is_stable_train_through_surface_injury(injury: dict | None) -> bool:
    """True for a stable, non-severe surface (skin) injury that should train through.

    A graze/abrasion/blister that is not high severity and carries no red-flag
    signal is a skin/friction *hygiene* constraint — not injured tissue. Such an
    injury must not drive rehab drills, anatomical exercise/region blocking, or
    hard-work suppression; it surfaces only as a single hygiene/friction note.

    Returns False (so existing danger gates stay unchanged) for anything that is
    not a minor surface type — including cut/laceration (deep-wound/stitch risk)
    and infection — any high/severe surface injury, or an injury carrying a
    red-flag / needs-review / clearance / bleeding / worsening flag.
    """
    if not isinstance(injury, dict):
        return False
    injury_type = _normalize_injury_type(injury.get("injury_type") or injury.get("rehab_type"))
    if injury_type not in MINOR_SURFACE_TRAIN_THROUGH_TYPES:
        return False
    severity = str(injury.get("severity") or "").strip().lower()
    if severity in {"high", "severe"}:
        return False
    flags = injury.get("flags")
    if isinstance(flags, str):
        flags = [flags]
    elif not isinstance(flags, (list, tuple, set)) and flags is not None:
        return False
    for flag in flags or []:
        token = str(flag or "").strip().lower()
        if token and any(marker in token for marker in _SURFACE_TRAIN_THROUGH_RED_FLAG_MARKERS):
            return False
    return True


def all_stable_train_through_surface(parsed_injuries) -> bool:
    """True when there is ≥1 parsed injury and every one is a stable, train-through
    surface (skin) injury.

    Used by callers that must decide whether the athlete's *entire* injury picture
    is skin/friction hygiene (no rehab, no load suppression). Requires a non-empty
    list of dicts; a missing, empty, or malformed list returns False so the caller
    keeps normal active-injury handling. A real injury alongside a graze fails this
    check (not every entry qualifies).
    """
    items = list(parsed_injuries or [])
    if not items or not all(isinstance(item, dict) for item in items):
        return False
    return all(is_stable_train_through_surface_injury(item) for item in items)


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
