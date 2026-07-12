"""ASGI middleware that enforces a hard ceiling on actual received body bytes.

The cheap ``Content-Length`` check in ``api/app.py`` rejects oversized requests
when clients declare an honest length, but it can be bypassed: chunked transfers
carry no ``Content-Length``, and a client can simply understate (or omit) the
header. This middleware counts bytes off the ASGI ``receive`` channel as the body
streams in and aborts with 413 once the limit is crossed — before the
application buffers the whole body — regardless of what the header claimed.
"""

from __future__ import annotations

import logging

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("api")


def normalize_request_path(value: object) -> str:
    """Normalize non-root request paths for path-specific body limits."""

    path = str(value or "")
    return path.rstrip("/") if path != "/" and path.endswith("/") else path


class _RequestBodyTooLarge(BaseException):
    """Internal signal that the streamed body crossed the configured ceiling.

    Inherits from ``BaseException`` (not ``Exception``) so that if it ever has
    to propagate — e.g. in the ``response_started`` re-raise path — Starlette's
    ``ServerErrorMiddleware``, which only catches ``Exception``, can't swallow
    it and rewrite the response into a generic 500.
    """


class RequestBodySizeLimitMiddleware:
    """Reject requests whose streamed body exceeds ``max_body_bytes``."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        path_limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.path_limits = path_limits or {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = normalize_request_path(scope.get("path"))
        request_limit = self.path_limits.get(path, self.max_body_bytes)
        body_seen = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal body_seen
            message = await receive()
            if message["type"] == "http.request":
                body_seen += len(message.get("body", b""))
                if body_seen > request_limit:
                    raise _RequestBodyTooLarge()
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            logger.warning(
                "[http] request:body_too_large_streamed method=%s path=%s received=%s limit=%s",
                scope.get("method"),
                scope.get("path"),
                body_seen,
                request_limit,
            )
            if response_started:
                # The app already began responding despite the oversized body;
                # we can no longer emit our own status, so re-raise to let the
                # server tear the connection down rather than corrupt the stream.
                raise
            response = JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "request body too large", "code": "request_body_too_large"},
            )
            await response(scope, receive, send)
