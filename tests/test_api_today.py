"""API tests for the Block 4 Today/Overview endpoints.

Covers the Today check-in submit (+ server recommendation), session-completion
upsert, the normalized command view, and the landing endpoint. Uses the
in-process FakeStore via the shared test client.
"""

from tests.support import _build_client

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PLAN = "22222222-2222-2222-2222-222222222222"


def _seed_plan(store, plan_id: str = PLAN_ID, athlete_id: str = "athlete-1") -> str:
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": athlete_id,
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    return plan_id


def _checkin_body(**overrides) -> dict:
    base = {"plan_id": PLAN_ID, "sleep": "good", "body": "normal", "pain": "none", "phase": "GPP"}
    return {**base, **overrides}


class TestTodayCheckin:
    def test_checkin_persists_and_returns_recommendation(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        resp = client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body(sleep="poor"))
        assert resp.status_code == 201
        body = resp.json()
        assert body["recommendation_state"] == "modify"
        assert body["recommendation_reason"] == "Poor sleep; use the modified option today."
        assert "poor_sleep" in body["triggers"]
        assert store.today_checkins["athlete-1"], "check-in row must persist"

    def test_same_day_checkin_upserts_single_row(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body())
        client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body(sleep="poor"))
        assert len(store.today_checkins["athlete-1"]) == 1
        assert store.today_checkins["athlete-1"][0]["recommendation_state"] == "modify"

    def test_client_supplied_recommendation_is_ignored(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        resp = client.post(
            "/api/today/checkin",
            headers=ATHLETE,
            json=_checkin_body(pain="high", recommendation_state="train_as_planned"),
        )
        assert resp.json()["recommendation_state"] == "pull_back"


class TestPlanOwnership:
    def _seed_other(self, store):
        # Plan belongs to a different athlete.
        store.plans[OTHER_PLAN] = {
            "id": OTHER_PLAN,
            "athlete_id": "someone-else",
            "status": "ready",
            "plan_name": "Other",
            "created_at": "2026-06-01T00:00:00+00:00",
        }

    def test_checkin_rejected_for_unowned_plan(self):
        client, store, _ = _build_client()
        self._seed_other(store)
        resp = client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body(plan_id=OTHER_PLAN))
        assert resp.status_code == 404
        assert not store.today_checkins.get("athlete-1")

    def test_completion_rejected_for_unowned_plan(self):
        client, store, _ = _build_client()
        self._seed_other(store)
        resp = client.post(
            "/api/today/session-completion",
            headers=ATHLETE,
            json={"plan_id": OTHER_PLAN, "session_id": "s1", "status": "started"},
        )
        assert resp.status_code == 404
        assert not store.session_completions.get("athlete-1")

    def test_checkin_rejects_malformed_plan_id(self):
        client, store, _ = _build_client()
        resp = client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body(plan_id="not-a-uuid"))
        assert resp.status_code == 422
        assert not store.today_checkins.get("athlete-1")


class TestSessionCompletion:
    def _post(self, client, **overrides):
        base = {"plan_id": PLAN_ID, "session_id": "s1", "status": "started"}
        return client.post("/api/today/session-completion", headers=ATHLETE, json={**base, **overrides})

    def test_started_completion(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        resp = self._post(client, status="started")
        assert resp.status_code == 201
        body = resp.json()
        assert body["completion_status"] == "started"
        assert body["landing_session_state"] == "resume"
        assert body["completion"]["started_at"]

    def test_done_requires_completed_at_is_stamped(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        body = self._post(client, status="done").json()
        assert body["completion_status"] == "done"
        assert body["completion"]["completed_at"]
        assert body["landing_session_state"] == "completed"

    def test_modified_without_reason_is_rejected(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        assert self._post(client, status="modified").status_code == 422
        ok = self._post(client, status="modified", modification_reason="swapped to recovery")
        assert ok.status_code == 201

    def test_skipped_completion(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        body = self._post(client, status="skipped").json()
        assert body["completion_status"] == "skipped"
        assert body["landing_session_state"] == "completed"

    def test_duplicate_completion_upserts_single_row(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        self._post(client, status="started")
        self._post(client, status="done")
        assert len(store.session_completions["athlete-1"]) == 1
        assert store.session_completions["athlete-1"][0]["status"] == "done"


class TestTodayState:
    def test_no_active_plan_returns_intake_cta(self):
        client, _store, _ = _build_client()
        body = client.get("/api/today", headers=ATHLETE).json()
        assert body["active_plan"] == {}
        assert [a["id"] for a in body["quick_actions"]] == ["complete_intake"]
        assert body["today"]["recommendation_state"] == "not_checked_in"

    def test_active_plan_without_checkin_is_not_checked_in(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        body = client.get("/api/today", headers=ATHLETE).json()
        assert body["active_plan"]["id"] == PLAN_ID
        assert body["today"]["recommendation_state"] == "not_checked_in"
        assert {a["id"] for a in body["quick_actions"]} == {"open_today", "view_plan"}

    def test_valid_recommendation_is_mirrored(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body(sleep="poor"))
        body = client.get("/api/today", headers=ATHLETE).json()
        assert body["today"]["recommendation_state"] == "modify"
        assert body["today"]["recommendation_reason"]


class TestLanding:
    def test_no_plan_routes_to_intake(self):
        client, _store, _ = _build_client()
        body = client.get("/api/today/landing", headers=ATHLETE).json()
        assert body["target"] == "intake"
        assert body["row"] == 1

    def test_plan_without_checkin_routes_to_overview_cta(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        body = client.get("/api/today/landing", headers=ATHLETE).json()
        assert body["target"] == "overview"
        assert body["cta"] == "check_in"
        assert body["row"] == 6

    def test_checked_in_today_routes_to_today(self):
        client, store, _ = _build_client()
        _seed_plan(store)
        client.post("/api/today/checkin", headers=ATHLETE, json=_checkin_body())
        body = client.get("/api/today/landing", headers=ATHLETE).json()
        assert body["target"] == "today"
        assert body["row"] == 5
