from __future__ import annotations

import pytest

import api.app as app_module
from api import generation_runtime
from api.generation_runtime import (
    _invoke_planner,
    _stage1_planner_timeout_seconds,
    _stage2_finalize_timeout_seconds,
    default_planner,
)


_ENVIRONMENT_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")


def _clear_environment_markers(monkeypatch):
    for var in _ENVIRONMENT_VARS:
        monkeypatch.delenv(var, raising=False)


def test_stage1_planner_timeout_default_is_240(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.delenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", raising=False)
    assert _stage1_planner_timeout_seconds() == 240.0


@pytest.mark.parametrize("sentinel", ["", "0", "none", "None", "NONE"])
def test_stage1_planner_timeout_sentinels_disable_timeout_outside_production(monkeypatch, sentinel):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", sentinel)
    assert _stage1_planner_timeout_seconds() is None


def test_stage1_planner_timeout_sentinel_does_not_disable_in_production(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "0")
    assert _stage1_planner_timeout_seconds() == 240.0


def test_stage1_planner_timeout_invalid_falls_back_to_240(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "not-a-number")
    assert _stage1_planner_timeout_seconds() == 240.0


def test_stage1_planner_timeout_respects_valid_override(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "60")
    assert _stage1_planner_timeout_seconds() == 60.0


def test_stage1_planner_timeout_respects_fractional_positive_override(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "0.5")
    assert _stage1_planner_timeout_seconds() == 0.5


def test_stage2_finalize_timeout_default_is_240(monkeypatch):
    monkeypatch.delenv("APP_STAGE2_FINALIZE_TIMEOUT_SECONDS", raising=False)
    assert _stage2_finalize_timeout_seconds() == 240.0


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
