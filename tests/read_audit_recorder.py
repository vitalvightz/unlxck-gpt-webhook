"""Opt-in pytest measurement plugin for existing synthetic workflow tests.

Enable with -p tests.read_audit_recorder --read-audit-output PATH. Counts are
logical FakeStore entries, never database operations. No payloads are retained.
"""
from collections import Counter
from contextvars import ContextVar
import functools
import json
from pathlib import Path
import time

import pytest
from starlette.testclient import TestClient
from tests.support import FakeStore

_current = ContextVar("synthetic_workflow", default=None)
_results = []


def pytest_addoption(parser):
    parser.addoption("--read-audit-output")


def pytest_configure(config):
    if not config.getoption("--read-audit-output"):
        return
    original_request = TestClient.request
    @functools.wraps(original_request)
    def request(self, method, url, *args, **kwargs):
        current = _current.get()
        if current is None:
            return original_request(self, method, url, *args, **kwargs)
        started = time.perf_counter()
        response = None
        try:
            response = original_request(self, method, url, *args, **kwargs)
            return response
        finally:
            # Only source-defined terminal operation names; never URL values.
            path = str(url).split("?")[0]
            allowed = {"checkin", "session-completion", "injury-checkin", "rehab-responses", "exercise-log", "exercise-logs", "pending", "history", "progress", "me", "today", "plans"}
            operation = path.rsplit("/", 1)[-1]
            current["requests"].append({"operation": operation if operation in allowed else "dynamic_endpoint",
                "method": method, "status": response.status_code if response is not None else None,
                "roundtrip_ms": (time.perf_counter()-started)*1000,
                "decoded_body_bytes": len(response.content) if response is not None else None})
    TestClient.request = request
    config._read_audit_original_request = original_request
    originals = {}
    for name in dir(FakeStore):
        original = getattr(FakeStore, name)
        if callable(original) and name.startswith(("get_", "list_", "count_", "ensure_")):
            originals[name] = original
            def wrap(fn, method):
                @functools.wraps(fn)
                def counted(*args, **kwargs):
                    current = _current.get()
                    if current is not None:
                        current["store_method_calls"][method] += 1
                    return fn(*args, **kwargs)
                return counted
            setattr(FakeStore, name, wrap(original, name))
    config._read_audit_originals = originals


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if not item.config.getoption("--read-audit-output"):
        yield
        return
    current = {"scenario": item.nodeid, "store_method_calls": Counter(), "requests": [],
               "database_operations": None, "database_execution_ms": None, "frontend_latency_ms": None}
    token = _current.set(current)
    started = time.perf_counter()
    try:
        outcome = yield
        current["passed"] = outcome.excinfo is None
    finally:
        current["workflow_ms"] = (time.perf_counter()-started)*1000
        _current.reset(token)
        _results.append(current)


def pytest_unconfigure(config):
    path = config.getoption("--read-audit-output")
    if path:
        Path(path).write_text(json.dumps({"source": "synthetic-existing-test-workflows", "scenarios": _results}, indent=2) + "\n")
        TestClient.request = config._read_audit_original_request
        for name, original in config._read_audit_originals.items():
            setattr(FakeStore, name, original)
        _results.clear()
