import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SOURCE = (REPO_ROOT / ".github" / "workflows" / "deploy-hetzner.yml").read_text(
    encoding="utf-8"
)
DEPLOY_STEP = WORKFLOW_SOURCE.split("- name: Deploy backend", 1)[1].split(
    "- name: Remove transferred bundle from server", 1
)[0]
PUBLIC_HEALTH_STEP = WORKFLOW_SOURCE.split("- name: Verify public health endpoint", 1)[1]


def test_remote_health_probe_targets_local_caddy_without_cloudflare():
    assert 'HEALTH_HOST="api.unlxck.com"' in DEPLOY_STEP
    assert 'HEALTH_URL="https://${HEALTH_HOST}/health"' in DEPLOY_STEP
    assert '--noproxy "$HEALTH_HOST"' in DEPLOY_STEP
    assert '--resolve "${HEALTH_HOST}:443:127.0.0.1"' in DEPLOY_STEP

    # Keep the independent runner-side check on the public Cloudflare path.
    assert "--resolve" not in PUBLIC_HEALTH_STEP
    assert "https://api.unlxck.com/health" in PUBLIC_HEALTH_STEP


def test_deploy_and_rollback_validate_and_reload_caddy_configuration():
    assert 'CADDY_CONFIG="/etc/caddy/Caddyfile"' in DEPLOY_STEP
    assert 'caddy validate --config "$CADDY_CONFIG"' in DEPLOY_STEP
    assert 'caddy reload --config "$CADDY_CONFIG"' in DEPLOY_STEP

    # One definition plus calls on the deployment and rollback paths.
    assert DEPLOY_STEP.count("validate_and_reload_caddy") == 3
    assert "restored Caddy configuration could not be reloaded" in DEPLOY_STEP


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is unavailable")
def test_remote_deploy_script_has_valid_bash_syntax():
    remote_script = DEPLOY_STEP.split("<<'REMOTE_SCRIPT'", 1)[1].rsplit(
        "REMOTE_SCRIPT", 1
    )[0]

    subprocess.run(
        ["bash", "-n"],
        input=textwrap.dedent(remote_script),
        text=True,
        check=True,
    )
