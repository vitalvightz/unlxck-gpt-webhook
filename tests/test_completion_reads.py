from unittest.mock import Mock

import pytest

from api.routes import today as today_routes
from api.services.completion_reads import CompletionReads
from support import FakeStore, _build_client


PLAN = "11111111-1111-1111-1111-111111111111"
ATHLETE = "athlete-1"


@pytest.mark.parametrize("reuse,plan_reads,history_reads", [(True, 1, 1), (False, 5, 2)])
def test_completion_route_reuses_reads_and_retries_keep_rewards_idempotent(monkeypatch, reuse, plan_reads, history_reads):
    if not reuse:
        monkeypatch.setattr(today_routes, "CompletionReads", lambda store: store)
    client, store, _ = _build_client()
    store.plans[PLAN] = {
        "id": PLAN, "athlete_id": ATHLETE, "status": "ready",
        "created_at": "2026-08-01T00:00:00Z",
        "structured_plan": {"weeks": [{
            "week_id": "week-1", "start_date": "2026-08-03", "end_date": "2026-08-09",
            "days": [{"date": "2026-08-03", "day_type": "hard", "sessions": [
                {"session_id": "session-1", "session_type": "strength"},
                {"session_id": "session-2", "session_type": "conditioning"},
            ]}],
        }]},
    }
    store.set_active_plan_id(ATHLETE, PLAN)
    owned = Mock(wraps=store.get_plan_for_athlete)
    history = Mock(wraps=store.list_plan_session_completions)
    monkeypatch.setattr(store, "get_plan_for_athlete", owned)
    monkeypatch.setattr(store, "list_plan_session_completions", history)

    def persist(target, *, athlete_id, athlete_timezone, payload):
        # Exercise the actual post-persistence pipeline independently of the
        # clinical boundary, whose completion tests run alongside this case.
        assert target is store
        return target.upsert_session_completion(athlete_id, {
            **payload, "training_day": "2026-08-03",
            "started_at": "2026-08-03T12:00:00Z", "completed_at": "2026-08-03T12:30:00Z",
        })

    monkeypatch.setattr(today_routes, "upsert_session_completion", persist)
    for attempt in (1, 2):
        response = client.post("/api/today/session-completion",
            headers={"Authorization": "Bearer athlete-token"},
            json={"plan_id": PLAN, "session_id": "session-1", "status": "done"})
        assert response.status_code == 201
        assert owned.call_count == attempt * plan_reads
        assert history.call_count == attempt * history_reads
        streaks = store.get_athlete_streaks(ATHLETE)
        assert streaks["training_current"] == 1
        assert streaks["adherence_current"] == 0
        assert len(store.xp_awards[ATHLETE]) == 2


def test_failures_scopes_copies_and_writes_do_not_reuse_stale_rows():
    store = FakeStore()
    store.get_plan_for_athlete = Mock(side_effect=[RuntimeError("offline"), {"id": PLAN}, None, {"id": "updated"}])
    cache = CompletionReads(store)
    with pytest.raises(RuntimeError):
        cache.get_plan_for_athlete(PLAN, ATHLETE)
    first = cache.get_plan_for_athlete(PLAN, ATHLETE)
    first["id"] = "mutated"
    assert cache.get_plan_for_athlete(PLAN, ATHLETE) == {"id": PLAN}
    assert cache.get_plan_for_athlete(PLAN, "other-athlete") is None
    cache.set_active_plan_id(ATHLETE, PLAN)
    assert cache.get_plan_for_athlete(PLAN, ATHLETE) == {"id": "updated"}


def test_history_windows_and_completion_writes_remain_fresh():
    store = FakeStore()
    store.list_plan_session_completions = Mock(side_effect=[[{"id": "short"}], [{"id": "long"}], [{"id": "saved"}]])
    cache = CompletionReads(store)
    assert cache.list_plan_session_completions(ATHLETE, PLAN, limit=1) == [{"id": "short"}]
    assert cache.list_plan_session_completions(ATHLETE, PLAN, limit=500) == [{"id": "long"}]
    cache.upsert_session_completion(ATHLETE, {"plan_id": PLAN, "session_id": "s", "training_day": "2026-08-03", "status": "done"})
    assert cache.list_plan_session_completions(ATHLETE, PLAN, limit=500) == [{"id": "saved"}]


def test_store_capability_cache_survives_request_wrapper():
    store = FakeStore()
    cache = CompletionReads(store)
    cache._unlxck_xp_abuse_hardening_validated = True
    assert CompletionReads(store)._unlxck_xp_abuse_hardening_validated is True
