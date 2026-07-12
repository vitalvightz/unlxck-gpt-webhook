"""Unit tests for the streaming request-body size guard.

These drive the ASGI interface directly so we can simulate a body that streams
in over several chunks while understating (or omitting) Content-Length — the
case the cheap header check in ``api/app.py`` cannot catch.
"""

from __future__ import annotations

import asyncio

from api.request_body_guard import RequestBodySizeLimitMiddleware, normalize_request_path


def _run(coro):
    return asyncio.run(coro)


async def _drive(middleware, body_chunks, *, path="/api/plans/generate"):
    """Send ``body_chunks`` through ``middleware`` and capture the response start."""

    scope = {"type": "http", "method": "POST", "path": path}
    chunks = list(body_chunks)
    inner_called = {"value": False}

    async def receive():
        if chunks:
            chunk = chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": bool(chunks)}
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def inner_app(scope, receive, send):
        # A realistic endpoint reads the whole body before responding.
        inner_called["value"] = True
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware.app = inner_app
    await middleware(scope, receive, send)
    return sent, inner_called["value"]


def test_oversized_streamed_body_is_rejected_with_413():
    middleware = RequestBodySizeLimitMiddleware(None, max_body_bytes=10)
    # Five 4-byte chunks = 20 bytes, exceeding the 10-byte ceiling, with no
    # Content-Length declared at all.
    sent, _inner_called = _run(_drive(middleware, [b"aaaa"] * 5))

    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 413


def test_body_within_limit_passes_through():
    middleware = RequestBodySizeLimitMiddleware(None, max_body_bytes=100)
    sent, inner_called = _run(_drive(middleware, [b"aaaa", b"bbbb"]))

    assert inner_called is True
    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 200


def test_non_http_scope_is_passed_through_untouched():
    middleware = RequestBodySizeLimitMiddleware(None, max_body_bytes=1)
    seen = {"value": False}

    async def inner_app(scope, receive, send):
        seen["value"] = True

    middleware.app = inner_app

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(message):
        return None

    _run(middleware({"type": "lifespan"}, receive, send))
    assert seen["value"] is True


def test_path_specific_limit_accepts_a_trailing_slash():
    middleware = RequestBodySizeLimitMiddleware(
        None,
        max_body_bytes=10,
        path_limits={"/api/feedback/global": 100},
    )
    sent, inner_called = _run(
        _drive(
            middleware,
            [b"a" * 20],
            path="/api/feedback/global/",
        )
    )
    assert inner_called is True
    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 200


def test_request_path_normalization_preserves_root():
    assert normalize_request_path("/") == "/"
    assert normalize_request_path("/api/feedback/global/") == "/api/feedback/global"
