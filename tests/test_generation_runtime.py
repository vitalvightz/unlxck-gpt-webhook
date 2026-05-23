from __future__ import annotations

import pytest

from api.generation_runtime import _stage1_planner_timeout_seconds, _stage2_finalize_timeout_seconds


_ENVIRONMENT_VARS = ("APP_ENV", "ENVIRONMENT", "UNLXCK_ENV", "NODE_ENV")


def _clear_environment_markers(monkeypatch):
    for var in _ENVIRONMENT_VARS:
        monkeypatch.delenv(var, raising=False)


def test_stage1_planner_timeout_default_is_180(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.delenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", raising=False)
    assert _stage1_planner_timeout_seconds() == 180.0


@pytest.mark.parametrize("sentinel", ["", "0", "none", "None", "NONE"])
def test_stage1_planner_timeout_sentinels_disable_timeout_outside_production(monkeypatch, sentinel):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", sentinel)
    assert _stage1_planner_timeout_seconds() is None


def test_stage1_planner_timeout_sentinel_does_not_disable_in_production(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "0")
    assert _stage1_planner_timeout_seconds() == 180.0


def test_stage1_planner_timeout_invalid_falls_back_to_180(monkeypatch):
    _clear_environment_markers(monkeypatch)
    monkeypatch.setenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "not-a-number")
    assert _stage1_planner_timeout_seconds() == 180.0


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
