"""Tracking-only rehabilitation uses real policy, completion and evidence paths."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.contracts.clinician_clearance import clinician_clears_baseline, permits_rehabilitation_stage
from api.contracts.injury_policy import resolve_injury_policy
from api.contracts.rehab_stage import resolve_rehab_stage
from api.services import today_service
from api.services.injury_episode_service import InjuryEpisodeObservation, record_episode_observation, apply_episode_observations
from api.services.rehab_completion_service import build_rehab_response_contexts, record_reported_permission_rehab
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank
from tests.support import FakeStore

NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


@pytest.fixture
def athlete(monkeypatch):
    monkeypatch.setattr("tests.support._now", lambda: NOW.isoformat())
    store, owner = FakeStore(), str(uuid4())
    store.upsert_today_checkin(owner, dict(plan_id=None, training_day=NOW.date().isoformat(),
        recommendation_state="train_as_planned", pain="none", body="good"))
    return store, owner


def injury(athlete, area="Chest", kind="strain", **fields):
    from api.contracts.rehab_exposure import injury_evidence_identity
    store, owner = athlete
    return store.create_injury_flag(owner, {**injury_evidence_identity(area, kind),
        "body_area": area, "description": kind, "severity": "mild", "status": "open", **fields})


def permission(athlete, row, level="sport_specific", scopes=None):
    return record_episode_observation(athlete[0], athlete_id=athlete[1], training_day=NOW.date().isoformat(),
        observation=InjuryEpisodeObservation(injury_id=row["id"], injury_episode_id=row["episode_id"],
            event_type="clinician_clearance_report", scopes=scopes or ["rehab", "training", "contact"],
            rehabilitation_permission={"schema_version": 1, "level": level}))


def view(athlete, now=NOW):
    return today_service.build_today_command_view(athlete[0], athlete_id=athlete[1], athlete_timezone="UTC", now=now)


def complete(athlete, live, status="done", **fields):
    return today_service.upsert_session_completion(athlete[0], athlete_id=athlete[1], athlete_timezone="UTC", now=NOW,
        payload=dict(plan_id=None, session_id=live["session"]["session_id"], status=status,
            prescription_revision=live["revision"], **fields))


def test_thevital1_tracking_only_shoulder_sprain_and_knee_swelling(athlete):
    shoulder = injury(athlete, "Left shoulder", "sprain", body_region="shoulder", side="left")
    knee = injury(athlete, "Right knee", "swelling", body_region="knee", side="right")
    assert resolve_rehab_stage(knee).medical_gate
    before = deepcopy(athlete[0].injury_flags)
    for row in (shoulder, knee):
        permission(athlete, row)
    current = view(athlete)
    assert not current.active_plan.get("id") and not athlete[0].plans
    assert athlete[0].injury_flags == before  # reports never mutate athlete injury records
    assert current.effective_clinician_clearance["level"] == "train_contact"
    for row in current.open_injuries:
        assert row["rehab_decision"]["outcome"] != "medical_review"
        assert not row["rehab_medical_gate"]
        assert clinician_clears_baseline(row, contact=True)
        assert permits_rehabilitation_stage(row, "return")
        assert row["rehab_decision"]["stage"] in {"calm", "restore"}
        assert row["clinician_clearance"]["externally_verified"] is False


@pytest.mark.parametrize("level,allowed", [("not_cleared", []), ("gentle_recovery", ["calm", "restore"]),
    ("loading", ["calm", "restore", "load"]), ("sport_specific", ["calm", "restore", "load", "dynamic", "return"])])
@pytest.mark.parametrize("scopes", [["rehab"], ["rehab", "training"], ["rehab", "training", "contact"]])
def test_reported_levels_are_independent_authoritative_permissions(athlete, level, allowed, scopes):
    row = injury(athlete)
    event = permission(athlete, row, level, scopes)
    reported = apply_episode_observations(row, [event], as_of=NOW)
    for stage in ("calm", "restore", "load", "dynamic", "return"):
        assert permits_rehabilitation_stage(reported, stage) == (stage in allowed)
    assert clinician_clears_baseline(reported) == ("training" in scopes)
    assert clinician_clears_baseline(reported, contact=True) == ("contact" in scopes)
    assert resolve_rehab_stage(reported).stage == resolve_rehab_stage(row).stage


@pytest.mark.parametrize("description", ["swelling with fever", "rapidly increasing swelling", "swelling cold foot",
    "swelling cannot bear weight", "swelling chest pain breathlessness"])
def test_permission_never_removes_explicit_emergency_signals(athlete, description):
    row = injury(athlete, "Right knee", description, body_region="knee", side="right", injury_type="swelling")
    permission(athlete, row)
    current = view(athlete).open_injuries[0]
    assert current["rehab_medical_gate"]
    assert current["rehab_decision"]["outcome"] == "medical_review"
    assert not view(athlete).live_prescription


def test_standalone_rehab_completes_once_with_episode_evidence(athlete):
    row = injury(athlete)
    current = view(athlete)
    live = current.live_prescription
    assert live and live["rehab_only"] and not live["safety_hold"]
    assert current.open_injuries[0]["rehab_decision"]["schedule"]["state"] == "due"
    complete(athlete, live, "started")
    resumed = view(athlete).live_prescription
    assert resumed["frozen"] and resumed["revision"] == live["revision"]
    done = complete(athlete, resumed, rehab_performance="done_as_shown")
    prompts, contexts = build_rehab_response_contexts(athlete[0], athlete_id=athlete[1], plan_row={"id": None},
        training_day=done["training_day"], session_id=done["session_id"], completion=done)
    assert prompts and contexts[0]["injury_episode_id"] == row["episode_id"]
    done.update(athlete[0].initialize_session_completion_rehab_contexts(athlete[1], completion_id=done["id"],
        plan_id=None, session_id=done["session_id"], training_day=done["training_day"], contexts=contexts))
    first = record_reported_permission_rehab(athlete[0], athlete_id=athlete[1], plan_row={"id": None}, completion=done)
    retry = record_reported_permission_rehab(athlete[0], athlete_id=athlete[1], plan_row={"id": None}, completion=done)
    assert first and first == retry and len(athlete[0].rehab_exposures) == len(first)
    assert str(first[0].injury_episode_id) == row["episode_id"]
    assert len(athlete[0].session_completions[athlete[1]]) == 1
    assert view(athlete).open_injuries[0]["rehab_decision"]["schedule"]["state"] == "already_completed"
    assert view(athlete).live_prescription is None
    retry = complete(athlete, live, rehab_performance="done_as_shown")
    assert not retry["_entered_completed_status"]


def test_no_published_stage_is_content_gap_not_clearance_hold():
    row = dict(id=str(uuid4()), episode_id=str(uuid4()), athlete_id=str(uuid4()), status="open", severity="mild",
        body_area="Left wrist", body_region="wrist", canonical_location="wrist", injury_type="impingement", rehab_stage="restore")
    result = resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank())
    assert result["outcome"] == "unsupported_prescription" and result["prescription"] is None
    assert result["summary"] == "No rehab exercises available for this stage yet."


def test_standalone_rejects_forged_or_stale_work(athlete):
    injury(athlete)
    live = view(athlete).live_prescription
    with pytest.raises(HTTPException):
        complete(athlete, {**live, "revision": "0" * 64}, rehab_performance="done_as_shown")
    with pytest.raises(HTTPException):
        complete(athlete, {**live, "session": {**live["session"], "session_id": "fake"}}, rehab_performance="done_as_shown")
    row = athlete[0].get_today_checkin(athlete[1], None, NOW.date().isoformat())
    athlete[0].upsert_today_checkin(athlete[1], {**row, "neurological_symptoms": True})
    assert view(athlete).live_prescription is None or view(athlete).live_prescription["safety_hold"]
    with pytest.raises(HTTPException):
        complete(athlete, live, rehab_performance="done_as_shown")


def test_two_episodes_keep_independent_permissions_and_completion(athlete):
    chest = injury(athlete)
    knee = injury(athlete, "Right knee", "swelling", body_region="knee", side="right")
    permission(athlete, chest, "gentle_recovery", ["rehab", "training"])
    permission(athlete, knee)
    current = view(athlete)
    assert current.effective_clinician_clearance["level"] == "train_no_contact"
    blocks = current.live_prescription["session"]["blocks"]
    assert {(b["injury_id"], b["injury_episode_id"]) for b in blocks} <= {(chest["id"], chest["episode_id"]), (knee["id"], knee["episode_id"])}
    complete(athlete, current.live_prescription, rehab_performance="done_as_shown")
    completed_owners = {b["injury_id"] for b in blocks}
    for row in view(athlete).open_injuries:
        assert (row["rehab_decision"]["schedule"]["state"] == "already_completed") == (row["id"] in completed_owners)


def test_two_available_routines_keep_distinct_stages_and_evidence_owners(athlete):
    chest = injury(athlete, latest_reported_status="improving", latest_reported_at=NOW.isoformat(),
        created_at="2026-10-19T12:00:00Z")
    ankle = injury(athlete, "Right ankle", "sprain")
    permission(athlete, chest, "gentle_recovery", ["rehab", "training"])
    permission(athlete, ankle)
    current = view(athlete)
    decisions = {row["id"]: row["rehab_decision"] for row in current.open_injuries}
    assert decisions[chest["id"]]["stage"] == "restore"
    assert decisions[ankle["id"]]["stage"] == "calm"
    blocks = current.live_prescription["session"]["blocks"]
    assert {(b["injury_id"], b["injury_episode_id"]) for b in blocks} == {
        (chest["id"], chest["episode_id"]), (ankle["id"], ankle["episode_id"])}
    done = complete(athlete, current.live_prescription, rehab_performance="done_as_shown")
    _, contexts = build_rehab_response_contexts(athlete[0], athlete_id=athlete[1], plan_row={"id": None},
        training_day=done["training_day"], session_id=done["session_id"], completion=done)
    assert {c["injury_episode_id"] for c in contexts} == {chest["episode_id"], ankle["episode_id"]}
    assert len({c["response_group_id"] for c in contexts}) == 2


def test_tracking_injury_updates_preserve_the_plan_free_checkin(athlete):
    today_service.submit_today_injury_checkin(athlete[0], athlete_id=athlete[1], athlete_timezone="UTC", now=NOW,
        payload={"injuries": [{"body_area": "Left shoulder", "description": "sprain", "severity": "mild", "status": "ongoing"}]})
    checkin = athlete[0].get_today_checkin(athlete[1], None, NOW.date().isoformat())
    assert checkin["phase"] is None and checkin["plan_id"] is None


def test_missing_readiness_is_an_explicit_schedule_hold(athlete):
    injury(athlete)
    athlete[0].today_checkins.clear()
    current = view(athlete)
    assert current.open_injuries[0]["rehab_decision"]["schedule"]["state"] == "held"
    assert "check-in" in current.open_injuries[0]["rehab_decision"]["schedule"]["reason"]
    assert current.live_prescription is None


def tracking_consumer(monkeypatch):
    from tests.test_rehab_experience import consumer, CHEST
    journey, client = consumer(monkeypatch, CHEST)
    journey.store.plans.clear()
    journey.store.set_active_plan_id(journey.athlete, None)
    journey.store.upsert_today_checkin(journey.athlete, dict(plan_id=None, training_day=journey.day,
        recommendation_state="train_as_planned", pain="none", body="good"))
    return journey, client


def test_authenticated_completion_route_records_standalone_evidence_once(monkeypatch):
    from tests.test_rehab_experience import HEADERS, view as api_view
    journey, client = tracking_consumer(monkeypatch)
    current = api_view(client)
    live = current["live_prescription"]
    assert live and not live["safety_hold"]
    payload = dict(plan_id=None, session_id=live["session"]["session_id"], status="done",
        prescription_revision=live["revision"], rehab_performance="done_as_shown", rehab_tracking="injury_checkin")
    for _ in range(2):
        response = client.post("/api/today/session-completion", headers=HEADERS, json=payload)
        assert response.status_code == 201, response.text
        assert response.json()["completion"]["plan_id"] is None
        assert journey.store.get_session_completion(journey.athlete, payload["session_id"], journey.day)["rehab_response_contexts"]
    assert len(journey.store.session_completions[journey.athlete]) == 1
    assert journey.store.rehab_exposures
    assert len({str(row["event_json"]["injury_episode_id"]) for row in journey.store.rehab_exposures.values()}) == 1
    assert api_view(client)["open_injuries"][0]["rehab_decision"]["schedule"]["state"] == "already_completed"


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    from tests.test_rehab_experience import HEADERS, view as api_view
    with pytest.MonkeyPatch.context() as patch:
        journey, client = tracking_consumer(patch)
        profile = client.get("/api/me", headers=HEADERS).json()
        fixture = {"available": {"view": api_view(client), "profile": profile}}
        journey.store.injury_flags[journey.athlete] = []
        for area, kind in [("Left shoulder", "sprain"), ("Right knee", "swelling")]:
            today_service.submit_today_injury_checkin(journey.store, athlete_id=journey.athlete,
                athlete_timezone="UTC", now=journey.now, payload={"injuries": [
                    {"body_area": area, "description": kind, "severity": "mild", "status": "ongoing"}]})
            row = journey.store.injury_flags[journey.athlete][-1]
            record_episode_observation(journey.store, athlete_id=journey.athlete, training_day=journey.day,
                observation=InjuryEpisodeObservation(injury_id=row["id"], injury_episode_id=row["episode_id"],
                    event_type="clinician_clearance_report", scopes=["rehab", "training", "contact"],
                    rehabilitation_permission={"schema_version": 1, "level": "sport_specific"}))
        fixture["tracking_only"] = {"view": api_view(client), "profile": profile}
        Path(sys.argv[1]).write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
