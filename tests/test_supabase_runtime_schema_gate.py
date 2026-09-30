"""Tests for the CI policy around the live Supabase schema checker."""

from __future__ import annotations

from tools.run_supabase_runtime_schema_gate import (
    is_main_deploy,
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


def test_main_deploy_detection_accepts_capitalized_main_branch():
    assert is_main_deploy(_env(GITHUB_REF_NAME="Main"))


def test_main_deploy_detection_does_not_require_branch_protection():
    # An unprotected Main still deploys, so it must still be gated.
    assert is_main_deploy(_env(GITHUB_REF_NAME="main", GITHUB_REF_PROTECTED="false"))
    assert is_main_deploy(_env(GITHUB_REF_NAME="main", GITHUB_REF_PROTECTED="true"))


def test_main_deploy_detection_requires_push_to_main():
    assert not is_main_deploy(_env(GITHUB_EVENT_NAME="pull_request", GITHUB_REF_NAME="main"))
    assert not is_main_deploy(_env(GITHUB_REF_NAME="release"))


def test_required_flag_makes_any_run_mandatory():
    assert is_main_deploy(
        _env(GITHUB_EVENT_NAME="workflow_dispatch", SUPABASE_SCHEMA_GATE_REQUIRED="true")
    )
    assert not is_main_deploy(_env(SUPABASE_SCHEMA_GATE_REQUIRED="false"))


def test_gate_fails_when_main_deploy_lacks_supabase_credentials(capsys):
    called = False

    def schema_check(argv: list[str]) -> int:
        nonlocal called
        called = True
        return 0

    result = run_gate(_env(GITHUB_REF_NAME="Main"), schema_check=schema_check)

    assert result == 2
    assert not called
    output = capsys.readouterr().out
    assert "mandatory for Main/main deploys" in output
    assert "SUPABASE_URL" in output
    assert "SUPABASE_SERVICE_ROLE_KEY" in output


def test_gate_skips_missing_credentials_away_from_main(capsys):
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


def test_deploy_workflow_runs_mandatory_schema_gate_before_deploying():
    workflow = open(".github/workflows/deploy-hetzner.yml", encoding="utf-8").read()

    gate = workflow.index("python tools/run_supabase_runtime_schema_gate.py")
    assert "SUPABASE_SCHEMA_GATE_REQUIRED: \"true\"" in workflow
    assert gate < workflow.index("- name: Deploy backend")
