"""Custom prescriptions use the shared Open Plan execution and history paths."""
import copy
from datetime import date, timedelta
from uuid import uuid4

import pytest

from api.contracts.injury_policy import reconcile_session_prescription
from api.models import PlanRequest
from api.plan_mappers import _map_profile_row
from api.services.active_plan import set_active_plan
from api.services.custom_plans import custom_open_plan_result
from api.services.open_plan_timeline import project_open_structured_plan
from api.services.streaks import qualifying_training_days
from api.services.today_service import _structured_day_for_training_day, resolve_training_day
from api.services.training_library import cache
from api.structured_plan_models import StructuredTrainingPlan
from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}
OTHER = {"Authorization": "Bearer admin-token"}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def body(weekday="Monday"):
    return {"name": "Athlete week", "sessions": [
        {"id": str(uuid4()), "name": "Strength", "weekday": weekday,
         "session_type": "strength_power", "exercises": [
             {"id": str(uuid4()), "origin": "manual", "name": "My squat",
              "notes": "Use my rack", "dose": {"mode": "reps", "sets": 3, "reps": 5,
              "load_or_intensity": "80 kg", "rest_seconds": 90, "tempo": "3-1-X", "per_side": True}},
         ]},
        {"id": str(uuid4()), "name": "Rounds", "weekday": weekday,
         "session_type": "conditioning", "exercises": [
             {"id": str(uuid4()), "origin": "manual", "name": "My bike",
              "dose": {"mode": "intervals", "rounds": 4, "work_seconds": 30, "rest_seconds": 0}},
         ]},
    ]}


@pytest.fixture
def api():
    client, store, _ = _build_client()
    store.create_intake("athlete-1", PlanRequest(athlete={"full_name": "Ari Mensah"}, no_scheduled_fight=True))
    return client, store


def publish(client, prescription):
    response = client.post("/api/custom-plans", headers=AUTH, json=prescription)
    assert response.status_code == 201, response.text
    draft = response.json()
    response = client.post(f"/api/custom-plans/{draft['id']}/open-plan", headers=AUTH)
    assert response.status_code == 200, response.text
    return draft, response.json()["plan_id"]


def current_plan(api):
    client, store = api
    day = resolve_training_day(None)
    weekday = WEEKDAYS[date.fromisoformat(day).weekday()]
    draft, plan_id = publish(client, body(weekday))
    row = store.plans[plan_id]
    # Keep the execution fixture in its current block even when run Fri-Sun.
    monday = date.fromisoformat(day) - timedelta(days=date.fromisoformat(day).weekday())
    row["created_at"] = f"{monday}T12:00:00+00:00"
    row["planning_brief"]["athlete_snapshot"]["plan_creation_weekday"] = "Mon"
    active = client.post(f"/api/plans/{plan_id}/set-active", headers=AUTH)
    assert active.status_code == 200, active.text
    return draft, row, day


def checkin(client, plan_id):
    response = client.post("/api/today/checkin", headers=AUTH, json={
        "plan_id": plan_id, "sleep": "good", "body": "normal", "pain": "none", "phase": "GPP",
    })
    assert response.status_code == 201, response.text


def complete(client, plan_id, session_id, status="started", **extra):
    response = client.post("/api/today/session-completion", headers=AUTH, json={
        "plan_id": plan_id, "session_id": session_id, "status": status, **extra,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_publication_validates_exact_doses_and_uses_shared_detail(api):
    client, store = api
    draft, plan_id = publish(client, body())
    row = store.plans[plan_id]
    plan = StructuredTrainingPlan.model_validate(row["structured_plan"])
    assert row["fight_date"] is None and row["status"] == "ready"
    assert plan.plan_metadata.plan_type == "open_ongoing_system"
    assert store.get_active_plan_id("athlete-1") is None
    assert not store.generation_jobs
    first, second = plan.weeks[0].days[0].sessions
    assert first.blocks[0].athlete_dose == draft["sessions"][0]["exercises"][0]["dose"]
    assert first.blocks[0].rest.value == 90 and second.blocks[0].rest.value == 0
    assert first.blocks[0].prescription_text == "3 × 5 · 80 kg · rest 90s · tempo 3-1-X · per side"
    assert first.blocks[0].load.value == 80 and first.blocks[0].load.unit == "kg"
    assert first.blocks[0].notes == "Use my rack"
    assert not first.blocks[0].progression_rule and not first.blocks[0].why_today
    detail = client.get(f"/api/plans/{plan_id}", headers=AUTH)
    assert detail.status_code == 200, detail.text
    detail = detail.json()
    assert detail["custom_plan_id"] == draft["id"]
    summaries = client.get("/api/plans", headers=AUTH).json()
    assert summaries[0]["custom_plan_id"] == draft["id"]
    assert detail["structured_card_state"]["state"] == "live"
    assert detail["schedule_context"]["projection_status"] == "projected"
    assert len(detail["outputs"]["structured_plan"]["weeks"]) == 4


def test_retry_has_one_published_plan_and_ownership_is_enforced(api):
    client, store = api
    draft, plan_id = publish(client, body())
    endpoint = f"/api/custom-plans/{draft['id']}/open-plan"
    assert client.post(endpoint, headers=AUTH).json()["plan_id"] == plan_id
    assert len(store.plans) == 1
    assert client.post(endpoint, headers=OTHER).status_code == 404
    assert client.post(endpoint).status_code == 401
    assert client.post(f"/api/plans/{plan_id}/set-active", headers=OTHER).status_code == 404


@pytest.mark.parametrize("missing", ["sessions", "weekday", "dose"])
def test_incomplete_drafts_save_but_cannot_execute(api, missing):
    client, store = api
    value = body()
    if missing == "sessions":
        value["sessions"] = []
    elif missing == "weekday":
        value["sessions"][0]["weekday"] = None
    else:
        value["sessions"][0]["exercises"][0]["dose"] = {}
    saved = client.post("/api/custom-plans", headers=AUTH, json=value)
    assert saved.status_code == 201
    assert client.post(f"/api/custom-plans/{saved.json()['id']}/open-plan", headers=AUTH).status_code == 422
    assert not store.plans


def test_sparring_and_support_on_one_day_project_without_duplicates(api):
    client, store = api
    value = body()
    value["sessions"].insert(0, {
        "id": str(uuid4()), "name": "Hard sparring", "weekday": "Monday",
        "session_type": "sparring", "exercises": [],
    })
    _, plan_id = publish(client, value)
    projected, context = project_open_structured_plan(store.plans[plan_id], store.plans[plan_id]["structured_plan"],
                                                     current_training_day="2026-11-09")
    assert context["projection_status"] == "projected"
    assert len(projected["weeks"][0]["days"][0]["sessions"]) == 3
    assert projected["weeks"][0]["days"][0]["today_card"]["coach_led_contact"] == "Hard sparring"


def test_shared_today_completion_logging_and_history(api):
    client, store = api
    _, row, day = current_plan(api)
    plan_id = row["id"]
    matched, _ = _structured_day_for_training_day(row, day)
    sessions = matched["sessions"]
    checkin(client, plan_id)
    today = client.get("/api/today", headers=AUTH)
    assert today.status_code == 200, today.text
    assert today.json()["today"]["next_session"]["session_id"] == sessions[0]["session_id"]
    complete(client, plan_id, sessions[0]["session_id"])
    for session in sessions:
        for block in session["blocks"]:
            logged = client.post("/api/today/exercise-log", headers=AUTH, json={
                "plan_id": plan_id, "block_id": block["block_id"], "status": "as_prescribed",
            })
            assert logged.status_code == 201, logged.text
            assert logged.json()["log"]["prescribed"]["athlete_dose"] == block["athlete_dose"]
            assert logged.json()["log"]["session_id"] == session["session_id"]
    complete(client, plan_id, sessions[0]["session_id"], "done")
    before = copy.deepcopy(store.xp_awards)
    complete(client, plan_id, sessions[1]["session_id"], "done")
    complete(client, plan_id, sessions[0]["session_id"], "done")
    completions = store.session_completions["athlete-1"]
    assert len(completions) == 2 and all(c["status"] == "done" for c in completions)
    assert len(store.exercise_logs) == 2
    assert store.xp_awards == before
    history = client.get("/api/today/session-completions", headers=AUTH).json()
    assert {c["session_title"] for c in history} == {"Strength", "Rounds"}


def test_renewal_preserves_weekdays_doses_ids_and_training_history(api):
    _, store = api
    profile = _map_profile_row(store.profiles["athlete-1"])
    draft = {**body(), "id": str(uuid4()), "incomplete": False}
    result = custom_open_plan_result(draft, profile, training_day="2026-10-12")
    row = {"id": result["plan_id"], "athlete_id": "athlete-1", "created_at": "2026-10-12T12:00:00Z", **result}
    store.plans[row["id"]] = row
    original = copy.deepcopy(row)
    p1, c1 = project_open_structured_plan(row, row["structured_plan"], current_training_day="2026-10-12")
    p2, c2 = project_open_structured_plan(row, row["structured_plan"], current_training_day="2026-11-09")
    assert (c1["block_number"], c2["block_number"]) == (1, 2)
    for old, new in zip(p1["weeks"], p2["weeks"]):
        assert old["days"][0]["weekday"] == new["days"][0]["weekday"] == "Mon"
        assert old["days"][0]["sessions"] == new["days"][0]["sessions"]
        assert date.fromisoformat(new["days"][0]["date"]).weekday() == 0
    store.upsert_session_completion("athlete-1", {
        "plan_id": row["id"], "session_id": p1["weeks"][0]["days"][0]["sessions"][0]["session_id"],
        "training_day": "2026-10-12", "status": "done",
    })
    qualified, _ = qualifying_training_days(store, athlete_id="athlete-1", today=date(2026, 11, 9))
    assert date(2026, 10, 12) in qualified
    assert row == original


def test_edits_keep_original_logs_and_cannot_replace_a_started_day(api):
    client, store = api
    draft, row, day = current_plan(api)
    old = copy.deepcopy(row)
    session = row["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]
    checkin(client, row["id"])
    complete(client, row["id"], session["session_id"])
    saved_completions = copy.deepcopy(store.session_completions)
    value = body(WEEKDAYS[date.fromisoformat(day).weekday()])
    value["name"] = "Edited doses"
    assert client.put(f"/api/custom-plans/{draft['id']}", headers=AUTH, json=value).status_code == 200
    new_id = client.post(f"/api/custom-plans/{draft['id']}/open-plan", headers=AUTH).json()["plan_id"]
    assert new_id != row["id"] and store.plans[row["id"]] == old
    response = client.post(f"/api/plans/{new_id}/set-active", headers=AUTH, json={"overlap_action": "replace"})
    assert response.status_code == 409 and "next training day" in response.text
    assert store.get_active_plan_id("athlete-1") == row["id"]
    assert store.session_completions == saved_completions
    next_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    set_active_plan(store, "athlete-1", new_id, overlap_action="replace", current_training_day=next_day)
    assert store.get_active_plan_id("athlete-1") == new_id
    assert store.plans[row["id"]]["status"] == "archived"


def test_injury_holds_athlete_prescription_without_substitution_or_added_rehab():
    session = {"session_id": "manual", "session_type": "strength_power", "prescription_source": "athlete",
               "blocks": [{"block_id": "lift", "block_type": "strength", "display_name": "My squat", "sets": 3}]}
    live = reconcile_session_prescription(session, plan_id="plan", training_day="2026-10-12", decisions=[{
        "activation": "live", "injury_id": "knee", "injury_episode_id": "episode",
        "outcome": "restricted", "restrictions": {"blocked_regions": ["knee"], "blocked_tags": [], "contact_limit": "full"},
    }])
    assert live["safety_hold"]
    assert live["session"]["blocks"][0]["display_name"] == "My squat"
    assert live["session"]["blocks"][0]["sets"] == 3
    assert all(c["action"] == "held" for c in live["changes"])


def test_catalogue_identity_and_media_survive_shared_mapper(api):
    client, store = api
    record = next(r for r in cache.get().records if r["summary"]["category"] == "training" and r["entry"]["exercise_key"])
    key = record["entry"]["exercise_key"]
    store.exercise_media[key] = {"exercise_key": key, "video_id": "abcdefghijk", "status": "ok", "source": "curated",
                                 "made_for_kids": False}
    from api.services.exercise_media import reset_media_index_cache
    reset_media_index_cache()
    value = body()
    value["sessions"][0]["exercises"][0] = {"id": str(uuid4()), "origin": "catalogue",
        "catalogue_id": record["entry"]["catalogue_id"], "dose": {"mode": "reps", "sets": 2, "reps": 6}}
    try:
        _, plan_id = publish(client, value)
        detail = client.get(f"/api/plans/{plan_id}", headers=AUTH).json()
        block = detail["outputs"]["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
        assert block["exercise_key"] == key and block["catalogue_id"] == record["entry"]["catalogue_id"]
        assert detail["outputs"]["exercise_media"][f"exercise:{key}"]["video_id"] == "abcdefghijk"
    finally:
        reset_media_index_cache()


def test_private_attachment_keeps_owner_scoped_reference_in_shared_cards(api):
    client, store = api
    media_id = str(uuid4())
    store.get_private_media = lambda owner, key: (
        {"id": media_id, "athlete_id": "athlete-1", "provider": "youtube", "video_id": "abcdefghijk",
         "start_s": 2, "end_s": 12} if owner == "athlete-1" and key == media_id else None
    )
    value = body()
    value["sessions"][0]["exercises"][0]["media_id"] = media_id
    _, plan_id = publish(client, value)
    detail = client.get(f"/api/plans/{plan_id}", headers=AUTH).json()
    block = detail["outputs"]["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert block["private_media_id"] == media_id
    assert "url" not in block and block["exercise_key"] is None
    assert client.post("/api/custom-plans", headers=OTHER, json=value).status_code == 404


@pytest.mark.parametrize("scopes", [["rehab"], ["rehab", "training"]])
def test_clinical_clearance_keeps_selected_contact_work_held(scopes):
    episode = str(uuid4())
    session = {"session_id": "sparring", "session_type": "sparring", "title": "Hard sparring",
               "prescription_source": "athlete", "blocks": [
                   {"block_id": "rounds", "block_type": "sparring", "display_name": "My rounds",
                    "rounds": 3, "work": {"value": 180, "unit": "seconds"}, "contact_level": "full"},
               ]}
    before = copy.deepcopy(session)
    live = reconcile_session_prescription(session, plan_id="plan", training_day="2026-10-12", decisions=[],
        injuries=[{"id": "injury", "episode_id": episode, "status": "open",
                   "clinician_clearance": {"episode_id": episode, "scopes": scopes}}])
    assert live["safety_hold"]
    assert live["session"]["blocks"][0]["display_name"] == "My rounds"
    assert live["session"]["blocks"][0]["rounds"] == 3
    assert session == before


def test_activation_refuses_corrupt_custom_structured_contract(api):
    client, store = api
    _, plan_id = publish(client, body())
    store.plans[plan_id]["structured_plan"]["plan_metadata"]["plan_type"] = "invalid"
    assert client.post(f"/api/plans/{plan_id}/set-active", headers=AUTH).status_code == 409
    assert store.get_active_plan_id("athlete-1") is None


def test_generated_cards_cannot_claim_athlete_authority_or_private_media(api):
    from api.services.effective_structured_plan import resolve_effective_structured_plan
    client, store = api
    _, plan_id = publish(client, body())
    row = copy.deepcopy(store.plans[plan_id])
    row["planning_brief"].pop("custom_plan")
    block = row["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block["private_media_id"] = str(uuid4())
    resolved = resolve_effective_structured_plan(row)
    block = resolved["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert "prescription_source" not in resolved["plan_metadata"]
    assert "prescription_source" not in block and "private_media_id" not in block
    assert block["sets"] == 3 and block["load"]["value"] == 80


def test_readiness_and_severe_injury_still_gate_execution(api):
    client, store = api
    _, row, _ = current_plan(api)
    session_id = row["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]["session_id"]
    checkin(client, row["id"])
    store.create_injury_flag("athlete-1", {"body_area": "Left knee", "description": "Severe knee pain",
                                         "severity": "severe", "status": "open", "plan_id": row["id"]})
    response = client.post("/api/today/session-completion", headers=AUTH, json={
        "plan_id": row["id"], "session_id": session_id, "status": "started",
    })
    assert response.status_code == 409
    assert not store.session_completions.get("athlete-1")


@pytest.mark.parametrize("session_type", ["skill", "sparring"])
def test_coach_sessions_without_exercises_use_shared_today_actions(api, session_type):
    client, store = api
    day = resolve_training_day(None)
    value = body(WEEKDAYS[date.fromisoformat(day).weekday()])
    value["sessions"] = [{**value["sessions"][0], "name": "Coach session",
                          "session_type": session_type, "exercises": []}]
    _, plan_id = publish(client, value)
    row = store.plans[plan_id]
    monday = date.fromisoformat(day) - timedelta(days=date.fromisoformat(day).weekday())
    row["created_at"] = f"{monday}T12:00:00+00:00"
    row["planning_brief"]["athlete_snapshot"]["plan_creation_weekday"] = "Mon"
    assert client.post(f"/api/plans/{plan_id}/set-active", headers=AUTH).status_code == 200
    checkin(client, plan_id)
    today = client.get("/api/today", headers=AUTH).json()
    assert today["today"]["next_session"]["title"] == "Coach session"
    session_id = today["today"]["next_session"]["session_id"]
    complete(client, plan_id, session_id)
    complete(client, plan_id, session_id, "done")
    assert client.get("/api/today", headers=AUTH).json()["today"]["completion_status"] == "done"
