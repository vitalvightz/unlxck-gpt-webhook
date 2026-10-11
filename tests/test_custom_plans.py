"""Custom drafts: owner CRUD, exact catalogue identity, order and dose bounds."""
import copy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from api.services.training_library import cache
from api.services.exercise_media import reset_media_index_cache
from api.store import SupabaseAppStore
from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}
OTHER = {"Authorization": "Bearer admin-token"}
URL = "/api/custom-plans"


@pytest.fixture(scope="module")
def identities():
    records = cache.get().records
    return {category: [record["entry"]["catalogue_id"] for record in records
                       if record["summary"]["category"] == category][:2]
            for category in ("training", "rehab", "learn")}


@pytest.fixture
def api():
    client, store, _ = _build_client()
    reset_media_index_cache()
    yield client, store
    reset_media_index_cache()


def payload(identities):
    return {"name": "My weekly plan", "sessions": [
        {"id": str(uuid4()), "name": "Strength", "weekday": "Monday", "exercises": [
            {"id": str(uuid4()), "catalogue_id": identity, "dose": {"mode": "reps", "sets": 3, "reps": 5, "rest_seconds": 90}}
            for identity in identities["training"]]},
        {"id": str(uuid4()), "name": "Conditioning", "weekday": "Tuesday", "exercises": []},
    ]}


def test_owner_crud_preserves_order_identity_and_generated_state(api, identities):
    client, store = api
    before = copy.deepcopy(store.plans)
    body = payload(identities)
    key = cache.get().by_id[identities["training"][0]]["entry"]["exercise_key"]
    store.exercise_media[key] = {"exercise_key": key, "video_id": "abcdefghijk", "made_for_kids": False, "status": "ok", "source": "curated"}
    created = client.post(URL, headers=AUTH, json=body)
    assert created.status_code == 201, created.text
    plan = created.json()
    path = f"{URL}/{plan['id']}"
    assert plan["kind"] == "self_directed" and plan["incomplete"]
    assert plan["sessions"][0]["exercises"][0]["snapshot"]["media"]["video_id"] == "abcdefghijk"
    for expected, exercise in zip(body["sessions"][0]["exercises"], plan["sessions"][0]["exercises"]):
        assert exercise["catalogue_id"] == expected["catalogue_id"] == exercise["snapshot"]["catalogue_id"]
        assert exercise["snapshot"]["source_revision"] and exercise["snapshot"]["row_revision"]
        assert exercise["snapshot"]["prescription_allowed"] is False
        preview = client.get("/api/training/library/entry", headers=AUTH, params={"catalogue_id": exercise["catalogue_id"]}).json()
        assert exercise["snapshot"]["exercise_key"] == preview["exercise_key"]
        assert exercise["snapshot"]["media"] == preview["media"]
    assert client.get(path, headers=AUTH).json() == plan
    assert client.get(URL, headers=AUTH).json() == [plan]
    assert client.get(URL, headers=OTHER).json() == []
    assert client.get(path, headers=OTHER).status_code == 404
    assert client.put(path, headers=OTHER, json=body).status_code == 404
    assert client.delete(path, headers=OTHER).status_code == 404
    body["name"] = "Edited weekly plan"
    body["sessions"].reverse()
    body["sessions"][1]["exercises"].reverse()
    body["sessions"][1]["exercises"][0]["dose"] = {"mode": "duration", "duration_seconds": 30, "rest_seconds": 0}
    edited = client.put(path, headers=AUTH, json=body)
    assert edited.status_code == 200, edited.text
    reopened = client.get(path, headers=AUTH).json()
    assert reopened["name"] == body["name"]
    assert [session["id"] for session in reopened["sessions"]] == [session["id"] for session in body["sessions"]]
    assert [exercise["id"] for exercise in reopened["sessions"][1]["exercises"]] == [exercise["id"] for exercise in body["sessions"][1]["exercises"]]
    assert reopened["sessions"][1]["exercises"][0]["dose"]["duration_seconds"] == 30
    assert client.delete(path, headers=AUTH).status_code == 204
    assert client.get(path, headers=AUTH).status_code == 404
    assert client.get(URL, headers=AUTH).json() == []
    assert store.plans == before
    assert not store.session_completions and not store.external_training_sessions


@pytest.mark.parametrize("category", ["rehab", "learn", "missing"])
def test_only_exact_training_identities_are_addable(api, identities, category):
    client, store = api
    body = payload(identities)
    body["sessions"][0]["exercises"][0]["catalogue_id"] = identities[category][0] if category != "missing" else "made-up"
    assert client.post(URL, headers=AUTH, json=body).status_code == 422
    assert not store.custom_plans


@pytest.mark.parametrize("dose", [
    {"sets": 0}, {"sets": True}, {"reps": -1}, {"reps": 2.5}, {"reps": "5"},
    {"duration_seconds": 30}, {"rest_seconds": -1}, {"rest_seconds": 3601},
    {"mode": "duration", "duration_seconds": 0}, {"mode": "duration", "reps": 5},
    {"mode": "minutes"}, {"load_or_intensity": "x" * 81},
])
def test_invalid_doses_rejected_without_writes(api, identities, dose):
    client, store = api
    body = payload(identities)
    body["sessions"][0]["exercises"][0]["dose"] = dose
    assert client.post(URL, headers=AUTH, json=body).status_code == 422
    assert not store.custom_plans


def test_incomplete_drafts_and_unassigned_days_persist(api, identities):
    client, _ = api
    body = payload(identities)
    body["sessions"] = body["sessions"][:1]
    body["sessions"][0]["weekday"] = None
    exercise = body["sessions"][0]["exercises"][0]
    exercise["dose"] = {}
    saved = client.post(URL, headers=AUTH, json=body).json()
    assert saved["incomplete"] and saved["sessions"][0]["exercises"][0]["incomplete"]
    assert saved["sessions"][0]["exercises"][0]["dose"]["reps"] is None
    assert saved["sessions"][0]["weekday"] is None
    exercise["dose"] = {"mode": "duration", "duration_seconds": 45}
    complete = client.put(f"{URL}/{saved['id']}", headers=AUTH, json=body).json()
    assert not complete["incomplete"]


def test_cannot_forge_owner_snapshot_or_execution_fields(api, identities):
    client, store = api
    for field in ("athlete_id", "kind", "plan_id", "active"):
        assert client.post(URL, headers=AUTH, json={**payload(identities), field: "forged"}).status_code == 422
    body = payload(identities)
    body["sessions"][0]["exercises"][0]["snapshot"] = {"name": "forged"}
    assert client.post(URL, headers=AUTH, json=body).status_code == 422
    body = payload(identities)
    body["sessions"][0]["exercises"][1]["id"] = body["sessions"][0]["exercises"][0]["id"]
    assert client.post(URL, headers=AUTH, json=body).status_code == 422
    assert not store.custom_plans


def test_all_routes_require_authentication(api, identities):
    client, _ = api
    path = f"{URL}/{uuid4()}"
    assert client.get(URL).status_code == 401
    assert client.get(path).status_code == 401
    assert client.post(URL, json=payload(identities)).status_code == 401
    assert client.put(path, json=payload(identities)).status_code == 401
    assert client.delete(path).status_code == 401


@pytest.mark.parametrize("operation", ["create", "list", "get", "update", "delete"])
def test_privileged_store_queries_are_owner_scoped(operation):
    client = MagicMock()
    query = client.table.return_value
    for method in ("select", "insert", "update", "delete", "eq", "order", "limit"):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "plan", "athlete_id": "owner"}])
    store = SupabaseAppStore(client=client, admin_emails=set())
    fields = {"name": "Plan", "sessions": [], "incomplete": True, "athlete_id": "attacker", "kind": "active"}
    if operation == "create":
        store.create_custom_plan("owner", fields)
        query.insert.assert_called_once_with({"name": "Plan", "sessions": [], "incomplete": True, "athlete_id": "owner"})
    elif operation == "list":
        store.list_custom_plans("owner")
        query.eq.assert_called_once_with("athlete_id", "owner")
    else:
        getattr(store, f"{operation}_custom_plan")("owner", "plan", *([fields] if operation == "update" else []))
        assert [call.args for call in query.eq.call_args_list] == [("athlete_id", "owner"), ("id", "plan")]
        if operation == "update":
            query.update.assert_called_once_with({"name": "Plan", "sessions": [], "incomplete": True})
    client.table.assert_called_once_with("custom_training_plans")
