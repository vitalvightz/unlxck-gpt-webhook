"""Execution boundaries omitted by the existing clearance/ownership matrices."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from api.services import today_service
from tests.test_clinician_clearance_today import (
    CONTACT, DAY, NOW, context as clearance_context, execute, live_injury, report,
    session, set_sessions, view,
)


@pytest.fixture
def context():
    return clearance_context.__wrapped__()


def contact_camp(context):
    live_injury(context, "ankle")
    set_sessions(context, [session("sparring", "Hard sparring", [dict(
        block_id="contact", block_type="sparring", display_name="Hard sparring",
        mechanical_load_regions=["ankle"], contact_level="full")])])
    report(context, CONTACT)


def update_checkin(context, fields):
    store, athlete, plan, _ = context
    row = store.get_today_checkin(athlete, plan, DAY)
    store.upsert_today_checkin(athlete, {**row, **fields})


@pytest.mark.parametrize("status", ["started", "done", "modified"])
def test_current_pullback_holds_frozen_contact_without_rewriting_acceptance(context, status):
    contact_camp(context)
    accepted = execute(context, view(context).live_prescription)
    snapshot = deepcopy(accepted["prescription_snapshot"])
    update_checkin(context, {"pain": "manageable"})
    current = view(context)
    live = current.live_prescription
    assert current.today.decision_tier == "pull_back"
    assert live["frozen"] and live["session"] == snapshot["session"]
    assert live["revision"] == snapshot["revision"] and live["safety_hold"]
    with pytest.raises(HTTPException) as blocked:
        execute(context, live, status, session_rpe=5, modification_reason="Reduced rounds")
    assert blocked.value.status_code == 409
    assert context[0].get_session_completion(context[1], "session-1", DAY)["prescription_snapshot"] == snapshot
    stopped = execute(context, live, "modified", modification_reason="Stopped on new readiness",
                      rehab_performance="stopped")
    assert stopped["prescription_snapshot"] == snapshot


@pytest.mark.parametrize("status", ["started", "done", "modified"])
def test_red_flag_stop_cannot_be_bypassed_by_support_completion(context, status):
    live_injury(context, "ankle")
    set_sessions(context, [session("mindset", "Tactical cue", [dict(
        block_id="cue", block_type="mindset", display_name="Tactical cue",
        mechanical_load_regions=[], contact_level="none")])])
    report(context, CONTACT)
    update_checkin(context, {"sharp_pain": True})
    assert view(context).today.decision_tier == "stop"
    with pytest.raises(HTTPException) as blocked:
        today_service.upsert_session_completion(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW,
            payload=dict(plan_id=context[2], session_id="session-1", status=status,
                         session_rpe=1, modification_reason="Reduced cue"))
    assert blocked.value.status_code == 409


@pytest.mark.parametrize("fields,tier", [({}, "green"), ({"sleep": "poor"}, "modify"),
    ({"pain": "manageable"}, "pull_back"), ({"sharp_pain": True}, "stop"), (None, "not_checked_in")])
def test_frozen_contact_readiness_equivalence_classes(context, fields, tier):
    contact_camp(context)
    accepted = execute(context, view(context).live_prescription)
    snapshot = deepcopy(accepted["prescription_snapshot"])
    if fields is None:
        context[0].today_checkins[context[1]] = []
    else:
        update_checkin(context, fields)
    current = view(context)
    live = current.live_prescription
    assert current.today.decision_tier == tier
    assert live["session"] == snapshot["session"] and live["revision"] == snapshot["revision"]
    assert live["safety_hold"] == (tier in {"pull_back", "stop", "not_checked_in"})
    if tier in {"green", "modify"}:
        execute(context, live, "done", session_rpe=5)


def test_no_checkin_does_not_allow_uncatalogued_injury_completion(context):
    report(context, CONTACT)
    context[0].today_checkins[context[1]] = []
    current = view(context)
    assert current.today.decision_tier == "not_checked_in" and current.live_prescription is None
    with pytest.raises(HTTPException) as blocked:
        today_service.upsert_session_completion(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW,
            payload=dict(plan_id=context[2], session_id="session-1", status="started"))
    assert blocked.value.status_code == 409


@pytest.mark.parametrize("severity", ["mild", "moderate"])
@pytest.mark.parametrize("status", ["ongoing", "improving"])
def test_full_clearance_stable_and_improving_baselines_do_not_advance_rehab(context, severity, status):
    injury = live_injury(context, "ankle", severity)
    context[0].update_injury_flag(injury["id"], {"latest_reported_status": status})
    set_sessions(context, [session("strength", "Strength", [dict(
        block_id="work", block_type="strength", mechanical_load_regions=["ankle"], contact_level="none")])])
    before = view(context).open_injuries[0]["rehab_decision"]["stage"]
    report(context, CONTACT)
    current = view(context)
    assert current.open_injuries[0]["rehab_decision"]["stage"] == before
    assert not current.live_prescription["safety_hold"]
    assert any(b.get("block_id") == "work" for b in current.live_prescription["session"]["blocks"])


def test_pullback_preserves_independently_reviewed_nonloading_rehab(context):
    live_injury(context, "chest")
    report(context, CONTACT)
    update_checkin(context, {"sleep": "poor", "body": "flat", "pain": "manageable"})
    current = view(context)
    assert current.today.decision_tier == "pull_back"
    live = current.live_prescription
    assert live["rehab_only"] and not live["safety_hold"]
    assert all(b["block_type"] == "rehab" and not b["is_loading"] for b in live["session"]["blocks"])
    execute(context, live)
    execute(context, view(context).live_prescription, "done", rehab_performance="done_as_shown")


def test_severe_injury_support_exemption_survives_when_red_flags_are_clear(context):
    live_injury(context, "ankle", "severe")
    set_sessions(context, [session("mindset", "Tactical cue", [dict(
        block_id="cue", block_type="mindset", mechanical_load_regions=[], contact_level="none")])])
    report(context, CONTACT)
    current = view(context)
    assert current.today.injury_hold_exempt and current.today.decision_tier == "green"
    today_service.upsert_session_completion(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW,
        payload=dict(plan_id=context[2], session_id="session-1", status="done", session_rpe=1))


def test_known_combat_contact_cannot_use_full_clearance_to_override_poor_sleep(context):
    contact_camp(context)
    context[0].plans[context[2]]["technical_style"] = ["kickboxing"]
    context[0].plans[context[2]]["structured_plan"]["weeks"][0]["days"][0]["day_type"] = "hard"
    execute(context, view(context).live_prescription)
    update_checkin(context, {"sleep": "poor"})
    current = view(context)
    assert current.today.decision_tier == "pull_back" and current.live_prescription["safety_hold"]
    with pytest.raises(HTTPException):
        execute(context, current.live_prescription, "done", session_rpe=5)


@pytest.mark.parametrize("frozen", [False, True])
@pytest.mark.parametrize("gate", [dict(severity="severe"), dict(latest_reported_status="worse"),
    dict(body_area="Ankle", description="Ankle fracture"), dict(body_area="Head", description="Concussion")])
def test_second_hard_injury_gate_wins_in_either_order(context, frozen, gate):
    contact_camp(context)
    accepted = execute(context, view(context).live_prescription) if frozen else None
    context[0].create_injury_flag(context[1], {"body_area": "Chest", "description": "Chest strain",
        "severity": "moderate", "status": "open", **gate})
    first = view(context)
    context[0].injury_flags[context[1]].reverse()
    second = view(context)
    assert first.today.decision_tier == second.today.decision_tier
    assert second.today.decision_tier in {"stop", "pull_back"}
    for current in (first, second):
        live = current.live_prescription
        assert live is None or live["safety_hold"]
        if accepted:
            assert live["session"] == accepted["prescription_snapshot"]["session"]
            assert live["revision"] == accepted["prescription_snapshot"]["revision"]
    with pytest.raises(HTTPException):
        today_service.upsert_session_completion(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW,
            payload=dict(plan_id=context[2], session_id="session-1", status="done", session_rpe=5))


@pytest.mark.parametrize("area,description", [("Ankle", "Ankle fracture"), ("Head", "Concussion")])
def test_medical_review_without_live_policy_still_blocks_noncontact_submission(context, area, description):
    injury = live_injury(context, "ankle")
    context[0].update_injury_flag(injury["id"], {"body_area": area, "description": description})
    set_sessions(context, [session("strength", "Light strength", [dict(
        block_id="light", block_type="strength", mechanical_load_regions=["shoulder"], contact_level="none", load="low")])])
    report(context, CONTACT)
    current = view(context)
    assert current.open_injuries[0]["rehab_decision"]["outcome"] == "medical_review"
    assert current.today.decision_tier in {"stop", "pull_back"} and current.live_prescription is None
    with pytest.raises(HTTPException) as blocked:
        today_service.upsert_session_completion(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW,
            payload=dict(plan_id=context[2], session_id="session-1", status="started"))
    assert blocked.value.status_code == 409
