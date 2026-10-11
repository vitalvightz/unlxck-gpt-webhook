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


def test_manual_and_legacy_round_trip(api, identities):
    client, store = api
    before = copy.deepcopy(store.plans)
    body = payload(identities)
    manual = {
        "id": str(uuid4()),
        "origin": "manual",
        "name": "My bag rounds",
        "equipment": "Heavy bag",
        "notes": "My practice",
        "dose": {
            "mode": "intervals",
            "rounds": 5,
            "work_seconds": 300,
            "rest_seconds": 30,
            "rpe": 7,
        },
    }
    body["sessions"][0]["exercises"].insert(0, manual)
    created = client.post(URL, headers=AUTH, json=body)
    assert created.status_code == 201, created.text
    plan = created.json()
    path = f"{URL}/{plan['id']}"
    assert plan["sessions"][0]["exercises"][0]["origin"] == "manual"
    assert "snapshot" not in plan["sessions"][0]["exercises"][0]
    body["sessions"][0]["exercises"].reverse()
    manual["name"] = "Renamed rounds"
    assert client.put(path, headers=AUTH, json=body).status_code == 200
    assert client.get(path, headers=OTHER).status_code == 404
    assert client.put(path, headers=OTHER, json=body).status_code == 404
    assert client.delete(path, headers=OTHER).status_code == 404
    # Persisted PR #2831 rows have neither origin nor new optional dose fields.
    row = store.custom_plans[plan["id"]]
    for session in row["sessions"]:
        for exercise in session["exercises"]:
            if exercise["origin"] == "catalogue":
                exercise.pop("origin")
                for field in (
                    "rounds",
                    "work_seconds",
                    "rpe",
                    "tempo",
                    "per_side",
                    "distance",
                    "distance_unit",
                    "prescription",
                ):
                    exercise["dose"].pop(field, None)
    assert client.get(path, headers=AUTH).status_code == 200
    assert client.get(URL, headers=AUTH).status_code == 200
    body["sessions"][0]["exercises"] = [manual]
    assert client.put(path, headers=AUTH, json=body).status_code == 200
    for field in (
        "catalogue_id",
        "snapshot",
        "verified_goals",
        "athlete_id",
        "execution_allowed",
    ):
        invalid = copy.deepcopy(body)
        invalid["sessions"][0]["exercises"][0][field] = "injected"
        assert client.put(path, headers=AUTH, json=invalid).status_code == 422
    assert store.plans == before


@pytest.mark.parametrize(
    "raw,mode,seconds",
    [
        (
            {
                "rounds": 5,
                "work_sec": 300,
                "rest_sec": 30,
                "total_minutes": 27,
                "duration": "5 x 5min rounds, 30s rest",
                "rpe": 7,
            },
            "intervals",
            300,
        ),
        ({"total_minutes": 30}, "duration", 1800),
        ({"duration": "90 seconds"}, "duration", 90),
        ({"duration": "10 min", "rpe": 6}, "duration", 600),
        ({"sets": 3, "reps": 8, "rest_sec": 90}, "reps", None),
        (
            {
                "rounds": 5,
                "work_sec": 300,
                "rest_sec": 30,
                "duration": "3x5min, 30s rest",
            },
            "text",
            None,
        ),
        ({"rounds": 5, "work_sec": 300}, "text", None),
        ({"rounds": "5", "total_minutes": 30}, "text", None),
        (
            {
                "rounds": 5,
                "work_sec": 300,
                "rest_sec": 30,
                "prescription": "3x5min, 30s rest",
            },
            "text",
            None,
        ),
        ({}, None, None),
    ],
)
def test_source_suggestions_current_explicit_evidence(
    api, identities, monkeypatch, raw, mode, seconds
):
    client, _ = api
    identity = identities["training"][0]
    record = copy.deepcopy(cache.get().by_id[identity])
    record["entry"]["raw"] = raw
    monkeypatch.setattr(cache, "get", lambda: SimpleNamespace(by_id={identity: record}))
    response = client.get(
        f"{URL}/source-suggestion", params={"catalogue_id": identity}, headers=AUTH
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["source_revision"] and result["row_revision"]
    assert (result["dose"]["mode"] if result["dose"] else None) == mode
    if seconds:
        assert (
            result["dose"][
                "work_seconds" if mode == "intervals" else "duration_seconds"
            ]
            == seconds
        )
    assert (
        client.get(
            f"{URL}/source-suggestion", params={"catalogue_id": identity}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "dose",
    [
        {"mode": "intervals", "rounds": 0},
        {"mode": "intervals", "work_seconds": 1.5},
        {"mode": "duration", "rounds": 5},
        {"mode": "text", "reps": 5},
        {"mode": "reps", "rpe": 11},
        {"mode": "duration", "distance": -1},
        {"mode": "duration", "distance_unit": "unknown"},
    ],
)
def test_new_dose_validation(api, dose):
    client, _ = api
    body = {
        "name": "Draft",
        "sessions": [
            {
                "id": str(uuid4()),
                "name": "Practice",
                "exercises": [
                    {
                        "id": str(uuid4()),
                        "origin": "manual",
                        "name": "My practice",
                        "dose": dose,
                    }
                ],
            }
        ],
    }
    assert client.post(URL, headers=AUTH, json=body).status_code == 422
