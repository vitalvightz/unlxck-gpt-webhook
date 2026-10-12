from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.services.onboarding_metrics import (
    summarize_time_to_first_usable_plan,
    time_to_first_usable_plan_seconds,
)
from support import _build_client

ADMIN = {"Authorization": "Bearer admin-token"}
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def test_seconds_from_signup_to_first_usable_plan():
    row = {"created_at": "2026-10-01T10:00:00Z", "first_usable_plan_at": "2026-10-01T10:04:30+00:00"}
    assert time_to_first_usable_plan_seconds(row) == 270
    assert time_to_first_usable_plan_seconds({"created_at": "2026-10-01T10:00:00Z"}) is None
    # Clock skew never reports a negative wait.
    skewed = {"created_at": "2026-10-01T10:00:05Z", "first_usable_plan_at": "2026-10-01T10:00:00Z"}
    assert time_to_first_usable_plan_seconds(skewed) == 0


def test_summary_counts_athlete_signups_in_window_and_reports_median_and_p75():
    since = NOW - timedelta(days=30)
    signup = NOW - timedelta(days=2)
    rows = [
        {"role": "athlete", "created_at": _iso(signup), "first_usable_plan_at": _iso(signup + timedelta(minutes=minutes))}
        for minutes in (2, 4, 6, 30)
    ]
    rows.append({"role": "athlete", "created_at": _iso(signup), "first_usable_plan_at": None})
    rows.append({"role": "admin", "created_at": _iso(signup), "first_usable_plan_at": _iso(signup)})
    rows.append({"role": "athlete", "created_at": _iso(NOW - timedelta(days=40)), "first_usable_plan_at": _iso(NOW)})

    summary = summarize_time_to_first_usable_plan(rows, window_days=30, since=since)

    assert summary == {
        "window_days": 30,
        "signups": 5,
        "with_usable_plan": 4,
        "median_seconds": 4 * 60,
        "p75_seconds": 6 * 60,
    }


def test_summary_with_no_plans_has_no_percentiles():
    summary = summarize_time_to_first_usable_plan(
        [{"role": "athlete", "created_at": _iso(NOW), "first_usable_plan_at": None}],
        window_days=7,
        since=NOW - timedelta(days=7),
    )
    assert summary["signups"] == 1
    assert summary["with_usable_plan"] == 0
    assert summary["median_seconds"] is None
    assert summary["p75_seconds"] is None


def test_admin_endpoint_reports_time_to_first_plan_and_is_admin_only():
    client, store, _ = _build_client()
    signed_up = datetime.now(timezone.utc) - timedelta(hours=1)
    store.profiles["athlete-1"]["created_at"] = _iso(signed_up)
    store.plans["plan-first"] = {
        "id": "plan-first",
        "athlete_id": "athlete-1",
        "status": "ready",
        "created_at": _iso(signed_up + timedelta(minutes=3)),
    }

    response = client.get("/api/admin/metrics/time-to-first-plan?days=7", headers=ADMIN)

    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 7
    assert body["signups"] >= 1
    assert body["with_usable_plan"] == 1
    assert body["median_seconds"] == 180

    athlete = client.get("/api/admin/athletes/athlete-1", headers=ADMIN).json()
    assert athlete["time_to_first_usable_plan_seconds"] == 180

    denied = client.get(
        "/api/admin/metrics/time-to-first-plan",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert denied.status_code == 403
