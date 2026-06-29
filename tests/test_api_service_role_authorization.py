from __future__ import annotations

from api.auth import AuthenticatedUser
from support import _build_client, _build_request, finalized_result


def _create_two_athletes(client, store):
    athlete_a = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    athlete_b = AuthenticatedUser(user_id="athlete-2", email="bea@example.com", full_name="Bea Jones", metadata={})
    store.ensure_profile(athlete_a)
    store.ensure_profile(athlete_b)
    client.app.state.auth_service.users_by_token["athlete-token"] = athlete_a
    client.app.state.auth_service.users_by_token["athlete-b-token"] = athlete_b


def _create_resources_for_each_athlete(store):
    request = _build_request()
    intake_a = store.create_intake("athlete-1", request)
    intake_b = store.create_intake("athlete-2", request)
    plan_a = store.create_plan(athlete_id="athlete-1", intake_id=intake_a["id"], request=request, result=finalized_result())
    plan_b = store.create_plan(athlete_id="athlete-2", intake_id=intake_b["id"], request=request, result=finalized_result())
    job_a = store.create_or_get_generation_job(athlete_id="athlete-1", client_request_id="job-a", source="self_serve", request_payload=request.model_dump(mode="json"))
    job_b = store.create_or_get_generation_job(athlete_id="athlete-2", client_request_id="job-b", source="self_serve", request_payload=request.model_dump(mode="json"))
    store.update_generation_job(job_a["id"], status="failed", error="boom")
    store.update_generation_job(job_b["id"], status="failed", error="boom")
    return plan_a, plan_b, job_a, job_b


def _assert_denied(response):
    assert response.status_code in {403, 404}


def test_cross_user_plan_and_job_authorization_regression():
    client, store, _ = _build_client()
    _create_two_athletes(client, store)
    _, plan_b, _, job_b = _create_resources_for_each_athlete(store)

    _assert_denied(client.get(f"/api/plans/{plan_b['id']}", headers={"Authorization": "Bearer athlete-token"}))
    _assert_denied(client.patch(f"/api/plans/{plan_b['id']}/name", json={"plan_name": "hijack"}, headers={"Authorization": "Bearer athlete-token"}))
    _assert_denied(client.delete(f"/api/plans/{plan_b['id']}", headers={"Authorization": "Bearer athlete-token"}))

    _assert_denied(client.get(f"/api/generation-jobs/{job_b['id']}", headers={"Authorization": "Bearer athlete-token"}))
    _assert_denied(client.post(f"/api/generation-jobs/{job_b['id']}/retry", headers={"Authorization": "Bearer athlete-token"}))


def test_athlete_cannot_access_admin_endpoints_regression():
    client, store, _ = _build_client()
    _create_two_athletes(client, store)

    _assert_denied(client.get("/api/admin/plans", headers={"Authorization": "Bearer athlete-token"}))
    _assert_denied(client.get("/api/admin/athletes", headers={"Authorization": "Bearer athlete-token"}))


def _admin_routes(app) -> list[tuple[str, str]]:
    """Every (method, path) under /api/admin exposed by the app.

    Introspecting the live router (rather than hardcoding a list) makes this a
    true matrix guard: any admin route added later that forgets
    ``Depends(require_admin)`` is exercised automatically and will fail here.
    """
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path.startswith("/api/admin") or not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.append((method, path))
    return routes


def _concrete_path(path: str) -> str:
    # Substitute path params with placeholders. require_admin runs during
    # dependency resolution, before the handler validates the value, so the
    # placeholder never needs to resolve to a real row to trigger the 403.
    parts = []
    for segment in path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append("00000000-0000-0000-0000-000000000000")
        else:
            parts.append(segment)
    return "/".join(parts)


def test_every_admin_route_denies_a_plain_athlete():
    """Comprehensive matrix: a non-admin athlete is rejected on EVERY admin
    route, not just the hand-picked few. Guards against a new admin endpoint
    silently shipping without ``require_admin``."""
    client, store, _ = _build_client()
    _create_two_athletes(client, store)

    admin_routes = _admin_routes(client.app)
    # Sanity: the app actually exposes a meaningful admin surface; otherwise a
    # routing regression could make this test vacuously pass.
    assert len(admin_routes) >= 15

    headers = {"Authorization": "Bearer athlete-token"}
    failures: list[str] = []
    for method, path in admin_routes:
        url = _concrete_path(path)
        response = client.request(method, url, headers=headers, json={})
        # require_admin denies with 403. We must never see a success (2xx) or a
        # validation error (422) that would imply the guard was bypassed and the
        # request reached body/handler processing.
        if response.status_code != 403:
            failures.append(f"{method} {path} -> {response.status_code}")

    assert not failures, "admin routes reachable by a plain athlete: " + "; ".join(failures)


def test_athlete_cannot_update_other_athlete_nutrition_through_indirect_admin_id():
    client, store, _ = _build_client()
    _create_two_athletes(client, store)

    response = client.put(
        "/api/admin/athletes/athlete-2/nutrition/current",
        headers={"Authorization": "Bearer athlete-token"},
        json={},
    )
    _assert_denied(response)


def test_nutrition_update_remains_scoped_to_current_profile():
    client, store, _ = _build_client()
    _create_two_athletes(client, store)

    profile_b_before = dict(store.profiles["athlete-2"])
    workspace = client.get("/api/nutrition/current", headers={"Authorization": "Bearer athlete-token"}).json()
    response = client.put(
        "/api/nutrition/current",
        headers={"Authorization": "Bearer athlete-token"},
        json={
            "nutrition_profile": workspace["nutrition_profile"],
            "shared_camp_context": workspace["shared_camp_context"],
            "s_and_c_preferences": workspace["s_and_c_preferences"],
            "nutrition_readiness": workspace["nutrition_readiness"],
            "nutrition_monitoring": workspace["nutrition_monitoring"],
            "nutrition_coach_controls": workspace["nutrition_coach_controls"],
        },
    )

    assert response.status_code == 200
    # Verify the update was applied to the correct profile. Persistence strips
    # None-valued keys via model_dump(exclude_none=True) (matching the real
    # store), so the round-trip is semantically lossless rather than byte-equal.
    expected_profile = {
        key: value for key, value in workspace["nutrition_profile"].items() if value is not None
    }
    assert store.profiles["athlete-1"]["nutrition_profile"] == expected_profile
    # Verify it did not leak to the other profile
    assert store.profiles["athlete-2"] == profile_b_before
