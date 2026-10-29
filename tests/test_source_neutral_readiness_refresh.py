"""Authoritative reads, real mutation boundaries, unchanged deterministic rules."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest

from api.contracts.external_training import ExternalTrainingCreate, ExternalTrainingFields
from api.services import today_service
from api.services.today_readiness_boundary import build_today_command_view
from api.services.training_history import (
    create_external_training, delete_external_training, training_history, update_external_training,
)
from fightcamp.completed_workload import completed_workload
from tests.test_prescribed_workload_provenance import ATHLETE, DAY, NOW, PLAN, make_store, report


@pytest.fixture
def evidence(monkeypatch):
    """Observe the actual context delivered to the real engine, never stub it."""
    calls = []
    engine = today_service.build_readiness_adjustment

    def evaluate(checkin, context):
        decision = engine(checkin, context)
        calls.append((checkin, deepcopy(context), decision))
        return decision

    monkeypatch.setattr(today_service, "build_readiness_adjustment", evaluate)
    return calls


def checked_store(**answers):
    store = make_store(sibling="Strength")
    store.upsert_today_checkin(ATHLETE, {"plan_id": PLAN, "training_day": DAY,
        "sleep": "good", "body": "flat", "pain": "none", "phase": "SPP",
        "recommendation_state": "train_as_planned", "recommendation_triggers": [], **answers})
    return store


def read(store, evidence, *, now=NOW, zone="Europe/London", sessions=None, demanding=None):
    evidence.clear()
    view = build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone=zone, now=now)
    if sessions is not None:
        assert evidence, "Today must evaluate fresh workload, not its check-in snapshot"
        checkin, context, decision = evidence[-1]
        workload = completed_workload(context.recent_sessions, view.today.training_day)
        assert workload["sessions"] == sessions
        assert workload["demanding_sessions"] == demanding
        assert view.today.recommendation_state == decision.decision
        assert view.today.recommendation_reason == decision.message
        assert checkin.body == "flat"
    return view


def manual(store, *, now=NOW, effort="hard", request=None):
    return create_external_training(store, ATHLETE, "Europe/London", ExternalTrainingCreate(
        activity="boxing", duration_minutes=90, effort=effort, client_request_id=request or uuid4()), now=now)


def test_exact_strength_boxing_edit_delete_sequence(evidence):
    store = checked_store()
    main = store.plans[PLAN]["structured_plan"]["weeks"][0]["days"][0]["sessions"][0]
    main.update(session_type="strength", title="Strength")
    before = deepcopy((store.plans, store.today_checkins))
    read(store, evidence, sessions=0, demanding=0)
    report(store, now=NOW.replace(hour=9))
    strength = deepcopy(store.session_completions)
    first = read(store, evidence, now=NOW.replace(hour=9), sessions=1, demanding=1)
    assert "Heavy recent load" not in first.today.recommendation_trigger_labels
    assert store.get_session_completion(ATHLETE, "sibling", DAY)["completion_origin"] == "day_credit"
    boxing = manual(store, now=NOW.replace(hour=18))
    second = read(store, evidence, now=NOW.replace(hour=18), sessions=2, demanding=2)
    assert "Heavy recent load" in second.today.recommendation_trigger_labels
    assert {row["source"] for row in evidence[-1][1].recent_sessions} == {"unlxck", "external"}
    update_external_training(store, ATHLETE, boxing["id"], ExternalTrainingFields(
        activity="boxing", duration_minutes=90, effort="moderate"))
    edited = read(store, evidence, now=NOW.replace(hour=19), sessions=2, demanding=1)
    assert "Heavy recent load" not in edited.today.recommendation_trigger_labels
    assert [r["effort"] for r in evidence[-1][1].recent_sessions if r["source"] == "external"] == ["moderate"]
    delete_external_training(store, ATHLETE, boxing["id"])
    deleted = read(store, evidence, now=NOW.replace(hour=19, minute=15), sessions=1, demanding=1)
    assert deleted.today.recommendation_reason == first.today.recommendation_reason
    assert store.session_completions == strength
    assert (store.plans, store.today_checkins) == before
    assert not store.rehab_exposures and not store.sparring_logs


def test_two_prescribed_reports_and_rpe_correction_refresh_without_manual_probe(evidence):
    store = checked_store()
    first = report(store)
    read(store, evidence, sessions=1, demanding=1)
    second = report(store, "sibling", now=NOW + timedelta(hours=1))
    loaded = read(store, evidence, sessions=2, demanding=2)
    assert "Heavy recent load" in loaded.today.recommendation_trigger_labels
    assert {row["id"] for row in evidence[-1][1].recent_sessions} == {first["id"], second["id"]}
    # Retrying the same completion preserves its occurrence; changing its RPE
    # replaces the actual report rather than appending an extra workload event.
    report(store, "sibling", session_rpe=5)
    updated = read(store, evidence, sessions=2, demanding=1)
    assert "Heavy recent load" not in updated.today.recommendation_trigger_labels
    report(store, "sibling", session_rpe=5)
    assert read(store, evidence, sessions=2, demanding=1).today == updated.today


def test_manual_only_repeat_edit_delete_and_late_create_retry(evidence):
    from fastapi import HTTPException
    store = checked_store()
    request = uuid4()
    first = manual(store, request=request)
    read(store, evidence, sessions=1, demanding=1)
    assert manual(store, request=request)["id"] == first["id"]
    read(store, evidence, sessions=1, demanding=1)
    second = manual(store)
    assert second["id"] != first["id"]
    loaded = read(store, evidence, sessions=2, demanding=2)
    assert "Heavy recent load" in loaded.today.recommendation_trigger_labels
    for row in (first, second):
        delete_external_training(store, ATHLETE, row["id"])
    empty = read(store, evidence, sessions=0, demanding=0)
    assert "Heavy recent load" not in empty.today.recommendation_trigger_labels
    with pytest.raises(HTTPException) as error:
        manual(store, request=request)
    assert error.value.status_code == 410
    read(store, evidence, sessions=0, demanding=0)


@pytest.mark.parametrize("source", ["list_session_completions", "list_external_training_sessions"])
def test_failed_history_after_successful_write_is_conservative_and_retries(monkeypatch, evidence, source):
    store = checked_store(body="normal")
    saved = manual(store)
    before = deepcopy(store.external_training_sessions)
    original = getattr(store, source)
    with monkeypatch.context() as outage:
        def fail(*args, **kwargs):
            raise RuntimeError("history unavailable")
        outage.setattr(store, source, fail)
        view = read(store, evidence)
        assert view.today.recommendation_state != "train_as_planned"
        assert view.today.recommendation_confidence != "high"
        assert "recent session" in view.today.recommendation_confidence_note.lower()
    assert store.external_training_sessions == before
    assert getattr(store, source) == original
    recovered = read(store, evidence)
    assert saved["id"] in {r["id"] for r in evidence[-1][1].recent_sessions}
    assert recovered.today.recommendation_state == evidence[-1][2].decision


def test_evaluation_failure_does_not_undo_completed_write(monkeypatch, evidence):
    store = checked_store()
    saved = manual(store)
    with monkeypatch.context() as outage:
        def fail(*args, **kwargs):
            raise RuntimeError("evaluation unavailable")
        outage.setattr(today_service, "build_readiness_adjustment", fail)
        with pytest.raises(RuntimeError, match="evaluation unavailable"):
            read(store, evidence)
    assert [row["id"] for row in training_history(store, ATHLETE)] == [saved["id"]]
    read(store, evidence, sessions=1, demanding=1)


def test_unknown_legacy_is_not_recovery_and_does_not_rewrite_history(evidence):
    store = checked_store(body="normal")
    store.upsert_session_completion(ATHLETE, {"plan_id": PLAN, "session_id": "main",
        "training_day": DAY, "status": "done", "session_rpe": 9})
    before = deepcopy(store.session_completions)
    view = read(store, evidence)
    assert completed_workload(evidence[-1][1].recent_sessions, DAY)["sessions"] == 0
    assert view.today.recommendation_state != "train_as_planned"
    assert store.session_completions == before


@pytest.mark.parametrize("restriction", ["neurological_symptoms", "sharp_pain", "injury"])
def test_safety_precedence_after_workload_removed(evidence, restriction):
    store = checked_store(**({restriction: True} if restriction != "injury" else {}))
    if restriction == "injury":
        store.create_injury_flag(ATHLETE, {"body_area": "knee", "description": "Knee injury",
            "severity": "severe", "status": "open"})
    row = manual(store)
    view = read(store, evidence)
    assert view.today.recommendation_state == "pull_back"
    delete_external_training(store, ATHLETE, row["id"])
    view = read(store, evidence)
    assert view.today.recommendation_state == "pull_back"
    assert view.today.decision_tier in {"stop", "pull_back"}


def test_read_reuses_successful_history_within_build_but_never_across_reads(monkeypatch, evidence):
    store = checked_store()
    report(store)
    counts = {"list_session_completions": 0, "list_external_training_sessions": 0}
    # Consumers ask for different windows: only identical reads can be shared.
    calls = []
    for name in counts:
        original = getattr(store, name)
        def wrapped(*args, _name=name, _original=original, **kwargs):
            counts[_name] += 1
            calls.append((_name, repr(args), repr(kwargs)))
            return _original(*args, **kwargs)
        monkeypatch.setattr(store, name, wrapped)
    first = read(store, evidence, sessions=1, demanding=1)
    assert len(calls) == len(set(calls))
    assert not any("include_deleted': True" in call[2] for call in calls)
    previous = dict(counts)
    calls.clear()
    assert read(store, evidence, sessions=1, demanding=1).today == first.today
    assert counts == {key: value * 2 for key, value in previous.items()}
    assert len(calls) == len(set(calls))


def test_athlete_local_rollover_never_reuses_yesterdays_checkin(evidence):
    store = checked_store()
    report(store)
    # 02:00 UTC is still the previous New York training day (04:00 cutoff).
    now = NOW + timedelta(days=1)
    now = now.replace(hour=2)
    view = read(store, evidence, now=now, zone="America/New_York", sessions=1, demanding=1)
    assert view.today.training_day == DAY
    next_day = read(store, evidence, now=now.replace(hour=12), zone="America/New_York")
    assert next_day.today.training_day != DAY
    assert next_day.today.decision_tier == "not_checked_in"


def test_overlapping_evaluations_cannot_persist_an_older_recommendation(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    store = checked_store()
    manual(store)
    before = deepcopy(store.today_checkins)
    captured, release = Event(), Event()
    engine = today_service.build_readiness_adjustment
    inputs = []

    def paused(checkin, context):
        count = completed_workload(context.recent_sessions, DAY)["sessions"]
        inputs.append(count)
        if count == 1:
            captured.set()
            assert release.wait(10), "test failed to release old evaluation"
        return engine(checkin, context)

    monkeypatch.setattr(today_service, "build_readiness_adjustment", paused)
    def load():
        return build_today_command_view(store, athlete_id=ATHLETE, athlete_timezone="Europe/London", now=NOW)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old = pool.submit(load)
        try:
            assert captured.wait(10), "old evaluation never reached the engine"
            manual(store, now=NOW + timedelta(hours=1))
            newest = load()
            assert "Heavy recent load" in newest.today.recommendation_trigger_labels
        finally:
            release.set()
        older = old.result(timeout=10)
    assert "Heavy recent load" not in older.today.recommendation_trigger_labels
    assert load().today.recommendation_reason == newest.today.recommendation_reason
    assert inputs == [1, 2, 2]
    assert store.today_checkins == before


@pytest.mark.parametrize("invalidation_fails", [False, True])
def test_successful_route_mutations_then_authoritative_read(monkeypatch, evidence, invalidation_fails):
    import api.app
    from api.services.today_command_cache import recent_today_command
    from tests.support import _build_client
    class Clock(type(NOW)):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(today_service, "datetime", Clock)
    # Session completion builds Today through the readiness boundary, which
    # reads its own clock; it must see the same day as the seeded check-in.
    from api.services import today_readiness_boundary, today_readiness_boundary_core
    monkeypatch.setattr(today_readiness_boundary, "datetime", Clock)
    monkeypatch.setattr(today_readiness_boundary_core, "datetime", Clock)
    client, store, _ = _build_client()
    seeded = checked_store()
    store.plans = seeded.plans
    store.today_checkins = seeded.today_checkins
    store.set_active_plan_id(ATHLETE, PLAN)
    auth = {"Authorization": "Bearer athlete-token"}
    def get():
        evidence.clear()
        response = client.get("/api/today", headers=auth)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        return response.json()["today"]
    initial = get()
    if invalidation_fails:
        def fail(*args, **kwargs):
            raise RuntimeError("cache unavailable")
        monkeypatch.setattr(api.app, "forget_today_command", fail)
    response = client.post("/api/today/session-completion", headers=auth, json={
        "plan_id": PLAN, "session_id": "main", "status": "done", "session_rpe": 8})
    assert response.status_code == 201, response.text
    if not invalidation_fails:
        assert recent_today_command(store, athlete_id=ATHLETE, athlete_timezone="Europe/London") is None
    get()
    assert completed_workload(evidence[-1][1].recent_sessions, DAY)["sessions"] == 1
    response = client.post("/api/training/sessions", headers=auth, json={
        "activity": "boxing", "duration_minutes": 90, "effort": "hard",
        "training_day": DAY, "client_request_id": str(uuid4())})
    assert response.status_code == 201, response.text
    entry_id = response.json()["id"]
    loaded = get()
    assert "Heavy recent load" in loaded["recommendation_trigger_labels"]
    assert completed_workload(evidence[-1][1].recent_sessions, DAY)["sessions"] == 2
    response = client.patch(f"/api/training/sessions/{entry_id}", headers=auth, json={
        "activity": "boxing", "duration_minutes": 90, "effort": "moderate"})
    assert response.status_code == 200, response.text
    assert "Heavy recent load" not in get()["recommendation_trigger_labels"]
    assert completed_workload(evidence[-1][1].recent_sessions, DAY)["demanding_sessions"] == 1
    assert client.delete(f"/api/training/sessions/{entry_id}", headers=auth).status_code == 204
    assert "Heavy recent load" not in get()["recommendation_trigger_labels"]
    assert completed_workload(evidence[-1][1].recent_sessions, DAY)["sessions"] == 1
    assert initial["training_day"] == DAY


def test_today_opened_during_pending_mutation_refreshes_after_commit(monkeypatch, evidence):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    store = checked_store()
    entered, commit = Event(), Event()
    original = store.create_external_training_session
    def delayed(*args, **kwargs):
        entered.set()
        assert commit.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(store, "create_external_training_session", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(manual, store)
        try:
            assert entered.wait(10)
            read(store, evidence, sessions=0, demanding=0)
        finally:
            commit.set()
        pending.result(timeout=10)
    read(store, evidence, sessions=1, demanding=1)


def test_separate_worker_store_does_not_serve_its_old_cached_command(evidence):
    from api.services.today_command_cache import remember_today_command
    store = checked_store()
    # Two server-side store facades over the same persistence, with independent
    # process caches. This exercises the same path regardless of client device.
    class WorkerStore:
        def __init__(self):
            self._unlxck_today_command_cache = {}
        def __getattr__(self, name):
            return getattr(store, name)
    worker_one, worker_two = WorkerStore(), WorkerStore()
    old = read(worker_two, evidence, sessions=0, demanding=0)
    remember_today_command(worker_two, athlete_id=ATHLETE, athlete_timezone="Europe/London", view=old)
    manual(worker_one)
    manual(worker_one, now=NOW + timedelta(hours=1))
    current = read(worker_two, evidence, sessions=2, demanding=2)
    assert "Heavy recent load" in current.today.recommendation_trigger_labels
    assert "Heavy recent load" not in old.today.recommendation_trigger_labels
