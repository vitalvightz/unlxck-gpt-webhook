"""Hamstring strain policy: two reviewed existing drills, CALM and RESTORE only."""
import json
import shutil
from copy import deepcopy
from uuid import uuid4

import pytest

from api.contracts.injury_policy import rehab_allocation_count, reconcile_session_prescription, resolve_injury_policy
from api.contracts.rehab_completion import resolve_rehab_completion
from api.contracts.rehab_schedule import schedule_rehab
from api.services.rehab_completion_service import session_rehab_items
from fightcamp.config import DATA_DIR
from fightcamp.rehab_clinical import load_clinical_policies, validate_clinical_bank
from fightcamp.rehab_protocols import get_rehab_bank
from tools.rehab_metadata_review_lib import REVIEW_STATE_NEEDS_REVIEW, REVIEW_STATE_REVIEWED, load_ledger

DAY = "2026-10-02"
PLAN = str(uuid4())
ATHLETE = str(uuid4())
CALM = "hamstring_unspecified_standing_bent_knee_stretch_active_rom"
RESTORE = "hamstring_unspecified_standing_hamstring_isometric_against_wall"
BRIDGE = "hamstring_unspecified_isometric_hamstring_bridge_hold_30s"
# Unchanged pilot content: this policy must not alter another injury policy.
PILOT_HASHES = {"chest_strain": "bcb04950b08fa56d411e0117010d9dcc47c6057bc8fc84c2304fb746e20ba8d9",
                "ankle_sprain": "d88c6de44d3cb6e120a86863594525505a03ee37a900e307f5d4ce6b0c9f173b"}


def policy():
    return next(p for p in load_clinical_policies() if p.policy_id == "hamstring_strain")


def injury(stage="restore", **changes):
    row = dict(id=str(uuid4()), episode_id=str(uuid4()), athlete_id=ATHLETE, canonical_location="hamstring",
               body_region="hamstring", body_area="Left hamstring", description="Left hamstring strain", side="left",
               injury_type="strain", severity="mild", status="open", created_at="2026-09-30T00:00:00Z",
               updated_at="2026-09-30T00:00:00Z")
    if stage == "restore":
        row.update(status="monitoring", latest_reported_status="improving", rehab_stage="restore")
    row.update(changes)
    return row


def decide(row, **kwargs):
    return resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank(), **kwargs)


def test_policy_is_sourced_bounded_and_leaves_pilot_policies_unchanged():
    policies = {p.policy_id: p for p in load_clinical_policies()}
    assert {k: policies[k].content_hash for k in PILOT_HASHES} == PILOT_HASHES
    current = policy()
    assert (current.region, current.injury_type, current.status, current.activation) == ("hamstring", "strain", "active", "live")
    assert current.live_stages == ["calm", "restore"] and current.transitions == []
    assert current.stage_bundles == {}
    assert [p.drill_id for p in current.prescriptions] == [CALM, RESTORE]
    assert all(p.dose is None and p.camp_doses == {} and p.sources for p in current.prescriptions)
    assert [p.minimum_gap_days for p in current.prescriptions] == [1, 3]
    assert all(p.allowed_severities == ["low", "moderate"] for p in current.prescriptions)
    assert validate_clinical_bank((current,), get_rehab_bank()) == []


def test_only_the_two_policy_drills_left_needs_review():
    ledger = load_ledger()
    reviewed = {r["drill_id"] for r in ledger if r["review_state"] == REVIEW_STATE_REVIEWED}
    assert reviewed == {CALM, RESTORE}
    hamstring = [r for r in ledger if r["location"] in {"hamstring", "hamstrings"}]
    assert sum(r["review_state"] == REVIEW_STATE_NEEDS_REVIEW for r in hamstring) == len(hamstring) - 2
    # Variable-demand progressions in the legacy notes remain flagged.
    assert all("VARIABLE_DEMAND_PROGRESSION" in r["flags"] for r in ledger if r["drill_id"] in reviewed)


def test_new_strain_gets_gentle_calm_movement_only():
    decision = decide(injury("calm"))
    assert decision["stage"] == "calm" and decision["outcome"] == "prescribed_rehab"
    current = decision["prescription"]
    assert current["drill_id"] == CALM and "drills" not in current
    assert current["dose"] == {} and not current["is_loading"] and current["minimum_gap_days"] == 1


def test_restore_prescribes_the_isometric_and_records_its_completion():
    row = injury()
    decision = decide(row)
    current = decision["prescription"]
    assert current["drill_id"] == RESTORE and "drills" not in current
    assert current["minimum_gap_days"] == 3 and current["is_loading"] and current["dose"] == {}
    accepted = reconcile_session_prescription(None, decisions=[decision], plan_id=PLAN, training_day=DAY)
    blocks = accepted["session"]["blocks"]
    assert [b["rehab_drill_id"] for b in blocks] == [RESTORE] and rehab_allocation_count(blocks) == 1
    items = session_rehab_items({"id": PLAN}, training_day=DAY, session_id=accepted["session"]["session_id"],
                                prescription=accepted)
    completion = dict(status="done", rehab_performance="done_as_shown", prescription_snapshot=accepted)
    assert [c.drill_id for c in resolve_rehab_completion(items, [row], completion=completion).eligible] == [RESTORE]


def test_bilateral_bridge_is_not_prescribed_because_its_work_cannot_be_attributed():
    # The completion contract cannot evidence one side with a bilateral_only
    # drill, so prescribing the bridge would silently drop its exposure.
    assert BRIDGE not in {p.drill_id for p in policy().prescriptions}
    assert next(r for r in load_ledger() if r["drill_id"] == BRIDGE)["review_state"] == REVIEW_STATE_NEEDS_REVIEW


def test_restore_recovery_day_falls_back_to_lighter_calm_movement():
    row = injury()
    alternative = decide(row, excluded_drill_ids=[RESTORE])
    assert alternative["stage"] == "restore"
    assert alternative["prescription"]["drill_id"] == CALM and not alternative["prescription"]["is_loading"]


@pytest.mark.parametrize("side", ["unknown", "", None])
def test_side_specific_drills_fail_closed_without_a_known_side(side):
    assert decide(injury(side=side))["prescription"] is None
    assert decide(injury("calm", side=side))["prescription"] is None


@pytest.mark.parametrize("changes,outcome", [
    (dict(severity="severe"), "medical_review"),
    (dict(severity="high"), "medical_review"),
    (dict(status="resolved"), "no_rehab_indicated"),
])
def test_severe_and_resolved_episodes_never_receive_rehab(changes, outcome):
    decision = decide(injury(**changes))
    assert decision["outcome"] == outcome and decision["prescription"] is None


def test_equipment_lists_do_not_exclude_bodyweight_drills():
    assert decide(injury(), equipment=["dumbbell"])["prescription"]["drill_id"] == RESTORE
    assert decide(injury("calm"), equipment=[])["prescription"]["drill_id"] == CALM


def test_worse_report_holds_restore_and_clearance_cannot_advance_stage():
    worse = decide(injury("calm", latest_reported_status="worse"))
    assert worse["stage"] == "calm"
    cleared = injury("calm", clinician_clearance=dict(episode_id="x", scopes=["rehab", "training", "contact"]))
    cleared["clinician_clearance"]["episode_id"] = cleared["episode_id"]
    decision = decide(cleared)
    assert decision["stage"] == "calm" and decision["prescription"]["drill_id"] == CALM


def test_loading_gates_hold_restore_work():
    row = injury()
    decision = decide(row)
    assert schedule_rehab(row, decision, training_day=DAY, readiness_decision="pull_back")["state"] == "held"
    assert schedule_rehab(row, decision, training_day=DAY, training_session={
        "blocks": [dict(block_type="strength", mechanical_load_regions=["hamstring"], load="high")]
    })["state"] == "deferred"


@pytest.mark.parametrize("session_type,allocated", [("rehab", 2), ("sparring", 1)])
def test_multi_injury_with_ankle_keeps_daily_ceiling(session_type, allocated):
    hamstring = decide(injury())
    ankle_row = dict(id=str(uuid4()), episode_id=str(uuid4()), athlete_id=ATHLETE, canonical_location="ankle",
                     body_region="ankle", body_area="Left ankle", side="left", injury_type="sprain", severity="mild",
                     status="monitoring", latest_reported_status="improving", rehab_stage="restore",
                     created_at="2026-09-30T00:00:00Z", updated_at="2026-09-30T00:00:00Z")
    ankle = decide(ankle_row)
    session = dict(session_id="s", session_type=session_type, blocks=[
        dict(block_id="training", block_type="strength", mechanical_load_regions=["shoulder"], contact_level="none")])
    result = reconcile_session_prescription(session, decisions=[hamstring, ankle], plan_id=PLAN, training_day=DAY)
    assert result["allocation_limit"] == allocated
    assert rehab_allocation_count(result["session"]["blocks"]) == allocated
    assert sum(c.get("action") == "deferred" for c in result["changes"]) == 2 - allocated


def test_seed_reproduces_committed_data(tmp_path, monkeypatch):
    from tools import seed_rehab_hamstring_strain
    names = ("rehab_bank.json", "rehab_metadata_review.json", "rehab_clinical_policies.json")
    (tmp_path / "data").mkdir()
    for name in names:
        shutil.copy(DATA_DIR / name, tmp_path / "data" / name)
    monkeypatch.setattr(seed_rehab_hamstring_strain, "ROOT", tmp_path)
    seed_rehab_hamstring_strain.main()
    for name in names:
        assert (tmp_path / "data" / name).read_text(encoding="utf-8") == (DATA_DIR / name).read_text(encoding="utf-8")


def test_seed_refuses_a_changed_source(tmp_path, monkeypatch):
    from tools import seed_rehab_hamstring_strain
    (tmp_path / "data").mkdir()
    bank = deepcopy(get_rehab_bank())
    next(d for g in bank for d in g["drills"] if d["id"] == CALM)["notes"] = "Changed source"
    (tmp_path / "data" / "rehab_bank.json").write_text(json.dumps(bank), encoding="utf-8")
    shutil.copy(DATA_DIR / "rehab_metadata_review.json", tmp_path / "data" / "rehab_metadata_review.json")
    monkeypatch.setattr(seed_rehab_hamstring_strain, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="source changed"):
        seed_rehab_hamstring_strain.main()
