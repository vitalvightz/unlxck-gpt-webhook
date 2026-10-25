from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from api.services.product_analytics import summarize
from api.routes.product_analytics import build_product_analytics_router
from api.dependencies import get_store, require_admin, require_profile

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


def athlete(id="a", signup="2026-10-01T12:00:00+00:00", **kw):
    return {
        **dict(
            id=id,
            created_at=signup,
            professional_status="",
            technical_style=[],
            starting_path="tracking_first",
        ),
        **kw,
    }


def fact(
    day,
    aid="a",
    action="session_completed",
    meaningful=True,
    count=1,
    feature="strength",
):
    return dict(
        athlete_id=aid,
        day=day,
        action=action,
        meaningful=meaningful,
        count=count,
        feature=feature,
        first_at=f"{day}T12:00:00+00:00",
        last_at=f"{day}T12:00:00+00:00",
    )


def report(athletes=None, facts=None, **kw):
    return summarize(
        dict(athletes=athletes or [], facts=facts or [], **kw), now=NOW, days=30
    )


def test_empty_denominators():
    r = report()
    assert r["registered"] == 0
    assert r["stickiness"] is None
    assert r["retention"]["7"] == dict(eligible=0, returned=0, percent=None)


def test_unique_users_days_and_discovery_excluded():
    r = report(
        [athlete()],
        [
            fact("2026-10-25", count=4),
            fact("2026-10-25", action="plan_opened", meaningful=False),
            fact("2026-10-24"),
        ],
    )
    assert (r["dau"], r["wau"], r["mau"]) == (1, 1, 1)
    assert r["average_active_days"] == 2
    assert r["athletes"][0]["first_activity"].startswith("2026-10-24")
    assert r["athletes"][0]["last_activity"].startswith("2026-10-25")
    assert next(f for f in r["features"] if f["feature"] == "strength")["uses"] == 5


def test_exact_return_days_and_incomplete_cohorts():
    ps = [
        athlete("a"),
        athlete("b", "2026-10-24T00:00:00+00:00"),
        athlete("c", "2026-09-01T00:00:00+00:00"),
    ]
    r = summarize(
        dict(
            athletes=ps,
            facts=[fact("2026-10-02"), fact("2026-10-08"), fact("2026-10-01", "c")],
        ),
        now=NOW,
        days=0,
    )
    assert r["retention"]["1"] == dict(eligible=2, returned=1, percent=50.0)
    assert r["retention"]["7"] == dict(eligible=2, returned=1, percent=50.0)
    assert r["retention"]["30"] == dict(eligible=1, returned=1, percent=100.0)
    # Yesterday's signup has not finished its D1 return window today.
    assert r["retention"]["1"]["eligible"] == 2


def test_plan_free_onboarding_and_observed_only_dropoffs():
    r = report(
        [athlete()],
        [
            fact("2026-10-01", action="onboarding_started", meaningful=False),
            fact("2026-10-02", action="onboarding_completed", meaningful=False),
            fact("2026-10-03", feature="manual"),
        ],
    )
    c = next(
        c
        for c in r["conversions"]
        if c["label"] == "Onboarded plan-first → usable plan"
    )
    assert c["eligible"] == 0 and c["percent"] is None
    assert r["dropoffs"]["observed_onboarding_not_completed_24h"] == 0
    assert report([athlete()])["dropoffs"]["observed_onboarding_not_completed_24h"] == 0


def test_session_denominator_matched_and_mature_abandonment():
    sessions = [
        dict(
            athlete_id="a",
            started_at="2026-10-01T12:00:00+00:00",
            completed_at=None,
            status="started",
        ),
        dict(
            athlete_id="a",
            started_at="2026-10-25T10:00:00+00:00",
            completed_at=None,
            status="started",
        ),
        dict(
            athlete_id="a",
            started_at=None,
            completed_at="2026-10-01T14:00:00+00:00",
            status="done",
        ),
    ]
    r = report([athlete()], sessions=sessions)
    assert r["sessions_started"] == 2 and r["observed_session_abandonments"] == 1
    c = next(
        c
        for c in r["conversions"]
        if c["label"] == "Observed session starts → completed"
    )
    assert c["eligible"] == 2 and c["converted"] == 0


def test_date_boundaries_and_segments():
    data = dict(
        athletes=[athlete(), athlete("b", professional_status="professional")],
        facts=[fact("2026-10-19"), fact("2026-10-18"), fact("2026-10-26")],
    )
    r = summarize(data, now=NOW, days=7)
    assert (
        r["active"] == 1
        and r["previous_active"] == 1
        and r["average_active_days"] == 0.5
    )
    assert (
        summarize(data, now=NOW, days=7, professional_status="professional")["active"]
        == 0
    )


def test_errors_never_become_activity():
    r = report(
        [athlete()],
        [fact("2026-10-24", action="operation_failed", meaningful=False, count=3)],
    )
    assert r["ever_active"] == 0 and r["errors"][0]["errors_per_athlete"] == 3


class Client:
    def __init__(self):
        self.calls = []

    def rpc(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=True))


def api_client():
    app = FastAPI()
    app.include_router(build_product_analytics_router())
    store = SimpleNamespace(client=Client(), admin_emails=set())
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[require_profile] = lambda: SimpleNamespace(
        athlete_id="owner"
    )

    def deny():
        raise HTTPException(403, "admin access required")

    app.dependency_overrides[require_admin] = deny
    return TestClient(app), store


def test_ingestion_actor_timestamp_and_controlled_events():
    c, s = api_client()
    body = dict(event_name="timer_started", feature="timer", request_id=str(uuid4()))
    assert c.post("/api/analytics/events", json=body).status_code == 202
    assert s.client.calls[0][1]["p_athlete_id"] == "owner"
    for extra in (
        {"athlete_id": "other"},
        {"created_at": "2000-01-01"},
        {"payload": {"notes": "private"}},
    ):
        assert (
            c.post("/api/analytics/events", json={**body, **extra}).status_code == 422
        )
    assert (
        c.post("/api/analytics/events", json={**body, "feature": "plans"}).status_code
        == 422
    )
    assert (
        c.post(
            "/api/analytics/events", json={**body, "event_name": "operation_failed"}
        ).status_code
        == 422
    )


def test_all_reports_admin_only():
    c, _ = api_client()
    assert c.get("/api/admin/product-analytics").status_code == 403
    assert c.get(f"/api/admin/athletes/{uuid4()}/activity").status_code == 403


def test_timer_completions_match_observed_flow_starts():
    r = report(
        [athlete()],
        timer_flows=[
            dict(
                athlete_id="a",
                started_at="2026-10-10T12:00:00+00:00",
                completed_at="2026-10-10T12:05:00+00:00",
                exited_at=None,
            ),
            dict(
                athlete_id="a",
                started_at="2026-10-11T12:00:00+00:00",
                completed_at=None,
                exited_at="2026-10-11T12:01:00+00:00",
            ),
        ],
    )
    f = next(f for f in r["features"] if f["feature"] == "timer")
    assert f["completion"] == dict(started=2, completed=1, percent=50.0)
    assert f["observed_early_exits"] == 1


def test_failure_followup_requires_full_window_and_does_not_claim_causality():
    r = report(
        [athlete()],
        [
            fact("2026-10-01", action="operation_failed", meaningful=False),
            fact("2026-10-20"),
        ],
    )
    assert r["friction_followup"][0]["eligible_athletes"] == 1
    assert r["friction_followup"][0]["no_recorded_return_7d"] == 1
    r = report(
        [athlete()], [fact("2026-10-24", action="operation_failed", meaningful=False)]
    )
    assert r["friction_followup"][0]["eligible_athletes"] == 0


def test_admin_pagination_and_filters_are_validated():
    c, store = api_client()
    c.app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        athlete_id="admin"
    )
    store.client.rpc = lambda name, args: SimpleNamespace(
        execute=lambda: SimpleNamespace(
            data=dict(athletes=[athlete("a"), athlete("b")], facts=[])
        )
    )
    response = c.get("/api/admin/product-analytics?days=7&offset=1&limit=1")
    assert response.status_code == 200 and response.json()["athlete_total"] == 2
    assert len(response.json()["athletes"]) == 1
    assert c.get("/api/admin/product-analytics?days=8").status_code == 422
    assert c.get("/api/admin/product-analytics?offset=-1").status_code == 422
    assert c.get("/api/admin/product-analytics?limit=101").status_code == 422
    assert (
        c.get("/api/admin/product-analytics?professional_status=professional").json()[
            "registered"
        ]
        == 0
    )


def test_children_cannot_enable_optional_browser_tracking():
    c, store = api_client()
    c.app.dependency_overrides[require_profile] = lambda: SimpleNamespace(
        athlete_id="child", is_minor=True
    )
    assert (
        c.put("/api/analytics/preference", json=dict(enabled=True)).status_code == 403
    )
    assert c.post(
        "/api/analytics/events",
        json=dict(event_name="timer_started", feature="timer", request_id=str(uuid4())),
    ).json() == dict(accepted=False)
    assert not store.client.calls


def test_generated_plan_and_profile_timestamps_never_replace_meaningful_activity():
    r = report(
        [athlete()],
        [
            fact("2026-10-01"),
            fact(
                "2026-10-25", action="plan_generated", meaningful=False, feature="plans"
            ),
        ],
    )
    assert r["athletes"][0]["first_activity"].startswith("2026-10-01")
    assert r["athletes"][0]["last_activity"].startswith("2026-10-01")
    assert r["dau"] == 0


def test_observed_signals_identify_athletes_without_guessing_unobserved_intent():
    r = report(
        [athlete("a"), athlete("b")],
        [fact("2026-10-01", action="onboarding_started", meaningful=False)],
    )
    assert "Observed onboarding start unresolved for 24h" in r["athletes"][0]["signals"]
    assert r["athletes"][1]["signals"] == []


def test_failed_feature_write_is_observed_without_copying_error_text():
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from api.services.product_friction import install_product_friction

    app = FastAPI()
    store = SimpleNamespace(client=Client())
    app.state.store = store

    @app.post("/api/training/sessions")
    def fail(request: Request):
        request.state.athlete_id = "verified-owner"
        request.state.request_id = "request-identity"
        return JSONResponse(
            {"detail": "Private operational error text"}, status_code=503
        )

    install_product_friction(app)
    response = TestClient(app).post("/api/training/sessions")
    assert response.status_code == 503
    name, args = store.client.calls[0]
    assert name == "ingest_product_event"
    assert args["p_athlete_id"] == "verified-owner"
    assert args["p_event_name"] == "operation_failed" and args["p_feature"] == "manual"
    assert "Private operational error text" not in str(args)
