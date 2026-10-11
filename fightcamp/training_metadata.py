"""Small field-scoped discovery adapters; no planner or clinical imports.

Reviewed terminology does not certify the source association, apparatus
interchangeability, quantity, clinical eligibility or permission to prescribe.
"""
from __future__ import annotations

import re
from pathlib import Path

from shared.contracts import load_shared_contract, require_object

CONTRACT_FILES = tuple(Path(__file__).resolve().parents[1] / "shared" / name
                       for name in ("equipment-aliases.json", "training-metadata.json"))
AUDIT_REPORT = "reports/metadata_integrity/remediation.json"
AUDIT_REVISION = "ad82c28911103e11915a5567fc18623c056ba7d4"


def load_projection() -> dict:
    mappings, reviews, goal_reviews, discovery_filters, facet_aliases = [], [], [], [], []
    for path in CONTRACT_FILES:
        contract = require_object(load_shared_contract(path.name), "catalogue_projection", source=path.name)
        if contract.get("scope") != "discovery_only":
            raise ValueError("Metadata projection must remain discovery-only")
        mappings.extend(contract["mappings"])
        reviews.extend(contract.get("association_reviews", []))
        goal_reviews.extend(contract.get("goal_reviews", []))
        discovery_filters.extend(contract.get("discovery_filters", []))
        facet_aliases.extend(contract.get("facet_aliases", []))
    keys = [(m["field"], value) for m in mappings for value in m["source_values"]]
    if len(keys) != len(set(keys)):
        raise ValueError("Ambiguous field-scoped metadata alias")
    goal_keys = [(r["catalogue_id"], r["canonical_id"]) for r in goal_reviews]
    if len(goal_keys) != len(set(goal_keys)):
        raise ValueError("Duplicate reviewed Goal assignment")
    ids = [(r["group"], r["id"]) for r in discovery_filters]
    if len(ids) != len(set(ids)) or any(group not in {"movement", "training_method", "skill_focus", "physical_focus"} for group, _ in ids):
        raise ValueError("Invalid discovery filter dictionary")
    return {"mappings": mappings, "association_reviews": reviews, "goal_reviews": goal_reviews,
            "discovery_filters": discovery_filters, "facet_aliases": facet_aliases}


def exercise_details(entry: dict, projection: dict) -> list[dict]:
    """Closed, field-specific descriptive labels; never Goal or safety evidence."""
    if entry["content_class"] not in {"strength_power", "conditioning", "technical_coordination"}:
        return []
    result = []
    for rule in projection.get("discovery_filters", []):
        for source in rule["sources"]:
            if source.get("content_classes") and entry["content_class"] not in source["content_classes"]:
                continue
            raw = entry["raw"].get(source["field"])
            values = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
            if set(source["values"]).intersection(v for v in values if isinstance(v, str)):
                result.append({"value": rule["id"], "label": rule["label"], "group": rule["group"]})
                break
    return result


def mapping_for(field: str, value: str, projection: dict, content_class: str | None = None) -> dict | None:
    return next((m for m in projection["mappings"] if m["field"] == field and value in m["source_values"]
                 and ("content_classes" not in m or content_class in m["content_classes"])), None)


def project_value(entry: dict, field: str, value: str, projection: dict, pointer: str) -> dict:
    known = entry["metadata"].get(field, {}).get("state") == "known"
    mapping = mapping_for(field, value, projection, entry["content_class"]) if known else None
    review = next((r for r in projection["association_reviews"] if r["catalogue_id"] == entry["catalogue_id"]
                   and r["field"] == field and r["source_value"] == value), None)
    if review and entry["row_sha256"] != review["row_sha256"]:
        raise ValueError("Stale source association review: " + entry["catalogue_id"])
    compound = bool(re.search(r"[,/+|&]", value))
    evidence = {f: entry["raw"][f] for f in ("name", "equipment_note", "instructions", "notes", "description")
                if f in entry["raw"]} if field == "equipment" else {}
    return {
        "canonical_id": mapping["canonical_id"] if mapping else value,
        "label": mapping["label"] if mapping else value.replace("_", " ").replace("-", " ").capitalize(),
        "source_value": value, "source_field": field,
        "dimension": mapping["dimension"] if mapping else field,
        "subtype": mapping.get("subtype") if mapping else None,
        "catalogue_id": entry["catalogue_id"], "source": entry["source"], "source_pointer": pointer,
        "row_revision": entry["row_sha256"],
        "source_revision": entry["source_sha256"],
        "audit_decision": mapping["audit_decision"] if mapping else None,
        "audit_report": AUDIT_REPORT if mapping and mapping.get("audit_decision") else None,
        "audit_revision": AUDIT_REVISION if mapping and mapping.get("audit_decision") else None,
        "status": "association_review" if review else "reviewed_alias" if mapping else "unresolved_compound" if compound else "source_value",
        "filter_eligible": known and review is None,
        "association_note": review["reason"] if review else None,
        "requirement_evidence": evidence,
    }


def project_entry(entry: dict, projection: dict) -> list[dict]:
    result = []
    for review in projection["association_reviews"]:
        if review["catalogue_id"] == entry["catalogue_id"] and entry["row_sha256"] != review["row_sha256"]:
            raise ValueError("Stale source association review: " + entry["catalogue_id"])
    for field in ("equipment", "tags"):
        raw = entry["raw"].get(field)
        values = [(None, raw)] if isinstance(raw, str) else list(enumerate(raw)) if isinstance(raw, list) else []
        for ordinal, value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            # Keep equipment source tokens; only the reviewed anatomical tags
            # gain a projected anatomy dimension. Other tags remain untouched.
            if field == "tags" and not mapping_for(field, value, projection, entry["content_class"]):
                continue
            pointer = entry["source_pointer"] + "/" + field + ("/" + str(ordinal) if ordinal is not None else "")
            result.append(project_value(entry, field, value, projection, pointer))
    for review in projection.get("goal_reviews", []):
        if review["catalogue_id"] != entry["catalogue_id"]:
            continue
        if entry["content_class"] not in {"strength_power", "conditioning", "technical_coordination"}:
            raise ValueError("Goal reviews must apply only to Training")
        if entry["row_sha256"] != review["row_sha256"]:
            raise ValueError("Stale Goal review: " + entry["catalogue_id"])
        # Exact reviewed identities only. No name/tag/method/energy inference.
        evidence = {field: entry["raw"][field] for field in review["evidence_fields"]}
        if review.get("programming_evidence"):
            evidence["programming_context"] = review["programming_evidence"]
        source_field = review.get("source_field", "why")
        result.append({
            "canonical_id": review["canonical_id"], "label": review["label"],
            "source_field": source_field, "source_value": str(entry["raw"][source_field]),
            "dimension": "goals", "subtype": None,
            "catalogue_id": entry["catalogue_id"], "source": entry["source"],
            "source_pointer": entry["source_pointer"] + "/" + source_field,
            "row_revision": entry["row_sha256"], "source_revision": entry["source_sha256"],
            "audit_decision": review["audit_decision"], "audit_report": AUDIT_REPORT,
            "audit_revision": AUDIT_REVISION, "status": "reviewed_goal", "filter_eligible": True,
            "association_note": review["rationale"], "requirement_evidence": {},
            "goal_evidence": evidence,
        })
    return result


def canonical_filter(field: str, value: str, category: str, projection: dict | None) -> str:
    if category == "training":
        alias = next((r for r in (projection or {}).get("facet_aliases", [])
                      if r["field"] == field and value in r["source_values"]), None)
        if alias:
            return alias["canonical_id"]
    source_field = "equipment" if field == "equipment" else "tags" if field == "body_focus" and category == "training" else None
    if projection and source_field:
        # No clinical target-region aliases and no parent/subtype substitution.
        mapping = mapping_for(source_field, value, projection, "strength_power" if source_field == "tags" else None)
        if mapping:
            return mapping["canonical_id"]
    return value


def filter_label(field: str, value: str, projection: dict | None) -> str | None:
    alias = next((r for r in (projection or {}).get("facet_aliases", [])
                  if r["field"] == field and r["canonical_id"] == value), None)
    if alias:
        return alias["label"]
    dimension = "equipment" if field == "equipment" else "anatomical_focus" if field == "body_focus" else None
    return next((m["label"] for m in (projection or {}).get("mappings", [])
                 if m["dimension"] == dimension and m["canonical_id"] == value), None)
