from api.routes import profile as profile_routes
from support import _build_client


def test_get_me_reconciles_activation_xp_from_persisted_response(monkeypatch):
    captured = []

    def capture(_store, **kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(profile_routes, "reconcile_activation_xp", capture)
    client, _, _ = _build_client()

    response = client.get(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["athlete_id"] == "athlete-1"
    assert captured[0]["profile"].athlete_id == "athlete-1"
    latest_intake = captured[0]["latest_intake"]
    captured_intake = (
        latest_intake.model_dump(mode="json")
        if hasattr(latest_intake, "model_dump")
        else latest_intake
    )
    assert captured_intake == response.json()["latest_intake"]


def test_profile_update_reconciles_against_the_persisted_updated_profile(monkeypatch):
    captured = []

    def capture(_store, **kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(profile_routes, "reconcile_activation_xp", capture)
    client, _, _ = _build_client()

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
        },
    )

    assert response.status_code == 200
    assert len(captured) == 1
    persisted_profile = captured[0]["profile"]
    assert persisted_profile.full_name == "Ari Mensah"
    assert persisted_profile.technical_style == ["boxing"]


def test_activation_xp_failure_never_breaks_profile_reads(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("xp unavailable")

    monkeypatch.setattr(profile_routes, "reconcile_activation_xp", fail)
    client, _, _ = _build_client()

    response = client.get(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["athlete_id"] == "athlete-1"
