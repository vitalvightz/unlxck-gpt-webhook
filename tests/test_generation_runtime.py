from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import BackgroundTasks, HTTPException

import api.app as app_module
from api import generation_runtime
from api import worker as worker_module
from api.generation import persistence, stage1_runner
from api.generation_runtime import (
    _invoke_planner,
    _stage1_mp_start_method,
    _stage1_planner_timeout_seconds,
    _stage2_finalize_timeout_seconds,
    default_planner,
    generation_status_from_plan_status,
    is_in_process_generation_enabled,
    run_stage1_planner,
)
from api.stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError
from support import FakeStage2Automator, FakeStore, _build_request, finalized_result, seed_default_profiles


_ENVIRONMENT_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")

# With the "spawn" start method the planner child cold-imports this test module
# (and its api.app import chain), which can take a couple of seconds in a slow
# CI sandbox. These tests exercise result/error delivery, not startup latency,
# so they need a timeout that comfortably clears spawn import cost. Production
# uses a 600s Stage 1 timeout, so import overhead is irrelevant there.
_SPAWN_TEST_TIMEOUT_SECONDS = 30.0


def _spawn_planner_returns(payload):
    return {"ok": payload["value"]}


def _spawn_planner_with_progress(payload, *, progress_callback=None):
    assert progress_callback is not None
    progress_callback("planner_started", "Planner started", "", {})
    return {"ok": True}


def _spawn_planner_raises(payload):
    raise RuntimeError("boom")


def _spawn_planner_hangs(payload):
    import time
    time.sleep(2)
    return {"ok": True}


def _spawn_planner_exits(payload):
    import os
    os._exit(0)


def _spawn_planner_returns_then_sleeps(payload):
    import time

    if payload.get("progress_callback"):
        payload["progress_callback"]("handoff_ready", "handoff ready", "", {})
    result = {"status": "ok", "value": payload["value"]}
    time.sleep(0.3)
    return result


def _spawn_planner_returns_large_result(payload):
    blob = "x" * 2_000_000
    return {"status": "ok", "blob": blob, "value": payload["value"]}


def _spawn_planner_returns_ready_plan(payload):
    return {"status": "ready", "plan_text": "draft"}


def _spawn_planner_returns_empty_plan(payload):
    return {"status": "ready", "plan_text": ""}


def _clear_environment_markers(monkeypatch):
    for var in _ENVIRONMENT_VARS:
        monkeypatch.delenv(var, raising=False)


def test_stage1_planner_timeout_default_is_600(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.delenv("STAGE1_PLANNER_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", raising=False)
    assert _stage1_planner_timeout_seconds() == 600.0


@pytest.mark.parametrize("sentinel", ["", "0", "none", "None", "NONE"])
def test_stage1_planner_timeout_sentinels_disable_timeout_outside_production(monkeypatch, sentinel):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", sentinel)
    assert _stage1_planner_timeout_seconds() is None


def test_stage1_planner_timeout_sentinel_does_not_disable_in_production(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "0")
    assert _stage1_planner_timeout_seconds() == 600.0


def test_stage1_planner_timeout_invalid_falls_back_to_600(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "not-a-number")
    assert _stage1_planner_timeout_seconds() == 600.0


def test_stage1_planner_timeout_respects_valid_override(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "60")
    assert _stage1_planner_timeout_seconds() == 60.0


def test_stage1_planner_timeout_respects_fractional_positive_override(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "0.5")
    assert _stage1_planner_timeout_seconds() == 0.5


def test_stage1_planner_timeout_prefers_new_env_over_legacy(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "60")
    assert _stage1_planner_timeout_seconds() == 600.0


def test_stage1_mp_start_method_defaults_to_spawn(monkeypatch):
    monkeypatch.delenv("UNLXCK_STAGE1_MP_START_METHOD", raising=False)
    assert _stage1_mp_start_method() == "spawn"


def test_stage1_mp_start_method_invalid_falls_back_to_spawn(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "invalid")
    assert _stage1_mp_start_method() == "spawn"


def test_stage1_run_planner_returns_result(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")
    result = asyncio.run(
        run_stage1_planner(_spawn_planner_returns, {"value": 3}, timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS)
    )
    assert result == {"ok": 3}


def test_stage1_run_planner_relays_progress(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")
    codes: list[str] = []

    def callback(code, label, detail, meta):
        codes.append(code)

    result = asyncio.run(
        run_stage1_planner(
            _spawn_planner_with_progress,
            {"value": 1},
            progress_callback=callback,
            timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS,
        )
    )
    assert result == {"ok": True}
    assert "planner_started" in codes


def test_stage1_run_planner_raises_controlled_runtime_error(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run_stage1_planner(_spawn_planner_raises, {}, timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS))


def test_stage1_run_planner_preserves_child_traceback(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(stage1_runner.Stage1PlannerError) as exc_info:
        asyncio.run(run_stage1_planner(_spawn_planner_raises, {}, timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS))

    # The child-process stack trace must survive the parent re-raise so it can
    # be surfaced in structured logs for admin diagnostics.
    child_traceback = exc_info.value.child_traceback
    assert child_traceback is not None
    assert "Traceback" in child_traceback
    assert "boom" in child_traceback


def test_stage1_run_planner_timeout(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_stage1_planner(_spawn_planner_hangs, {}, timeout_seconds=0.1))


def test_stage1_run_planner_child_exit_without_result_raises_controlled_error(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(RuntimeError, match="Stage 1 planner process exited without result"):
        asyncio.run(run_stage1_planner(_spawn_planner_exits, {}, timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS))


def test_stage1_run_planner_returns_after_planner_returns(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")
    result = asyncio.run(
        run_stage1_planner(
            _spawn_planner_returns_then_sleeps, {"value": 7}, timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS
        )
    )
    assert result == {"status": "ok", "value": 7}


def test_stage1_run_planner_reads_large_result_from_queue(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")
    codes: list[str] = []

    def callback(code, label, detail, meta):
        codes.append(code)

    result = asyncio.run(
        run_stage1_planner(
            _spawn_planner_returns_large_result,
            {"value": 9},
            progress_callback=callback,
            timeout_seconds=_SPAWN_TEST_TIMEOUT_SECONDS,
        )
    )
    assert result["status"] == "ok"
    assert result["value"] == 9
    assert len(result["blob"]) == 2_000_000
    assert "stage1_result_queue_received" in codes


def test_in_process_generation_default_is_worker_only(monkeypatch):
    monkeypatch.delenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", raising=False)
    assert is_in_process_generation_enabled() is False


def test_in_process_generation_env_override_enabled(monkeypatch):
    monkeypatch.setenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", "1")
    assert is_in_process_generation_enabled() is True


def test_worker_stale_timeout_default_is_300_when_env_unset(monkeypatch):
    monkeypatch.delenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", raising=False)
    assert worker_module._worker_stale_after_seconds() == 300


def test_worker_stale_timeout_default_ignores_stage1_timeout(monkeypatch):
    monkeypatch.delenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", raising=False)
    monkeypatch.setenv("STAGE1_PLANNER_TIMEOUT_SECONDS", "720")
    assert worker_module._worker_stale_after_seconds() == 300


def test_worker_stale_timeout_invalid_falls_back_to_300(monkeypatch):
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_STALE_AFTER_SECONDS", "not-a-number")
    assert worker_module._worker_stale_after_seconds() == 300


def test_worker_max_concurrency_default_is_1(monkeypatch):
    monkeypatch.delenv("UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS", raising=False)
    assert worker_module._worker_max_concurrent_jobs() == 1


def test_worker_max_concurrency_invalid_falls_back_to_1(monkeypatch):
    monkeypatch.setenv("UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS", "not-a-number")
    assert worker_module._worker_max_concurrent_jobs() == 1


def test_worker_tick_processes_queued_job_to_terminal_status():
    store = FakeStore()
    seed_default_profiles(store)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-processes-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    active_tasks: set[str] = set()
    detached_tasks: set[asyncio.Task[None]] = set()

    # Drive the tick and drain the detached job task inside a single event loop.
    # _tick() schedules the job as a detached task and returns without awaiting
    # it; if each step ran in its own asyncio.run(), that call's shutdown would
    # cancel the still-pending task before it could claim and process the job.
    # Production keeps one long-lived loop across ticks, so this mirrors it.
    async def _drive_until_drained() -> None:
        await worker_module._tick(
            store=store,
            active_tasks=active_tasks,
            detached_tasks=detached_tasks,
            stale_after_seconds=660,
            max_concurrent_jobs=1,
        )
        while detached_tasks:
            await asyncio.gather(*list(detached_tasks))
            await asyncio.sleep(0)

    original_builder = worker_module.build_default_stage2_automator
    worker_module.build_default_stage2_automator = lambda: FakeStage2Automator(result=finalized_result())
    try:
        asyncio.run(_drive_until_drained())
    finally:
        worker_module.build_default_stage2_automator = original_builder

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] in {"completed", "review_required"}
    assert job["completed_at"] is not None


def test_generation_job_request_parse_failure_is_diagnostic(caplog):
    store = FakeStore()
    seed_default_profiles(store)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-parse-failure",
        source="self_serve",
        request_payload={"_triage_resume_override": {"approved": True}},
    )
    planner_called = False

    def planner(payload: dict) -> dict:
        nonlocal planner_called
        planner_called = True
        return {"status": "ready"}

    with caplog.at_level("INFO"):
        asyncio.run(
            generation_runtime.run_generation_job(
                job_id=created["id"],
                store=store,
                planner_fn=planner,
                stage2=FakeStage2Automator(result_factory=finalized_result),
                active_tasks=set(),
            )
        )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "failed"
    assert str(job["error"]).startswith("request_parse_failed:")
    assert planner_called is False
    milestone_codes = [milestone["code"] for milestone in job["progress_milestones"]]
    assert milestone_codes == [
        "job_loaded",
        "request_payload_parse_started",
        "request_payload_parse_failed",
    ]
    assert "worker:job_loaded" in caplog.text
    assert "worker:payload_raw" in caplog.text
    assert "worker:before_request_parse" in caplog.text
    assert "worker:request_parse_failed" in caplog.text
    assert "worker:after_request_parse" not in caplog.text


def test_stage2_finalize_timeout_default_is_1500(monkeypatch):
    # Must cover the worst-case sum of the per-request Stage 2 timeouts:
    # plan-text pass (210s) + structured first + repair (600s each).
    monkeypatch.delenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", raising=False)
    assert _stage2_finalize_timeout_seconds() == 1500.0


@pytest.mark.parametrize("sentinel", ["", "0", "none", "None", "NONE"])
def test_stage2_finalize_timeout_sentinels_disable_timeout(monkeypatch, sentinel):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", sentinel)
    assert _stage2_finalize_timeout_seconds() is None


def test_stage2_finalize_timeout_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "not-a-number")
    assert _stage2_finalize_timeout_seconds() == 1500.0


def test_stage2_finalize_timeout_respects_valid_override(monkeypatch):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "60")
    assert _stage2_finalize_timeout_seconds() == 60.0


def test_stage2_finalize_timeout_enforces_minimum_of_1(monkeypatch):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "0.5")
    assert _stage2_finalize_timeout_seconds() == 1.0


# ---------------------------------------------------------------------------
# Technical Stage 2 failures complete the job on the Stage 1 plan.
#
# These cover the four ways Stage 2 can fail to produce a usable plan. In every
# case Stage 1 has already built a complete deterministic plan, so the job
# completes on that rather than failing generation. This is distinct from the
# validator path (a Stage 2 plan that EXISTS but is flagged), which publishes
# the Stage 2 plan as publishable_with_flags.
# ---------------------------------------------------------------------------


def _run_stage2_failure_job(store, stage2, *, client_request_id, planner_fn=None):
    job = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id=client_request_id,
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=job["id"],
            store=store,
            planner_fn=planner_fn or _spawn_planner_returns_ready_plan,
            stage2=stage2,
            active_tasks=set(),
        )
    )
    return store.get_generation_job(job["id"])


# Milestones that assert Stage 2 actually returned something. None of them can
# be true when the finalizer never produced a plan, so the fallback path must
# not emit any of them.
_STAGE2_RESPONSE_MILESTONES = (
    "stage2_model_response_received",
    "stage2_response_parse_started",
    "stage2_response_parsed",
    "stage2_result_ready",
    "stage2_validated",
    "stage2_flagged",
    "stage2_review_required",
)


def _assert_completed_on_stage1_plan(store, saved, *, reason):
    assert saved["status"] == "completed"
    assert not saved["error"]
    plan = next(iter(store.plans.values()))
    assert plan["status"] == "ready"
    assert plan["plan_text"] == "draft"
    assert plan["stage2_status"] == "stage2_failed_stage1_fallback"
    assert plan["stage2_validator_report"]["stage2_fallback"]["reason"] == reason
    codes = [milestone["code"] for milestone in saved["progress_milestones"]]
    assert "stage2_stage1_fallback" in codes
    # The run must not claim a response it never got.
    assert [code for code in _STAGE2_RESPONSE_MILESTONES if code in codes] == []
    return plan


def test_stage2_timeout_completes_job_on_stage1_plan(monkeypatch):
    class HangingStage2:
        async def finalize(self, *, stage1_result: dict, log_context: dict | None = None) -> dict:
            await asyncio.sleep(1)
            return finalized_result()

    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "0.01")
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store, HangingStage2(), client_request_id="stage2-timeout"
    )

    _assert_completed_on_stage1_plan(store, saved, reason="stage2_timeout")
    codes = [milestone["code"] for milestone in saved["progress_milestones"]]
    assert "stage2_drafting" in codes
    assert "stage2_model_call_started" in codes
    # The job is no longer failed, so the timeout-failure milestone must not fire.
    assert "stage2_finalizer_timeout" not in codes


def test_stage2_provider_error_completes_job_on_stage1_plan():
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(
            error=Stage2AutomationError("Stage 2 model request failed. Check server logs.")
        ),
        client_request_id="stage2-provider-error",
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_model_error")
    assert "Stage 2 model request failed" in (
        plan["stage2_validator_report"]["stage2_fallback"]["detail"]
    )


def test_stage2_unavailable_completes_job_on_stage1_plan():
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(
            error=Stage2AutomationUnavailableError(
                "OPENAI_API_KEY is required for automated Stage 2 finalization."
            )
        ),
        client_request_id="stage2-unavailable",
    )

    _assert_completed_on_stage1_plan(store, saved, reason="stage2_unavailable")


def test_stage2_incomplete_output_completes_job_on_stage1_plan():
    # A response truncated before a full plan raises Stage2AutomationError from
    # _generate_text — there is no usable Stage 2 plan, so Stage 1's completes.
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(
            error=Stage2AutomationError(
                "Stage 2 model response was incomplete before producing a full plan."
            )
        ),
        client_request_id="stage2-incomplete",
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_model_error")
    assert "incomplete" in plan["stage2_validator_report"]["stage2_fallback"]["detail"]


def test_unexpected_stage2_exception_completes_job_on_stage1_plan():
    # A TypeError, validator crash, or any other unanticipated exception inside
    # Stage 2 must degrade the same way a known failure does. Stage 2 is only
    # genuinely non-blocking if the unexpected case is covered too.
    class ExplodingStage2:
        async def finalize(self, *, stage1_result: dict, log_context: dict | None = None) -> dict:
            raise TypeError("unexpected crash inside the finalizer")

    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store, ExplodingStage2(), client_request_id="stage2-unexpected"
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_unexpected_error")
    assert "unexpected crash" in plan["stage2_validator_report"]["stage2_fallback"]["detail"]
    # An arbitrary exception carries no evidence that a request reached the
    # provider, so no attempt is claimed. Only attempts we can evidence count.
    assert plan["stage2_attempt_count"] == 0


def test_unavailable_stage2_records_zero_attempts():
    # Unavailable means no provider request was ever made, so nothing was
    # attempted. Every other failure got at least as far as starting one.
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(
            error=Stage2AutomationUnavailableError("OPENAI_API_KEY is required.")
        ),
        client_request_id="stage2-unavailable-attempts",
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_unavailable")
    assert plan["stage2_attempt_count"] == 0


def test_prompt_budget_failure_records_zero_provider_attempts():
    # The prompt-budget check raises before any request reaches the provider, so
    # no tokens were burned. Counting it as an attempt corrupts cost telemetry.
    store = FakeStore()
    seed_default_profiles(store)

    error = Stage2AutomationError("Stage 2 first_pass prompt too large: 214880 chars > 180000")
    assert error.provider_request_started is False

    saved = _run_stage2_failure_job(
        store, FakeStage2Automator(error=error), client_request_id="stage2-prompt-budget"
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_model_error")
    assert plan["stage2_attempt_count"] == 0


def test_provider_error_after_request_records_one_attempt():
    # The mirror case: a failure raised once the request was in flight did burn
    # tokens, so it counts.
    store = FakeStore()
    seed_default_profiles(store)

    error = Stage2AutomationError("Stage 2 model request failed. Check server logs.")
    error.provider_request_started = True

    saved = _run_stage2_failure_job(
        store, FakeStage2Automator(error=error), client_request_id="stage2-after-request"
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_model_error")
    assert plan["stage2_attempt_count"] == 1


def test_stage1_fallback_records_a_terminal_structured_card_outcome():
    # Without a terminal marker the card state derives as "none", which reads as
    # "might still be building" and leaves the client polling for a conversion
    # that is never going to run.
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(error=Stage2AutomationError("Stage 2 model request failed")),
        client_request_id="stage2-card-state",
    )

    plan = _assert_completed_on_stage1_plan(store, saved, reason="stage2_model_error")
    assert plan["structured_plan"] is None
    assert plan["stage2_validator_report"]["structured_plan"]["status"] == "not_attempted"


def test_stage1_fallback_milestone_copy_stays_neutral_for_the_athlete():
    # Milestones render on the athlete's generation screen. The technical reason
    # belongs in the log and the admin-only validator report, not here.
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(error=Stage2AutomationError("Stage 2 model request failed")),
        client_request_id="stage2-neutral-copy",
    )

    fallback = next(
        m for m in saved["progress_milestones"] if m["code"] == "stage2_stage1_fallback"
    )
    blurb = f"{fallback['label']} {fallback['detail']}".lower()
    for leak in ("finaliz", "stage 1", "stage 2", "fail", "ai ", "unusable", "fallback"):
        assert leak not in blurb, f"athlete-visible milestone leaks {leak!r}: {blurb}"


def test_flagged_release_does_not_claim_a_review_is_required():
    # publishable_with_flags releases to the athlete; the flags are for
    # asynchronous admin audit. Nothing is waiting on a review, so the run must
    # not emit a milestone saying one is needed.
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(
            result=finalized_result(
                status="publishable_with_flags",
                stage2_status="stage2_failed",
            )
        ),
        client_request_id="stage2-flagged",
    )

    assert saved["status"] == "completed"
    plan = next(iter(store.plans.values()))
    assert plan["status"] == "publishable_with_flags"
    codes = [milestone["code"] for milestone in saved["progress_milestones"]]
    assert "stage2_flagged" in codes
    assert "stage2_review_required" not in codes
    # The response/parse milestones are true here — Stage 2 did return a plan.
    assert "stage2_model_response_received" in codes
    assert "stage2_response_parsed" in codes


def test_stage2_failure_still_fails_job_when_stage1_has_no_plan_text():
    # The boundary: no Stage 1 plan means nothing to fall back to, so the job
    # fails exactly as it did before rather than publishing an empty plan.
    store = FakeStore()
    seed_default_profiles(store)

    saved = _run_stage2_failure_job(
        store,
        FakeStage2Automator(error=Stage2AutomationError("Stage 2 model request failed")),
        client_request_id="stage2-no-stage1-plan",
        planner_fn=_spawn_planner_returns_empty_plan,
    )

    assert saved["status"] == "failed"
    assert "Stage 2 model request failed" in saved["error"]
    assert not store.plans


def test_invoke_planner_passes_progress_callback_when_supported():
    received: list[object] = []

    def planner(payload, *, progress_callback=None):
        received.append(progress_callback)
        return payload

    def callback(code, label, detail, meta):
        return None

    result = _invoke_planner(planner, {"ok": True}, callback)
    assert result == {"ok": True}
    assert received == [callback]


def test_invoke_planner_skips_progress_callback_for_legacy_planner():
    received: list[dict[str, bool]] = []

    def planner(payload):
        received.append(payload)
        return payload

    def callback(code, label, detail, meta):
        return None

    result = _invoke_planner(planner, {"ok": True}, callback)
    assert result == {"ok": True}
    assert received == [{"ok": True}]


def test_invoke_planner_does_not_swallow_internal_type_error():
    def planner(payload, *, progress_callback=None):
        raise TypeError("internal bug")

    with pytest.raises(TypeError, match="internal bug"):
        _invoke_planner(planner, {"ok": True}, lambda *args: None)


def test_default_planner_emits_diagnostic_milestones_before_generate_plan_sync(monkeypatch):
    emitted_codes: list[str] = []
    generate_plan_called = {"value": False}

    def fake_generate_plan_sync(payload, *, progress_callback=None):
        generate_plan_called["value"] = True
        return {"plan": "ok"}

    monkeypatch.setattr(stage1_runner, "generate_plan_sync", fake_generate_plan_sync)

    def callback(code, label, detail, meta):
        assert generate_plan_called["value"] is False
        emitted_codes.append(code)

    result = default_planner({"athlete": "x"}, progress_callback=callback)

    assert result == {"plan": "ok"}
    assert emitted_codes[:2] == [
        "stage1_default_planner_entered",
        "stage1_generate_plan_sync_entering",
    ]


def test_invoke_planner_with_app_default_planner_emits_full_stage1_diagnostics(monkeypatch):
    emitted_codes: list[str] = []

    def fake_generate_plan_sync(payload, *, progress_callback=None):
        return {"plan": "ok"}

    monkeypatch.setattr(stage1_runner, "generate_plan_sync", fake_generate_plan_sync)

    def callback(code, label, detail, meta):
        emitted_codes.append(code)

    result = _invoke_planner(app_module._default_planner, {"athlete": "x"}, callback)

    assert result == {"plan": "ok"}
    assert emitted_codes[:4] == [
        "stage1_planner_callable_entering",
        "stage1_planner_callable_supports_progress_callback",
        "stage1_default_planner_entered",
        "stage1_generate_plan_sync_entering",
    ]


def test_admin_latest_intake_job_fails_when_intake_id_is_missing():
    store = FakeStore()
    seed_default_profiles(store)
    request = _build_request().model_dump(mode="json")
    store.generation_jobs["job-1"] = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "status": "queued",
        "source": "admin_latest_intake",
        "request_payload": request,
        "intake_id": None,
    }
    asyncio.run(
        generation_runtime.run_generation_job(
            job_id="job-1",
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )
    assert store.generation_jobs["job-1"]["status"] == "failed"
    assert store.generation_jobs["job-1"]["error"] == "admin latest intake job is missing intake_id"


def test_admin_latest_intake_job_fails_when_linked_intake_is_for_different_athlete():
    store = FakeStore()
    seed_default_profiles(store)
    request = _build_request().model_dump(mode="json")
    intake = store.create_intake("athlete-2", _build_request())
    store.generation_jobs["job-1"] = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "status": "queued",
        "source": "admin_latest_intake",
        "request_payload": request,
        "intake_id": intake["id"],
    }
    asyncio.run(
        generation_runtime.run_generation_job(
            job_id="job-1",
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )
    assert store.generation_jobs["job-1"]["status"] == "failed"
    assert store.generation_jobs["job-1"]["error"] == "admin latest intake job intake belongs to a different athlete"


def test_admin_latest_intake_job_accepts_semantically_equivalent_linked_payload():
    store = FakeStore()
    seed_default_profiles(store)
    request = _build_request().model_dump(mode="json")
    intake = store.create_intake("athlete-1", _build_request())
    linked_payload = dict(intake["intake"])
    linked_payload.pop("no_scheduled_fight", None)
    linked_payload.pop("open_camp_weeks", None)
    store.update_intake(
        intake["id"],
        intake=linked_payload,
        fight_date=intake["fight_date"],
        technical_style=intake["technical_style"],
    )
    store.generation_jobs["job-1"] = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "status": "queued",
        "source": "admin_latest_intake",
        "request_payload": request,
        "intake_id": intake["id"],
    }
    asyncio.run(
        generation_runtime.run_generation_job(
            job_id="job-1",
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )
    assert store.generation_jobs["job-1"]["status"] == "completed"


def test_admin_latest_intake_job_fails_when_linked_payload_differs_from_request_payload():
    store = FakeStore()
    seed_default_profiles(store)
    request = _build_request().model_dump(mode="json")
    linked_request = _build_request({"fatigue_level": "high"})
    intake = store.create_intake("athlete-1", linked_request)
    store.generation_jobs["job-1"] = {
        "id": "job-1",
        "athlete_id": "athlete-1",
        "status": "queued",
        "source": "admin_latest_intake",
        "request_payload": request,
        "intake_id": intake["id"],
    }
    asyncio.run(
        generation_runtime.run_generation_job(
            job_id="job-1",
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )
    assert store.generation_jobs["job-1"]["status"] == "failed"
    assert store.generation_jobs["job-1"]["error"] == "admin latest intake job request_payload does not match linked intake payload"


def test_terminal_success_without_plan_id_is_downgraded_to_failed_with_error_message():
    store = FakeStore()
    seed_default_profiles(store)
    request_payload = _build_request().model_dump(mode="json")
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="terminal-missing-plan-id",
        source="self_serve",
        request_payload=request_payload,
    )

    original_update_generation_job = store.update_generation_job

    def flaky_update_generation_job(job_id: str, **changes: dict) -> dict:
        updated = original_update_generation_job(job_id, **changes)
        if "final_result" in changes:
            updated = original_update_generation_job(job_id, plan_id=None)
        return updated

    store.update_generation_job = flaky_update_generation_job  # type: ignore[assignment]

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "failed"
    assert isinstance(job.get("error"), str)
    assert job["error"].strip() == "Plan was saved but the generation job lost its plan_id. Open plan history or contact support."


def test_terminal_success_with_deleted_plan_row_is_downgraded_to_failed():
    store = FakeStore()
    seed_default_profiles(store)
    request_payload = _build_request().model_dump(mode="json")
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="terminal-deleted-plan-row",
        source="self_serve",
        request_payload=request_payload,
    )

    original_get_plan = store.get_plan

    def flaky_get_plan(plan_id: str):  # type: ignore[no-untyped-def]
        row = original_get_plan(plan_id)
        if row is not None:
            # Simulate the plan row being deleted right after it was persisted.
            return None
        return row

    store.get_plan = flaky_get_plan  # type: ignore[assignment]

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "failed"


@pytest.mark.parametrize(
    ("plan_status", "expected_generation_status"),
    [
        ("generated", "completed"),
        ("ready", "completed"),
        ("publishable_with_flags", "completed"),
        ("triage_blocked", "review_required"),
        ("archived", "completed"),
        ("held_for_review", "review_required"),
        ("review_required", "review_required"),
        ("medical_hold", "review_required"),
        ("restricted_rehab_only", "review_required"),
        ("needs_review", "review_required"),
    ],
)
def test_generation_status_from_plan_status_mapper(plan_status: str, expected_generation_status: str):
    assert generation_status_from_plan_status(plan_status) == expected_generation_status


def test_generation_job_status_never_uses_legacy_plan_status_values():
    for legacy_status in ("publishable_with_flags", "held_for_review"):
        mapped = generation_status_from_plan_status(legacy_status)
        assert mapped != legacy_status


def test_generation_status_from_unknown_plan_status_requires_review():
    assert generation_status_from_plan_status("new_clinical_hold") == "review_required"


# ---------------------------------------------------------------------------
# Direct seam coverage added ahead of the generation_runtime split refactor.
# These pin behaviour that was previously only exercised indirectly, so later
# code-movement PRs have a tight regression net. No production code changes.
# ---------------------------------------------------------------------------


class _RecordingStore:
    """Minimal store stub that records update_generation_job calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def update_generation_job(self, job_id: str, **changes: object) -> dict:
        self.calls.append((job_id, dict(changes)))
        return {"id": job_id, **changes}


class _FailingUpdateStore:
    """Store stub whose update_generation_job always raises."""

    def update_generation_job(self, job_id: str, **changes: object) -> dict:
        raise RuntimeError("db down")


class _CapacityStore:
    """Store stub controlling count_active_generation_jobs for scheduler tests."""

    def __init__(self, *, count_result: int = 0, count_exc: Exception | None = None) -> None:
        self._count_result = count_result
        self._count_exc = count_exc

    def count_active_generation_jobs(self, *, stale_after_seconds: int) -> int:
        if self._count_exc is not None:
            raise self._count_exc
        return self._count_result


# --- should_skip_stage2 (triage skip decision) -----------------------------


def test_should_skip_stage2_blocks_triage_blocked_status():
    assert generation_runtime.should_skip_stage2({"status": "triage_blocked"}) is True


def test_should_skip_stage2_triage_blocked_status_allows_with_override():
    assert (
        generation_runtime.should_skip_stage2(
            {"status": "triage_blocked"}, allow_triage_resume_override=True
        )
        is False
    )


def test_should_skip_stage2_blocks_when_injury_triage_should_block():
    stage1 = {"status": "ready", "injury_triage": {"should_block_stage2": True}}
    assert generation_runtime.should_skip_stage2(stage1) is True
    assert generation_runtime.should_skip_stage2(stage1, allow_triage_resume_override=True) is False


@pytest.mark.parametrize("mode", ["medical_hold", "restricted_rehab_only", "needs_review"])
def test_should_skip_stage2_blocks_on_injury_triage_mode(mode: str):
    stage1 = {"status": "ready", "injury_triage": {"mode": mode}}
    assert generation_runtime.should_skip_stage2(stage1) is True
    assert generation_runtime.should_skip_stage2(stage1, allow_triage_resume_override=True) is False


def test_should_skip_stage2_blocks_on_why_log_injury_triage():
    stage1 = {"why_log": {"injury_triage": {"should_block_stage2": True}}}
    assert generation_runtime.should_skip_stage2(stage1) is True


def test_should_skip_stage2_allows_clean_ready_result():
    assert generation_runtime.should_skip_stage2({"status": "ready"}) is False


# --- is_openai_quota_error (admin-safe error mapping) ----------------------


@pytest.mark.parametrize(
    "message",
    [
        "insufficient_quota",
        "You exceeded your current quota, please check your plan",
        "OpenAI quota/rate limit reached",
        "Error 429: quota exceeded for this org",
    ],
)
def test_is_openai_quota_error_detects_quota_messages(message: str):
    assert generation_runtime.is_openai_quota_error(Exception(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "connection reset by peer",
        "429 Too Many Requests",  # rate limit without quota wording
        "validation failed",
    ],
)
def test_is_openai_quota_error_ignores_non_quota_messages(message: str):
    assert generation_runtime.is_openai_quota_error(Exception(message)) is False


# --- _compact_generation_job_final_result (final_result shaping) -----------


def test_compact_final_result_drops_non_essential_keys_for_real_plan():
    final_result = {
        "status": "ready",
        "stage2_status": "stage2_pass",
        "plan_text": "# big plan text",
        "why_log": {"x": 1},
        "full_name": "Jordan",
    }
    compact = generation_runtime._compact_generation_job_final_result(final_result)
    assert compact == {"status": "ready", "stage2_status": "stage2_pass"}


def test_compact_final_result_preserves_triage_context_for_held_outcome():
    final_result = {
        "status": "medical_hold",
        "stage2_status": "skipped",
        "plan_text": "# should be dropped",
        "why_log": {"injury_triage": {"mode": "medical_hold"}},
        "injury_triage": {"mode": "medical_hold"},
        "full_name": "Jordan",
    }
    compact = generation_runtime._compact_generation_job_final_result(final_result)
    assert compact == {
        "status": "medical_hold",
        "stage2_status": "skipped",
        "why_log": {"injury_triage": {"mode": "medical_hold"}},
        "injury_triage": {"mode": "medical_hold"},
        "full_name": "Jordan",
    }


# --- build_progress_recorder (milestone persistence) -----------------------


def test_build_progress_recorder_persists_milestone_and_heartbeat():
    store = _RecordingStore()
    milestones, callback = generation_runtime.build_progress_recorder(job_id="job-x", store=store)
    callback("stage1_planner_invoked", "Stage 1 planner invoked", "detail", {"k": "v"})

    assert len(store.calls) == 1
    job_id, changes = store.calls[0]
    assert job_id == "job-x"
    assert changes["heartbeat_at"]
    persisted = changes["progress_milestones"]
    assert persisted[-1]["code"] == "stage1_planner_invoked"
    assert persisted[-1]["meta"] == {"k": "v"}
    assert milestones[-1]["code"] == "stage1_planner_invoked"


def test_build_progress_recorder_swallows_persist_failures():
    store = _FailingUpdateStore()
    milestones, callback = generation_runtime.build_progress_recorder(job_id="job-x", store=store)

    # Must not raise even though the store write fails.
    callback("stage1_planner_invoked", "label", "detail", {})

    assert milestones[-1]["code"] == "stage1_planner_invoked"


def test_build_progress_recorder_respects_should_persist_guard():
    store = _RecordingStore()
    milestones, callback = generation_runtime.build_progress_recorder(
        job_id="job-x", store=store, should_persist=lambda: False
    )
    callback("stage1_planner_invoked", "label", "detail", {})

    assert store.calls == []
    assert milestones == []


def test_build_progress_recorder_caps_persisted_milestones():
    store = _RecordingStore()
    cap = generation_runtime._MAX_PERSISTED_MILESTONES
    milestones, callback = generation_runtime.build_progress_recorder(job_id="job-x", store=store)
    for index in range(cap + 5):
        callback(f"code-{index}", "label", "detail", {})

    assert len(milestones) == cap
    last_snapshot = store.calls[-1][1]["progress_milestones"]
    assert len(last_snapshot) == cap
    assert milestones[-1]["code"] == f"code-{cap + 4}"


# --- schedule_generation_job_if_needed (isolated branches) -----------------


def test_schedule_worker_only_mode_does_not_schedule_or_consume_capacity():
    store = _CapacityStore(count_result=0)
    background_tasks = BackgroundTasks()
    active_tasks: set[str] = set()
    job = {"id": "job-1", "status": "queued"}

    returned = asyncio.run(
        generation_runtime.schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=active_tasks,
            enable_in_process_generation=False,
            stale_job_checker=lambda j, **kw: False,
            stale_after_seconds=300,
        )
    )

    assert returned == job
    assert background_tasks.tasks == []
    assert active_tasks == set()


def test_schedule_defers_when_capacity_reached(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1")
    store = _CapacityStore(count_result=1)
    background_tasks = BackgroundTasks()
    active_tasks: set[str] = set()
    job = {"id": "job-1", "status": "queued"}

    returned = asyncio.run(
        generation_runtime.schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=active_tasks,
            enable_in_process_generation=True,
            stale_job_checker=lambda j, **kw: False,
            stale_after_seconds=300,
        )
    )

    assert returned == job
    assert background_tasks.tasks == []
    assert "job-1" not in active_tasks


def test_schedule_defers_when_capacity_count_unavailable(monkeypatch):
    monkeypatch.setenv("APP_GENERATION_MAX_CONCURRENT_JOBS", "1")
    store = _CapacityStore(
        count_exc=HTTPException(status_code=503, detail="capacity check unavailable")
    )
    background_tasks = BackgroundTasks()
    active_tasks: set[str] = set()
    job = {"id": "job-1", "status": "queued"}

    returned = asyncio.run(
        generation_runtime.schedule_generation_job_if_needed(
            job=job,
            background_tasks=background_tasks,
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=active_tasks,
            enable_in_process_generation=True,
            stale_job_checker=lambda j, **kw: False,
            stale_after_seconds=300,
        )
    )

    assert returned == job
    assert background_tasks.tasks == []
    assert "job-1" not in active_tasks


# --- Stage 2 token/cost metadata persistence -------------------------------


_STAGE2_COST_FIXTURE = {
    "stage2_model": "gpt-5-mini",
    "stage2_input_tokens": 1000,
    "stage2_output_tokens": 2000,
    "stage2_total_tokens": 3000,
    "stage2_estimated_cost_usd": 0.123456,
    "stage2_attempt_count": 1,
    "stage2_response_id": "resp_abc",
    "stage2_cost_recorded_at": "2026-06-06T00:00:00+00:00",
}


def test_successful_generation_records_stage2_cost_on_job():
    store = FakeStore()
    seed_default_profiles(store)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage2-cost-success",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(
                result=finalized_result(stage2_cost=dict(_STAGE2_COST_FIXTURE))
            ),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "completed"
    assert job["stage2_model"] == "gpt-5-mini"
    assert job["stage2_total_tokens"] == 3000
    assert job["stage2_estimated_cost_usd"] == 0.123456
    assert job["stage2_response_id"] == "resp_abc"


def test_failed_stage2_records_available_cost_on_job():
    store = FakeStore()
    seed_default_profiles(store)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage2-cost-failure",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    error = Stage2AutomationError("Stage 2 model request failed. Check server logs.")
    error.stage2_cost = {
        "stage2_model": "gpt-5-mini",
        "stage2_input_tokens": 500,
        "stage2_output_tokens": None,
        "stage2_total_tokens": None,
        "stage2_estimated_cost_usd": 0.0,
        "stage2_attempt_count": 1,
        "stage2_response_id": None,
        "stage2_cost_recorded_at": "2026-06-06T00:00:00+00:00",
    }

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(error=error),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "failed"
    assert job["stage2_model"] == "gpt-5-mini"
    assert job["stage2_input_tokens"] == 500
    assert job["stage2_output_tokens"] is None


def test_missing_stage2_cost_metadata_does_not_crash_generation():
    # A finalized result without stage2_cost (e.g. legacy automator) must still
    # complete the job; the cost columns simply stay unset.
    store = FakeStore()
    seed_default_profiles(store)
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="stage2-cost-absent",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result=finalized_result()),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "completed"
    assert job.get("stage2_model") is None


# --- post-terminal cleanup must not undo saved plan/job state --------------


def test_cleanup_failure_after_terminal_persist_preserves_plan_and_job():
    store = FakeStore()
    seed_default_profiles(store)
    request_payload = _build_request().model_dump(mode="json")
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="cleanup-failure",
        source="self_serve",
        request_payload=request_payload,
    )

    def boom_clear(athlete_id: str) -> None:
        raise RuntimeError("cleanup boom")

    store.clear_onboarding_draft = boom_clear  # type: ignore[assignment]

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "completed"
    plan_id = job.get("plan_id")
    assert plan_id
    assert store.get_plan(plan_id) is not None


def test_cleanup_timeout_after_terminal_persist_preserves_plan_and_job(monkeypatch):
    monkeypatch.setattr(persistence, "_POST_PERSIST_CLEANUP_TIMEOUT_SECONDS", 0.05)
    store = FakeStore()
    seed_default_profiles(store)
    request_payload = _build_request().model_dump(mode="json")
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="cleanup-timeout",
        source="self_serve",
        request_payload=request_payload,
    )

    def slow_clear(athlete_id: str) -> None:
        time.sleep(0.3)

    store.clear_onboarding_draft = slow_clear  # type: ignore[assignment]

    asyncio.run(
        generation_runtime.run_generation_job(
            job_id=created["id"],
            store=store,
            planner_fn=app_module._noop_planner,
            stage2=FakeStage2Automator(result_factory=finalized_result),
            active_tasks=set(),
        )
    )

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] == "completed"
    plan_id = job.get("plan_id")
    assert plan_id
    assert store.get_plan(plan_id) is not None
