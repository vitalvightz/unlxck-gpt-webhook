from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.check_xp_hardening_rollout as gate


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")


class _Rpc:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.payload)


class _Client:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.rpc_name = ""

    def rpc(self, name: str) -> _Rpc:
        self.rpc_name = name
        return _Rpc(self.payload)


def _configure(monkeypatch: pytest.MonkeyPatch, payload: object) -> _Client:
    client = _Client(payload)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    monkeypatch.setattr(gate, "create_client", lambda url, key: client)
    return client


def test_final_rollout_payload_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _configure(
        monkeypatch,
        {
            "ok": True,
            "version": gate.EXPECTED_VERSION,
            "rollout_ready": True,
            "open_plan_scope_ready": True,
        },
    )

    gate.validate_xp_hardening_rollout()

    assert client.rpc_name == "validate_xp_abuse_hardening"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"ok": True, "version": gate.EXPECTED_VERSION},
        {
            "ok": True,
            "version": gate.EXPECTED_VERSION,
            "rollout_ready": True,
            "open_plan_scope_ready": False,
        },
        {
            "ok": True,
            "version": "stale",
            "rollout_ready": True,
            "open_plan_scope_ready": True,
        },
    ],
)
def test_partial_or_stale_rollout_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
) -> None:
    _configure(monkeypatch, payload)

    with pytest.raises(RuntimeError):
        gate.validate_xp_hardening_rollout()


def test_missing_service_role_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(RuntimeError):
        gate.validate_xp_hardening_rollout()


def test_api_health_requires_database_rollout_and_http_health() -> None:
    assert "test -f /tmp/unlxck-xp-hardening-ready" in COMPOSE
    assert "python tools/check_xp_hardening_rollout.py" in COMPOSE
    assert "touch /tmp/unlxck-xp-hardening-ready" in COMPOSE
    assert "curl --fail --silent http://127.0.0.1:8000/health" in COMPOSE
    assert COMPOSE.index("python tools/check_xp_hardening_rollout.py") < COMPOSE.index(
        "curl --fail --silent http://127.0.0.1:8000/health"
    )
