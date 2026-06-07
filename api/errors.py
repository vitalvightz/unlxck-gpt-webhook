"""Machine-readable HTTP errors.

The frontend recovers from some backend conditions (notably the multi-tab
"a job is already running" conflict) by inspecting the error. Matching on the
human-readable ``detail`` string is brittle — any copy edit silently breaks
recovery. ``CodedHTTPException`` attaches a stable ``code`` alongside the
existing string ``detail`` so clients can branch on ``code`` while the prose
stays free to change. The response builders in ``api/app.py`` surface the code
as a top-level ``code`` field, leaving ``detail`` untouched for backwards
compatibility.
"""

from __future__ import annotations

from fastapi import HTTPException, status

# Emitted whenever a new generation job is blocked because an existing job for
# the same athlete is still queued or running (typically a second tab/device).
GENERATION_ALREADY_IN_FLIGHT_CODE = "generation_already_in_flight"
GENERATION_ALREADY_IN_FLIGHT_MESSAGE = (
    "A generation job is already queued or running for this account."
)
CLIENT_REQUEST_ID_PAYLOAD_MISMATCH_CODE = "client_request_id_payload_mismatch"
CLIENT_REQUEST_ID_PAYLOAD_MISMATCH_MESSAGE = (
    "This request id has already been used for a different generation payload."
)


class CodedHTTPException(HTTPException):
    """``HTTPException`` carrying a stable machine-readable ``code``."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def generation_already_in_flight_error() -> CodedHTTPException:
    """409 raised when another job for the athlete is already in flight."""

    return CodedHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        code=GENERATION_ALREADY_IN_FLIGHT_CODE,
        detail=GENERATION_ALREADY_IN_FLIGHT_MESSAGE,
    )


def client_request_id_payload_mismatch_error() -> CodedHTTPException:
    """409 raised when a reused client request id carries a different payload."""

    return CodedHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        code=CLIENT_REQUEST_ID_PAYLOAD_MISMATCH_CODE,
        detail=CLIENT_REQUEST_ID_PAYLOAD_MISMATCH_MESSAGE,
    )
