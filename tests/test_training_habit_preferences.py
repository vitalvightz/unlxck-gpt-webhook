"""Routines are explicit profile preferences, never completed training evidence."""
import copy
import pytest
from api.models import ProfileUpdateRequest
from api.store import SupabaseAppStore
from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}
DECISION = {"weekday": 0, "activity": "boxing", "duration_minutes": 60, "state": "confirmed", "decided_on": "2026-10-19"}


def payload(revision=0, **changes):
    return {"training_habits": {"enabled": True, "decisions": [{**DECISION, **changes}]}, "training_habits_revision": revision}


def test_confirmation_persists_and_stale_device_cannot_overwrite_or_create_evidence():
    client, store, _ = _build_client()
    other = copy.deepcopy(store.profiles["admin-1"])
    response = client.put("/api/me", headers=AUTH, json=payload())
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["training_habits"]["decisions"] == [DECISION]
    assert response.json()["profile"]["training_habits_revision"] == 1
    assert client.get("/api/me", headers=AUTH).json()["profile"]["training_habits_revision"] == 1
    assert client.put("/api/me", headers=AUTH, json=payload(activity="strength")).status_code == 409
    assert store.profiles["athlete-1"]["training_habits"]["decisions"] == [DECISION]
    assert store.profiles["admin-1"] == other
    assert not store.external_training_sessions
    assert client.get("/api/training/history", headers=AUTH).json()["sessions"] == []
    assert client.put("/api/me", json=payload()).status_code == 401
    updated = client.put("/api/me", headers=AUTH, json=payload(1, duration_minutes=45))
    assert updated.status_code == 200
    assert updated.json()["profile"]["training_habits"]["decisions"][0]["duration_minutes"] == 45


@pytest.mark.parametrize("change", [{"weekday": -1}, {"weekday": 7}, {"weekday": True}, {"duration_minutes": 0},
    {"duration_minutes": 601}, {"duration_minutes": 45.5}, {"activity": "contact_clearance"}, {"state": "authorised"}, {"decided_on": "bad"}])
def test_invalid_routines_are_rejected(change):
    client, _, _ = _build_client()
    assert client.put("/api/me", headers=AUTH, json=payload(**change)).status_code == 422


def test_revision_pair_and_unique_bounded_decisions():
    from pydantic import ValidationError
    for body in [
        {"training_habits": {"enabled": True, "decisions": []}},
        {"training_habits_revision": 0},
        {"training_habits": {"enabled": True, "decisions": [DECISION, DECISION]}, "training_habits_revision": 0},
        {"training_habits": {"enabled": True, "decisions": [DECISION] * 43}, "training_habits_revision": 0},
    ]:
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(**body)


def test_consent_withdrawal_blocks_learning_preferences_but_allows_pause():
    client, store, _ = _build_client()
    store.profiles["athlete-1"]["health_data_consent"] = False
    store.profiles["athlete-1"]["health_consent_withdrawn_at"] = "2026-10-18T12:00:00Z"
    assert client.put("/api/me", headers=AUTH, json=payload()).status_code == 403
    assert client.put("/api/me", headers=AUTH, json={"training_habits": {"enabled": False, "decisions": []}, "training_habits_revision": 0}).status_code == 200


def test_manual_history_filter_excludes_prescribed_rows():
    from tests.test_api_exercise_log import _seed_plan
    client, store, _ = _build_client()
    plan = _seed_plan(store, blocks=[])
    store.upsert_session_completion("athlete-1", {"plan_id": plan, "session_id": "s-strength", "training_day": "2026-10-10", "status": "done"})
    body = {"activity": "boxing", "duration_minutes": 60, "effort": "hard", "client_request_id": "00000000-0000-4000-8000-000000000045"}
    assert client.post("/api/training/sessions", headers=AUTH, json=body).status_code == 201
    rows = client.get("/api/training/history?manual_only=true&limit=200", headers=AUTH).json()["sessions"]
    assert len(rows) == 1 and rows[0]["source"] == "external"


def test_real_store_filters_profile_owner_and_compares_revision():
    from types import SimpleNamespace
    calls = []
    class Query:
        def update(self, fields):
            calls.append(("update", fields))
            return self
        def eq(self, key, value):
            calls.append(("eq", key, value))
            return self
        def execute(self): return SimpleNamespace(data=[])
    class Client:
        def table(self, table):
            calls.append(("table", table))
            return Query()
    store = SupabaseAppStore.__new__(SupabaseAppStore)
    store.client = Client()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        store.update_profile("athlete-1", ProfileUpdateRequest(**payload()))
    assert error.value.status_code == 409
    assert ("eq", "id", "athlete-1") in calls
    assert ("eq", "training_habits_revision", 0) in calls
    assert next(item[1] for item in calls if item[0] == "update")["training_habits_revision"] == 1
