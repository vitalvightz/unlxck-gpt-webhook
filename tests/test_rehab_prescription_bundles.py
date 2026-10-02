"""Opt-in stage bundles use the existing scheduler and exposure contracts."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.contracts.injury_policy import reconcile_session_prescription, resolve_injury_policy
from api.contracts.rehab_completion import (
    build_rehab_exposure_event, build_rehab_response_prompts, resolve_rehab_completion,
)
from api.contracts.rehab_schedule import schedule_rehab
from api.services.rehab_completion_service import session_rehab_items
from fightcamp.rehab_clinical import ClinicalPolicy, load_clinical_policies, policy_review_hash
from fightcamp.rehab_protocols import get_rehab_bank

DAY = "2026-10-02"
PLAN = str(uuid4())
ATHLETE = str(uuid4())
IDS = ["ankle_sprain_supported_balance", "ankle_sprain_heel_lowering"]


def fixture(bundle=True):
    policy = next(p for p in load_clinical_policies() if p.policy_id == "ankle_sprain")
    if bundle:
        raw = policy.model_dump()
        raw.update(status="draft", activation="shadow", content_hash=None,
                   stage_bundles={"restore": IDS})
        draft = ClinicalPolicy.model_validate(raw)
        policy = ClinicalPolicy.model_validate({
            **draft.model_dump(), "status": "active", "activation": "live",
            "content_hash": policy_review_hash(draft),
        })
    injury = dict(id=str(uuid4()), episode_id=str(uuid4()), athlete_id=ATHLETE,
                  canonical_location="ankle", body_region="ankle", body_area="Left ankle",
                  side="left", injury_type="sprain", severity="mild", status="monitoring",
                  latest_reported_status="improving", rehab_stage="restore")
    decision = resolve_injury_policy(injury, policies=(policy,), bank=get_rehab_bank())
    return policy, injury, decision


def snapshot(decisions, session=None, frozen=None):
    return reconcile_session_prescription(session, decisions=decisions, plan_id=PLAN,
                                         training_day=DAY, frozen=frozen)


def test_single_drill_shape_identity_dose_and_hash_are_unchanged():
    policy, _, decision = fixture(bundle=False)
    assert policy_review_hash(policy) == policy.content_hash
    current = decision["prescription"]
    assert current["drill_id"] == IDS[1] and current["dose"] == {}
    assert "drills" not in current
    blocks = snapshot([decision])["session"]["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["block_id"] == f"rehab:{decision['injury_id']}:{decision['injury_episode_id']}"
    assert "rehab_allocation_id" not in blocks[0]


def test_bundle_expands_all_reviewed_drills_once_and_preserves_order():
    _, _, decision = fixture()
    assert [d["drill_id"] for d in decision["prescription"]["drills"]] == IDS
    first = snapshot([decision])
    blocks = first["session"]["blocks"]
    assert [b["rehab_drill_id"] for b in blocks] == IDS
    assert len({b["block_id"] for b in blocks}) == 2
    assert len({b["rehab_allocation_id"] for b in blocks}) == 1
    assert all(b["minimum_gap_days"] == 2 for b in blocks)
    repeated = snapshot([decision], first["session"])
    assert repeated["session"]["blocks"] == blocks
    assert not snapshot([decision], frozen=first)["safety_hold"]


@pytest.mark.parametrize("session_type,allocated", [("rehab", 2), ("sparring", 1)])
def test_bundle_uses_one_allocation_and_keeps_sparring_ceiling(session_type, allocated):
    _, _, decision = fixture()
    second = deepcopy(decision)
    second.update(injury_id=str(uuid4()), injury_episode_id=str(uuid4()))
    first = snapshot([decision], dict(session_id="s", session_type=session_type, blocks=[
        dict(block_id="training", block_type="strength", mechanical_load_regions=["shoulder"], contact_level="none"),
    ]))
    result = snapshot([decision, second], first["session"])
    assert result["allocation_limit"] == allocated
    assert sum(b["block_type"] == "rehab" for b in result["session"]["blocks"]) == allocated * len(IDS)
    assert sum(b["injury_id"] == decision["injury_id"] for b in result["session"]["blocks"]) == 2
    assert any(c.get("injury_id") == second["injury_id"] and c["action"] == "deferred"
               for c in result["changes"]) == (allocated == 1)


@pytest.mark.parametrize("state", ["held", "deferred", "recovery_day"])
def test_schedule_gate_applies_to_entire_bundle(state):
    _, _, decision = fixture()
    decision["schedule"] = {"state": state}
    assert snapshot([decision]) is None


def test_loading_readiness_training_and_medical_gates_hold_whole_bundle():
    _, injury, decision = fixture()
    assert decision["prescription"]["is_loading"]
    assert schedule_rehab(injury, decision, training_day=DAY, readiness_decision="pull_back")["state"] == "held"
    assert schedule_rehab(injury, decision, training_day=DAY, training_session={
        "blocks": [dict(block_type="strength", mechanical_load_regions=["ankle"], load="high")]
    })["state"] == "deferred"
    first = snapshot([decision])
    changed = deepcopy(decision)
    changed["loading_hold"] = True
    assert snapshot([changed], frozen=first)["safety_hold"]
    changed = deepcopy(decision)
    changed["outcome"] = "medical_review"
    assert snapshot([changed], frozen=first)["safety_hold"]
    # Check every accepted member: a hold on the first cannot be hidden by the last.
    first["session"]["blocks"][0]["injury_episode_id"] = str(uuid4())
    assert snapshot([decision], frozen=first)["safety_hold"]


def test_cadence_recognizes_any_member_and_reserves_the_episode_once():
    policy, injury, decision = fixture()
    previous = resolve_injury_policy(injury, policies=(policy,), bank=get_rehab_bank(),
                                     excluded_drill_ids=[IDS[1]])
    assert previous["prescription"] is None  # atomic combination, no silent substitute
    _, _, single = fixture(bundle=False)
    single["injury_id"], single["injury_episode_id"] = injury["id"], injury["episode_id"]
    completion = dict(athlete_id=ATHLETE, training_day=DAY, status="started",
                      prescription_snapshot=snapshot([single]))
    assert schedule_rehab(injury, decision, training_day=DAY, completions=[completion])["state"] == "already_completed"
    completion.update(status="done", training_day="2026-10-01")
    # Even when the primary bundle member is balance, yesterday's heel lowering wins.
    assert schedule_rehab(injury, decision, training_day=DAY, completions=[completion])["state"] == "recovery_day"


@pytest.mark.parametrize("performance,state", [
    ("done_as_shown", "performed_amount_unknown"),
    ("changed", "partial_amount_unknown"),
    ("stopped", "partial_amount_unknown"),
])
def test_completion_produces_valid_distinct_exposures_and_one_response_group(performance, state):
    _, injury, decision = fixture()
    accepted = snapshot([decision])
    completion = dict(status="done" if performance == "done_as_shown" else "modified",
                      rehab_performance=performance, prescription_snapshot=accepted)
    items = session_rehab_items({"id": PLAN}, training_day=DAY,
                               session_id=f"rehab-{DAY}", prescription=accepted)
    resolution = resolve_rehab_completion(items, [injury], completion=completion)
    assert len(resolution.eligible) == 2
    prompts = build_rehab_response_prompts(resolution, [injury])
    assert len(prompts) == 1 and prompts[0].drill_ids == tuple(IDS)
    events = [build_rehab_exposure_event(
        candidate, athlete_id=ATHLETE, plan_id=PLAN, session_id=f"rehab-{DAY}",
        training_day=DAY, completion=completion, during="same", limit="no",
    ) for candidate in resolution.eligible]
    assert len({e.exposure_id for e in events}) == 2
    assert len({e.response_group_id for e in events}) == 1
    assert all(e.is_attributable_to(injury) and e.dose_completed.completion_state == state for e in events)
    assert all(e.dose_completed.reps is None and e.dose_completed.sets is None for e in events)


@pytest.mark.parametrize("ids", [
    ["ankle_sprain_supported_balance", "not_reviewed"],
    ["ankle_sprain_supported_balance", "ankle_sprain_gentle_movement"],
    ["ankle_sprain_supported_balance", "ankle_sprain_supported_balance"],
])
def test_unreviewed_wrong_stage_or_duplicate_member_cannot_enter_bundle(ids):
    policy, _, _ = fixture(bundle=False)
    raw = policy.model_dump()
    raw.update(status="draft", activation="shadow", content_hash=None, stage_bundles={"restore": ids})
    with pytest.raises(ValidationError, match="bundle"):
        ClinicalPolicy.model_validate(raw)


def test_stale_bank_member_and_excluded_member_fail_closed():
    policy, injury, _ = fixture()
    bank = deepcopy(get_rehab_bank())
    member = next(d for g in bank for d in g["drills"] if d["id"] == IDS[0])
    member["name"] = "Unreviewed change"
    result = resolve_injury_policy(injury, policies=(policy,), bank=bank)
    assert result["prescription"] is None
    result = resolve_injury_policy(injury, policies=(policy,), bank=get_rehab_bank(),
                                   excluded_drill_ids=[IDS[0]])
    assert result["prescription"] is None and result["reason_codes"] == ["reviewed_bundle_member_ineligible"]


def test_bundle_change_requires_a_new_policy_content_hash():
    policy, _, _ = fixture()
    with pytest.raises(ValidationError, match="content hash"):
        ClinicalPolicy.model_validate({**policy.model_dump(), "stage_bundles": {"restore": list(reversed(IDS))}})
