"""Migrating chest/ankle onto family + profile composition changes no live output.

The pre-migration policy file is frozen in ``tests/fixtures``. Every comparison
runs the same resolver, scheduler, reconciler, Today view and generation path
against both. The only permitted difference is the additive
``progression.next_transition`` diagnostic, which must report a blocked
transition and never change a stage.
"""
from __future__ import annotations

import itertools
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from api.contracts.injury_policy import reconcile_session_prescription, resolve_injury_policy
from api.contracts.rehab_schedule import schedule_rehab
from fightcamp.rehab_clinical import load_clinical_policies, policy_review_hash
from fightcamp.rehab_protocols import get_rehab_bank
from tests.support import FakeStore

LEGACY_PATH = Path(__file__).parent / "fixtures" / "rehab_clinical_policies_v2_legacy.json"
DAY = "2026-10-02"
PLAN = str(uuid4())
ATHLETE = str(uuid4())
REGIONS = {"chest_strain": ("chest", "strain", "Chest"), "ankle_sprain": ("ankle", "sprain", "Ankle")}


def legacy():
    return load_clinical_policies(LEGACY_PATH)


def composed():
    return tuple(p for p in load_clinical_policies() if p.policy_id in REGIONS)


def strip(decision):
    """Remove only the additive diagnostic; assert it is blocked when present."""
    decision = deepcopy(decision)
    nxt = (decision.get("progression") or {}).pop("next_transition", None)
    if nxt is not None:
        assert nxt["status"] in {"blocked", "closed"} and nxt["to_stage"] == "load"
        assert decision["stage"] == "restore"
    return decision


def injury(policy_id, *, stage, side="left", severity="mild", status=None, reported=None, **extra):
    region, kind, label = REGIONS[policy_id]
    row = dict(id=str(uuid4()), episode_id=str(uuid4()), athlete_id=ATHLETE, canonical_location=region,
               body_region=region, body_area=f"Left {label.lower()}", description=f"{label} {kind}", side=side,
               injury_type=kind, severity=severity, status=status or ("monitoring" if stage == "restore" else "open"),
               created_at="2026-09-28T00:00:00Z", updated_at="2026-09-28T00:00:00Z")
    if stage == "restore":
        row.update(latest_reported_status=reported or "improving", rehab_stage="restore")
    elif reported:
        row["latest_reported_status"] = reported
    row.update(extra)
    return row


def setback_rows(row, *, improved_after=False):
    rows = [dict(id=str(uuid4()), athlete_id=row["athlete_id"], created_at="2026-09-29T12:00:00Z",
                 event_json=dict(injury_id=row["id"], injury_episode_id=row["episode_id"],
                                 response=dict(next_day_response="worse"), dose_completed={}))]
    if improved_after:
        row["latest_reported_at"] = "2026-10-01T12:00:00Z"
    return rows


def test_policy_content_and_integrity_hashes_are_identical():
    old, new = legacy(), composed()
    assert [p.policy_id for p in old] == [p.policy_id for p in new]
    for before, after in zip(old, new):
        assert before.model_dump(exclude={"pathway_family", "transitions"}) == after.model_dump(exclude={"pathway_family", "transitions"})
        assert before.content_hash == after.content_hash == policy_review_hash(after) == policy_review_hash(before)
        assert before.transitions == [] and not any(t.promotable for t in after.transitions)


CASES = list(itertools.product(
    ["chest_strain", "ankle_sprain"],
    [dict(stage="calm"), dict(stage="restore"), dict(stage="restore", reported="worse"),
     dict(stage="calm", reported="worse"), dict(stage="restore", severity="moderate"),
     dict(stage="restore", severity="severe"), dict(stage="restore", severity="high"),
     dict(stage="restore", status="resolved"), dict(stage="restore", side="unknown"), dict(stage="calm", side=None),
     dict(stage="restore", side="bilateral"), dict(stage="restore", setback=True),
     dict(stage="restore", setback=True, improved=True)],
    ["", "GPP", "TAPER"],
    [None, "modify", "pull_back"],
    [False, True],
))


@pytest.mark.parametrize("policy_id,case,phase,readiness,truncated", CASES)
def test_decisions_are_identical_across_the_live_matrix(policy_id, case, phase, readiness, truncated):
    case = dict(case)
    setback, improved = case.pop("setback", False), case.pop("improved", False)
    row = injury(policy_id, **case)
    exposures = setback_rows(row, improved_after=improved) if setback else []
    bank = get_rehab_bank()
    kwargs = dict(bank=bank, phase=phase, exposures=exposures, readiness_decision=readiness, history_truncated=truncated)
    before = resolve_injury_policy(deepcopy(row), policies=legacy(), **kwargs)
    after = resolve_injury_policy(deepcopy(row), policies=composed(), **kwargs)
    assert "next_transition" not in (before.get("progression") or {})
    assert strip(after) == before
    for excluded in ([], [p.drill_id for p in legacy()[0 if policy_id == "chest_strain" else 1].prescriptions][:1]):
        assert strip(resolve_injury_policy(deepcopy(row), policies=composed(), excluded_drill_ids=excluded, **kwargs)) == \
            resolve_injury_policy(deepcopy(row), policies=legacy(), excluded_drill_ids=excluded, **kwargs)
    if before.get("prescription"):
        for session in (None, {"blocks": [dict(block_type="strength", mechanical_load_regions=[row["body_region"]], load="high")]}):
            assert schedule_rehab(row, after, training_day=DAY, readiness_decision=readiness, training_session=session) == \
                schedule_rehab(row, before, training_day=DAY, readiness_decision=readiness, training_session=session)


@pytest.mark.parametrize("session_type", [None, "rehab", "strength", "sparring"])
@pytest.mark.parametrize("stages", [("calm", "calm"), ("restore", "calm"), ("restore", "restore")])
def test_reconciled_today_snapshots_are_identical_for_multi_injury_days(session_type, stages):
    rows = [injury("ankle_sprain", stage=stages[0]), injury("chest_strain", stage=stages[1])]
    session = None if session_type is None else dict(session_id="s", session_type=session_type, blocks=[
        dict(block_id="t", block_type="strength", mechanical_load_regions=["shoulder"], contact_level="none")])
    snapshots = []
    for policies in (legacy(), composed()):
        decisions = [resolve_injury_policy(deepcopy(r), policies=policies, bank=get_rehab_bank()) for r in rows]
        snapshots.append(reconcile_session_prescription(deepcopy(session), decisions=decisions, plan_id=PLAN,
                                                        training_day=DAY, injuries=deepcopy(rows)))
    assert snapshots[0] == snapshots[1]
    if snapshots[0]:
        assert snapshots[0]["revision"] == snapshots[1]["revision"]
        # Frozen snapshots accepted under the legacy file stay valid under composition.
        decisions = [resolve_injury_policy(deepcopy(r), policies=composed(), bank=get_rehab_bank()) for r in rows]
        assert reconcile_session_prescription(None, decisions=decisions, plan_id=PLAN, training_day=DAY,
                                              frozen=snapshots[0], injuries=deepcopy(rows))["safety_hold"] is \
            reconcile_session_prescription(None, decisions=[resolve_injury_policy(deepcopy(r), policies=legacy(),
                                           bank=get_rehab_bank()) for r in rows], plan_id=PLAN, training_day=DAY,
                                           frozen=snapshots[0], injuries=deepcopy(rows))["safety_hold"]


@pytest.mark.parametrize("reported", ["ongoing", "improving", "worse"])
@pytest.mark.parametrize("clearance", [None, ["rehab"], ["rehab", "training", "contact"]])
def test_today_view_is_identical(monkeypatch, reported, clearance):
    from api.services import today_service
    row = injury("ankle_sprain", stage="calm", reported=reported, status="monitoring",
                 id="11111111-1111-1111-1111-111111111111", episode_id="22222222-2222-2222-2222-222222222222")
    if clearance:
        row["clinician_clearance"] = dict(episode_id=row["episode_id"], scopes=clearance)
    chest = injury("chest_strain", stage="calm", id="33333333-3333-3333-3333-333333333333",
                   episode_id="44444444-4444-4444-4444-444444444444")
    store = FakeStore()
    store.injury_flags[ATHLETE] = [row, chest]
    store.plans[PLAN] = dict(id=PLAN, athlete_id=ATHLETE, status="ready", created_at="2026-09-01T00:00:00Z",
        structured_plan={"weeks": [{"phase_label": "TAPER", "days": [{"date": DAY, "day_type": "rest", "sessions": []}]}]})
    store.set_active_plan_id(ATHLETE, PLAN)
    store.upsert_today_checkin(ATHLETE, dict(plan_id=PLAN, training_day=DAY, recommendation_state="train_as_planned",
                                             pain="none", body="good"))
    views = []
    for policies in (legacy(), composed()):
        monkeypatch.setattr(today_service, "load_clinical_policies", lambda p=policies: p)
        views.append(today_service.build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="UTC",
                                                            now=datetime(2026, 10, 2, 12, tzinfo=timezone.utc)))
    before, after = views
    assert [strip(i["rehab_decision"]) for i in after.open_injuries] == [i["rehab_decision"] for i in before.open_injuries]
    assert after.live_prescription == before.live_prescription
    assert after.model_dump(exclude={"open_injuries"}) == before.model_dump(exclude={"open_injuries"})


@pytest.mark.parametrize("policy_id", ["chest_strain", "ankle_sprain"])
@pytest.mark.parametrize("phase", ["GPP", "SPP", "TAPER"])
def test_camp_generation_reviewed_line_is_identical(monkeypatch, policy_id, phase):
    from fightcamp import rehab_clinical, rehab_protocols
    region, kind, _ = REGIONS[policy_id]
    episode = dict(injury_id=str(uuid4()), episode_id=str(uuid4()), injury_type=kind, severity="mild", status="open",
                   side="left", athlete_id=ATHLETE)
    results = []
    for policies in (legacy(), composed()):
        monkeypatch.setattr(rehab_clinical, "load_clinical_policies", lambda p=policies: p)
        option = rehab_protocols._reviewed_episode_option(deepcopy(episode), region, phase)
        option["decision"] = strip(option["decision"])
        results.append(option)
    assert results[0] == results[1]
