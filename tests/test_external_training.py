"""Manual work is independent of prescriptions, but shared readiness evidence."""
import copy
from datetime import date, datetime, timedelta, timezone
import logging
from uuid import uuid4

import pytest

from api.contracts.external_training import ExternalTrainingCreate
from api.contracts.readiness_message import ReadinessCheckin, build_readiness_adjustment
from api.models import PlanRequest
from api.services import today_service
from api.services.sparring_readiness_snapshot import annotate_payload_with_sparring_readiness
from api.services.training_history import create_external_training, training_history
from fightcamp.completed_workload import completed_workload
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context
from fightcamp.plan_pipeline_blocks import _generate_conditioning_blocks
from fightcamp.sparring_readiness import sparring_readiness_flags
from tests.support import _build_client, FakeStore
from tests.test_api_exercise_log import _seed_plan

AUTH = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
DAY = "2026-10-10"


def body(**changes):
    return {"client_request_id": str(uuid4()), "activity": "sparring", "duration_minutes": 60, "effort": "hard", **changes}


@pytest.fixture
def api():
    client, store, _ = _build_client()
    return client, store


def log(api, **changes):
    client, _ = api
    response = client.post("/api/training/sessions", headers=AUTH, json=body(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def history(client, headers=AUTH):
    response = client.get("/api/training/history", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["sessions"]


def test_no_plan_and_rest_day_logging_preserves_prescribed_guards(api):
    client, store = api
    first = log(api)
    assert first["source"] == "external" and first["plan_id"] is None
    _seed_plan(store, blocks=[])
    plan = next(iter(store.plans.values()))
    plan["structured_plan"]["weeks"][0]["days"][0]["sessions"] = []
    before = copy.deepcopy(store.plans)
    second = log(api, activity="roadwork", effort="easy", duration_minutes=25)
    assert len(history(client)) == 2 and first["id"] != second["id"]
    rejected = client.post("/api/today/session-completion", headers=AUTH, json={
        "plan_id": plan["id"], "session_id": "made-up", "status": "done"})
    assert rejected.status_code in {409, 422}
    assert store.plans == before
    assert not store.session_completions.get("athlete-1")


def test_retry_edit_delete_and_delayed_retry(api):
    client, store = api
    payload = body()
    first = client.post("/api/training/sessions", headers=AUTH, json=payload).json()
    retry = client.post("/api/training/sessions", headers=AUTH, json=payload)
    assert retry.status_code == 201 and retry.json()["id"] == first["id"]
    conflict = client.post("/api/training/sessions", headers=AUTH, json={**payload, "duration_minutes": 90})
    assert conflict.status_code == 409
    updated = client.patch(f"/api/training/sessions/{first['id']}", headers=AUTH,
        json={"activity": "boxing", "duration_minutes": 45, "effort": "moderate"})
    assert updated.status_code == 200
    assert updated.json()["training_day"] == first["training_day"]
    assert updated.json()["duration_minutes"] == 45
    assert client.post("/api/training/sessions", headers=AUTH, json=payload).json()["activity"] == "boxing"
    assert len(history(client)) == 1
    for _ in range(2):
        assert client.delete(f"/api/training/sessions/{first['id']}", headers=AUTH).status_code == 204
    assert not history(client)
    assert client.post("/api/training/sessions", headers=AUTH, json=payload).status_code == 410
    assert client.patch(f"/api/training/sessions/{first['id']}", headers=AUTH,
        json={"activity": "sparring", "duration_minutes": 60, "effort": "hard"}).status_code == 404
    assert len(store.external_training_sessions) == 1


def test_ownership_and_authentication(api):
    client, _ = api
    row = log(api)
    assert not history(client, ADMIN)
    assert client.patch(f"/api/training/sessions/{row['id']}", headers=ADMIN,
        json={"activity": "boxing", "duration_minutes": 30, "effort": "easy"}).status_code == 404
    assert client.delete(f"/api/training/sessions/{row['id']}", headers=ADMIN).status_code == 404
    assert client.post("/api/training/sessions", json=body()).status_code == 401
    assert client.get("/api/training/history").status_code == 401


@pytest.mark.parametrize("change", [
    {"duration_minutes": 0}, {"duration_minutes": -1}, {"duration_minutes": 601},
    {"duration_minutes": 60.5}, {"duration_minutes": True}, {"duration_minutes": "60"},
    {"effort": "RPE 8"}, {"effort": "Hard"}, {"activity": "rehab"},
    {"training_day": "2027-01-01"}, {"plan_id": str(uuid4())},
    {"training_day": "2026-02-30"}, {"training_day": "2026-10-09T12:00:00Z"},
    {"training_day": 1791547200}, {"training_day": True},
    {"client_request_id": "not-a-uuid"},
])
def test_invalid_inputs(api, change):
    client, store = api
    response = client.post("/api/training/sessions", headers=AUTH, json=body(**change))
    assert response.status_code == 422
    assert not store.external_training_sessions


@pytest.mark.parametrize("zone,instant,expected", [
    ("America/New_York", "2026-10-11T02:30:00+00:00", "2026-10-10"),
    ("Pacific/Auckland", "2026-10-10T15:00:00+00:00", "2026-10-11"),
    ("Europe/London", "2026-10-25T01:30:00+00:00", "2026-10-24"),
    ("Europe/London", "2026-10-25T03:01:00+00:00", "2026-10-25"),
])
def test_athlete_local_day_rollover_dst_and_retry(zone, instant, expected):
    store = FakeStore()
    request = ExternalTrainingCreate(**body())
    first = create_external_training(store, "athlete-1", zone, request, now=datetime.fromisoformat(instant))
    assert first["training_day"] == expected
    retry = create_external_training(store, "athlete-1", zone, request, now=NOW.replace(day=26))
    assert retry["training_day"] == expected and retry["id"] == first["id"]


def test_backdated_api_logging_and_retry_keep_the_reported_day(api):
    client, _ = api
    current_day = date.fromisoformat(log(api)["training_day"])
    yesterday = (current_day - timedelta(days=1)).isoformat()
    payload = body(training_day=yesterday)
    first = client.post("/api/training/sessions", headers=AUTH, json=payload)
    assert first.status_code == 201 and first.json()["training_day"] == yesterday
    retry = client.post("/api/training/sessions", headers=AUTH, json=payload)
    assert retry.json()["id"] == first.json()["id"]
    assert len(history(client)) == 2
    changed_date = {**payload, "training_day": (current_day - timedelta(days=2)).isoformat()}
    assert client.post("/api/training/sessions", headers=AUTH, json=changed_date).status_code == 409


def test_selected_date_respects_local_rollover_and_rejects_future_work():
    from fastapi import HTTPException
    store = FakeStore()
    instant = datetime.fromisoformat("2026-10-11T02:30:00+00:00")
    # New York is still on the 10th, and Auckland's training day is the 11th.
    future = ExternalTrainingCreate(**body(training_day="2026-10-11"))
    with pytest.raises(HTTPException) as error:
        create_external_training(store, "athlete-1", "America/New_York", future, now=instant)
    assert error.value.status_code == 422 and not store.external_training_sessions
    accepted = create_external_training(store, "athlete-1", "Pacific/Auckland", future, now=instant)
    assert accepted["training_day"] == "2026-10-11"
    before_rollover = datetime.fromisoformat("2026-10-25T01:30:00+00:00")
    with pytest.raises(HTTPException):
        create_external_training(store, "athlete-1", "Europe/London",
            ExternalTrainingCreate(**body(training_day="2026-10-25")), now=before_rollover)


def test_omitted_date_keeps_existing_retry_fingerprint():
    import hashlib
    import json
    store = FakeStore()
    request = ExternalTrainingCreate(**body())
    row = create_external_training(store, "athlete-1", None, request, now=NOW)
    # The exact pre-sport field set: rows logged before sport/session type
    # existed must keep retrying against the same fingerprint.
    original_fields = {"activity": "sparring", "duration_minutes": 60, "effort": "hard"}
    assert row["request_fingerprint"] == hashlib.sha256(json.dumps(original_fields, sort_keys=True).encode()).hexdigest()
    explicit_null = ExternalTrainingCreate(**request.model_dump(mode="json"))
    retry = create_external_training(store, "athlete-1", None, explicit_null, now=NOW + timedelta(days=1))
    assert retry["id"] == row["id"] and retry["training_day"] == DAY


def test_plan_deletion_and_regeneration_do_not_erase_manual_history(api):
    client, store = api
    log(api)
    _seed_plan(store, blocks=[])
    store.plans.clear()
    _seed_plan(store, blocks=[])
    assert len(history(client)) == 1


def test_no_double_counting_or_rehab_xp_side_effects(api):
    client, store = api
    _seed_plan(store, blocks=[])
    plan = next(iter(store.plans.values()))
    day = today_service.resolve_training_day(None)
    store.upsert_session_completion("athlete-1", {"plan_id": plan["id"], "session_id": "s-strength", "training_day": day, "status": "done", "session_rpe": 8})
    store.exercise_logs.extend([{"athlete_id": "athlete-1", "block_id": "a"}, {"athlete_id": "athlete-1", "block_id": "b"}])
    store.injury_flags["athlete-1"] = [{"id": "injury", "status": "open", "blocked_training_tags": ["contact", "impact"]}]
    store.rehab_exposures["exposure"] = {"injury_id": "injury", "stage": "restore", "response": "pending"}
    before = copy.deepcopy((store.xp_awards, store.rehab_exposures, store.injury_flags, store.session_completions, store.plans))
    row = log(api)
    mixed = history(client)
    assert {r["source"] for r in mixed} == {"unlxck", "external"}
    assert len(mixed) == 2
    assert before == (store.xp_awards, store.rehab_exposures, store.injury_flags, store.session_completions, store.plans)
    client.delete(f"/api/training/sessions/{row['id']}", headers=AUTH)
    assert len(history(client)) == 1


def seed_manual(store, *, effort="hard", duration=60, day=DAY):
    return create_external_training(store, "athlete-1", "Europe/London",
        ExternalTrainingCreate(**body(effort=effort, duration_minutes=duration)), now=datetime.fromisoformat(day + "T12:00:00+00:00"))


def adaptive_context(store):
    _seed_plan(store, blocks=[])
    plan = next(iter(store.plans.values()))
    plan["structured_plan"]["weeks"][0]["days"][0] = {
        "date": DAY, "sessions": [{"session_id": "conditioning", "session_type": "conditioning", "title": "Conditioning", "blocks": []}]}
    return today_service._readiness_context_and_status(store, athlete_id="athlete-1", plan_row=plan, training_day=DAY, phase="SPP")[0]


def generation_context(store, monkeypatch):
    from fightcamp import input_parsing
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: NOW)
    request = PlanRequest(athlete={"full_name": "Fighter", "technical_style": ["boxing"], "professional_status": "professional"},
        fight_date="2026-11-20", fatigue_level="low", weekly_training_frequency=4,
        training_availability=["monday", "wednesday", "friday", "sunday"])
    payload = annotate_payload_with_sparring_readiness(request.to_payload(), store=store, athlete_id="athlete-1", training_day=DAY)
    parsed = PlanInput.from_payload(payload)
    return build_runtime_context(plan_input=parsed, random_seed=1, logger=logging.getLogger("test"))


def test_sixty_minutes_hard_sparring_reaches_both_paths_without_rpe_or_contact_inference(monkeypatch):
    store = FakeStore()
    row = seed_manual(store)
    today = adaptive_context(store)
    assert completed_workload(today.recent_sessions, DAY) == {
        "sessions": 1, "demanding_sessions": 1, "actual_minutes": 60, "hard_minutes": 60}
    assert today.recent_sessions[0]["id"] == row["id"]
    assert "session_rpe" not in today.recent_sessions[0]
    decision = build_readiness_adjustment(ReadinessCheckin(sleep="good", body="sharp", pain="none"), today)
    assert decision.decision == "train_as_planned"
    generation = generation_context(store, monkeypatch)
    history_input = generation.training_context.sparring_readiness["training_history"]
    assert history_input["workload"]["hard_minutes"] == 60
    assert history_input["sessions"][0]["effort"] == "hard"
    assert not sparring_readiness_flags(generation.training_context.sparring_readiness)


def test_yesterdays_sixty_minutes_hard_sparring_reaches_both_adaptive_paths(monkeypatch):
    store = FakeStore()
    request = ExternalTrainingCreate(**body(training_day="2026-10-09"))
    row = create_external_training(store, "athlete-1", "Europe/London", request, now=NOW)
    today = adaptive_context(store)
    assert today.recent_sessions[0]["training_day"] == "2026-10-09"
    assert completed_workload(today.recent_sessions, DAY)["hard_minutes"] == 60
    generation = generation_context(store, monkeypatch)
    evidence = generation.training_context.sparring_readiness["training_history"]
    assert evidence["sessions"][0]["id"] == row["id"]
    assert evidence["workload"]["hard_minutes"] == 60
    assert "session_rpe" not in evidence["sessions"][0]
    assert not sparring_readiness_flags(generation.training_context.sparring_readiness)
    retry = create_external_training(store, "athlete-1", "Europe/London", request, now=NOW + timedelta(days=1))
    assert retry["id"] == row["id"] and retry["training_day"] == "2026-10-09"


def test_repeated_workload_with_poor_readiness_uses_existing_today_and_generation_controls(monkeypatch):
    store = FakeStore()
    seed_manual(store, day="2026-10-09", duration=35)
    seed_manual(store)
    context = adaptive_context(store)
    checkin = ReadinessCheckin(sleep="good", body="flat", pain="none", phase="SPP")
    today = build_readiness_adjustment(checkin, context)
    assert today.decision == "modify"
    assert "recent_hard_load_plus_poor_today" in today.triggers
    store.upsert_today_checkin("athlete-1", {"plan_id": next(iter(store.plans)), "training_day": DAY,
        "sleep": "good", "body": "flat", "pain": "none", "phase": "SPP"})
    generation = generation_context(store, monkeypatch)
    captured = []
    def selector(flags):
        captured.append(flags)
        return "", [], [], {}, [], {}
    monkeypatch.setattr("fightcamp.plan_pipeline_blocks.generate_conditioning_block", selector)
    before_phases = copy.deepcopy(generation.phase_weeks)
    _generate_conditioning_blocks(generation)
    assert captured[0]["fatigue"] == "moderate"
    assert captured[0]["sparring_readiness"]["training_history"]["workload"]["actual_minutes"] == 95
    assert all(flags["fatigue"] == "low" for flags in captured[1:])
    assert generation.training_context.fatigue == "low" and generation.phase_weeks == before_phases
    assert not sparring_readiness_flags(generation.training_context.sparring_readiness)


@pytest.mark.parametrize("status", ["planned", "not_started", "started", "skipped"])
def test_planned_or_uncompleted_work_never_counts(status):
    store = FakeStore()
    store.upsert_session_completion("athlete-1", {"plan_id": "p", "session_id": "s", "training_day": DAY, "status": status, "session_rpe": 10})
    rows = training_history(store, "athlete-1")
    assert rows == []
    assert completed_workload([{"status": status, "training_day": DAY, "session_rpe": 10}], DAY)["demanding_sessions"] == 0


def test_history_tab_preserves_skipped_work_and_prescribed_details_without_counting_it(api):
    client, store = api
    _seed_plan(store, blocks=[])
    plan = next(iter(store.plans.values()))
    store.upsert_session_completion("athlete-1", {"plan_id": plan["id"], "session_id": "s-strength", "training_day": DAY,
        "status": "skipped", "notes": "Coach changed training", "modification_reason": "Rest", "session_rpe": 10})
    assert not history(client)
    rows = client.get("/api/training/history?include_skipped=true&limit=200", headers=AUTH).json()["sessions"]
    assert len(rows) == 1 and rows[0]["status"] == "skipped"
    assert rows[0]["notes"] == "Coach changed training" and rows[0]["session_rpe"] == 10
    assert completed_workload(rows, DAY)["demanding_sessions"] == 0


def test_deleted_future_stale_easy_and_other_athlete_do_not_raise_workload():
    store = FakeStore()
    seed_manual(store, day="2026-09-01")
    seed_manual(store, day="2026-10-11")
    seed_manual(store, effort="easy")
    row = seed_manual(store)
    store.delete_external_training_session("athlete-1", row["id"])
    create_external_training(store, "other", None, ExternalTrainingCreate(**body()), now=NOW)
    workload = completed_workload(training_history(store, "athlete-1"), DAY)
    assert workload["demanding_sessions"] == 0 and workload["actual_minutes"] == 60


def test_edit_and_delete_remove_hard_work_from_both_adaptive_inputs(monkeypatch):
    store = FakeStore()
    row = seed_manual(store)
    store.update_external_training_session("athlete-1", row["id"], {"activity": "boxing", "duration_minutes": 30, "effort": "easy"})
    today = adaptive_context(store)
    generation = generation_context(store, monkeypatch)
    assert completed_workload(today.recent_sessions, DAY)["demanding_sessions"] == 0
    assert generation.training_context.sparring_readiness["training_history"]["workload"]["actual_minutes"] == 30
    store.delete_external_training_session("athlete-1", row["id"])
    assert not adaptive_context(store).recent_sessions
    assert generation_context(store, monkeypatch).training_context.sparring_readiness["training_history"]["workload"]["sessions"] == 0


def test_external_history_failure_uses_existing_today_failsafe(monkeypatch):
    store = FakeStore()
    seed_manual(store)
    adaptive_context(store)
    monkeypatch.setattr(store, "list_external_training_sessions", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    plan = next(iter(store.plans.values()))
    _, availability = today_service._readiness_context_and_status(store,
        athlete_id="athlete-1", plan_row=plan, training_day=DAY, phase="SPP")
    assert "completions_unavailable" in availability.reason_codes
    history_input = generation_context(store, monkeypatch).training_context.sparring_readiness["training_history"]
    assert history_input["available"] is False


def test_stale_readiness_does_not_drive_future_conditioning(monkeypatch):
    store = FakeStore()
    seed_manual(store)
    seed_manual(store, day="2026-10-09")
    store.upsert_today_checkin("athlete-1", {"training_day": "2026-10-09", "sleep": "poor", "body": "flat", "pain": "none"})
    captured = []
    monkeypatch.setattr("fightcamp.plan_pipeline_blocks.generate_conditioning_block", lambda flags: (captured.append(flags) or ("", [], [], {}, [], {})))
    _generate_conditioning_blocks(generation_context(store, monkeypatch))
    assert all(flags["fatigue"] == "low" for flags in captured)


def test_health_consent_guard_preserved_while_history_and_delete_remain_available(api):
    client, store = api
    row = log(api)
    store.profiles["athlete-1"]["health_consent_withdrawn_at"] = "2026-10-10T12:00:00Z"
    store.profiles["athlete-1"]["health_data_consent"] = False
    assert client.post("/api/training/sessions", headers=AUTH, json=body()).status_code == 403
    assert client.patch(f"/api/training/sessions/{row['id']}", headers=AUTH,
        json={"activity": "boxing", "duration_minutes": 30, "effort": "easy"}).status_code == 403
    assert len(history(client)) == 1
    assert client.delete(f"/api/training/sessions/{row['id']}", headers=AUTH).status_code == 204


def test_each_manual_mutation_invalidates_existing_today_cache(api):
    from api.services.today_command_cache import remember_today_command, recent_today_command
    client, store = api
    def remember():
        remember_today_command(store, athlete_id="athlete-1", athlete_timezone="", view={"stale": True})
        assert recent_today_command(store, athlete_id="athlete-1", athlete_timezone="") is not None
    def cleared():
        assert recent_today_command(store, athlete_id="athlete-1", athlete_timezone="") is None
    remember()
    row = log(api)
    cleared()
    remember()
    assert client.patch(f"/api/training/sessions/{row['id']}", headers=AUTH,
        json={"activity": "boxing", "duration_minutes": 45, "effort": "easy"}).status_code == 200
    cleared()
    remember()
    assert client.delete(f"/api/training/sessions/{row['id']}", headers=AUTH).status_code == 204
    cleared()


def test_today_read_rechecks_stored_decision_after_manual_logging_and_deletion():
    store = FakeStore()
    adaptive_context(store)
    plan_id = next(iter(store.plans))
    store.upsert_today_checkin("athlete-1", {"plan_id": plan_id, "training_day": DAY,
        "sleep": "good", "body": "flat", "pain": "none", "phase": "SPP",
        "recommendation_state": "train_as_planned", "recommendation_triggers": []})
    before = copy.deepcopy((store.plans, store.today_checkins))
    first = seed_manual(store)
    second = seed_manual(store)
    view = today_service.build_today_command_view(store, athlete_id="athlete-1", athlete_timezone="Europe/London", now=NOW)
    assert "Heavy recent load" in view.today.recommendation_trigger_labels
    assert view.today.recommendation_state != "train_as_planned"
    assert (store.plans, store.today_checkins) == before
    for row in (first, second):
        store.delete_external_training_session("athlete-1", row["id"])
    view = today_service.build_today_command_view(store, athlete_id="athlete-1", athlete_timezone="Europe/London", now=NOW)
    assert "Heavy recent load" not in view.today.recommendation_trigger_labels
