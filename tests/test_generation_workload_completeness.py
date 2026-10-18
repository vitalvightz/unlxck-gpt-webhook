"""Source health survives real snapshot -> runtime -> sparring decisions."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.contracts.external_training import ExternalTrainingCreate
from api.generation_runtime import run_generation_job
from api.models import PlanRequest
from api.services.sparring_readiness_snapshot import annotate_payload_with_sparring_readiness
from api.services.training_history import create_external_training
from fightcamp.athlete_model import _build_athlete_model
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import _generate_conditioning_blocks
from fightcamp.plan_pipeline_runtime import build_runtime_context
from fightcamp.sparring_dose_planner import hard_sparring_cutoff, hard_sparring_risk_state
from fightcamp.sparring_readiness import sparring_readiness_flags
from tests.support import FakeStore, FakeStage2Automator, _build_request, finalized_result, seed_default_profiles, stage1_result
from tests.test_dynamic_sparring_cutoff import _single_day
from tests.test_store_external_training import store_query

ATHLETE = "athlete-1"
DAY = "2026-10-18"
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
PRESCRIBED = "list_session_completions"
MANUAL = "list_external_training_sessions"


@pytest.fixture(autouse=True)
def evaluation_clock(monkeypatch):
    monkeypatch.setattr("fightcamp.input_parsing._utc_now", lambda: NOW)
    monkeypatch.setattr("api.services.sparring_readiness_snapshot.resolve_training_day", lambda zone: DAY)


def request():
    return PlanRequest(athlete={"full_name": "Fighter", "technical_style": ["boxing"], "professional_status": "professional"},
        fight_date="2026-11-20", fatigue_level="low", weekly_training_frequency=4,
        training_availability=["monday", "wednesday", "friday", "sunday"], hard_sparring_days=["friday"])


def prescribed(store, session="strength", *, day=DAY, origin="reported", rpe=5):
    plan = store.plans.setdefault("history-plan", {"id": "history-plan", "athlete_id": ATHLETE,
        "structured_plan": {"weeks": [{"days": []}]}})
    plan["structured_plan"]["weeks"][0]["days"].append({"date": day, "sessions": [
        {"session_id": session, "title": "Strength", "session_type": "strength", "blocks": []}]})
    return store.upsert_session_completion(ATHLETE, {"plan_id": "history-plan", "session_id": session,
        "training_day": day, "status": "done", "session_rpe": rpe, "completion_origin": origin})


def manual(store, *, effort="hard", now=NOW):
    return create_external_training(store, ATHLETE, "", ExternalTrainingCreate(
        activity="boxing", duration_minutes=90, effort=effort, client_request_id=uuid4()), now=now)


def snapshot(store, *, day=DAY):
    return annotate_payload_with_sparring_readiness(request().to_payload(), store=store,
        athlete_id=ATHLETE, training_day=day)["_sparring_readiness"]


def downstream(context, payload=None):
    parsed = PlanInput.from_payload({**(payload or request().to_payload()), "_sparring_readiness": context})
    runtime = build_runtime_context(plan_input=parsed, random_seed=1, logger=logging.getLogger("test"))
    model = _build_athlete_model(training_context=runtime.training_context, sport="boxing", record="9-2",
        rounds_format="3x3", camp_length_weeks=4, short_notice=False)
    return runtime, model


def fail(*args, **kwargs):
    raise RuntimeError("private database exception must not be logged")


@pytest.mark.parametrize("failed", [(), (PRESCRIBED,), (MANUAL,), (PRESCRIBED, MANUAL)])
def test_source_failures_preserve_verified_work_and_final_safety_decision(monkeypatch, failed):
    store = FakeStore()
    strength, boxing = prescribed(store), manual(store)
    for source in failed:
        monkeypatch.setattr(store, source, fail)
    result = snapshot(store)
    history = result["training_history"]
    assert history["available"] is (not failed)
    assert set(history["unavailable"]) == set(failed)
    assert set(result["unavailable"]) == set(failed)
    expected = ({strength["id"]} if PRESCRIBED not in failed else set()) | ({boxing["id"]} if MANUAL not in failed else set())
    assert {row["id"] for row in history["sessions"]} == expected
    assert history["workload"]["sessions"] == len(expected)
    assert history["workload"]["actual_minutes"] == (90 if MANUAL not in failed else 0)
    # Unknown workload is not manufactured heavy workload or head contact.
    flags = sparring_readiness_flags(result)
    assert "high_contact_load" not in flags and "high_fatigue" not in flags
    assert ("sparring_history_unavailable" in flags) is bool(failed)
    _, model = downstream(result)
    assert hard_sparring_risk_state(model) == ("ELEVATED" if failed else "NORMAL")
    assert hard_sparring_cutoff(model) == (17 if failed else 14)
    assert _single_day(16, **model)[2]["effective_load"] == ("technical" if failed else "hard")
    assert all(row["contact_load"] == "none" for row in result["sessions"])
    assert not store.sparring_logs and not store.rehab_exposures


def test_successful_empty_history_is_complete_and_keeps_normal_low_load_policy():
    result = snapshot(FakeStore())
    assert result["unavailable"] == []
    assert result["training_history"]["available"] is True
    assert result["training_history"]["unavailable"] == []
    assert result["training_history"]["sessions"] == []
    assert result["training_history"]["workload"] == {
        "sessions": 0, "demanding_sessions": 0, "actual_minutes": 0, "hard_minutes": 0}
    _, model = downstream(result)
    assert hard_sparring_risk_state(model) == "NORMAL"
    assert _single_day(16, **model)[2]["effective_load"] == "hard"


@pytest.mark.parametrize("source", [PRESCRIBED, MANUAL])
def test_next_read_recovers_without_duplicate_workload_or_cached_failure(monkeypatch, source):
    store = FakeStore()
    prescribed(store)
    manual(store)
    before = deepcopy((store.session_completions, store.external_training_sessions))
    with monkeypatch.context() as outage:
        outage.setattr(store, source, fail)
        broken = snapshot(store)
        assert broken["training_history"]["available"] is False
        assert hard_sparring_risk_state(downstream(broken)[1]) == "ELEVATED"
    for _ in range(2):
        recovered = snapshot(store)
        assert recovered["unavailable"] == []
        assert recovered["training_history"]["available"] is True
        assert recovered["training_history"]["workload"]["sessions"] == 2
        assert hard_sparring_risk_state(downstream(recovered)[1]) == "NORMAL"
    assert (store.session_completions, store.external_training_sessions) == before


@pytest.mark.parametrize("origin,sessions,complete", [("reported", 2, True), ("day_credit", 1, True), (None, 1, False)])
def test_same_day_identity_and_completion_provenance(origin, sessions, complete):
    store = FakeStore()
    prescribed(store, "first", rpe=8)
    prescribed(store, "second", origin=origin, rpe=9)
    before = deepcopy(store.session_completions)
    result = snapshot(store)
    assert result["training_history"]["workload"]["sessions"] == sessions
    assert result["training_history"]["available"] is complete
    flags = sparring_readiness_flags(result)
    assert ("high_fatigue" in flags) is (origin == "reported")
    assert ("sparring_history_unavailable" in flags) is (origin is None)
    _, model = downstream(result)
    assert hard_sparring_cutoff(model) == (14 if origin == "day_credit" else 17)
    assert store.session_completions == before


def test_legacy_window_does_not_extend_five_day_workload_policy():
    store = FakeStore()
    prescribed(store, day="2026-10-12", origin=None)
    result = snapshot(store)
    assert result["training_history"]["available"] is True
    assert result["training_history"]["workload"]["sessions"] == 0
    assert "completion_provenance" in result["unavailable"]  # Existing seven-day contact window.
    assert hard_sparring_risk_state(downstream(result)[1]) == "ELEVATED"


@pytest.mark.parametrize("source", ["list_today_checkins", "list_injury_flags", "get_plan"])
def test_other_safety_sources_retain_component_attribution(monkeypatch, source):
    store = FakeStore()
    prescribed(store)
    monkeypatch.setattr(store, source, fail)
    result = snapshot(store)
    token = "completion_plan" if source == "get_plan" else source
    assert token in result["unavailable"]
    # Injury/contact-plan reads do not erase known physical workload.
    assert result["training_history"]["workload"]["sessions"] == 1
    assert result["training_history"]["available"] is (source != "list_today_checkins")
    if source == "get_plan":
        assert result["sessions"][0]["contact_load"] == "unknown"
    assert hard_sparring_risk_state(downstream(result)[1]) == "ELEVATED"


@pytest.mark.parametrize("source", [PRESCRIBED, MANUAL])
@pytest.mark.parametrize("bad", [None, {}, "invalid", [None], [{"athlete_id": ATHLETE}],
    [{"athlete_id": ATHLETE, "training_day": "bad-date"}], [{"athlete_id": "another-owner"}]])
def test_malformed_source_is_not_successful_empty_evidence(monkeypatch, source, bad):
    store = FakeStore()
    prescribed(store)
    manual(store)
    monkeypatch.setattr(store, source, lambda *args, **kwargs: bad)
    result = snapshot(store)
    assert source in result["training_history"]["unavailable"]
    assert result["training_history"]["available"] is False
    assert result["training_history"]["workload"]["sessions"] == 1
    assert hard_sparring_risk_state(downstream(result)[1]) == "ELEVATED"


def test_partial_malformed_rows_keep_valid_evidence_and_log_only_source_health(monkeypatch, caplog):
    store = FakeStore()
    manual(store)
    original = store.list_external_training_sessions
    monkeypatch.setattr(store, MANUAL, lambda *args, **kwargs: original(*args, **kwargs) + [{"athlete_id": ATHLETE}])
    result = snapshot(store)
    assert result["training_history"]["workload"]["sessions"] == 1
    assert result["training_history"]["available"] is False
    assert hard_sparring_risk_state(downstream(result)[1]) == "ELEVATED"
    assert "source=list_external_training_sessions" in caplog.text
    monkeypatch.setattr(store, PRESCRIBED, fail)
    snapshot(store)
    assert "source=list_session_completions" in caplog.text
    assert "private database exception" not in caplog.text
    assert "boxing" not in caplog.text.lower()


@pytest.mark.parametrize("restriction", ["neurological", "injury"])
def test_missing_workload_cannot_override_existing_contact_or_injury_restrictions(monkeypatch, restriction):
    store = FakeStore()
    if restriction == "neurological":
        store.upsert_today_checkin(ATHLETE, {"plan_id": "p", "training_day": DAY,
            "sleep": "good", "body": "normal", "pain": "none", "neurological_symptoms": True})
    else:
        store.create_injury_flag(ATHLETE, {"body_area": "knee", "description": "knee injury",
            "severity": "severe", "status": "open", "blocked_training_tags": ["contact", "sparring"]})
    monkeypatch.setattr(store, PRESCRIBED, fail)
    result = snapshot(store)
    assert result["training_history"]["available"] is False
    _, model = downstream(result)
    assert hard_sparring_risk_state(model) == "CONTACT_BLOCKED"
    assert _single_day(30, **model)[2]["effective_load"] == "none"


def test_failed_workload_does_not_progress_rehab_or_allow_higher_stage_drills(monkeypatch):
    from api.services.rehab_stage_snapshot import annotate_payload_with_rehab_stage
    from fightcamp.rehab_selector import select_rehab_candidate
    from tests.test_rehab_generation_boundary import ATHLETE as rehab_athlete, _flag_for_guided, _guided
    store = FakeStore()
    guided = _guided("Left ankle")
    _flag_for_guided(store, guided, latest_reported_status="ongoing")
    monkeypatch.setattr(store, PRESCRIBED, fail)
    stamped = annotate_payload_with_rehab_stage({"guided_injuries": [guided]}, store=store, athlete_id=rehab_athlete)
    stage = stamped["guided_injuries"][0]["rehab_generation_context"]["rehab_stage"]
    assert stage == "calm"
    context = annotate_payload_with_sparring_readiness(stamped, store=store, athlete_id=rehab_athlete,
        training_day=DAY)["_sparring_readiness"]
    assert context["training_history"]["available"] is False
    assert hard_sparring_risk_state(downstream(context)[1]) == "ELEVATED"
    selected = select_rehab_candidate(injury={"body_region": "ankle", "canonical_location": "ankle",
        "injury_type": "sprain", "side": "left", "severity": "moderate"}, rehab_stage=stage,
        candidates=[{"id": name, "rehab_stage": name, "target_regions": ["ankle"],
                     "care_pathway": "msk", "injury_type": "sprain"}
                    for name in ("calm", "restore", "load", "dynamic")], available_equipment=None)
    assert selected.selected_drill_id == "calm"
    assert {row["id"] for row in selected.ranked_drills} == {"calm"}


@pytest.mark.parametrize("source", [PRESCRIBED, MANUAL, "list_today_checkins", "list_injury_flags"])
@pytest.mark.parametrize("data", [None, {}, "invalid", [None]])
def test_store_missing_response_data_cannot_masquerade_as_empty(source, data):
    store, query = store_query()
    query.in_.return_value = query
    query.execute.return_value = SimpleNamespace(data=data)
    with pytest.raises(HTTPException) as error:
        getattr(store, source)(ATHLETE)
    assert error.value.status_code == 503
    failed = annotate_payload_with_sparring_readiness({}, store=store, athlete_id=ATHLETE, training_day=DAY)["_sparring_readiness"]
    assert source in failed["unavailable"]
    assert failed["training_history"]["available"] is False
    assert failed["training_history"]["workload"]["sessions"] == 0
    assert hard_sparring_risk_state(downstream(failed)[1]) == "ELEVATED"
    query.execute.return_value = SimpleNamespace(data=[])
    assert getattr(store, source)(ATHLETE) == []
    result = annotate_payload_with_sparring_readiness({}, store=store, athlete_id=ATHLETE, training_day=DAY)["_sparring_readiness"]
    assert result["training_history"]["available"] is True
    assert hard_sparring_risk_state(downstream(result)[1]) == "NORMAL"


def test_partial_history_cannot_run_a_complete_history_conditioning_adjustment(monkeypatch):
    store = FakeStore()
    manual(store)
    manual(store)
    store.upsert_today_checkin(ATHLETE, {"plan_id": "p", "training_day": DAY,
        "sleep": "good", "body": "flat", "pain": "none", "phase": "SPP"})
    original = store.list_session_completions
    monkeypatch.setattr(store, PRESCRIBED, fail)
    result = snapshot(store)
    runtime, model = downstream(result)
    captured = []
    monkeypatch.setattr("fightcamp.plan_pipeline_blocks.generate_conditioning_block",
        lambda flags: (captured.append(flags) or ("", [], [], {}, [], {})))
    _generate_conditioning_blocks(runtime)
    assert result["training_history"]["available"] is False
    assert captured and all(flags["fatigue"] == "low" for flags in captured)
    # Low remains explicit intake fatigue, never a conclusion that the partial
    # workload is complete. Contact uses the existing unavailable-evidence gate.
    assert all(flags["sparring_readiness"]["training_history"]["available"] is False for flags in captured)
    assert hard_sparring_risk_state(model) == "ELEVATED"

    # Once the source recovers, the same two verified Hard sessions plus the
    # current flat check-in can use the existing first-phase adjustment again.
    monkeypatch.setattr(store, PRESCRIBED, original)
    recovered = snapshot(store)
    assert recovered["training_history"]["available"] is True
    assert recovered["training_history"]["workload"]["sessions"] == 2
    captured.clear()
    _generate_conditioning_blocks(downstream(recovered)[0])
    assert captured[0]["fatigue"] == "moderate"
    assert all(flags["fatigue"] == "low" for flags in captured[1:])


def _partial_evidence_planner(payload, *, progress_callback=None):
    context = payload["_sparring_readiness"]
    history = context["training_history"]
    assert history["available"] is False
    assert history["unavailable"] == [PRESCRIBED]
    assert history["workload"]["sessions"] == 1
    assert history["workload"]["actual_minutes"] == 90
    assert context["sessions"] == []
    _, model = downstream(context, payload)
    assert hard_sparring_risk_state(model) == "ELEVATED"
    assert _single_day(16, **model)[2]["effective_load"] == "technical"
    return stage1_result()


@pytest.mark.parametrize("source", ["athlete", "admin_latest_intake", "admin_triage_resume"])
def test_real_generation_and_regeneration_worker_receive_incomplete_evidence(monkeypatch, source):
    store = FakeStore()
    seed_default_profiles(store)
    body = _build_request()
    intake = store.create_intake(ATHLETE, body)
    manual(store)
    monkeypatch.setattr(store, PRESCRIBED, fail)
    plan_id = None
    if source == "admin_triage_resume":
        # Resume regenerates the linked plan; no old stage-one result is reused.
        plan_id = store.create_plan(athlete_id=ATHLETE, intake_id=intake["id"], request=body,
            result={"plan_text": "Old plan"})["id"]
    job = store.create_or_get_generation_job(athlete_id=ATHLETE, client_request_id=str(uuid4()),
        source=source, request_payload=body.model_dump(mode="json"), intake_id=intake["id"], plan_id=plan_id)
    asyncio.run(run_generation_job(job_id=job["id"], store=store, planner_fn=_partial_evidence_planner,
        stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set()))
    saved = store.get_generation_job(job["id"])
    assert saved["status"] == "completed", saved.get("error")
    if plan_id:
        assert saved["plan_id"] == plan_id
    assert "_sparring_readiness" not in store.get_latest_intake(ATHLETE)["intake"]
