from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "deploy-hetzner.yml").read_text()
DEPLOY_SCRIPT = (REPO_ROOT / "scripts" / "deploy_hetzner.sh").read_text()
COMPOSE = (REPO_ROOT / "compose.yaml").read_text()
GITIGNORE = (REPO_ROOT / ".gitignore").read_text().splitlines()


def test_workflow_has_safe_triggers_and_concurrency() -> None:
    assert "push:" in WORKFLOW
    assert "- Main" in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert "group: hetzner-production" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW


def test_workflow_uses_strict_ssh_and_expected_secrets() -> None:
    for secret_name in (
        "HETZNER_HOST",
        "HETZNER_USER",
        "HETZNER_SSH_PORT",
        "HETZNER_SSH_PRIVATE_KEY",
        "HETZNER_SSH_KNOWN_HOSTS",
    ):
        assert f"secrets.{secret_name}" in WORKFLOW

    assert "StrictHostKeyChecking=yes" in WORKFLOW
    assert "StrictHostKeyChecking=no" not in WORKFLOW
    assert "UserKnownHostsFile=" in WORKFLOW


def test_workflow_gates_before_deploying() -> None:
    assert "needs: preflight" in WORKFLOW
    assert "tests/test_api_generation_flows.py" in WORKFLOW
    assert "tests/test_generation_runtime.py" in WORKFLOW
    assert "docker compose config --quiet" in WORKFLOW
    assert "docker compose build api worker" in WORKFLOW


def test_deploy_script_preserves_state_and_rolls_back() -> None:
    assert "set -Eeuo pipefail" in DEPLOY_SCRIPT
    assert "flock -n" in DEPLOY_SCRIPT
    assert "git ls-files --error-unmatch .env.production" in DEPLOY_SCRIPT
    assert "git check-ignore -q .env.production" in DEPLOY_SCRIPT
    assert 'git reset --hard "$TARGET_SHA"' in DEPLOY_SCRIPT
    assert 'git reset --hard "$PREVIOUS_SHA"' in DEPLOY_SCRIPT
    assert "docker compose down" not in DEPLOY_SCRIPT
    assert "docker stop --time 610" in DEPLOY_SCRIPT
    assert "docker compose up -d --no-deps worker" in DEPLOY_SCRIPT
    assert "verify_public_health" in DEPLOY_SCRIPT
    assert "DEPLOY_RESULT=\"rolled_back\"" in DEPLOY_SCRIPT


def test_worker_has_single_consumer_and_long_shutdown_drain() -> None:
    assert 'UNLXCK_GENERATION_WORKER_MAX_CONCURRENT_JOBS: "1"' in COMPOSE
    assert 'UNLXCK_GENERATION_WORKER_SHUTDOWN_GRACE_SECONDS: "600"' in COMPOSE
    assert "stop_grace_period: 610s" in COMPOSE


def test_production_environment_file_is_ignored() -> None:
    assert ".env.production" in GITIGNORE
