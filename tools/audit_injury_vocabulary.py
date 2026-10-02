#!/usr/bin/env python3
"""Audit that every injury vocabulary stays in step with the canonical taxonomy.

Read-only. Nothing here defines an injury type or location: every set is
derived from :data:`fightcamp.injury_taxonomy.INJURY_TAXONOMY`, the injury
registry, the location registry / parser location map, the rehab bank, the
rehab pathways file and the guided-injury frontend options. The audit reports
drift between them so a future rehab expansion cannot silently leave an injury
type or location behind.

Exit codes: ``0`` when no drift was found, ``1`` otherwise.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fightcamp import guided_injury_resolver, injury_triage  # noqa: E402
from fightcamp.injury_location_registry import (  # noqa: E402
    LOCATION_REGISTRY,
    canonicalize_location_from_registry,
)
from fightcamp.injury_registry import (  # noqa: E402
    ALL_INJURY_TYPES,
    REHAB_BLOCKED_TYPES,
    REHAB_SAFE_TYPES,
    SURFACE_TISSUE_TYPES,
    URGENT_INJURY_TYPES,
)
from fightcamp.injury_taxonomy import INJURY_TAXONOMY  # noqa: E402
from fightcamp.rehab_schema import canonical_rehab_locations, canonical_rehab_types  # noqa: E402

BANK_PATH = REPO_ROOT / "data" / "rehab_bank.json"
PATHWAYS_PATH = REPO_ROOT / "data" / "rehab_pathways.json"
GUIDED_CARD_PATH = REPO_ROOT / "web" / "components" / "guided-injury-card.tsx"

UNSPECIFIED = "unspecified"
# Taxonomy categories that must never be loaded through an automatic MSK family.
_UNSAFE_CATEGORIES = frozenset({"structural", "neurological", "medical", "post_op"})


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def frontend_guided_tokens(path: Path = GUIDED_CARD_PATH) -> tuple[set[str], set[str]]:
    """Return (injury_type option values, surface_type option values) from the card."""
    source = path.read_text(encoding="utf-8")
    start = source.index("INJURY_TYPE_GROUPS")
    end = source.index("];", start)
    block = source[start:end]
    types = set(re.findall(r'value:\s*"([a-z_]+)"', block))
    surfaces = set(re.findall(r'surface_type:\s*"([a-z_]+)"', block))
    return types, surfaces


def triage_structured_tokens() -> set[str]:
    """Guided ``injury_type`` tokens that injury triage routes explicitly."""
    source = inspect.getsource(injury_triage._apply_structured_injury_signals)
    return set(re.findall(r'injury_type\s*==\s*"([a-z_]+)"', source))


def _resolve_guided(injury_type: str, surface_type: str = "") -> str:
    guided = SimpleNamespace(
        area="", notes="", avoid="", injury_type=injury_type, surface_type=surface_type, injury_subtypes=[]
    )
    return guided_injury_resolver.resolve_guided_injury_entry(guided, {"injury_type": UNSPECIFIED})["injury_type"]


def _audit_types(bank: list[dict], pathways: dict) -> tuple[dict[str, list], dict[str, Any]]:
    drift: dict[str, list] = defaultdict(list)

    taxonomy_keys = frozenset(INJURY_TAXONOMY)
    derived_safe = frozenset(k for k, rule in INJURY_TAXONOMY.items() if rule.get("rehab_allowed") is True)
    surface = frozenset(k for k, rule in INJURY_TAXONOMY.items() if rule.get("category") == "surface")
    unsafe = frozenset(
        k
        for k, rule in INJURY_TAXONOMY.items()
        if rule.get("urgent") or not rule.get("rehab_allowed") or rule.get("category") in _UNSAFE_CATEGORIES
    )
    msk = derived_safe - surface - {UNSPECIFIED}

    if ALL_INJURY_TYPES != taxonomy_keys:
        drift["ALL_INJURY_TYPES differs from taxonomy keys"] = sorted(ALL_INJURY_TYPES ^ taxonomy_keys)
    if REHAB_SAFE_TYPES != derived_safe:
        drift["REHAB_SAFE_TYPES differs from taxonomy rehab_allowed"] = sorted(REHAB_SAFE_TYPES ^ derived_safe)
    if canonical_rehab_types() != REHAB_SAFE_TYPES:
        drift["canonical_rehab_types() differs from REHAB_SAFE_TYPES"] = sorted(canonical_rehab_types() ^ REHAB_SAFE_TYPES)
    if SURFACE_TISSUE_TYPES != surface:
        drift["SURFACE_TISSUE_TYPES differs from taxonomy surface category"] = sorted(SURFACE_TISSUE_TYPES ^ surface)
    if UNSPECIFIED not in derived_safe:
        drift["unspecified fallback missing or rehab-blocked"] = [UNSPECIFIED]
    leaked = (REHAB_BLOCKED_TYPES | URGENT_INJURY_TYPES) & derived_safe
    if leaked:
        drift["urgent/blocked types marked rehab-safe"] = sorted(leaked)

    # Pathway families.
    owners: dict[str, list[str]] = defaultdict(list)
    family_types: dict[str, set[str]] = {}
    for family in pathways.get("families", []):
        fid = family["family_id"]
        family_types[fid] = set(family.get("injury_types", []))
        for injury_type in family_types[fid]:
            owners[injury_type].append(fid)
    owned = set(owners)
    drift["missing pathway family types"] = sorted(msk - owned)
    drift["duplicate family ownership"] = sorted(f"{t}: {sorted(fs)}" for t, fs in owners.items() if len(fs) > 1)
    drift["family types not in taxonomy"] = sorted(owned - taxonomy_keys)
    drift["unsafe types in MSK families"] = sorted(owned & unsafe)
    drift["surface types in MSK families"] = sorted(owned & surface)
    drift["unspecified owned by a family"] = sorted(owned & {UNSPECIFIED})

    # Rehab bank.
    bank_types = {str(group.get("type")) for group in bank}
    drift["unknown rehab-bank injury types"] = sorted(bank_types - taxonomy_keys)
    drift["rehab-blocked types in rehab bank"] = sorted((bank_types & taxonomy_keys) - derived_safe)

    # Pathway profiles.
    for profile in pathways.get("profiles", []):
        pid, itype, fam = profile.get("policy_id"), profile.get("injury_type"), profile.get("pathway_family")
        if itype not in taxonomy_keys:
            drift["profile injury types not in taxonomy"].append(f"{pid}: {itype}")
        elif itype not in msk:
            drift["profile injury types not rehab-safe MSK"].append(f"{pid}: {itype}")
        if fam not in family_types:
            drift["profile families undeclared"].append(f"{pid}: {fam}")
        elif itype not in family_types[fam]:
            drift["profile injury type outside its family"].append(f"{pid}: {itype} not in {fam}")

    snapshot = {
        "canonical_types": len(taxonomy_keys),
        "rehab_safe_types": len(derived_safe),
        "surface_types": len(surface),
        "unspecified_fallback": int(UNSPECIFIED in derived_safe),
        "msk_rehab_safe_types": len(msk),
        "pathway_families": len(family_types),
    }
    return drift, snapshot


def _audit_intake(drift: dict[str, list]) -> dict[str, Any]:
    """Every structured intake token must reach a known backend destination.

    A token is accepted when its resolved type is canonical (A/C), or — for the
    deliberately broad guided concepts — when injury triage routes the raw token
    explicitly (B: safety pathway; rehab lookups fall back to ``unspecified``).
    """
    types, surfaces = frontend_guided_tokens()
    triage_tokens = triage_structured_tokens()
    safety_routed: dict[str, str] = {}
    for token in sorted(types - {"surface_injury"}):
        resolved = _resolve_guided(token)
        if resolved in ALL_INJURY_TYPES:
            continue
        if token in triage_tokens:
            safety_routed[token] = resolved
        else:
            drift["unresolved structured intake tokens"].append(f"{token} -> {resolved}")
    for surface_token in sorted(surfaces):
        resolved = _resolve_guided("surface_injury", surface_token)
        if resolved not in ALL_INJURY_TYPES:
            drift["unresolved structured intake tokens"].append(f"surface_injury:{surface_token} -> {resolved}")
    if "surface_injury" in types and "surface_injury" not in triage_tokens:
        drift["unresolved structured intake tokens"].append("surface_injury (no triage route)")

    # Backend-side alias tables must emit canonical types.
    resolver_emits = (
        set(guided_injury_resolver.SPECIFIC_PARSER_TYPES)
        | set(guided_injury_resolver.SERIOUS_GUIDED_TYPES)
        | set(guided_injury_resolver.SURFACE_TYPE_TO_INJURY_TYPE.values())
    )
    drift["resolver alias targets not in taxonomy"] = sorted(resolver_emits - ALL_INJURY_TYPES)
    drift["frontend surface tokens unknown to resolver"] = sorted(
        surfaces - set(guided_injury_resolver.SURFACE_TYPE_TO_INJURY_TYPE)
    )

    from fightcamp.injury_synonyms import INJURY_SYNONYM_MAP

    drift["parser emits types unknown to registry"] = sorted(set(INJURY_SYNONYM_MAP) - ALL_INJURY_TYPES)
    return {"frontend_types": len(types), "frontend_surface_types": len(surfaces), "safety_routed": safety_routed}


def _audit_locations(bank: list[dict], pathways: dict, drift: dict[str, list]) -> dict[str, Any]:
    from fightcamp.injury_synonyms import LOCATION_MAP
    from fightcamp.rehab_protocols import normalize_rehab_location

    canonical = canonical_rehab_locations()
    parser_locations = set(LOCATION_MAP.values()) | set(LOCATION_REGISTRY)
    bank_locations = {str(group.get("location")) for group in bank}

    drift["non-canonical bank locations"] = sorted(bank_locations - canonical)
    for profile in pathways.get("profiles", []):
        if profile.get("region") not in canonical:
            drift["unknown profile regions"].append(f"{profile.get('policy_id')}: {profile.get('region')}")
    if UNSPECIFIED not in canonical or UNSPECIFIED not in bank_locations:
        drift["unspecified location fallback missing"] = [UNSPECIFIED]
    if normalize_rehab_location(None) != [UNSPECIFIED]:
        drift["unspecified location fallback missing"].append("normalize_rehab_location(None)")

    # Which clinical identities reach each bank location. Parser spellings are
    # collapsed through the location registry so aliases share one identity.
    reached_by: dict[str, set[str]] = defaultdict(set)
    for location in parser_locations:
        identity = canonicalize_location_from_registry(location) or location
        declared = set(LOCATION_REGISTRY.get(identity, {}).get("rehab_locations", []))
        for candidate in normalize_rehab_location(location):
            # A declared ``rehab_locations`` entry is a deliberate fallback
            # (e.g. jaw -> face), not a second identity for that bank region.
            if candidate not in bank_locations:
                continue
            reached_by.setdefault(candidate, set())
            if candidate == identity or candidate not in declared:
                reached_by[candidate].add(identity)
    drift["unreachable bank locations"] = sorted(bank_locations - set(reached_by) - {UNSPECIFIED})
    # A bank location claimed by two clinical identities would merge two
    # regions; ``unspecified`` is the deliberate shared bucket.
    drift["bank locations shared by several identities"] = sorted(
        f"{loc}: {sorted(ids)}" for loc, ids in reached_by.items() if loc != UNSPECIFIED and len(ids) > 1
    )
    return {
        "bank_locations": len(bank_locations),
        "canonical_locations": len(canonical),
        "profile_regions": sorted({p.get("region") for p in pathways.get("profiles", [])}),
    }


def audit() -> tuple[dict[str, list], dict[str, Any]]:
    bank = _load_json(BANK_PATH)
    pathways = _load_json(PATHWAYS_PATH)
    drift, snapshot = _audit_types(bank, pathways)
    snapshot["intake"] = _audit_intake(drift)
    snapshot["locations"] = _audit_locations(bank, pathways, drift)
    return {k: v for k, v in drift.items() if v}, snapshot


def main() -> int:
    drift, snapshot = audit()
    print("Injury vocabulary snapshot:")
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    if not drift:
        print("No injury vocabulary drift found.")
        return 0
    for label, items in sorted(drift.items()):
        print(f"{label}: {items}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
