"""API tests for athlete injury flagging and the admin review queue.

The dashboard / check-in / session-log endpoints this module used to cover were
removed with the legacy daily flow; ``/api/today`` (tests/test_today_service.py)
owns that surface now. Injury flagging is the remaining athlete-facing writer
into the admin review queue, so it is what seeds the queue tests here.
"""

from uuid import uuid4

from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
ADMIN = {"Authorization": "Bearer admin-token"}

KNEE_INJURY = {
    "body_area": "knee",
    "description": "sharp pain in right knee",
    "severity": "moderate",
}


class TestInjuryFlags:
    def test_manual_injury_report_creates_flag_and_review(self):
        client, store, _ = _build_client()
        response = client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"body_area": "shoulder", "description": "pinch on overhead press", "severity": "mild"},
        )
        assert response.status_code == 201
        assert response.json()["source"] == "manual"
        assert store.admin_reviews and store.admin_reviews[0]["status"] == "pending"

    def test_admin_resolves_injury_flag(self):
        client, store, _ = _build_client()
        client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"description": "pinch on overhead press"},
        )
        flag_id = store.injury_flags["athlete-1"][0]["id"]
        response = client.patch(
            f"/api/admin/injury-flags/{flag_id}", headers=ADMIN, json={"status": "resolved"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "resolved"
        assert response.json()["resolved_at"]

    def test_resolved_flag_drops_out_of_the_open_list(self):
        client, store, _ = _build_client()
        client.post("/api/injury-flags", headers=ATHLETE, json={"description": "tweak"})
        flag_id = store.injury_flags["athlete-1"][0]["id"]
        client.patch(f"/api/admin/injury-flags/{flag_id}", headers=ADMIN, json={"status": "resolved"})

        assert client.get("/api/injury-flags", headers=ATHLETE).json() == []
        with_resolved = client.get("/api/injury-flags?include_resolved=true", headers=ATHLETE)
        assert [row["status"] for row in with_resolved.json()] == ["resolved"]

    def test_athlete_cannot_resolve_flags(self):
        client, store, _ = _build_client()
        client.post(
            "/api/injury-flags", headers=ATHLETE, json={"description": "tweak"}
        )
        flag_id = store.injury_flags["athlete-1"][0]["id"]
        response = client.patch(
            f"/api/admin/injury-flags/{flag_id}", headers=ATHLETE, json={"status": "resolved"}
        )
        assert response.status_code == 403

    def test_injury_flags_require_auth(self):
        client, _, _ = _build_client()
        assert client.post("/api/injury-flags", json={"description": "tweak"}).status_code == 401
        assert client.get("/api/injury-flags").status_code == 401

    def test_rehab_exposure_uses_validated_immutable_path(self):
        client, store, _ = _build_client()
        injury = client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"body_area": "left ankle", "description": "left ankle sprain"},
        )
        assert injury.status_code == 201
        assert injury.json()["episode_id"]
        assert injury.json()["body_region"] == "ankle"
        assert injury.json()["side"] == "left"
        flag = store.injury_flags["athlete-1"][0]
        event = {
            "exposure_id": str(uuid4()),
            "injury_id": flag["id"],
            "injury_episode_id": flag["episode_id"],
            "drill_id": "ankle_control",
            "body_region": "ankle",
            "side": "left",
            "demand": {"target_regions": ["ankle"], "load": "low", "impact": "none", "velocity": "low"},
            "dose_completed": {"reps": 8},
            "occurred_at": "2026-08-20T12:00:00Z",
            "provenance": {"source": "athlete_logged_rehab", "recorded_at": "2026-08-20T12:01:00Z"},
        }
        first = client.post("/api/rehab-exposures", headers=ATHLETE, json=event)
        retry = client.post("/api/rehab-exposures", headers=ATHLETE, json=event)
        assert first.status_code == retry.status_code == 201
        assert len(store.rehab_exposures) == 1
        stored = next(iter(store.rehab_exposures.values()))["event_json"]
        assert stored["response_group_id"] == event["exposure_id"]

    def test_rehab_exposure_rejects_cross_region_and_side(self):
        client, store, _ = _build_client()
        client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"body_area": "left ankle", "description": "left ankle sprain"},
        )
        flag = store.injury_flags["athlete-1"][0]
        base = {
            "exposure_id": str(uuid4()), "injury_id": flag["id"], "injury_episode_id": flag["episode_id"],
            "drill_id": "ankle_control", "body_region": "ankle", "side": "right",
            "demand": {"target_regions": ["ankle"], "load": "low", "impact": "none", "velocity": "low"},
            "dose_completed": {"reps": 8}, "occurred_at": "2026-08-20T12:00:00Z",
            "provenance": {"source": "athlete_logged_rehab", "recorded_at": "2026-08-20T12:01:00Z"},
        }
        assert client.post("/api/rehab-exposures", headers=ATHLETE, json=base).status_code == 422
        base["side"] = "left"
        base["body_region"] = "shoulder"
        base["demand"]["target_regions"] = ["shoulder"]
        assert client.post("/api/rehab-exposures", headers=ATHLETE, json=base).status_code == 422


class TestAdminReviewQueue:
    def test_admin_sees_pending_reviews_with_athlete_context(self):
        client, _, _ = _build_client()
        client.post("/api/injury-flags", headers=ATHLETE, json=KNEE_INJURY)
        response = client.get("/api/admin/reviews", headers=ADMIN)
        assert response.status_code == 200
        reviews = response.json()
        assert len(reviews) == 1
        assert reviews[0]["status"] == "pending"
        assert reviews[0]["athlete_email"] == "ari@example.com"
        assert "review" in reviews[0]["reason"].lower()

    def test_admin_reviews_use_batch_athlete_lookup(self):
        client, store, _ = _build_client()
        client.post("/api/injury-flags", headers=ATHLETE, json=KNEE_INJURY)
        response = client.get("/api/admin/reviews", headers=ADMIN)
        assert response.status_code == 200
        assert store.list_admin_athletes_by_ids_calls == 1
        assert store.get_admin_athlete_calls == 0

    def test_second_flag_does_not_open_a_duplicate_review(self):
        client, store, _ = _build_client()
        client.post("/api/injury-flags", headers=ATHLETE, json=KNEE_INJURY)
        client.post(
            "/api/injury-flags",
            headers=ATHLETE,
            json={"body_area": "ankle", "description": "rolled it", "severity": "mild"},
        )
        assert len(client.get("/api/admin/reviews", headers=ADMIN).json()) == 1
        # Both flags still recorded; only the review is deduped.
        assert len(store.injury_flags["athlete-1"]) == 2

    def test_resolve_review_records_admin_and_clears_queue(self):
        client, _, _ = _build_client()
        client.post("/api/injury-flags", headers=ATHLETE, json=KNEE_INJURY)
        review_id = client.get("/api/admin/reviews", headers=ADMIN).json()[0]["id"]
        response = client.post(
            f"/api/admin/reviews/{review_id}/resolve",
            headers=ADMIN,
            json={"status": "resolved", "resolution_notes": "spoke to athlete, swapped drills"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "resolved"
        assert body["resolved_by"] == "ops@unlxck.test"
        assert client.get("/api/admin/reviews", headers=ADMIN).json() == []

    def test_resolve_rejects_a_non_uuid_review_id(self):
        client, _, _ = _build_client()
        response = client.post(
            "/api/admin/reviews/not-a-uuid/resolve",
            headers=ADMIN,
            json={"status": "resolved", "resolution_notes": "n/a"},
        )
        assert response.status_code == 404

    def test_review_queue_is_admin_only(self):
        client, _, _ = _build_client()
        assert client.get("/api/admin/reviews", headers=ATHLETE).status_code == 403
