"""Persisted Today inputs must reach canonical hard-sparring eligibility."""
from datetime import datetime, timedelta
import logging

import pytest

from api.models import PlanRequest, TodayCheckinRequest
from api.services.sparring_readiness_snapshot import annotate_payload_with_sparring_readiness
from fightcamp import input_parsing
from fightcamp.athlete_model import _build_athlete_model
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_runtime import build_runtime_context
from fightcamp.sparring_dose_planner import hard_sparring_cutoff, hard_sparring_risk_state
from tests.support import FakeStore
from tests.test_dynamic_sparring_cutoff import _single_day

TODAY = datetime(2026, 9, 4, 12)
ATHLETE = "sparring-athlete"


def _day(age):
    return (TODAY - timedelta(days=age)).date().isoformat()


def _checkin(store, age, athlete=ATHLETE, plan="old", **fields):
    request = TodayCheckinRequest(plan_id=plan, sleep="poor", body="flat", pain="none", phase="SPP", **fields)
    store.upsert_today_checkin(athlete, {**request.model_dump(), "training_day": _day(age)})


def _session(store, age, title="Hard sparring", athlete=ATHLETE, status="done", session_rpe=5):
    session_id = f"{title}-{age}"
    plan_id = f"plan-{athlete}"
    plan = store.plans.setdefault(plan_id, {"athlete_id": athlete, "structured_plan": {"weeks": [{"days": []}]}})
    plan["structured_plan"]["weeks"][0]["days"].append({"date": _day(age), "sessions": [
        {"session_id": session_id, "title": title, "blocks": []},
        {"session_id": "other-contact", "title": "Hard sparring"},
    ]})
    store.upsert_session_completion(athlete, {"plan_id": plan_id, "session_id": session_id, "training_day": _day(age), "status": status, "session_rpe": session_rpe})


def _model(store, monkeypatch, requested=False):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: TODAY)
    request = PlanRequest(athlete={"full_name": "Fighter", "technical_style": ["boxing"], "professional_status": "professional"},
        fight_date="2026-09-20", fatigue_level="low", weekly_training_frequency=4,
        training_availability=["monday", "wednesday", "friday", "sunday"],
        hard_sparring_days=["friday"], reduced_contact_requested=requested)
    payload = annotate_payload_with_sparring_readiness(request.to_payload(), store=store, athlete_id=ATHLETE, training_day=_day(0))
    parsed = PlanInput.from_payload(payload)
    context = build_runtime_context(plan_input=parsed, random_seed=1, logger=logging.getLogger("test"))
    return _build_athlete_model(training_context=context.training_context, sport="boxing", record="9-2", rounds_format="3x3", camp_length_weeks=4, short_notice=False)


@pytest.mark.parametrize("source,flag", [("recovery", "poor_recovery"), ("contact", "high_contact_load"), ("request", "reduced_contact_requested"), ("rpe", "high_fatigue")])
def test_persisted_inputs_reach_athlete_model_and_d17_conversion(monkeypatch, source, flag):
    store = FakeStore()
    if source == "recovery":
        for age in [0, 1, 2]:
            _checkin(store, age)
    if source in {"contact", "rpe"}:
        for age in [0, 2]:
            _session(store, age, title="Hard sparring" if source == "contact" else "Strength", session_rpe=9 if source == "rpe" else 5)
    model = _model(store, monkeypatch, requested=source == "request")
    assert flag in model["readiness_flags"]
    assert "sparring_readiness" not in model
    assert hard_sparring_risk_state(model) == "ELEVATED"
    assert hard_sparring_cutoff(model) == 17
    assert _single_day(16, **model)[2]["effective_load"] == "technical"


@pytest.mark.parametrize("source", ["empty", "one_bad_day", "duplicates", "stale", "future", "other_athlete", "strength", "skipped", "non_contact"])
def test_history_does_not_fabricate_elevated_risk(monkeypatch, source):
    store = FakeStore()
    if source == "one_bad_day":
        _checkin(store, 0)
    if source == "duplicates":
        for plan in ["a", "b", "c"]:
            _checkin(store, 0, plan=plan)
    if source in {"stale", "future", "other_athlete"}:
        for age in ([8, 9, 10] if source == "stale" else [-1, -2, -3] if source == "future" else [0, 1, 2]):
            _checkin(store, age, athlete="other" if source == "other_athlete" else ATHLETE)
            _session(store, age, athlete="other" if source == "other_athlete" else ATHLETE)
    if source in {"strength", "skipped", "non_contact"}:
        for age in [0, 1, 2]:
            _session(store, age, title="Strength" if source == "strength" else "Non-contact sparring drills" if source == "non_contact" else "Hard sparring", status="skipped" if source == "skipped" else "done")
    model = _model(store, monkeypatch)
    assert hard_sparring_risk_state(model) == "NORMAL"
    assert hard_sparring_cutoff(model) == 14
    assert _single_day(16, **model)[2]["effective_load"] == "hard"


def test_persisted_neurological_checkin_blocks_contact(monkeypatch):
    store = FakeStore()
    _checkin(store, 0, neurological_symptoms=True)
    model = _model(store, monkeypatch)
    assert hard_sparring_risk_state(model) == "CONTACT_BLOCKED"
    assert _single_day(30, **model)[2]["effective_load"] == "none"


def test_open_head_injury_does_not_expire_with_history_window(monkeypatch):
    store = FakeStore()
    store.create_injury_flag(ATHLETE, {"description": "suspected concussion", "body_area": "head", "severity": "severe", "status": "open", "created_at": "2025-01-01"})
    model = _model(store, monkeypatch)
    assert hard_sparring_risk_state(model) == "CONTACT_BLOCKED"


def test_failed_history_read_is_explicit_and_conservative(monkeypatch):
    store = FakeStore()
    def fail(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(store, "list_today_checkins", fail)
    model = _model(store, monkeypatch)
    assert "sparring_history_unavailable" in model["readiness_flags"]
    assert "sparring_readiness" not in model
    assert hard_sparring_cutoff(model) == 17


def _assert_history_planner(payload, *, progress_callback=None):
    from tests.support import stage1_result
    from fightcamp.sparring_readiness import sparring_readiness_flags
    assert "poor_recovery" in sparring_readiness_flags(payload["_sparring_readiness"])
    return stage1_result()


def test_generation_worker_loads_history_before_invoking_stage1():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.auth import AuthenticatedUser
    from api.services.today_service import resolve_training_day
    from tests.support import FakeAuthService, FakeStage2Automator, finalized_result, seed_default_profiles, _start_generation
    store = FakeStore()
    seed_default_profiles(store)
    today = datetime.fromisoformat(resolve_training_day("Europe/London"))
    for age in [0, 1, 2]:
        store.upsert_today_checkin("athlete-1", {"plan_id": "previous-plan", "training_day": (today - timedelta(days=age)).date().isoformat(), "sleep": "poor", "body": "flat", "pain": "none", "phase": "SPP"})
    athlete = AuthenticatedUser(user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={})
    client = TestClient(create_app(store=store, auth_service=FakeAuthService({"athlete-token": athlete}), planner=_assert_history_planner, stage2_automator=FakeStage2Automator(result=finalized_result()), enable_in_process_generation=True))
    _, job = _start_generation(client)
    assert job["status"] == "completed"
    assert "_sparring_readiness" not in store.get_latest_intake("athlete-1")["intake"]


@pytest.mark.parametrize("title,ages,expected", [
    ("Hard sparring", [0, 3], 14),
    ("Hard sparring", [0, 3, 6], 17),
    ("Hard sparring — reduced dose", [0, 1], 14),
    ("Hard sparring — reduced dose", [0, 2, 4, 6], 17),
])
def test_contact_thresholds_preserve_reduced_dose_classification(monkeypatch, title, ages, expected):
    store = FakeStore()
    for age in ages:
        _session(store, age, title=title)
    assert hard_sparring_cutoff(_model(store, monkeypatch)) == expected


def test_completion_cannot_read_another_athletes_plan(monkeypatch):
    store = FakeStore()
    _session(store, 0)
    store.plans[f"plan-{ATHLETE}"]["athlete_id"] = "someone-else"
    model = _model(store, monkeypatch)
    assert "sparring_history_unavailable" in model["readiness_flags"]
    assert "sparring_readiness" not in model
    assert hard_sparring_cutoff(model) == 17


def test_canonical_controlled_hard_contact_counts_as_hard(monkeypatch):
    store = FakeStore()
    for age in [0, 2]:
        _session(store, age, title="Hard sparring — controlled hard contact")
    model = _model(store, monkeypatch)
    assert "high_contact_load" in model["readiness_flags"]
    assert hard_sparring_cutoff(model) == 17


def test_raw_sparring_history_is_not_copied_into_athlete_model(monkeypatch):
    store = FakeStore()
    for age in [0, 1, 2]:
        _checkin(store, age)
    model = _model(store, monkeypatch)
    assert "poor_recovery" in model["readiness_flags"]
    assert "sparring_readiness" not in model
