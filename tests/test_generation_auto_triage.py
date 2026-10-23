from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.generation import orchestrator
from fightcamp import main as planner
from fightcamp.injury_triage import InjuryTriageResult
from support import FakeStage2Automator, FakeStore, _build_request, finalized_result, seed_default_profiles


@pytest.mark.parametrize("mode", ["needs_review", "restricted_rehab_only", "medical_hold", "full_plan"])
def test_generation_applies_standing_admin_approval_in_same_job(monkeypatch, mode):
    """Exercise worker -> real planner triage routing -> finalizer -> storage."""
    store = FakeStore()
    seed_default_profiles(store)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=f"auto-triage-{mode}",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    monkeypatch.setattr(
        planner, "triage_injuries",
        lambda _: InjuryTriageResult(mode=mode, should_block_stage2=mode != "full_plan"),
    )
    context_calls = []

    def build_context(**kwargs):
        context_calls.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(planner, "prime_plan_banks", lambda **_: None)
    monkeypatch.setattr(planner, "build_runtime_context", build_context)
    monkeypatch.setattr(planner, "generate_plan_blocks", lambda **_: {})
    monkeypatch.setattr(planner, "render_plan_bundle", lambda **_: SimpleNamespace(
        reason_log={}, coach_notes="stub", fight_plan_text="# Draft",
    ))
    monkeypatch.setattr(planner, "build_stage2_outputs", lambda **_: ({}, {}, "handoff"))

    async def run_inline(planner_fn, payload, *, progress_callback, **kwargs):
        return planner_fn(payload, progress_callback=progress_callback)

    monkeypatch.setattr(orchestrator, "run_stage1_planner", run_inline)
    final = finalized_result()
    final.pop("why_log", None)  # retain the real planner's triage audit
    stage2 = FakeStage2Automator(result=final)
    asyncio.run(orchestrator.run_generation_job(
        job_id=created["id"], store=store, planner_fn=planner.generate_plan_sync,
        stage2=stage2, active_tasks=set(),
    ))
    saved = store.get_generation_job(created["id"])
    codes = [item["code"] for item in saved["progress_milestones"]]
    if mode == "medical_hold":
        assert saved["status"] == "review_required"
        assert saved["final_result"]["injury_triage"]["mode"] == "medical_hold"
        assert not context_calls
        assert not stage2.calls
        assert not store.plans
        assert "triage_auto_approved" not in codes
        return

    assert saved["status"] == "completed", saved.get("error")
    assert len(store.generation_jobs) == 1
    assert len(store.plans) == 1
    assert len(stage2.calls) == 1
    plan = store.get_plan(saved["plan_id"])
    if mode == "full_plan":
        assert context_calls[0]["is_approved_triage_resume"] is False
        assert "triage_auto_approved" not in codes
        assert "injury_triage_resume_override" not in plan["why_log"]
    else:
        assert context_calls[0]["is_approved_triage_resume"] is True
        assert "triage_auto_approved" in codes
        assert plan["why_log"]["injury_triage_original"]["mode"] == mode
        audit = plan["why_log"]["injury_triage_resume_override"]
        assert audit["approval_source"] == "automatic_admin_policy"
        assert audit["bypassed_blocking"] is True
        assert audit["reason"]


def test_generation_preserves_explicit_manual_triage_approval(monkeypatch):
    store = FakeStore()
    seed_default_profiles(store)
    approval = {"approved": True, "allowed_modes": ["needs_review"], "reason": "Reviewed by admin"}
    payload = _build_request().model_dump(mode="json")
    payload["_triage_resume_override"] = approval
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1", client_request_id="manual-triage", source="self_serve",
        request_payload=payload,
    )
    seen = []

    async def run_inline(planner_fn, payload, **kwargs):
        seen.append(payload["_triage_resume_override"])
        return {"status": "ready", "plan_text": "# Draft"}

    monkeypatch.setattr(orchestrator, "run_stage1_planner", run_inline)
    asyncio.run(orchestrator.run_generation_job(
        job_id=job["id"], store=store, planner_fn=lambda _: {},
        stage2=FakeStage2Automator(result=finalized_result()), active_tasks=set(),
    ))
    assert seen == [approval]
    assert store.get_generation_job(job["id"])["status"] == "completed"
