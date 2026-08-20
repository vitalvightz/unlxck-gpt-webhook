"""Formal data contract for ``data/rehab_bank.json``.

This module is the single source of truth for the rehab bank's *shape*: the
finite value sets a drill may declare, the sentinel that marks a field as not
yet migrated, and the small helpers that read those fields back. It owns no
injury taxonomy and no location registry of its own — recognised injury types
come from :mod:`fightcamp.injury_taxonomy` (via :mod:`fightcamp.injury_registry`)
and recognised locations from the parser vocabulary plus
:mod:`fightcamp.injury_location_registry`.

Bank layout
-----------
Location and injury-type ownership stays where the bank already puts it: on the
*group* record. A drill never repeats them::

    {
      "location": "ankle",
      "type": "sprain",
      "phase_progression": "GPP -> SPP",
      "drills": [ {...}, {...} ]
    }

Migrated vs. unrestricted
-------------------------
Every contract field distinguishes "nobody has filled this in yet" from "this
was deliberately left open":

* ``None`` (JSON ``null``) always means **not migrated yet**. It is the
  deterministic incompleteness marker; :func:`unmigrated_fields` enumerates it.
* Any other value is authoritative, including the deliberately-open ones:
  ``[]`` for ``equipment`` (needs nothing) and for the
  ``progress_when``/``regress_when``/``stop_when`` rule lists (no criteria),
  ``"none"`` for ``impact``, and :data:`PAIN_CEILING_UNRESTRICTED` for
  ``pain_ceiling`` (no ceiling applies).

Scope note (PR1)
----------------
These are data contracts only. Nothing here participates in rehab exercise
selection; :func:`resolve_drill_function` is the one reader wired into runtime,
and it reproduces the legacy keyword classifier for every drill in the bank.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .injury_registry import REHAB_SAFE_TYPES, SURFACE_TISSUE_TYPES
from .injury_location_registry import LOCATION_REGISTRY
from .phases import PHASE_VALUES

# ---------------------------------------------------------------------------
# Finite value sets
# ---------------------------------------------------------------------------

#: Rehabilitation stages. Ordered from most protective to most demanding.
REHAB_STAGES: tuple[str, ...] = ("calm", "restore", "load", "dynamic", "return")

#: The six drill function classes. ``REHAB_FUNCTION_BUCKETS`` in
#: :mod:`fightcamp.rehab_protocols` keys its keyword lists by exactly these.
REHAB_FUNCTIONS: tuple[str, ...] = (
    "activation",
    "control",
    "isometric_analgesia",
    "mobility",
    "tendon_loading",
    "recovery_downregulation",
)

#: Physical-demand levels. ``"unknown"`` is a first-class value, not a gap: it
#: means the level was looked at and could not be defensibly stated, which is a
#: different fact from ``None`` (nobody has looked yet). Both are honest, and
#: neither may ever be read as a low-demand claim — an exposure carrying an
#: unknown level is valid observational evidence but is explicitly NOT positive
#: evidence for LOAD/DYNAMIC/RETURN qualification.
IMPACT_VALUES: tuple[str, ...] = ("unknown", "none", "low", "moderate", "high")
LOAD_VALUES: tuple[str, ...] = ("unknown", "minimal", "low", "moderate", "high")
VELOCITY_VALUES: tuple[str, ...] = ("unknown", "low", "moderate", "high")
LATERALITY_APPLICABILITY_VALUES: tuple[str, ...] = (
    "side_specific",
    "bilateral_only",
    "not_applicable",
    "unknown",
)
CONTRACTION_TYPE_VALUES: tuple[str, ...] = (
    "isometric",
    "concentric",
    "eccentric",
    "mixed",
    "unknown",
)
SPORT_SPECIFICITY_VALUES: tuple[str, ...] = ("general_rehab", "combat_sport", "unknown")
CONTACT_LEVEL_VALUES: tuple[str, ...] = ("none", "controlled", "full", "unknown")

#: Injury severities a drill may be gated on. This module owns the buckets and
#: the collapse; ``rehab_protocols._normalize_rehab_severity`` and the rehab
#: selector both read :func:`normalize_severity_bucket` rather than keeping a second
#: vocabulary of their own.
SEVERITY_VALUES: tuple[str, ...] = ("low", "moderate", "high")

#: Intake wording that maps onto a bank severity bucket. Intake collects an
#: athlete-facing word; the bank gates on a bucket. This is the one place the
#: two vocabularies meet.
SEVERITY_ALIASES: dict[str, str] = {
    "mild": "low",
    "low": "low",
    "moderate": "moderate",
    "high": "high",
    "severe": "high",
}

#: Structured dose slots. All three are optional *within* a migrated dose.
DOSE_FIELDS: tuple[str, ...] = ("sets", "reps", "duration_seconds")

#: ``pain_ceiling`` value meaning "deliberately no ceiling", as opposed to
#: ``None`` which means "not migrated yet".
PAIN_CEILING_UNRESTRICTED = "unrestricted"
PAIN_CEILING_MIN = 0
PAIN_CEILING_MAX = 10

#: Care pathways. Skin/surface injuries are integumentary, not musculoskeletal:
#: they carry wound-care instructions and never loading metadata.
CARE_TYPE_MUSCULOSKELETAL = "musculoskeletal"
CARE_TYPE_WOUND_CARE = "wound_care"
CARE_TYPES: tuple[str, ...] = (CARE_TYPE_MUSCULOSKELETAL, CARE_TYPE_WOUND_CARE)

#: Fields every drill carries, whatever its care pathway.
COMMON_DRILL_FIELDS: tuple[str, ...] = ("id", "name", "notes")

#: Musculoskeletal-only fields. A wound-care drill must not declare any of them.
MSK_DRILL_FIELDS: tuple[str, ...] = (
    "rehab_stage",
    "function",
    "equipment",
    "dose",
    "impact",
    "load",
    "velocity",
    "pain_ceiling",
    "allowed_severities",
    "progress_when",
    "regress_when",
    "stop_when",
    "target_regions",
    "laterality_applicability",
    "target_tissues",
    "contraction_type",
    "sport_specificity",
    "contact_level",
    "evidence_notes",
)

#: Fields subject to the migrated/unmigrated distinction.
# ``target_tissues`` is nullable by design: a region can be defensibly known
# without asserting a diagnosis or tissue. Its null therefore means unknown,
# not unfinished migration.
CONTRACT_FIELDS: tuple[str, ...] = tuple(field for field in MSK_DRILL_FIELDS if field != "target_tissues")

#: List-valued rule fields. ``[]`` is a deliberate "no criteria" value.
RULE_LIST_FIELDS: tuple[str, ...] = ("progress_when", "regress_when", "stop_when")

DRILL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

#: Phase tokens a ``phase_progression`` may use, and the arrow that joins them.
PHASE_TOKENS: frozenset[str] = frozenset(PHASE_VALUES)
PHASE_ARROW = "→"
_MOJIBAKE_PHASE_ARROW = "â†’"

_UNSPECIFIED_LOCATION = "unspecified"

_CANONICAL_LOCATIONS_CACHE: frozenset[str] | None = None


# ---------------------------------------------------------------------------
# Canonical registries (borrowed, never redefined)
# ---------------------------------------------------------------------------


def canonical_rehab_types() -> frozenset[str]:
    """Injury types a rehab-bank group may declare.

    Sourced from the project injury taxonomy: every type that permits rehab.
    Types held back for clinical clearance (fractures, ruptures, concussion,
    ...) never own bank entries — the red-flag path owns them.
    """
    return REHAB_SAFE_TYPES


def canonical_rehab_locations() -> frozenset[str]:
    """Locations a rehab-bank group may declare.

    The union of the injury parser's location vocabulary, the explicit
    ``rehab_locations`` aliases declared by
    :data:`fightcamp.injury_location_registry.LOCATION_REGISTRY`, and the bank's
    own ``unspecified`` fallback bucket. No location list is defined here.
    """
    global _CANONICAL_LOCATIONS_CACHE
    if _CANONICAL_LOCATIONS_CACHE is not None:
        return _CANONICAL_LOCATIONS_CACHE

    # Imported lazily: the parser module pulls in the (optional) spaCy stack.
    from .injury_synonyms import LOCATION_MAP

    locations: set[str] = {_UNSPECIFIED_LOCATION}
    locations.update(LOCATION_MAP.keys())
    locations.update(LOCATION_MAP.values())
    for data in LOCATION_REGISTRY.values():
        locations.update(data.get("rehab_locations", []))

    _CANONICAL_LOCATIONS_CACHE = frozenset(
        location for location in locations if isinstance(location, str) and location.strip()
    )
    return _CANONICAL_LOCATIONS_CACHE


def is_surface_injury_type(injury_type: str | None) -> bool:
    """True when the injury type is a skin/surface wound, not musculoskeletal."""
    return str(injury_type or "").strip().lower() in SURFACE_TISSUE_TYPES


def care_type_for_injury_type(injury_type: str | None) -> str:
    """Return the care pathway a group's drills belong to."""
    return CARE_TYPE_WOUND_CARE if is_surface_injury_type(injury_type) else CARE_TYPE_MUSCULOSKELETAL


def normalize_severity_bucket(value: object, *, default: str = "") -> str:
    """Collapse a raw injury severity onto the bank's severity contract.

    The bank gates drills on :data:`SEVERITY_VALUES`; intake and the injury
    flags speak a slightly wider vocabulary (``mild``, ``severe``). This is the
    single collapse both of them go through — there is deliberately no second
    severity vocabulary in the selector or in ``rehab_protocols``.

    ``default`` is what an unrecognised or absent severity becomes, and callers
    differ honestly on it. Rendering wants a safe middle bucket so a drill list
    can still be filtered; selection wants ``""`` so "we do not know this
    athlete's severity" stays distinguishable from "we know it is moderate" and
    can fail closed against a drill that gates on severity.
    """
    normalized = str(value or "").strip().lower()
    if normalized in SEVERITY_ALIASES:
        return SEVERITY_ALIASES[normalized]
    return normalized if normalized in SEVERITY_VALUES else default


# ---------------------------------------------------------------------------
# Structural helpers
# ---------------------------------------------------------------------------


def split_phase_progression(text: str | None) -> list[str]:
    """Return the normalized phase tokens encoded in ``phase_progression``.

    Accepts both the real arrow and its mojibake spelling, which older bank
    edits introduced.
    """
    normalized = (text or "").replace(_MOJIBAKE_PHASE_ARROW, PHASE_ARROW)
    return [segment.strip().upper() for segment in normalized.split(PHASE_ARROW) if segment.strip()]


def slugify(value: str) -> str:
    """Return a lowercase ``a-z0-9_`` slug, collapsing every other character."""
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def build_drill_id(location: str | None, injury_type: str | None, name: str | None) -> str:
    """Return the deterministic id for a drill in a location/type group."""
    return slugify(f"{location or ''} {injury_type or ''} {name or ''}")


def unmigrated_fields(drill: Mapping[str, Any], *, care_type: str = CARE_TYPE_MUSCULOSKELETAL) -> list[str]:
    """Return the contract fields still awaiting clinical migration.

    A field counts as unmigrated when it is absent or explicitly ``None``.
    Wound-care drills carry no musculoskeletal contract fields, so nothing is
    ever pending for them.
    """
    if care_type == CARE_TYPE_WOUND_CARE:
        return []
    return [field for field in CONTRACT_FIELDS if drill.get(field) is None]


def is_migration_complete(drill: Mapping[str, Any], *, care_type: str = CARE_TYPE_MUSCULOSKELETAL) -> bool:
    """True when every contract field on the drill carries a migrated value."""
    return not unmigrated_fields(drill, care_type=care_type)


def get_declared_function(drill: Mapping[str, Any]) -> str | None:
    """Return the drill's explicit function class, or ``None`` when unmigrated.

    An unrecognised value is reported as ``None`` rather than being coerced —
    callers must not let an unknown class masquerade as a valid one.
    """
    value = drill.get("function")
    if isinstance(value, str) and value in REHAB_FUNCTIONS:
        return value
    return None


def resolve_drill_function(drill: Mapping[str, Any], fallback: str) -> str:
    """Return the drill's explicit function class, else ``fallback``.

    ``fallback`` is the legacy keyword classification, kept for legacy and
    not-yet-migrated bank entries.
    """
    return get_declared_function(drill) or fallback
