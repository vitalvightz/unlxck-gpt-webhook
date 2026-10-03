"""Pathway families + regional profiles compose live policies without bespoke engines."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from fightcamp.injury_registry import REHAB_SAFE_TYPES, SURFACE_TISSUE_TYPES
from fightcamp.rehab_clinical import (
    PATHWAYS_PATH, compose_policy, content_hash, load_clinical_policies, load_pathway_catalog, policy_review_hash,
    validate_pathway_catalog,
)
from fightcamp.rehab_pathways import PathwayCatalog, TransitionRequirement, compose_transitions
from fightcamp.rehab_protocols import get_rehab_bank

SOURCE = "test-only://synthetic-source"


def raw_catalog():
    return json.loads(PATHWAYS_PATH.read_text(encoding="utf-8"))


def test_every_msk_injury_type_has_exactly_one_family_and_surface_care_stays_separate():
    catalog = load_pathway_catalog()
    assert validate_pathway_catalog(catalog) == []
    owned = [t for f in catalog.families for t in f.injury_types]
    assert sorted(owned) == sorted(REHAB_SAFE_TYPES - SURFACE_TISSUE_TYPES - {"unspecified"})
    assert not set(owned) & SURFACE_TISSUE_TYPES
    assert [f.family_id for f in catalog.families] == [
        "muscle_strain", "ligament_sprain_or_instability", "tendon_rehab", "joint_irritation_or_impingement",
        "hyperextension_or_joint_trauma", "contusion", "nonspecific_msk_symptoms"]


def test_families_and_safety_baseline_invent_no_clinical_criteria():
    catalog = load_pathway_catalog()
    assert {r.basis for r in catalog.safety_baseline} == {"product_safety", "data_sufficiency"}
    assert all(r.basis != "clinical" for f in catalog.families for t in f.transitions for r in t.requirements)
    for policy in load_clinical_policies():
        assert [t.key for t in policy.transitions] == ["restore->load", "load->dynamic", "dynamic->return"]
        assert not any(t.promotable for t in policy.transitions)
        assert policy.live_stages == ["calm", "restore"]


def test_shipped_profiles_name_their_family():
    assert {p.policy_id: p.pathway_family for p in load_clinical_policies()} == {
        "chest_strain": "muscle_strain", "ankle_sprain": "ligament_sprain_or_instability",
        "hamstring_strain": "muscle_strain", "calf_strain": "muscle_strain",
        "groin_strain": "muscle_strain", "quads_strain": "muscle_strain"}


@pytest.mark.parametrize("raw,match", [
    (dict(kind="next_day_response", basis="clinical", allowed_responses=["same"]), "must cite sources"),
    (dict(kind="minimum_observations", basis="clinical", minimum=2), "must cite sources"),
    (dict(kind="functional_checkpoint", basis="product_safety", checkpoint="pain_free_walking"), "clinical criterion"),
    (dict(kind="next_day_response", basis="product_safety"), "allowed responses"),
    (dict(kind="complete_history", basis="data_sufficiency", minimum=2), "declare a minimum"),
    (dict(kind="complete_history", basis="product_safety", sources=[SOURCE]), "only clinical"),
])
def test_requirement_contract_separates_clinical_safety_and_data_rules(raw, match):
    with pytest.raises(ValidationError, match=match):
        TransitionRequirement.model_validate({"requirement_id": "x", "description": "d", **raw})


def test_a_count_may_be_a_labelled_data_requirement_or_a_sourced_clinical_one():
    TransitionRequirement(requirement_id="x", kind="minimum_observations", basis="data_sufficiency", description="d", minimum=2)
    TransitionRequirement(requirement_id="x", kind="minimum_observations", basis="clinical", description="d",
                          minimum=2, sources=[SOURCE])


def calf_profile(**overrides):
    """The intended end state: new coverage is data, not engine code."""
    drill = next(d for g in get_rehab_bank() if g["location"] == "calf" for d in g["drills"])
    profile = {
        "policy_id": "calf_strain", "version": 1, "pathway_family": "muscle_strain", "region": "calf",
        "injury_type": "strain", "evidence_sources": [SOURCE], "blocked_regions": ["calf"],
        "prescriptions": [dict(drill_id=drill["id"], bank_hash=content_hash(drill), stage="restore",
                               instructions="Synthetic.", allowed_severities=["low"], stop_when=["Stop."], sources=[SOURCE])],
        "transition_overrides": {"restore->load": {"reason": "Region-specific functional check.", "add_requirements": [
            dict(requirement_id="calf_walk", kind="functional_checkpoint", basis="clinical", description="Walk check.",
                 sources=[SOURCE], checkpoint="pain_free_walking")]}},
    }
    profile.update(overrides)
    return profile


def test_a_new_regional_profile_composes_family_transitions_with_its_own_criteria():
    policy = compose_policy(load_pathway_catalog(), calf_profile())
    first = policy.transitions[0]
    baseline_ids = [r.requirement_id for r in load_pathway_catalog().safety_baseline]
    assert [r.requirement_id for r in first.requirements] == [*baseline_ids, "calf_walk"]
    assert first.promotable and not policy.transitions[1].promotable
    assert policy.pathway_family == "muscle_strain"


def test_profiles_cannot_escape_their_family_or_drop_safety():
    catalog = load_pathway_catalog()
    with pytest.raises(ValueError, match="outside pathway family"):
        compose_policy(catalog, calf_profile(injury_type="sprain"))
    with pytest.raises(ValueError, match="families own transitions"):
        compose_policy(catalog, calf_profile(transitions=[]))
    with pytest.raises(ValueError, match="cannot remove a product safety requirement"):
        compose_policy(catalog, calf_profile(transition_overrides={"restore->load": {
            "reason": "r", "remove_requirement_ids": ["no_unresolved_setback"]}}))
    with pytest.raises(ValueError, match="unknown transition override"):
        compose_policy(catalog, calf_profile(transition_overrides={"calm->restore": {"reason": "r"}}))
    with pytest.raises(ValueError, match="unknown functional checkpoint"):
        compose_policy(catalog, calf_profile(transition_overrides={"restore->load": {"reason": "r", "add_requirements": [
            dict(requirement_id="x", kind="functional_checkpoint", basis="clinical", description="d",
                 sources=[SOURCE], checkpoint="not_declared")]}}))
    with pytest.raises(ValueError, match="unknown pathway family"):
        compose_policy(catalog, calf_profile(pathway_family="bespoke_calf_engine"))


def test_profile_may_remove_a_data_requirement_only_with_a_stated_reason():
    catalog = load_pathway_catalog()
    family = catalog.family("muscle_strain")
    from fightcamp.rehab_pathways import TransitionOverride
    composed = compose_transitions(catalog, family, {"restore->load": TransitionOverride(
        reason="Sourced criterion replaces the generic exposure check.", remove_requirement_ids=["reviewed_stage_exposure"])})
    assert "reviewed_stage_exposure" not in [r.requirement_id for r in composed[0].requirements]
    with pytest.raises(ValidationError):
        TransitionOverride.model_validate({"remove_requirement_ids": ["reviewed_stage_exposure"]})


def test_only_promotable_transitions_are_hashed_content():
    catalog = load_pathway_catalog()
    blocked = compose_policy(catalog, calf_profile(transition_overrides={}))
    plain = blocked.model_copy(update={"transitions": []})
    assert policy_review_hash(blocked) == policy_review_hash(plain)
    promotable = compose_policy(catalog, calf_profile())
    assert policy_review_hash(promotable) != policy_review_hash(blocked)
    # Family membership alone is not content: it cannot move a stage.
    assert policy_review_hash(blocked.model_copy(update={"pathway_family": "contusion"})) == policy_review_hash(blocked)


def test_catalog_rejects_overlapping_families_and_clinical_baseline():
    raw = raw_catalog()
    raw["families"][1]["injury_types"].append("strain")
    with pytest.raises(ValidationError, match="more than one pathway family"):
        PathwayCatalog.model_validate(raw)
    raw = raw_catalog()
    raw["safety_baseline"].append(dict(requirement_id="x", kind="next_day_response", basis="clinical", description="d",
                                       sources=[SOURCE], allowed_responses=["same"]))
    with pytest.raises(ValidationError, match="cannot contain clinical criteria"):
        PathwayCatalog.model_validate(raw)


def test_a_live_higher_stage_requires_sourced_criteria_and_reviewed_content():
    catalog = load_pathway_catalog()
    with pytest.raises(ValidationError, match="cannot be live without an open transition"):
        compose_policy(catalog, calf_profile(transition_overrides={}, live_stages=["calm", "restore", "load"]))
    with pytest.raises(ValidationError, match="without a reviewed prescription"):
        compose_policy(catalog, calf_profile(live_stages=["calm", "restore", "load"]))
    with pytest.raises(ValidationError, match="every lower stage"):
        compose_policy(catalog, calf_profile(live_stages=["calm", "load"]))
