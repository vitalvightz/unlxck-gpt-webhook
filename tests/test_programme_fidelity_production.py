"""Replay the recorded production response; no live model or database writes."""
import asyncio
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from time import perf_counter
from types import SimpleNamespace

import pytest

from api.models import PlanRequest
from api.stage2_automation import OpenAIStage2Automator
from api.generation.persistence import persist_plan_and_finalize
from fightcamp import input_parsing, stage2_planning_brief
from fightcamp.conditioning import _conditioning_structured_profile, get_conditioning_bank
from fightcamp.goal_preservation import collect_goal_evidence
from fightcamp.late_fight_phase_eligibility import _stage1_phase_for_offset
from fightcamp.main import generate_plan_sync
from fightcamp.physical_session_frequency import cadence_windows, dated_appointments, appointment_budget_exceeded
from fightcamp.programme_fidelity import programme_fidelity_findings, reconcile_authoritative_programme
from fightcamp.stage2_validator import _goal_witness_dose_matches
from fightcamp.strength import _classify_prescription_type, _prescription_templates
from fightcamp.working_dose import working_dose
from support import FakeOpenAIClient, FakeStore

FIXTURES = Path(__file__).parent / "fixtures" / "programme_fidelity"


@pytest.fixture(scope="module")
def production_replay():
    intake = json.loads((FIXTURES / "affected_intake.json").read_text(encoding="utf8"))
    # Production did not persist its random seed. Fix it only for the source
    # regeneration; the recorded model response and authority are separate.
    intake["random_seed"] = 1
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(input_parsing, "_utc_now", lambda: datetime(2026, 10, 14, 3, 40))
        patch.setattr(stage2_planning_brief, "_utc_now", lambda: datetime(2026, 10, 14, 3, 40))
        stage1 = generate_plan_sync(PlanRequest(**intake).to_payload())
        patch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0")
        raw = (FIXTURES / "production_render.txt").read_text(encoding="utf8")
        client = FakeOpenAIClient([SimpleNamespace(id="recorded_response", output_text=raw,
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2))])
        final = asyncio.run(OpenAIStage2Automator(client=client, model="recorded").finalize(stage1_result=stage1))
    return intake, stage1, final, client


def test_recorded_authority_proves_missing_sessions_and_wrong_dates():
    brief = json.loads((FIXTURES / "recorded_authority.json").read_text(encoding="utf8"))
    raw = (FIXTURES / "production_render.txt").read_text(encoding="utf8")
    before = programme_fidelity_findings(brief, raw)
    assert any(f.get("scheduled_d_day") == 42 for f in before)
    assert "D-40 (Wednesday)" in raw and "D-26 (Thursday)" in raw
    fixed = reconcile_authoritative_programme(brief, raw)
    assert fixed["findings"] == []
    assert "D-40 (Monday)" in fixed["text"] and "D-26 (Monday)" in fixed["text"]
    for day in (42, 35, 28, 21):
        assert re.search(rf"D-{day} \(Saturday\).*Hard Sparring", fixed["text"], re.I)
    assert "### D-38 (Wednesday)" in fixed["text"]  # Original S&C day retained.


def test_intake_through_finalizer_preserves_real_goals_and_all_appointments(production_replay):
    _, stage1, final, client = production_replay
    brief = stage1["planning_brief"]
    assert len(client.responses.calls) == 1
    assert final["stage2_validator_report"]["errors"] == []
    assert programme_fidelity_findings(brief, final["final_plan_text"]) == []
    assert final["stage2_validator_report"]["programme_reconciliation"]["model_call_used"] is False
    goals = {g["goal"]: g for g in brief["goal_preservation"]}
    assert goals["speed"]["state"] == "build" and goals["speed"]["satisfied"]
    assert goals["power"]["satisfied"] and goals["conditioning"]["satisfied"]
    evidence = collect_goal_evidence(brief)
    bag = next(e for e in evidence if e.get("name") == "Max-Power Bag Burst")
    assert bag["work_sec"] == 5 and bag["rounds"] == 8 and bag["rest_sec"] == 60
    assert {"speed_quality", "ballistic_power"}.issubset(bag["intents"])
    assert any(e.get("name") == "Easy Assault Bike" for e in evidence)
    assert "Depth Drop (No Rebound)" not in final["final_plan_text"]
    assert "Weight information is incomplete" in final["final_plan_text"]
    for day in (42, 35, 28, 21):
        assert re.search(rf"D-{day} \(Saturday\).*Hard Sparring", final["final_plan_text"], re.I)


def test_six_sessions_is_a_total_count_across_progression_boundaries(production_replay):
    _, stage1, _, _ = production_replay
    role_map = stage1["planning_brief"]["weekly_role_map"]
    appointments = dated_appointments(role_map)
    windows = cadence_windows([(d["d_day"], d["weekday"]) for w in role_map["weeks"] for d in w["calendar_days"]])
    counts = [sum(r["countdown_offset"] in {d for d, _ in days} for r in appointments) for days in windows]
    assert max(counts) == 6 and not appointment_budget_exceeded(role_map, 6)
    # A legitimate same-day coach + S&C pair consumes two appointments.
    assert sum(r["countdown_offset"] == 44 for r in appointments) == 2
    extra = deepcopy(role_map)
    first = extra["weeks"][0]
    first["session_roles"].append({"category": "strength", "role_key": "extra_strength", "countdown_offset": 50})
    assert appointment_budget_exceeded(extra, 6)


@pytest.mark.parametrize("mutation", ["weekday", "missing", "exercise", "rest", "phase", "invented", "order"])
def test_post_finalization_drift_is_still_rejected(production_replay, mutation):
    _, stage1, final, _ = production_replay
    text = final["final_plan_text"]
    changes = {
        "weekday": lambda t: t.replace("D-40 (Monday)", "D-40 (Wednesday)"),
        "missing": lambda t: re.sub(r"### D-42 .*?(?=\n### |\n## Week )", "", t, flags=re.S),
        "exercise": lambda t: t.replace("Max-Power Bag Burst", "Assault Bike Sprint"),
        "rest": lambda t: t.replace("5s work, 60s rest x 8 rounds", "5s work, 20s rest x 8 rounds"),
        "phase": lambda t: t.replace("## Week 1 — GPP", "## Week 1 — SPP"),
        "invented": lambda t: t + "\n### D-999 (Monday) — Extra session\n- Squat — 3 x 10\n",
        "order": lambda t: re.sub(r"(### D-51 .*?)(### D-50 .*?)(?=\n### )", r"\2\1", t, count=1, flags=re.S),
    }
    changed = changes[mutation](text)
    assert changed != text
    assert programme_fidelity_findings(stage1["planning_brief"], changed)


def test_persistence_saves_corrected_programme_without_changing_visibility_policy(production_replay):
    intake, stage1, final, _ = production_replay
    request = PlanRequest(**intake)
    store = FakeStore()
    store.profiles["athlete-1"] = {"id": "athlete-1", "full_name": "Programme Fidelity Regression"}
    job = store.create_or_get_generation_job(athlete_id="athlete-1", client_request_id="fidelity-replay",
        source="web_intake", request_payload=request.model_dump(mode="json"))
    job = store.update_generation_job(job["id"], status="running")
    async def direct(fn, *args, **kwargs):
        return fn(*args, **kwargs)
    asyncio.run(persist_plan_and_finalize(job=job, job_id=job["id"], athlete_id="athlete-1",
        plan_id=None, intake_id=None, job_source="web_intake", resume_from_job_only=False,
        admin_resume_plan_row=None, final_result=deepcopy(final), request_body=request, store=store,
        emit_milestone=lambda *_args, **_kwargs: None, to_thread_with_heartbeat=direct, t_start=perf_counter()))
    assert len(store.plans) == 1
    saved = next(iter(store.plans.values()))
    assert saved["plan_text"] == final["final_plan_text"]
    assert programme_fidelity_findings(stage1["planning_brief"], saved["plan_text"]) == []


def test_inclusive_phase_allocation_matches_calendar_length():
    model = {"phase_weeks": {"days": {"GPP": 15, "SPP": 22, "TAPER": 15}}}
    phases = [_stage1_phase_for_offset(model, d) for d in range(52)]
    assert {phase: phases.count(phase) for phase in ("GPP", "SPP", "TAPER")} == model["phase_weeks"]["days"]
    assert phases[14] == "TAPER" and phases[15] == "SPP"
    assert phases[36] == "SPP" and phases[37] == "GPP"


def test_unpriced_closed_session_is_a_fidelity_failure(production_replay):
    _, stage1, final, _ = production_replay
    brief = deepcopy(stage1["planning_brief"])
    role = next(r for w in brief["weekly_role_map"]["weeks"] for r in w["session_roles"]
                if r.get("category") == "strength" and r.get("selected_exercise_assignments"))
    role["effective_strength_prescriptions"] = []
    findings = programme_fidelity_findings(brief, final["final_plan_text"])
    assert any(f["code"] == "authoritative_programme_unpriced_session" for f in findings)


def test_late_goal_repair_retains_earlier_speed_appointments(monkeypatch):
    from test_combat_training_allocation import run_lead
    _, brief = run_lead(monkeypatch, status="professional", training_frequency=9, fatigue="low",
                        hard_sparring_days=[], support_work_days=["Tuesday", "Thursday", "Friday"])
    assert all(g["satisfied"] for g in brief["goal_preservation"])
    evidence = collect_goal_evidence(brief)
    assert any(e["d_day"] == 36 and e["name"] == "Sled Push (Speed)"
               and e["development_quality"] for e in evidence)
    assert any(2 <= e["d_day"] <= 15 and "ballistic_power" in e["intents"] for e in evidence)


def test_exercise_method_controls_dose_and_braking_does_not_develop_speed():
    assert _classify_prescription_type({"name": "Landmine Push Press", "equipment": ["landmine"], "tags": ["core"]}) == "ballistic"
    hold_type = _classify_prescription_type({"name": "Staggered Stance Hold", "tags": ["core"]})
    hold = _prescription_templates("SPP")[hold_type]
    assert "hold" in hold and "tempo" not in hold and "reps" not in hold
    sled = _prescription_templates("SPP")[_classify_prescription_type({"name": "Sled Push (Speed)"})]
    assert "light sled" in sled and "5s" in sled and "rest 90s" in sled
    drop = next(d for d in get_conditioning_bank() if d["name"] == "Depth Drop (No Rebound)")
    assert _conditioning_structured_profile(drop)["alactic_structure"]
    assert not _conditioning_structured_profile(drop)["speed_development"]


def test_working_dose_does_not_inflate_authorised_volume_or_corrupt_tempo():
    assert working_dose("3–5x4–6 reps; rest 60–90s; RPE 6–8") == "3x4 reps; rest 90s; RPE 6"
    assert working_dose("2-4 sets x 6-10 reps, tempo 3-1-3") == "2 sets x 6 reps, tempo 3-1-3"
    assert working_dose("tempo 3–1–3") == "tempo 3–1–3"
    witness = {"work_sec": 5, "rest_sec": 60, "rounds": 8}
    assert _goal_witness_dose_matches(witness, "5s work, 60s rest x 8 rounds; RPE 8")
    assert not _goal_witness_dose_matches(witness, "5s work, 20s rest x 8 rounds; RPE 8")
    assert not _goal_witness_dose_matches(witness, "3s work, 60s rest x 8 rounds; RPE 8")


def test_a_label_or_low_effort_bag_touch_cannot_clear_power(production_replay):
    _, stage1, _, _ = production_replay
    brief = deepcopy(stage1["planning_brief"])
    for week in brief["weekly_role_map"]["weeks"]:
        for role in week["session_roles"]:
            for member in role.get("selected_exercise_assignments", []):
                if member["name"] == "Max-Power Bag Burst":
                    member["rpe"] = 3
    bag = next(e for e in collect_goal_evidence(brief) if e.get("name") == "Max-Power Bag Burst")
    assert "ballistic_power" not in bag["intents"]
    assert not bag["development_capable"]


@pytest.mark.parametrize("name,created_at", [
    ("earlier_before_notes", datetime(2026, 10, 13, 19, 26)),
    ("earlier_with_notes", datetime(2026, 10, 13, 19, 49)),
])
def test_earlier_saved_intakes_and_recorded_responses_have_the_same_fidelity_contract(name, created_at):
    intake = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf8"))
    intake["random_seed"] = 1
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(input_parsing, "_utc_now", lambda: created_at)
        patch.setattr(stage2_planning_brief, "_utc_now", lambda: created_at)
        patch.setenv("UNLXCK_STAGE2_STRUCTURED_PLAN", "0")
        stage1 = generate_plan_sync(PlanRequest(**intake).to_payload())
        raw = (FIXTURES / f"{name}_render.txt").read_text(encoding="utf8")
        client = FakeOpenAIClient([SimpleNamespace(id="recorded_response", output_text=raw,
            usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2))])
        final = asyncio.run(OpenAIStage2Automator(client=client, model="recorded").finalize(stage1_result=stage1))
    brief = stage1["planning_brief"]
    assert brief["athlete_snapshot"]["training_frequency"] == 6
    assert not appointment_budget_exceeded(brief["weekly_role_map"], 6)
    assert programme_fidelity_findings(brief, final["final_plan_text"]) == []
    assert final["stage2_validator_report"]["errors"] == []
    assert all(g["satisfied"] for g in brief["goal_preservation"])
    assert "Max-Power Bag Burst" in final["final_plan_text"]
