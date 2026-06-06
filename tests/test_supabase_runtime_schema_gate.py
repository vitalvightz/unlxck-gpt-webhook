"""Tests for the CI policy around the live Supabase schema checker."""

from __future__ import annotations

from tools.run_supabase_runtime_schema_gate import (
    is_protected_main_deploy,
    run_gate,
)


def _env(**overrides: str) -> dict[str, str]:
    env = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF_NAME": "feature/example",
        "GITHUB_REF_PROTECTED": "false",
    }
    env.update(overrides)
    return env


def test_protected_main_deploy_detection_requires_push_main_and_protection():
    assert is_protected_main_deploy(
        _env(GITHUB_REF_NAME="main", GITHUB_REF_PROTECTED="true")
    )
    assert not is_protected_main_deploy(
        _env(
            GITHUB_EVENT_NAME="pull_request",
            GITHUB_REF_NAME="main",
            GITHUB_REF_PROTECTED="true",
        )
    )
    assert not is_protected_main_deploy(
        _env(GITHUB_REF_NAME="main", GITHUB_REF_PROTECTED="false")
    )
    assert not is_protected_main_deploy(
        _env(GITHUB_REF_NAME="release", GITHUB_REF_PROTECTED="true")
    )


def test_gate_fails_when_protected_main_deploy_lacks_supabase_credentials(capsys):
    called = False

    def schema_check(argv: list[str]) -> int:
        nonlocal called
        called = True
        return 0

    result = run_gate(
        _env(GITHUB_REF_NAME="main", GITHUB_REF_PROTECTED="true"),
        schema_check=schema_check,
    )

    assert result == 2
    assert not called
    output = capsys.readouterr().out
    assert "mandatory for protected main deploys" in output
    assert "SUPABASE_URL" in output
    assert "SUPABASE_SERVICE_ROLE_KEY" in output


def test_gate_skips_missing_credentials_away_from_protected_main(capsys):
    called = False

    def schema_check(argv: list[str]) -> int:
        nonlocal called
        called = True
        return 1

    result = run_gate(_env(), schema_check=schema_check)

    assert result == 0
    assert not called
    assert "Skipping live schema check" in capsys.readouterr().out


def test_gate_runs_schema_check_when_credentials_exist():
    argv_seen = None

    def schema_check(argv: list[str]) -> int:
        nonlocal argv_seen
        argv_seen = argv
        return 1

    result = run_gate(
        _env(
            SUPABASE_URL="https://example.supabase.co",
            SUPABASE_SERVICE_ROLE_KEY="service-key",
        ),
        schema_check=schema_check,
    )

    assert result == 1
    assert argv_seen == []


def test_backend_checks_workflow_uses_mandatory_schema_gate():
    workflow = open(".github/workflows/backend-checks.yml", encoding="utf-8").read()

    assert "python tools/run_supabase_runtime_schema_gate.py" in workflow
    assert "python tools/check_supabase_runtime_schema.py" not in workflow
    assert "Skipping live schema check; staging secrets not configured." not in workflow
