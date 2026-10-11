"""Reviewed catalogue requirements, separate from athlete capability and clearance.

These source-bound corrections do not rewrite bank rows or change prescription
eligibility. An equipment match is discovery evidence, never permission to train.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from shared.contracts import load_shared_contract

REQUIREMENTS_FILE = Path(__file__).resolve().parents[1] / "shared/equipment-requirements.json"
MODES = frozenset({"SINGLE", "ALL", "ANY", "OPTIONAL", "UNKNOWN"})


def load_equipment_reviews() -> dict[str, dict]:
    contract = load_shared_contract(REQUIREMENTS_FILE.name)
    if contract.get("scope") != "discovery_only":
        raise ValueError("Equipment review cannot authorize prescription")
    reviews = {}
    for review in contract["reviews"]:
        identity = review["catalogue_id"]
        if identity in reviews or not review.get("evidence") or not review.get("audit_decisions"):
            raise ValueError("Ambiguous or unsupported equipment review: " + identity)
        if review["action"] not in {"CORRECT", "REVIEW"} or not review["groups"]:
            raise ValueError("Invalid equipment review: " + identity)
        for group in review["groups"]:
            mode, items = group["mode"], group["items"]
            if mode not in MODES or not isinstance(items, list) or len(items) != len(set(items)):
                raise ValueError("Invalid equipment requirement group")
            if any(not isinstance(item, str) or not item.strip() for item in items):
                raise ValueError("Invalid equipment item")
            if ((mode == "UNKNOWN" and items) or (mode == "SINGLE" and len(items) != 1)
                    or (mode in {"ALL", "ANY"} and len(items) < 2)
                    or (mode == "OPTIONAL" and not items)):
                raise ValueError("Invalid equipment requirement cardinality")
        unresolved = any(g["mode"] == "UNKNOWN" for g in review["groups"])
        if unresolved != (review["action"] == "REVIEW"):
            raise ValueError("Unresolved equipment cannot become verified")
        reviews[identity] = review
    return reviews


def project_requirements(entry: dict, reviews: dict[str, dict]) -> dict | None:
    review = reviews.get(entry["catalogue_id"])
    if review is None:
        return None
    if entry["row_sha256"] != review["row_sha256"] or entry["raw"].get("equipment") != review["source_value"]:
        raise ValueError("Stale equipment requirement review: " + entry["catalogue_id"])
    # Items denote exact source apparatus, not planner capability families.
    groups = [{"mode": g["mode"], "items": [
        {"canonical_id": item, "kind": "partner" if item == "partner" else "apparatus", "quantity": None}
        for item in g["items"]]} for g in review["groups"]]
    return {"status": "unresolved" if review["action"] == "REVIEW" else "reviewed",
            "groups": groups, "source_value": deepcopy(review["source_value"]),
            "source": entry["source"], "source_pointer": entry["source_pointer"] + "/equipment",
            "catalogue_id": entry["catalogue_id"], "row_revision": entry["row_sha256"],
            "audit_decisions": list(review["audit_decisions"]), "evidence": review["evidence"]}


def requirement_items(requirement: dict) -> set[str]:
    """Discoverable apparatus includes alternatives and clearly marked optional items."""
    return {item["canonical_id"] for group in requirement["groups"] for item in group["items"]}


def equipment_setup_available(requirement: dict, available: set[str]) -> bool:
    """Conservative setup-only check; intentionally unused by prescription engines.

    Callers must supply exact canonical source apparatus and explicitly declare
    partner availability. Unknown and absent review evidence always fail closed.
    """
    if requirement.get("status") != "reviewed" or not requirement.get("groups"):
        return False
    for group in requirement["groups"]:
        items = {item["canonical_id"] for item in group["items"]}
        mode = group["mode"]
        if mode == "UNKNOWN" or mode not in MODES:
            return False
        if ((mode == "SINGLE" and len(items) != 1) or (mode in {"ALL", "ANY"} and len(items) < 2)
                or (mode == "OPTIONAL" and not items)):
            return False
        # A capability set cannot prove a pair/count. Do not accept a quantified
        # mandatory setup without an inventory that establishes its quantity.
        if mode != "OPTIONAL" and any(item.get("quantity") not in (None, 1) for item in group["items"]):
            return False
        if mode in {"SINGLE", "ALL"} and (not items or not items <= available):
            return False
        if mode == "ANY" and not items & available:
            return False
    return True
