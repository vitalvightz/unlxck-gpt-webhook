"""Audit characterizations of Main; defect assertions describe observed behavior.

These tests deliberately do not implement a new workload or completion policy.
The report explains which assertions must change in a follow-up fix.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from api.contracts.readiness_message import ReadinessCheckin, build_readiness_adjustment
from api.services import today_service
from api.services.sparring_readiness_snapshot import annotate_payload_with_sparring_readiness
from api.services.today_readiness_boundary import build_today_command_view
from api.services.training_history import training_history
from fightcamp.completed_workload import completed_workload
from fightcamp.sparring_readiness import sparring_readiness_flags
from tests.support import FakeStore
from tests.test_external_training import DAY, NOW, adaptive_context, seed_manual


def _checkin(store, **changes):
    store.upsert_today_checkin("athlete-1", {
        "plan_id": next(iter(store.plans)), "training_day": DAY,
        "sleep": "good", "body": "sharp", "pain": "none", "phase": "SPP",
        "recommendation_state": "train_as_planned", "recommendation_triggers": [],
        **changes,
    })


def _view(store):
    return build_today_command_view(store, athlete_id="athlete-1",
                                   athlete_timezone="Europe/London", now=NOW)


def _prescribed(store, session="conditioning", **changes):
    return store.upsert_session_completion("athlete-1", {
        "plan_id": next(iter(store.plans)), "session_id": session,
        "training_day": DAY, "status": "done", "session_rpe": 8, **changes,
    })


@pytest.mark.parametrize("source", ["mixed", "manual", "prescribed"])
def test_separately_stored_same_day_occurrences_remain_two(source):
    store = FakeStore()
    context = adaptive_context(store)
    if source in {"mixed", "prescribed"}:
        _prescribed(store)
    else:
        seed_manual(store)
    if source in {"mixed", "manual"}:
        seed_manual(store)
    else:
        _prescribed(store, "second")
    rows = training_history(store, "athlete-1")
    assert len(rows) == 2
    assert completed_workload(rows + rows, DAY)["sessions"] == 2
    assert completed_workload(rows, DAY)["demanding_sessions"] == 2
    assert len({row["training_day"] for row in rows}) == 1
    adjustment = build_readiness_adjustment(ReadinessCheckin(body="flat"),
                                           replace(context, recent_sessions=rows))
    assert "recent_hard_load_plus_poor_today" in adjustment.triggers


def test_audit_one_submission_fans_out_and_becomes_two_demanding_workouts():
    store = FakeStore()
    context = adaptive_context(store)
    plan = next(iter(store.plans.values()))
    plan["structured_plan"]["weeks"][0]["days"][0]["sessions"].append({
        "session_id": "breathing", "session_type": "recovery",
        "title": "Breathing reset", "blocks": [],
    })
    today_service.upsert_session_completion(store, athlete_id="athlete-1",
        athlete_timezone="Europe/London", now=NOW,
        payload={"plan_id": plan["id"], "session_id": "conditioning", "status": "done", "session_rpe": 8})
    rows = training_history(store, "athlete-1")
    assert {row["session_id"] for row in rows} == {"conditioning", "breathing"}
    assert completed_workload(rows, DAY)["demanding_sessions"] == 2
    adjustment = build_readiness_adjustment(ReadinessCheckin(body="flat"),
                                           replace(context, recent_sessions=rows))
    assert "recent_hard_load_plus_poor_today" in adjustment.triggers


def test_audit_cap_loses_a_rule_and_order_changes_the_decision():
    context = adaptive_context(FakeStore())
    rows = [
        {"id": str(i), "source": "external", "training_day": day,
         "duration_minutes": 30, "effort": effort}
        for i, (day, effort) in enumerate([
            (DAY, "easy"), ("2026-10-09", "easy"), ("2026-10-08", "easy"),
            ("2026-10-07", "hard"), ("2026-10-06", "hard"),
        ])
    ]
    assert completed_workload(rows, DAY) == {
        "sessions": 3, "demanding_sessions": 0, "actual_minutes": 90, "hard_minutes": 0}
    assert completed_workload(rows, DAY, limit=None)["demanding_sessions"] == 2
    clean = ReadinessCheckin(sleep="good", body="sharp", pain="none", phase="SPP")
    capped = build_readiness_adjustment(clean, replace(context, recent_sessions=rows))
    reordered = build_readiness_adjustment(clean, replace(context, recent_sessions=list(reversed(rows))))
    assert capped.decision == "train_as_planned"
    assert reordered.decision == "modify"
    assert "recent_hard_session" in reordered.triggers


def test_audit_real_history_cap_hides_hard_work_after_easy_sessions():
    store = FakeStore()
    for day, effort in [("2026-10-06", "hard"), ("2026-10-07", "hard"),
                        ("2026-10-08", "easy"), ("2026-10-09", "easy"), (DAY, "easy")]:
        seed_manual(store, day=day, effort=effort)
    context = adaptive_context(store)
    assert [row["training_day"] for row in context.recent_sessions] == [
        DAY, "2026-10-09", "2026-10-08", "2026-10-07", "2026-10-06"]
    assert completed_workload(context.recent_sessions, DAY)["demanding_sessions"] == 0
    assert completed_workload(context.recent_sessions, DAY, limit=None)["demanding_sessions"] == 2
    assert build_readiness_adjustment(ReadinessCheckin(phase="SPP"), context).decision == "train_as_planned"


def test_audit_second_prescribed_submission_overwrites_first_sessions_rpe():
    store = FakeStore()
    adaptive_context(store)
    plan = next(iter(store.plans.values()))
    plan["structured_plan"]["weeks"][0]["days"][0]["sessions"].append({
        "session_id": "strength", "session_type": "strength", "title": "Strength", "blocks": []})
    for session, rpe in [("conditioning", 6), ("strength", 9)]:
        today_service.upsert_session_completion(store, athlete_id="athlete-1",
            athlete_timezone="Europe/London", now=NOW,
            payload={"plan_id": plan["id"], "session_id": session, "status": "done", "session_rpe": rpe})
    assert [row["session_rpe"] for row in training_history(store, "athlete-1")] == [9, 9]


def test_audit_truncation_before_status_filter_can_hide_all_completed_work():
    store = FakeStore()
    adaptive_context(store)
    _prescribed(store, "hard-1", training_day="2026-10-09")
    _prescribed(store, "hard-2", training_day="2026-10-09")
    for index in range(200):
        _prescribed(store, str(index), status="started")
    assert training_history(store, "athlete-1") == []
    assert len(training_history(store, "athlete-1", limit=202)) == 2
    context, availability = today_service._readiness_context_and_status(store,
        athlete_id="athlete-1", plan_row=next(iter(store.plans.values())),
        training_day=DAY, phase="SPP")
    assert "completions_unavailable" not in availability.reason_codes
    assert build_readiness_adjustment(ReadinessCheckin(phase="SPP"), context).decision == "train_as_planned"


def test_audit_prescribed_only_new_work_does_not_refresh_stored_recommendation():
    store = FakeStore()
    context = adaptive_context(store)
    _checkin(store, body="flat")
    _prescribed(store)
    _prescribed(store, "second")
    fresh = build_readiness_adjustment(ReadinessCheckin(body="flat", phase="SPP"),
        replace(context, recent_sessions=training_history(store, "athlete-1")))
    assert "recent_hard_load_plus_poor_today" in fresh.triggers
    assert "Heavy recent load" not in _view(store).today.recommendation_trigger_labels
    # Even an Easy manual row enables the live re-evaluation gate.
    seed_manual(store, effort="easy")
    assert "Heavy recent load" in _view(store).today.recommendation_trigger_labels


def test_manual_edit_delete_recompute_display_without_rewriting_history():
    store = FakeStore()
    adaptive_context(store)
    _checkin(store, body="flat")
    seed_manual(store)
    second = seed_manual(store)
    before = deepcopy((store.plans, store.today_checkins, store.session_completions))
    assert "Heavy recent load" in _view(store).today.recommendation_trigger_labels
    store.update_external_training_session("athlete-1", second["id"], {
        "activity": "boxing", "effort": "easy", "duration_minutes": 30})
    assert "Heavy recent load" not in _view(store).today.recommendation_trigger_labels
    store.delete_external_training_session("athlete-1", second["id"])
    assert "Heavy recent load" not in _view(store).today.recommendation_trigger_labels
    assert before == (store.plans, store.today_checkins, store.session_completions)


def test_manual_refresh_preserves_neurological_stop():
    store = FakeStore()
    adaptive_context(store)
    _checkin(store, neurological_symptoms=True, recommendation_state="pull_back",
             recommendation_triggers=["neurological_symptoms"])
    seed_manual(store)
    seed_manual(store)
    assert _view(store).today.decision_tier == "stop"


def test_manual_after_completion_preserves_accepted_prescription_and_history():
    store = FakeStore()
    adaptive_context(store)
    plan = next(iter(store.plans.values()))
    accepted = {"plan_id": plan["id"], "revision": "a" * 64,
                "session": deepcopy(plan["structured_plan"]["weeks"][0]["days"][0]["sessions"][0])}
    _prescribed(store, prescription_snapshot=accepted)
    _checkin(store, body="flat")
    before = deepcopy((store.plans, store.session_completions, store.today_checkins))
    seed_manual(store)
    _view(store)
    assert before == (store.plans, store.session_completions, store.today_checkins)


def test_canonical_today_cannot_stay_green_when_external_history_fails(monkeypatch):
    store = FakeStore()
    adaptive_context(store)
    _checkin(store)
    def unavailable(*args, **kwargs):
        raise RuntimeError("audit simulated outage")
    monkeypatch.setattr(store, "list_external_training_sessions", unavailable)
    assert _view(store).today.recommendation_state != "train_as_planned"


def test_audit_generation_completion_failure_marks_contact_but_not_workload_unavailable(monkeypatch):
    store = FakeStore()
    seed_manual(store)
    def unavailable(*args, **kwargs):
        raise RuntimeError("audit simulated outage")
    monkeypatch.setattr(store, "list_session_completions", unavailable)
    snapshot = annotate_payload_with_sparring_readiness({}, store=store,
        athlete_id="athlete-1", training_day=DAY)["_sparring_readiness"]
    assert "list_session_completions" in snapshot["unavailable"]
    assert snapshot["training_history"]["available"] is True
    assert "sparring_history_unavailable" in sparring_readiness_flags(snapshot)


def test_unknown_duration_is_zero_known_minutes_and_manual_sparring_is_not_contact():
    store = FakeStore()
    adaptive_context(store)
    _prescribed(store)
    seed_manual(store, duration=45)
    rows = training_history(store, "athlete-1")
    assert completed_workload(rows, DAY) == {
        "sessions": 2, "demanding_sessions": 2, "actual_minutes": 45, "hard_minutes": 45}
    manual = next(row for row in rows if row["source"] == "external")
    assert not sparring_readiness_flags({"as_of": DAY, "sessions": [manual]})
