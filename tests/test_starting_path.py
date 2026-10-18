"""Starting preferences persist without changing plans or training evidence."""
import copy

import pytest

from tests.support import _build_client

AUTH = {"Authorization": "Bearer athlete-token"}


@pytest.mark.parametrize("path", ["tracking_first", "plan_first"])
def test_starting_path_round_trip_is_owned_and_does_not_create_training(path):
    client, store, _ = _build_client()
    other = copy.deepcopy(store.profiles["admin-1"])
    response = client.put("/api/me", headers=AUTH, json={"starting_path": path})
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["starting_path"] == path
    assert client.get("/api/me", headers=AUTH).json()["profile"]["starting_path"] == path
    assert store.profiles["admin-1"] == other
    assert not store.external_training_sessions
    assert client.put("/api/me", json={"starting_path": path}).status_code == 401


def test_invalid_path_and_missing_consent_do_not_save():
    client, store, _ = _build_client()
    assert client.put("/api/me", headers=AUTH, json={"starting_path": "coach"}).status_code == 422
    store.profiles["athlete-1"]["terms_accepted_at"] = None
    assert client.put("/api/me", headers=AUTH, json={"starting_path": "tracking_first"}).status_code == 403
    assert store.profiles["athlete-1"].get("starting_path") is None


def test_preference_does_not_require_health_consent():
    client, store, _ = _build_client()
    store.profiles["athlete-1"]["health_data_consent"] = False
    response = client.put("/api/me", headers=AUTH, json={"starting_path": "tracking_first"})
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["health_consent_granted"] is False


def test_legacy_missing_column_does_not_look_like_a_new_account():
    client, store, _ = _build_client()
    assert client.get("/api/me", headers=AUTH).json()["profile"]["starting_path"] == "plan_first"
    store.profiles["athlete-1"]["starting_path"] = None
    assert client.get("/api/me", headers=AUTH).json()["profile"]["starting_path"] is None
