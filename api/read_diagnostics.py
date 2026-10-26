"""Opt-in request-local Data API attempt measurements; never SQL execution time."""
from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
import threading
import time
from typing import Any

import httpx

_current: ContextVar[ReadDiagnostics | None] = ContextVar("read_diagnostics", default=None)


@dataclass
class ReadDiagnostics:
    operations: int = 0
    reads: int = 0
    failures: int = 0
    repeated_reads: int = 0
    categories: Counter = field(default_factory=Counter)
    operation_ms: float = 0
    attempts: list = field(default_factory=list)
    # Salt and fingerprints live only for this request and are never exported.
    _salt: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)
    _seen: set = field(default_factory=set, repr=False)
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict:
        with self._lock:
            return {"operations": self.operations, "reads": self.reads,
                    "failures": self.failures, "repeated_reads": self.repeated_reads,
                    "reads_by_category": dict(self.categories),
                    "data_api_attempt_ms": round(self.operation_ms, 3),
                    "attempts": list(self.attempts)}


def begin():
    diagnostics = ReadDiagnostics()
    return diagnostics, _current.set(diagnostics)


def end(token):
    _current.reset(token)


class DiagnosticHttpClient(httpx.Client):
    """Same client behaviour; disabled path is one ContextVar lookup per send.

    Count every HTTP attempt, including exceptions and HTTP errors. RPCs are
    operations of unknown read/write type, not inferred reads. Auth/storage
    calls are excluded. Equivalent GETs include exact URL but no retained URL.
    """

    def send(self, request, *args, **kwargs):
        diagnostics = _current.get()
        if diagnostics is None or not request.url.path.startswith("/rest/v1/"):
            return super().send(request, *args, **kwargs)
        read = request.method in {"GET", "HEAD"} and "/rpc/" not in request.url.path
        # Only fixed safe categories leave this module; table/column names,
        # filters, RPC params, headers, bodies and errors are never exported.
        table = request.url.path.removeprefix("/rest/v1/")
        category = table if read and table in {
            "profiles", "plans", "athlete_intakes", "today_checkins",
            "session_completions", "exercise_logs", "injury_flags",
            "injury_episode_events", "generation_jobs", "external_training_sessions",
            "manual_exercise_entries", "athlete_streaks",
        } else ("other_table_read" if read else "write_or_rpc")
        identity = "\n".join((request.method, str(request.url),
                              request.headers.get("range", ""),
                              request.headers.get("range-unit", ""),
                              request.headers.get("accept", ""),
                              request.headers.get("prefer", ""))) if read else ""
        fingerprint = hmac.digest(diagnostics._salt, identity.encode(), hashlib.sha256) if read else None
        with diagnostics._lock:
            diagnostics.operations += 1
            if read:
                diagnostics.reads += 1
                diagnostics.categories[category] += 1
                diagnostics.repeated_reads += int(fingerprint in diagnostics._seen)
                diagnostics._seen.add(fingerprint)
        started = time.perf_counter()
        failed = True
        try:
            response = super().send(request, *args, **kwargs)
            failed = response.is_error
            return response
        finally:
            with diagnostics._lock:
                duration_ms = (time.perf_counter() - started) * 1000
                diagnostics.operation_ms += duration_ms
                diagnostics.attempts.append({"category": category, "read": read,
                                             "duration_ms": round(duration_ms, 3), "failed": failed})
                diagnostics.failures += int(failed)
