"""Injury vocabularies stay in step with the canonical taxonomy.

All sets are derived by ``tools/audit_injury_vocabulary.py``; the counts below
are only the current snapshot, not a source of truth.
"""

from __future__ import annotations

import copy
import json

import pytest

from tools import audit_injury_vocabulary as audit_mod


def test_no_injury_vocabulary_drift():
    drift, _ = audit_mod.audit()
    assert drift == {}, "\n".join(f"{label}: {items}" for label, items in sorted(drift.items()))


def test_current_snapshot():
    _, snapshot = audit_mod.audit()
    assert {k: snapshot[k] for k in (
        "canonical_types", "rehab_safe_types", "surface_types",
        "unspecified_fallback", "msk_rehab_safe_types", "pathway_families",
    )} == {
        "canonical_types": 33, "rehab_safe_types": 18, "surface_types": 5,
        "unspecified_fallback": 1, "msk_rehab_safe_types": 12, "pathway_families": 7,
    }
    # Broad guided concepts deliberately route through triage, not a canonical type.
    assert set(snapshot["intake"]["safety_routed"]) == {"tendon_ligament", "head_impact", "nerve_symptoms", "chest_breathing"}


def _audit_with(monkeypatch, *, pathways=None, bank=None):
    real_load = audit_mod._load_json
    def fake_load(path):
        if path == audit_mod.PATHWAYS_PATH and pathways is not None:
            return pathways
        if path == audit_mod.BANK_PATH and bank is not None:
            return bank
        return real_load(path)
    monkeypatch.setattr(audit_mod, "_load_json", fake_load)
    return audit_mod.audit()[0]


def _pathways():
    return copy.deepcopy(json.loads(audit_mod.PATHWAYS_PATH.read_text(encoding="utf-8")))


def test_detects_missing_and_duplicate_family_ownership(monkeypatch):
    pathways = _pathways()
    families = pathways["families"]
    dropped = families[0]["injury_types"].pop()
    families[1]["injury_types"].append(families[2]["injury_types"][0])
    drift = _audit_with(monkeypatch, pathways=pathways)
    assert dropped in drift["missing pathway family types"]
    assert drift["duplicate family ownership"]


@pytest.mark.parametrize("injected", ["fracture", "laceration", "unspecified", "not_a_type"])
def test_detects_unsafe_family_members(monkeypatch, injected):
    pathways = _pathways()
    pathways["families"][0]["injury_types"].append(injected)
    assert _audit_with(monkeypatch, pathways=pathways)


def test_detects_bad_bank_entries(monkeypatch):
    bank = json.loads(audit_mod.BANK_PATH.read_text(encoding="utf-8"))
    bank.append({"location": "knee", "type": "acl_tear", "drills": []})
    bank.append({"location": "nowhere_land", "type": "made_up", "drills": []})
    drift = _audit_with(monkeypatch, bank=bank)
    assert drift["rehab-blocked types in rehab bank"] == ["acl_tear"]
    assert drift["unknown rehab-bank injury types"] == ["made_up"]
    assert "nowhere_land" in drift["non-canonical bank locations"]


def test_detects_profile_drift(monkeypatch):
    pathways = _pathways()
    profile = pathways["profiles"][0]
    profile["region"] = "nowhere_land"
    profile["injury_type"] = "tendonitis"
    drift = _audit_with(monkeypatch, pathways=pathways)
    assert drift["unknown profile regions"]
    assert drift["profile injury type outside its family"]


def test_detects_unrouted_frontend_token(monkeypatch, tmp_path):
    card = tmp_path / "card.tsx"
    card.write_text(
        audit_mod.GUIDED_CARD_PATH.read_text(encoding="utf-8").replace(
            '{ label: "Blister", value: "surface_injury", surface_type: "blister" },',
            '{ label: "Blister", value: "surface_injury", surface_type: "blister" },\n'
            '      { label: "Mystery", value: "mystery_token" },\n'
            '      { label: "Burn", value: "surface_injury", surface_type: "burn" },',
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(audit_mod, "GUIDED_CARD_PATH", card)
    monkeypatch.setattr(audit_mod.frontend_guided_tokens, "__defaults__", (card,))
    drift = audit_mod.audit()[0]
    assert any("mystery_token" in item for item in drift["unresolved structured intake tokens"])
    assert "burn" in drift["frontend surface tokens unknown to resolver"]
