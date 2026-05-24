from __future__ import annotations

import asyncio

import pytest

import api.app as app_module
from api import generation_runtime
from api import worker as worker_module
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
from support import FakeStage2Automator, FakeStore, _build_request, finalized_result


_ENVIRONMENT_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")


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
    result = asyncio.run(run_stage1_planner(_spawn_planner_returns, {"value": 3}, timeout_seconds=2))
    assert result == {"ok": 3}


def test_stage1_run_planner_relays_progress(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")
    codes: list[str] = []

    def callback(code, label, detail, meta):
        codes.append(code)

    result = asyncio.run(
        run_stage1_planner(_spawn_planner_with_progress, {"value": 1}, progress_callback=callback, timeout_seconds=2)
    )
    assert result == {"ok": True}
    assert "planner_started" in codes


def test_stage1_run_planner_raises_controlled_runtime_error(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(run_stage1_planner(_spawn_planner_raises, {}, timeout_seconds=2))


def test_stage1_run_planner_timeout(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(run_stage1_planner(_spawn_planner_hangs, {}, timeout_seconds=0.1))


def test_stage1_run_planner_child_exit_without_result_raises_controlled_error(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")

    with pytest.raises(RuntimeError, match="Stage 1 planner process exited without result"):
        asyncio.run(run_stage1_planner(_spawn_planner_exits, {}, timeout_seconds=2))


def test_stage1_run_planner_returns_after_planner_returns(monkeypatch):
    monkeypatch.setenv("UNLXCK_STAGE1_MP_START_METHOD", "spawn")
    result = asyncio.run(run_stage1_planner(_spawn_planner_returns_then_sleeps, {"value": 7}, timeout_seconds=1.0))
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
            timeout_seconds=2,
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
    created = store.create_or_get_generation_job(
        athlete_id="athlete-1",
        client_request_id="worker-processes-queued",
        source="self_serve",
        request_payload=_build_request().model_dump(mode="json"),
    )
    active_tasks: set[str] = set()
    detached_tasks: set[asyncio.Task[None]] = set()

    original_builder = worker_module.build_default_stage2_automator
    worker_module.build_default_stage2_automator = lambda: FakeStage2Automator(result=finalized_result())
    try:
        asyncio.run(
            worker_module._tick(
                store=store,
                active_tasks=active_tasks,
                detached_tasks=detached_tasks,
                stale_after_seconds=660,
                max_concurrent_jobs=1,
            )
        )
        while detached_tasks:
            asyncio.run(asyncio.gather(*list(detached_tasks)))
    finally:
        worker_module.build_default_stage2_automator = original_builder

    job = store.get_generation_job(created["id"])
    assert job is not None
    assert job["status"] in {"completed", "review_required"}
    assert job["completed_at"] is not None


def test_stage2_finalize_timeout_default_is_600(monkeypatch):
    monkeypatch.delenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", raising=False)
    assert _stage2_finalize_timeout_seconds() == 600.0


@pytest.mark.parametrize("sentinel", ["", "0", "none", "None", "NONE"])
def test_stage2_finalize_timeout_sentinels_disable_timeout(monkeypatch, sentinel):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", sentinel)
    assert _stage2_finalize_timeout_seconds() is None


def test_stage2_finalize_timeout_invalid_falls_back_to_300(monkeypatch):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "not-a-number")
    assert _stage2_finalize_timeout_seconds() == 300.0


def test_stage2_finalize_timeout_respects_valid_override(monkeypatch):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "60")
    assert _stage2_finalize_timeout_seconds() == 60.0


def test_stage2_finalize_timeout_enforces_minimum_of_1(monkeypatch):
    monkeypatch.setenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", "0.5")
    assert _stage2_finalize_timeout_seconds() == 1.0


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

    monkeypatch.setattr(generation_runtime, "generate_plan_sync", fake_generate_plan_sync)

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

    monkeypatch.setattr(generation_runtime, "generate_plan_sync", fake_generate_plan_sync)

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


def test_terminal_success_without_plan_id_is_downgraded_to_failed_with_error_message():
    store = FakeStore()
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


@pytest.mark.parametrize(
    ("plan_status", "expected_generation_status"),
    [
        ("ready", "completed"),
        ("publishable_with_flags", "completed"),
        ("held_for_review", "review_required"),
        ("review_required", "review_required"),
    ],
)
def test_generation_status_from_plan_status_mapper(plan_status: str, expected_generation_status: str):
    assert generation_status_from_plan_status(plan_status) == expected_generation_status


def test_generation_job_status_never_uses_legacy_plan_status_values():
    for legacy_status in ("publishable_with_flags", "held_for_review"):
        mapped = generation_status_from_plan_status(legacy_status)
        assert mapped != legacy_status
