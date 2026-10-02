"""Independent episode allocations must remain actionable after other rehab ends."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.contracts.injury_policy import reconcile_session_prescription, resolve_injury_policy, rehab_allocation_count
from api.contracts.clinician_clearance import effective_clinician_clearance
from api.services import today_service
from api.services.injury_episode_service import InjuryEpisodeObservation, record_episode_observation
from api.services.rehab_completion_service import record_rehab_exposures
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank
from tests.support import FakeStore

DAY = "2026-10-02"
NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


@pytest.fixture
def context():
    store = FakeStore()
    athlete, plan = str(uuid4()), str(uuid4())
    store.plans[plan] = dict(id=plan, athlete_id=athlete, status="ready", created_at="2026-09-01T00:00:00Z",
        structured_plan={"weeks": [{"phase_label": "GPP", "days": [
            {"date": DAY, "day_type": "rest", "sessions": []},
            {"date": "2026-10-03", "day_type": "strength", "sessions": [
                {"session_id": "tomorrow", "session_type": "strength", "title": "Tomorrow's strength", "blocks": []}]}]}]})
    store.set_active_plan_id(athlete, plan)
    store.upsert_today_checkin(athlete, dict(plan_id=plan, training_day=DAY,
        recommendation_state="train_as_planned", pain="none", body="good"))
    chest = add_injury(store, athlete, "chest", ["rehab"])
    ankle = add_injury(store, athlete, "ankle", ["rehab", "training", "contact"])
    return store, athlete, plan, chest, ankle


def add_injury(store, athlete, region, scopes):
    row = store.create_injury_flag(athlete, dict(body_area="Chest" if region == "chest" else "Left ankle",
        description=region + (" strain" if region == "chest" else " sprain"), body_region=region,
        side="unknown" if region == "chest" else "left", severity="mild", status="monitoring"))
    row.update(created_at="2026-09-29T00:00:00Z", updated_at="2026-10-01T00:00:00Z", latest_reported_status="improving")
    next(i for i in store.injury_flags[athlete] if i["id"] == row["id"]).update(row)
    record_episode_observation(store, athlete_id=athlete, training_day=DAY,
        observation=InjuryEpisodeObservation(injury_id=row["id"], injury_episode_id=row["episode_id"],
            event_type="clinician_clearance_report", scopes=scopes))
    return row


def view(context):
    return today_service.build_today_command_view(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW)


def accept_ankle(context, status="done", legacy=True):
    store, athlete, plan, _, ankle = context
    decision = resolve_injury_policy({**ankle, "rehab_stage": "restore"}, policies=load_clinical_policies(), bank=get_rehab_bank())
    saved = reconcile_session_prescription(None, decisions=[decision], plan_id=plan, training_day=DAY)
    if legacy:
        saved["session"]["session_id"] = f"rehab-{DAY}"
    saved["injury_context"] = [{"id": i["id"], "episode_id": i["episode_id"]} for i in (context[3], ankle)]
    return store.upsert_session_completion(athlete, dict(plan_id=plan, session_id=saved["session"]["session_id"],
        training_day=DAY, status=status, prescription_snapshot=saved, started_at="2026-10-02T09:00:00Z",
        completed_at="2026-10-02T09:10:00Z" if status != "started" else None, rehab_performance="done_as_shown"))


def execute(context, live, status="started"):
    return today_service.upsert_session_completion(context[0], athlete_id=context[1], athlete_timezone="UTC", now=NOW,
        payload=dict(plan_id=context[2], session_id=live["session"]["session_id"], status=status,
                     prescription_revision=live["revision"], rehab_performance="done_as_shown" if status == "done" else None))


@pytest.mark.parametrize("legacy", [True, False])
def test_terminal_ankle_does_not_hide_or_own_due_chest(context, legacy):
    prior = accept_ankle(context, legacy=legacy)
    before = deepcopy(prior)
    current = view(context)
    states = {i["id"]: i["rehab_decision"]["schedule"]["state"] for i in current.open_injuries}
    assert states == {context[3]["id"]: "due", context[4]["id"]: "already_completed"}
    live = current.live_prescription
    assert live and not live["safety_hold"]
    assert current.today.session_scope == "today" and current.today.completion_status == "not_started"
    assert live["session"]["session_id"] != prior["session_id"]
    assert {b["injury_id"] for b in live["session"]["blocks"]} == {context[3]["id"]}
    assert rehab_allocation_count(live["session"]["blocks"]) == 1
    assert {row["id"] for row in live["injury_context"]} == {context[3]["id"], context[4]["id"]}
    assert live["readiness_context"]["id"]
    assert live["evidence_context"] == context[0].get_rehab_schedule_revision(context[1])
    execute(context, live)
    resumed = view(context).live_prescription
    assert resumed["frozen"] and resumed["session"] == live["session"]
    done = execute(context, resumed, "done")
    events = record_rehab_exposures(context[0], athlete_id=context[1], plan_row=context[0].plans[context[2]],
        training_day=DAY, session_id=done["session_id"], completion=done,
        answers={context[3]["id"]: dict(injury_episode_id=context[3]["episode_id"], during_response="same", limit_response="no")})
    assert len(events) == 1 and str(events[0].injury_id) == context[3]["id"]
    assert execute(context, resumed, "done")["prescription_snapshot"] == done["prescription_snapshot"]
    assert context[0].get_session_completion(context[1], prior["session_id"], DAY) == before
    assert view(context).live_prescription is None
    assert view(context).today.completion_status == "done"


@pytest.mark.parametrize("legacy", [True, False])
def test_started_rehab_resumes_its_accepted_ownership(context, legacy):
    prior = accept_ankle(context, status="started", legacy=legacy)
    current = view(context)
    assert current.live_prescription["frozen"]
    assert current.live_prescription["session"] == prior["prescription_snapshot"]["session"]
    assert current.today.completion_status == "started"


def test_two_due_injuries_use_two_allocations_and_bundle_members_stay_together(context):
    live = view(context).live_prescription
    assert live and not live["safety_hold"]
    blocks = live["session"]["blocks"]
    assert rehab_allocation_count(blocks) == 2 and len(blocks) == 3
    assert {b["injury_id"] for b in blocks} == {context[3]["id"], context[4]["id"]}
    assert len({b["rehab_allocation_id"] for b in blocks if b["injury_id"] == context[4]["id"]}) == 1
    execute(context, live)
    assert view(context).live_prescription["session"] == live["session"]


def test_daily_capacity_full_explicitly_defers_remaining_rehab(context):
    first = view(context).live_prescription
    execute(context, first)
    execute(context, first, "done")
    third = add_injury(context[0], context[1], "chest", ["rehab"])
    current = view(context)
    pending = next(i for i in current.open_injuries if i["id"] == third["id"])
    assert pending["rehab_decision"]["schedule"]["state"] == "deferred"
    assert "full" in pending["rehab_decision"]["schedule"]["reason"]
    assert current.live_prescription is None


def test_effective_clearance_is_order_independent_and_keeps_individual_history(context):
    store, athlete, _, chest, ankle = context
    history = deepcopy(store.injury_episode_events)
    current = view(context)
    effective = current.effective_clinician_clearance
    assert effective["level"] == "rehab_only" and effective["scopes"] == ["rehab"]
    assert effective["limited_by"] == [dict(injury_id=chest["id"], injury_episode_id=chest["episode_id"], label="Chest strain")]
    permissive = next(i for i in current.open_injuries if i["id"] == ankle["id"])
    assert set(permissive["clinician_clearance"]["scopes"]) == {"rehab", "training", "contact"}
    store.injury_flags[athlete].reverse()
    assert view(context).effective_clinician_clearance == effective
    assert store.injury_episode_events == history


@pytest.mark.parametrize("scopes", [[], ["training"], ["contact"], ["training", "contact"],
                                    ["rehab", "contact"], ["rehab", "training", "unknown"],
                                    ["rehab", "training", "training"], "rehab,training,contact", None, {}])
def test_noncanonical_clearance_fails_conservatively(context, scopes):
    rows = view(context).open_injuries
    rows[0]["clinician_clearance"]["scopes"] = scopes
    effective = effective_clinician_clearance(rows)
    assert effective["level"] == "rehab_only" and effective["requires_update"]
    entry = dict(session_id="camp", session_type="strength", blocks=[dict(block_type="strength",
        mechanical_load_regions=["shoulder"], contact_level="none")])
    held = reconcile_session_prescription(entry, decisions=[], injuries=rows, plan_id=context[2], training_day=DAY)
    assert held["safety_hold"]


@pytest.mark.parametrize("scopes", [["training"], ["contact"], ["rehab", "contact"], ["rehab", "rehab"]])
def test_new_noncanonical_reports_are_rejected_without_changing_history(context, scopes):
    history = deepcopy(context[0].injury_episode_events)
    with pytest.raises(HTTPException) as failure:
        record_episode_observation(context[0], athlete_id=context[1], training_day=DAY,
            observation=InjuryEpisodeObservation(injury_id=context[3]["id"], injury_episode_id=context[3]["episode_id"],
                event_type="clinician_clearance_report", scopes=scopes))
    assert failure.value.status_code == 422 and context[0].injury_episode_events == history


@pytest.mark.parametrize("scopes", [["training", "contact"], ["rehab", "training", "training"], "rehab,training,contact", None])
def test_existing_malformed_report_is_conservative_through_today_projection(context, scopes):
    for event in context[0].injury_episode_events.values():
        if event["injury_id"] == context[3]["id"]:
            event["payload"]["scopes"] = scopes
    history = deepcopy(context[0].injury_episode_events)
    current = view(context)
    assert current.effective_clinician_clearance["level"] == "rehab_only"
    assert current.effective_clinician_clearance["requires_update"]
    assert current.live_prescription["session"]["session_type"] == "rehab"
    assert context[0].injury_episode_events == history


def test_stale_and_resolved_injury_reports_cannot_lower_current_ceiling(context):
    rows = view(context).open_injuries
    rows[0]["status"] = "resolved"
    assert effective_clinician_clearance(rows)["level"] == "train_contact"
    rows[0]["status"] = "open"
    rows[0]["clinician_clearance"]["episode_id"] = "old"
    assert effective_clinician_clearance(rows)["level"] == "train_contact"


@pytest.mark.parametrize("scopes,rehab_only", [(["rehab"], True), (["rehab", "training"], False),
                                               (["rehab", "training", "contact"], False)])
def test_clearance_preserves_safe_camp_and_due_rehab_coexistence(context, scopes, rehab_only, monkeypatch):
    store, athlete, plan, chest, _ = context
    monkeypatch.setattr("tests.support._now", lambda: "2026-10-02T07:00:00Z")
    for event in store.injury_episode_events.values():
        if event["injury_id"] == chest["id"]:
            event["created_at"] = "2026-10-02T08:00:00Z"
    report = record_episode_observation(store, athlete_id=athlete, training_day=DAY,
        observation=InjuryEpisodeObservation(injury_id=chest["id"], injury_episode_id=chest["episode_id"],
            event_type="clinician_clearance_report", scopes=scopes))
    store.injury_episode_events[report["id"]]["created_at"] = "2026-10-02T09:00:00Z"
    camp = dict(session_id="camp", session_type="strength", title="Strength", blocks=[
        dict(block_id="safe", block_type="strength", mechanical_load_regions=["shoulder"], contact_level="none", load="low")])
    store.plans[plan]["structured_plan"]["weeks"][0]["days"][0].update(day_type="strength", sessions=[camp])
    live = view(context).live_prescription
    assert live and not live["safety_hold"] and live["rehab_only"] == rehab_only
    assert rehab_allocation_count(live["session"]["blocks"]) == 2
    assert any(b.get("block_id") == "safe" for b in live["session"]["blocks"]) == (not rehab_only)
    assert live["session"]["session_type"] == ("rehab" if rehab_only else "strength")
    execute(context, live)


def test_completed_camp_does_not_replace_due_chest_with_tomorrows_preview(context):
    store, athlete, plan, _, _ = context
    camp = dict(session_id="camp", session_type="strength", title="Strength", blocks=[])
    store.plans[plan]["structured_plan"]["weeks"][0]["days"][0].update(day_type="strength", sessions=[camp])
    store.upsert_session_completion(athlete, dict(plan_id=plan, session_id="camp", training_day=DAY, status="done"))
    accept_ankle(context, legacy=False)
    current = view(context)
    assert current.today.session_scope == "today"
    assert current.live_prescription["session"]["session_type"] == "rehab"
    execute(context, current.live_prescription)
    assert view(context).live_prescription["frozen"]


def test_accepted_sparring_day_limit_still_defers_second_injury(context):
    prior = accept_ankle(context)
    prior["prescription_snapshot"]["allocation_limit"] = 1
    # The stored snapshot is the accepted one-allocation sparring-day ceiling.
    next(row for row in context[0].session_completions[context[1]] if row["id"] == prior["id"])["prescription_snapshot"]["allocation_limit"] = 1
    current = view(context)
    chest = next(i for i in current.open_injuries if i["id"] == context[3]["id"])
    assert chest["rehab_decision"]["schedule"]["state"] == "deferred"
    assert current.live_prescription is None


def test_standalone_identity_uses_only_accepted_owners_and_is_order_independent(context):
    rows = view(context).open_injuries
    decisions = [row["rehab_decision"] for row in rows]
    def identity(items):
        return reconcile_session_prescription(None, decisions=items, injuries=rows, plan_id=context[2],
            training_day=DAY)["session"]["session_id"]
    assert identity(decisions) == identity(list(reversed(decisions)))
    assert identity(decisions[:1]) != identity(decisions[1:])
    deferred = deepcopy(decisions[1])
    deferred["schedule"]["state"] = "deferred"
    assert identity([decisions[0], deferred]) == identity(decisions[:1])


@pytest.mark.parametrize("legacy", [True, False])
@pytest.mark.parametrize("scenario", ["no_due_rehab", "due_rehab", "rehab_only", "started_rehab"])
def test_standalone_rehab_cannot_claim_outstanding_camp_ownership(context, legacy, scenario):
    store, athlete, plan, chest, ankle = context
    camp = dict(session_id="camp", session_type="strength", title="Today's strength", blocks=[
        dict(block_id="safe", block_type="strength", mechanical_load_regions=["shoulder"], contact_level="none", load="low")])
    store.plans[plan]["structured_plan"]["weeks"][0]["days"][0].update(day_type="strength", sessions=[camp])
    if scenario != "rehab_only":
        # The current report permits this non-contact camp work. Retain the
        # original report and make the later report unambiguously current.
        for event in store.injury_episode_events.values():
            if event["injury_id"] == chest["id"]:
                event["created_at"] = "2026-10-02T08:00:00Z"
        report = record_episode_observation(store, athlete_id=athlete, training_day=DAY,
            observation=InjuryEpisodeObservation(injury_id=chest["id"], injury_episode_id=chest["episode_id"],
                event_type="clinician_clearance_report", scopes=["rehab", "training"]))
        store.injury_episode_events[report["id"]]["created_at"] = "2026-10-02T09:00:00Z"
    prior = accept_ankle(context, status="started" if scenario == "started_rehab" else "done", legacy=legacy)
    if scenario == "no_due_rehab":
        decision = resolve_injury_policy({**chest, "rehab_stage": "restore"},
            policies=load_clinical_policies(), bank=get_rehab_bank())
        accepted = reconcile_session_prescription(None, decisions=[decision], plan_id=plan, training_day=DAY)
        store.upsert_session_completion(athlete, dict(plan_id=plan, session_id=accepted["session"]["session_id"],
            training_day=DAY, status="done", prescription_snapshot=accepted))
    before = deepcopy(store.session_completions[athlete])
    current = view(context)
    live = current.live_prescription
    assert current.today.session_scope == "today" and live
    assert store.session_completions[athlete] == before
    if scenario == "started_rehab":
        assert current.today.completion_status == "started" and live["frozen"]
        assert live["session"] == prior["prescription_snapshot"]["session"]
        assert {b["injury_id"] for b in live["session"]["blocks"]} == {ankle["id"]}
    else:
        assert current.today.completion_status == "not_started" and not live["safety_hold"]
        if scenario == "rehab_only":
            assert live["rehab_only"] and live["held_session_id"] == "camp"
            assert live["session"]["session_id"] != "camp"
        else:
            assert not live["rehab_only"] and live["session"]["session_id"] == "camp"
            assert any(b.get("block_id") == "safe" for b in live["session"]["blocks"])
        rehab = [b for b in live["session"]["blocks"] if b["block_type"] == "rehab"]
        assert rehab_allocation_count(rehab) == (0 if scenario == "no_due_rehab" else 1)
        assert {b["injury_id"] for b in rehab} == (set() if scenario == "no_due_rehab" else {chest["id"]})
        execute(context, live)
        assert view(context).live_prescription["frozen"]


def test_no_active_plan_still_reports_effective_current_clearance(context):
    expected = view(context).effective_clinician_clearance
    history = deepcopy(context[0].injury_episode_events)
    context[0].plans.clear()
    current = view(context)
    assert current.active_plan.get("id") is None
    assert current.effective_clinician_clearance == expected
    assert current.effective_clinician_clearance["level"] == "rehab_only"
    assert current.effective_clinician_clearance["limited_by"][0]["injury_id"] == context[3]["id"]
    assert len(current.open_injuries) == 2 and all(i.get("rehab_decision") for i in current.open_injuries)
    assert context[0].injury_episode_events == history
