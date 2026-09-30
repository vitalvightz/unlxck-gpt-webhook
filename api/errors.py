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

from typing import Any

from fastapi import HTTPException, status

from shared.contracts import shared_code, shared_message

# Emitted whenever a new generation job is blocked because an existing job for
# the same athlete is still queued or running (typically a second tab/device).
# The web client recovers on this code (shared/api-messages.json).
GENERATION_ALREADY_IN_FLIGHT_CODE, GENERATION_ALREADY_IN_FLIGHT_MESSAGE = shared_message(
    "generation_already_in_flight"
)
CLIENT_REQUEST_ID_PAYLOAD_MISMATCH_CODE = "client_request_id_payload_mismatch"
CLIENT_REQUEST_ID_PAYLOAD_MISMATCH_MESSAGE = (
    "This request id has already been used for a different generation payload."
)


# Generation failures the web app sorts by code (web/lib/generation-failure.ts)
# rather than by wording. The codes live in shared/api-messages.json.
GENERATION_DAILY_LIMIT_REACHED_CODE = shared_code("generation_daily_limit_reached")
GENERATION_RATE_LIMITED_CODE = shared_code("generation_rate_limited")
GENERATION_JOB_NOT_FOUND_CODE = shared_code("generation_job_not_found")
GENERATION_JOB_NOT_RETRYABLE_CODE = shared_code("generation_job_not_retryable")
GENERATION_JOB_HAS_SAVED_PLAN_CODE = shared_code("generation_job_has_saved_plan")
GENERATION_JOB_NOT_CANCELLABLE_CODE = shared_code("generation_job_not_cancellable")


class CodedHTTPException(HTTPException):
    """``HTTPException`` carrying a stable machine-readable ``code``."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        detail: Any,
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


def generation_daily_limit_error(detail: str) -> CodedHTTPException:
    """429 raised when the athlete has used today's generation allowance."""

    return CodedHTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code=GENERATION_DAILY_LIMIT_REACHED_CODE,
        detail=detail,
    )


def generation_rate_limited_error(*, retry_after_seconds: Any) -> CodedHTTPException:
    """429 raised when generation requests arrive faster than the short-window cap."""

    return CodedHTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code=GENERATION_RATE_LIMITED_CODE,
        detail={
            "message": "Too many plan generation requests. Try again shortly.",
            "retry_after_seconds": retry_after_seconds,
        },
    )


def generation_job_not_found_error() -> CodedHTTPException:
    """404 for a generation job that does not exist or belongs to someone else."""

    return CodedHTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        code=GENERATION_JOB_NOT_FOUND_CODE,
        detail="generation job not found",
    )


def generation_job_not_retryable_error() -> CodedHTTPException:
    """409 raised when a retry targets a job that has not failed."""

    return CodedHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        code=GENERATION_JOB_NOT_RETRYABLE_CODE,
        detail="only failed generation jobs can be retried",
    )


def generation_job_has_saved_plan_error() -> CodedHTTPException:
    """409 raised when a retry targets a job whose plan is already saved."""

    return CodedHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        code=GENERATION_JOB_HAS_SAVED_PLAN_CODE,
        detail="generation job already produced a saved plan",
    )


def generation_job_not_cancellable_error(
    detail: str = "only queued or running generation jobs can be cancelled",
) -> CodedHTTPException:
    """409 raised when a cancel targets a job that is no longer queued or running."""

    return CodedHTTPException(
        status_code=status.HTTP_409_CONFLICT,
        code=GENERATION_JOB_NOT_CANCELLABLE_CODE,
        detail=detail,
    )
