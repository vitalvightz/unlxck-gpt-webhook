"""The private trial briefing acknowledgement stored on the athlete profile."""

from __future__ import annotations

from datetime import datetime

from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}


def test_profile_starts_unacknowledged():
    client, _store, _ = _build_client()

    response = client.get("/api/me", headers=ATHLETE)

    assert response.status_code == 200
    assert response.json()["profile"]["private_trial_ack_at"] is None


def test_acknowledgement_is_stamped_by_the_server_not_the_client():
    client, store, _ = _build_client()

    response = client.put(
        "/api/me",
        headers=ATHLETE,
        json={"private_trial_acknowledged": True},
    )

    assert response.status_code == 200
    stamped = response.json()["profile"]["private_trial_ack_at"]
    assert stamped
    # A real timestamp, not an echo of anything the client could have chosen.
    assert datetime.fromisoformat(stamped)
    assert store.profiles["athlete-1"]["private_trial_ack_at"] == stamped
    # The intent field is never persisted as-is.
    assert "private_trial_acknowledged" not in store.profiles["athlete-1"]


def test_a_client_supplied_timestamp_never_reaches_the_profile():
    client, store, _ = _build_client()

    response = client.put(
        "/api/me",
        headers=ATHLETE,
        json={"private_trial_ack_at": "2020-01-01T00:00:00+00:00"},
    )

    # `private_trial_ack_at` is not an accepted update field, so the value is
    # dropped: the gate cannot be backdated or opened from the browser.
    assert response.status_code == 200
    assert response.json()["profile"]["private_trial_ack_at"] is None
    assert store.profiles["athlete-1"].get("private_trial_ack_at") is None


def test_unrelated_profile_edits_leave_the_acknowledgement_intact():
    client, store, _ = _build_client()
    client.put("/api/me", headers=ATHLETE, json={"private_trial_acknowledged": True})
    stamped = store.profiles["athlete-1"]["private_trial_ack_at"]

    response = client.put("/api/me", headers=ATHLETE, json={"stance": "southpaw"})

    assert response.status_code == 200
    assert response.json()["profile"]["private_trial_ack_at"] == stamped


def test_acknowledgement_can_be_cleared():
    client, store, _ = _build_client()
    client.put("/api/me", headers=ATHLETE, json={"private_trial_acknowledged": True})

    response = client.put(
        "/api/me",
        headers=ATHLETE,
        json={"private_trial_acknowledged": False},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["private_trial_ack_at"] is None
    assert store.profiles["athlete-1"]["private_trial_ack_at"] is None
