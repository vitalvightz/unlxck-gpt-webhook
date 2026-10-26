import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
import pytest

from api.read_diagnostics import DiagnosticHttpClient, begin, end


def test_attempts_failures_equivalence_and_privacy():
    attempts = []

    def respond(request):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("secret medical data")
        return httpx.Response(503 if len(attempts) == 2 else 200, json=[])

    with DiagnosticHttpClient(transport=httpx.MockTransport(respond)) as client:
        diagnostics, token = begin()
        try:
            for _ in range(3):
                try:
                    client.get("https://db.test/rest/v1/profiles?id=eq.secret-user", headers={"Authorization": "secret-token"})
                except httpx.ReadTimeout:
                    pass
            client.post("https://db.test/rest/v1/rpc/example", json={"injury": "secret-medical"})
            snapshot = diagnostics.snapshot()
        finally:
            end(token)
    assert snapshot["operations"] == 4
    assert snapshot["reads"] == 3
    assert snapshot["failures"] == 2
    assert snapshot["repeated_reads"] == 2
    assert snapshot["reads_by_category"] == {"profiles": 3}
    assert "secret" not in json.dumps(snapshot)


def test_disabled_preserves_response_and_exception():
    response = httpx.Response(200, json={"unchanged": True})
    error = httpx.ReadTimeout("unchanged")
    with DiagnosticHttpClient(transport=httpx.MockTransport(lambda _: response)) as client:
        assert client.get("https://db.test/rest/v1/plans") is response
    def fail(_):
        raise error
    with DiagnosticHttpClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(httpx.ReadTimeout) as caught:
            client.get("https://db.test/rest/v1/plans")
        assert caught.value is error


def test_concurrent_async_scopes_and_worker_threads_are_isolated():
    async def run(count):
        diagnostics, token = begin()
        try:
            await asyncio.sleep(0)
            def send():
                with DiagnosticHttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
                    for _ in range(count):
                        client.get("https://db.test/rest/v1/plans?id=eq.private")
            await asyncio.to_thread(send)
            return diagnostics.snapshot()["reads"]
        finally:
            end(token)
    async def both():
        return await asyncio.gather(run(2), run(5))
    assert asyncio.run(both()) == [2, 5]
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(lambda _: asyncio.run(both()), range(2))) == [[2, 5], [2, 5]]


def test_different_filters_and_rpc_are_not_duplicate_reads():
    with DiagnosticHttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        diagnostics, token = begin()
        try:
            for url in ("plans?id=eq.a", "plans?id=eq.b", "rpc/read_plan", "unknown-secret"):
                client.get(f"https://db.test/rest/v1/{url}")
            client.get("https://db.test/auth/v1/user")
            assert diagnostics.snapshot()["operations"] == 4
            assert diagnostics.snapshot()["reads"] == 3
            assert diagnostics.snapshot()["repeated_reads"] == 0
            assert "secret" not in json.dumps(diagnostics.snapshot())
        finally:
            end(token)


def test_real_store_retry_counts_every_attempt():
    from api.store import SupabaseAppStore
    attempts = []
    def respond(_):
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ReadTimeout("private error")
        return httpx.Response(200, json=[])
    store = SupabaseAppStore(None, set())
    with DiagnosticHttpClient(transport=httpx.MockTransport(respond)) as client:
        diagnostics, token = begin()
        try:
            response = store._run_with_transient_retry(
                operation="synthetic", backoff_seconds=0,
                fn=lambda: client.get("https://db.test/rest/v1/plans?id=eq.private"))
            assert response.status_code == 200
            assert diagnostics.snapshot()["reads"] == 3
            assert diagnostics.snapshot()["failures"] == 2
            assert diagnostics.snapshot()["repeated_reads"] == 2
        finally:
            end(token)


def test_middleware_opt_in_uses_route_patterns_and_preserves_responses(monkeypatch):
    from tests.support import _build_client
    from api import app as app_module
    captured = []
    original = app_module.logger.info
    def log(message, *args, **kwargs):
        if message == "[read-audit] %s":
            captured.append(json.loads(args[0]))
        else:
            original(message, *args, **kwargs)
    monkeypatch.setattr(app_module.logger, "info", log)
    client, _, _ = _build_client()
    path = "/api/plans/11111111-1111-1111-1111-111111111111?secret=medical"
    headers = {"Authorization": "Bearer athlete-token"}
    monkeypatch.delenv("UNLXCK_READ_DIAGNOSTICS", raising=False)
    disabled = client.get(path, headers=headers)
    assert captured == []
    monkeypatch.setenv("UNLXCK_READ_DIAGNOSTICS", "1")
    enabled = client.get(path, headers=headers)
    assert enabled.status_code == disabled.status_code
    assert {k: v for k, v in enabled.json().items() if k != "request_id"} == {k: v for k, v in disabled.json().items() if k != "request_id"}
    assert captured[0]["route"] == "/api/plans/{plan_id}"
    assert "secret" not in json.dumps(captured)
    assert "11111111" not in json.dumps(captured)
    assert "medical" not in json.dumps(captured)


def test_equivalence_respects_method_and_range_headers():
    with DiagnosticHttpClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        diagnostics, token = begin()
        try:
            url = "https://db.test/rest/v1/plans"
            client.get(url, headers={"Range": "0-9"})
            client.get(url, headers={"Range": "10-19"})
            client.head(url, headers={"Range": "0-9"})
            assert diagnostics.snapshot()["repeated_reads"] == 0
            client.get(url, headers={"Range": "0-9"})
            assert diagnostics.snapshot()["reads"] == 4
            assert diagnostics.snapshot()["repeated_reads"] == 1
        finally:
            end(token)
