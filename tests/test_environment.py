from __future__ import annotations

import os

from api.environment import apply_production_environment_defaults, is_production_environment


def test_apply_production_environment_defaults_sets_backend_markers(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("UNLXCK_ENV", raising=False)

    apply_production_environment_defaults()

    assert is_production_environment() is True
    assert os.environ["APP_ENV"] == "production"
    assert os.environ["UNLXCK_ENV"] == "production"


def test_apply_production_environment_defaults_preserves_explicit_values(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("UNLXCK_ENV", "staging")

    apply_production_environment_defaults()

    assert os.environ["APP_ENV"] == "development"
    assert os.environ["UNLXCK_ENV"] == "staging"
