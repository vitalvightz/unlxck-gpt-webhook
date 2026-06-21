from __future__ import annotations

import os

from api.environment import (
    apply_production_environment_defaults,
    is_production_environment,
    should_default_to_production,
)


def test_apply_production_environment_defaults_sets_backend_markers(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("UNLXCK_ENV", raising=False)

    apply_production_environment_defaults()
    try:
        assert is_production_environment() is True
        assert os.environ["APP_ENV"] == "production"
        assert os.environ["UNLXCK_ENV"] == "production"
    finally:
        # apply_production_environment_defaults writes directly to os.environ.
        # monkeypatch.delenv records no undo for vars that were absent, so it
        # cannot revert these writes — scrub them explicitly to avoid leaking
        # production markers into later tests (e.g. create_app's production
        # CORS validation would refuse to boot with localhost origins).
        os.environ.pop("APP_ENV", None)
        os.environ.pop("UNLXCK_ENV", None)


def test_apply_production_environment_defaults_preserves_explicit_values(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("UNLXCK_ENV", "staging")

    apply_production_environment_defaults()

    assert os.environ["APP_ENV"] == "development"
    assert os.environ["UNLXCK_ENV"] == "staging"


def test_should_default_to_production_when_supabase_runtime_config_exists(monkeypatch):
    # The pytest guard in should_default_to_production short-circuits to False
    # under test; drop it so the real runtime-config detection is exercised.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    assert should_default_to_production() is False

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")

    assert should_default_to_production() is True


def test_should_default_to_production_when_only_service_role_key_exists(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")

    assert should_default_to_production() is True
