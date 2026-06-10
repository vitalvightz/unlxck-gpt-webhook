from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

import httpx
from fastapi import HTTPException, status
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import Client, ClientOptions, create_client

from .auth import AuthenticatedUser
from .errors import client_request_id_payload_mismatch_error, generation_already_in_flight_error
from .environment import is_production_environment
from .error_sanitizer import sanitize_error_text
from .generation_config import generation_job_stale_after_seconds, generation_worker_id
from .generation.payloads import _stable_payload_hash
from .json_limits import (
    MAX_CLIENT_JSON_BYTES,
    MAX_JSON_DEPTH,
    MAX_SERVER_JSON_BYTES,
    validate_json_field,
)
from .models import (
    PlanRequest,
    ProfileUpdateRequest,
    USERNAME_CHANGE_WINDOW_DAYS,
    USERNAME_MAX_CHANGES_PER_WINDOW,
    validate_username,
)
from .schema_requirements import (
    GENERATION_JOB_STAGE2_COST_COLUMNS,
    PLAN_RUNTIME_REQUIRED_COLUMNS,
)
from .state_machine import (
    is_generation_job_status,
    is_plan_status,
    require_generation_job_transition,
    require_plan_transition,
)

logger = logging.getLogger(__name__)


def _guard_persisted_json(
    value: Any,
    *,
    field: str,
    max_bytes: int,
    context: str,
) -> None:
    """Reject oversized/too-deep JSON before it is written to Supabase.

    Defense-in-depth backstop for the Pydantic validators: server-assembled
    payloads (request_payload, stage2_payload) never pass through a request
    model, and some callers bypass the HTTP layer entirely. Raises a generic
    413 without echoing payload contents.
    """

    try:
        validate_json_field(
            value,
            field=field,
            max_bytes=max_bytes,
            max_depth=MAX_JSON_DEPTH,
            exc_factory=ValueError,
        )
    except ValueError as exc:
        logger.warning(
            "[store] payload_too_large field=%s max_bytes=%s %s reason=%s",
            field,
            max_bytes,
            context,
            str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"{field} payload too large",
        ) from None


PLAN_SUMMARY_SELECT = "id, athlete_id, full_name, fight_date, technical_style, plan_name, status, pdf_url, created_at"
GENERATION_JOB_SELECT = "*"
# Admin job-list endpoints render diagnostics that need request_payload and
# final_result but never read stage1_result (the largest intermediate blob,
# the full Stage 1 planner output). Listing many rows with select="*" loads
# every stage1_result into memory at once and was OOM-ing the 512MB instance,
# so admin list queries use this explicit projection that drops stage1_result.
GENERATION_JOB_ADMIN_LIST_SELECT = (
    "id, athlete_id, client_request_id, source, status, attempt_count, "
    "heartbeat_at, started_at, completed_at, created_at, updated_at, error, "
    "intake_id, plan_id, progress_milestones, request_payload, final_result"
)

_TRANSIENT_SUPABASE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
)
_STORE_CLIENT_ERRORS = (PostgrestAPIError, httpx.HTTPError)


class LastAdminError(RuntimeError):
    """Raised when a revoke would demote the only remaining admin.

    Guards against accidentally locking everyone out of the admin surface.
    Callers that genuinely intend this must pass ``allow_last_admin=True``.
    """
_TRANSIENT_POSTGREST_SNIPPETS = (
    "connection",
    "connect",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "server disconnected",
    "remote end closed",
    "connection reset",
    "connection terminated",
    "upstream",
    "gateway",
    "502",
    "503",
    "504",
)
_GENERATION_JOB_SCHEMA_SNIPPETS = (
    "schema cache",
    "could not find the table",
    "relation",
    "does not exist",
    "column",
    "generation_jobs",
)
_GENERATION_JOB_CONFLICT_SNIPPETS = (
    "23505",
    "duplicate key value violates unique constraint",
    "generation_jobs_athlete_client_request_key",
    "generation_jobs_one_active_job_per_athlete",
)
_GENERATION_JOB_TERMINAL_CONFLICT_SNIPPETS = (
    "wrong_generation_job_status",
    "stale_generation_job_attempt",
    "stale_generation_job_worker",
    "invalid_terminal_status",
)
_GENERATION_JOB_TERMINAL_MISSING_SNIPPETS = (
    "generation_job_missing",
)
PLAN_RUNTIME_SCHEMA_ERROR_DETAIL = (
    "plans table is missing required runtime columns; apply latest Supabase schema and redeploy"
)
GENERATION_JOB_ACTIVE_LOCK_ERROR_DETAIL = (
    "generation job active lock is missing; apply latest Supabase migrations and redeploy"
)
# Canonical source lives in api/schema_requirements.py so the live store and the
# deploy-gate runtime schema checker (tools/check_supabase_runtime_schema.py)
# can never drift apart. Re-exported here to preserve the existing import path.
_PLAN_RUNTIME_REQUIRED_COLUMNS_SET = set(PLAN_RUNTIME_REQUIRED_COLUMNS)
_PLAN_RUNTIME_SCHEMA_ERROR_SNIPPETS = (
    "schema cache",
    "column",
    "does not exist",
    "could not find",
)
_PLAN_SCHEMA_MISMATCH_DETAIL = "plans table schema mismatch; apply latest Supabase schema and redeploy"
_PLAN_INVALID_PAYLOAD_DETAIL = "invalid plans payload for table insert"
_VISIBLE_PLAN_STATUSES = {"ready", "publishable_with_flags"}

def _sanitize_error_text(exc: Exception) -> str:
    return sanitize_error_text(exc)


def _visible_plan_text_for_status(result: dict[str, Any], *, status_value: object | None = None) -> str:
    raw_status = result.get("status") if status_value is None else status_value
    status_text = str(raw_status or "").strip().lower()
    if status_text not in _VISIBLE_PLAN_STATUSES:
        return ""
    return str(
        result.get("plan_text")
        or result.get("final_plan_text")
        or result.get("draft_plan_text")
        or ""
    )


GENERATION_JOB_UNAVAILABLE_DETAIL = "generation job service temporarily unavailable"
GENERATION_JOB_SCHEMA_DETAIL = "generation job store is not ready; apply the latest Supabase schema and redeploy"

_is_production_environment = is_production_environment


def _claim_legacy_blank_status_jobs_enabled() -> bool:
    return os.getenv("UNLXCK_CLAIM_LEGACY_BLANK_STATUS_JOBS", "").strip() == "1"


def _raise_client_request_payload_mismatch_if_known(job: dict[str, Any], payload_hash: str) -> None:
    existing_hash = job.get("payload_hash")
    if existing_hash and existing_hash != payload_hash:
        raise client_request_id_payload_mismatch_error()


class AppStore(Protocol):
    def validate_runtime_schema(self) -> None: ...

    def is_admin_email(self, email: str) -> bool: ...

    def ensure_profile(self, user: AuthenticatedUser) -> dict[str, Any]: ...

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict[str, Any]: ...

    def change_username(self, athlete_id: str, username: str) -> dict[str, Any]: ...

    def get_latest_intake(self, athlete_id: str) -> dict[str, Any] | None: ...
    def get_intake(self, intake_id: str) -> dict[str, Any] | None: ...

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict[str, Any]: ...


    def update_intake(
        self,
        intake_id: str,
        *,
        intake: dict[str, Any],
        fight_date: str | None,
        technical_style: list[str],
    ) -> dict[str, Any]: ...

    def create_plan(
        self,
        *,
        athlete_id: str,
        intake_id: str,
        request: PlanRequest,
        result: dict[str, Any],
    ) -> dict[str, Any]: ...

    def list_user_plans(self, athlete_id: str) -> list[dict[str, Any]]: ...

    def get_plan(self, plan_id: str) -> dict[str, Any] | None: ...

    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict[str, Any] | None: ...

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any] | None: ...

    def rename_plan(self, plan_id: str, plan_name: str) -> dict[str, Any]: ...

    def rename_plan_for_athlete(self, plan_id: str, athlete_id: str, plan_name: str) -> dict[str, Any]: ...

    def archive_plan(self, plan_id: str) -> dict[str, Any]: ...

    def archive_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict[str, Any]: ...

    def delete_plan(self, plan_id: str) -> None: ...

    def delete_plan_for_athlete(self, plan_id: str, athlete_id: str) -> None: ...

    def create_or_get_generation_job(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict[str, Any],
        plan_id: str | None = None,
        intake_id: str | None = None,
        stale_after_seconds: int = 90,
    ) -> dict[str, Any]: ...
    def create_or_get_generation_job_with_daily_limit(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict[str, Any],
        daily_limit: int,
        day_start_iso: str,
        limit_reached_detail: str,
        counted_sources: set[str],
        plan_id: str | None = None,
        intake_id: str | None = None,
        stale_after_seconds: int = 90,
    ) -> dict[str, Any]: ...
    def count_generation_jobs_for_athlete_since(
        self,
        athlete_id: str,
        since_timestamp: str,
        *,
        sources: set[str] | None = None,
    ) -> int: ...
    def check_plan_generation_short_window_limit(
        self,
        athlete_id: str,
        max_requests: int,
        window_seconds: float,
    ) -> tuple[bool, int]: ...

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None: ...
    def recover_generation_job_if_stale(self, job: dict[str, Any] | None) -> dict[str, Any] | None: ...
    def get_generation_job_by_client_request_id(self, *, athlete_id: str, client_request_id: str) -> dict[str, Any] | None: ...
    def get_visible_active_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any] | None: ...
    def get_active_generation_job_for_athlete(
        self,
        athlete_id: str,
        *,
        stale_after_seconds: int | None = None,
    ) -> dict[str, Any] | None: ...
    def get_latest_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any] | None: ...

    def get_generation_job_by_plan_id(self, plan_id: str) -> dict[str, Any] | None: ...
    def has_active_generation_job_for_plan(self, plan_id: str) -> bool: ...
    def list_generation_jobs_for_athlete(self, athlete_id: str, *, limit: int = 10) -> list[dict[str, Any]]: ...
    def list_admin_active_generation_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]: ...
    def list_admin_triage_generation_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]: ...
    def list_orphaned_terminal_generation_jobs(self, *, limit: int = 500) -> list[dict[str, Any]]: ...
    def list_failed_triage_resume_jobs_with_approved_marker(self, *, limit: int = 500) -> list[dict[str, Any]]: ...

    def list_claimable_generation_jobs(self, *, limit: int = 20, stale_after_seconds: int | None = None) -> list[dict[str, Any]]: ...

    def claim_generation_job_start(self, job_id: str, *, stale_after_seconds: int | None = None, worker_id: str | None = None) -> dict[str, Any] | None: ...

    def claim_generation_job(self, job_id: str, *, stale_after_seconds: int | None = None, worker_id: str | None = None) -> dict[str, Any] | None: ...

    def count_active_generation_jobs(self, *, stale_after_seconds: int | None = None) -> int: ...

    def complete_generation_job(
        self,
        job_id: str,
        *,
        expected_attempt_count: int,
        final_status: str,
        final_result: dict[str, Any] | None = None,
        plan_id: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
        heartbeat_at: str | None = None,
        expected_status: str = "running",
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict[str, Any]: ...

    def fail_generation_job(
        self,
        job_id: str,
        *,
        expected_attempt_count: int,
        error: str,
        final_result: dict[str, Any] | None = None,
        plan_id: str | None = None,
        progress_milestones: list[Any] | None = None,
        failed_at: str | None = None,
        heartbeat_at: str | None = None,
        expected_status: str = "running",
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict[str, Any]: ...

    def update_generation_job(self, job_id: str, **changes: Any) -> dict[str, Any]: ...

    def record_stage2_cost(self, job_id: str, metadata: dict[str, Any]) -> None: ...

    def update_plan_stage2(self, plan_id: str, result: dict[str, Any]) -> dict[str, Any]: ...
    def update_plan_triage_approval(self, plan_id: str, *, why_log: dict[str, Any], stage2_status: str) -> dict[str, Any]: ...

    def list_admin_plans(
        self, *, limit: int = 50, offset: int = 0, q: str | None = None
    ) -> list[dict[str, Any]]: ...

    def list_admin_athletes(
        self, *, limit: int = 50, offset: int = 0, q: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_admin_athlete(self, athlete_id: str) -> dict[str, Any] | None: ...

    def clear_onboarding_draft(self, athlete_id: str) -> None: ...


def _encode_structured_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


_ADMIN_SEARCH_RESERVED = re.compile(r'[,()*\\"]+')


def _admin_search_clause(columns: tuple[str, ...], q: str | None) -> str | None:
    """Build a PostgREST ``or()`` expression of case-insensitive ilike matches.

    The raw query is stripped of characters that are structurally significant
    in a PostgREST ``or()`` expression (commas, parentheses, wildcards, quotes,
    backslashes) so a user-supplied search string cannot inject extra
    conditions or break the filter grammar. Returns ``None`` when the sanitized
    term is empty so callers can skip filtering entirely.
    """
    if not q:
        return None
    term = " ".join(_ADMIN_SEARCH_RESERVED.sub(" ", q).split())
    if not term:
        return None
    pattern = f"*{term}*"
    return ",".join(f"{column}.ilike.{pattern}" for column in columns)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _status_transition_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _progress_milestones(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _has_milestone_code(milestones: list[Any], code: str) -> bool:
    for entry in milestones:
        if isinstance(entry, dict) and str(entry.get("code") or "") == code:
            return True
    return False


def _should_recover_stalled_job(job: dict[str, Any]) -> bool:
    if isinstance(job.get("final_result"), dict):
        return True
    if str(job.get("plan_id") or "").strip():
        return True
    milestones = _progress_milestones(job.get("progress_milestones"))
    for entry in milestones:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "")
        if code not in {"final_result_persisted", "plan_saved", "generation_job_terminal_status_persisted"}:
            continue
        meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
        if str(meta.get("plan_id") or "").strip():
            return True
    return False


def _plan_id_from_terminal_milestones(job: dict[str, Any]) -> str | None:
    milestones = _progress_milestones(job.get("progress_milestones"))
    for entry in reversed(milestones):
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "")
        if code not in {"final_result_persisted", "plan_saved", "generation_job_terminal_status_persisted"}:
            continue
        meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
        plan_id = str(meta.get("plan_id") or "").strip()
        if plan_id:
            return plan_id
    return None


def is_pre_start_stale_generation_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    if str(job.get("status") or "") != "running":
        return False
    if _progress_milestones(job.get("progress_milestones")):
        return False
    if job.get("stage1_result") is not None:
        return False
    if job.get("final_result") is not None:
        return False
    if job.get("completed_at") is not None:
        return False

    heartbeat_at = _parse_datetime(job.get("heartbeat_at"))
    started_at = _parse_datetime(job.get("started_at"))
    now = datetime.now(timezone.utc)
    reference_time = heartbeat_at or started_at
    if reference_time is None:
        return False
    return (now - reference_time).total_seconds() >= max(1, stale_after_seconds)


def is_worker_start_stale_generation_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    if str(job.get("status") or "") != "running":
        return False
    if job.get("completed_at") is not None:
        return False
    if job.get("stage1_result") is not None:
        return False
    if job.get("final_result") is not None:
        return False
    milestones = _progress_milestones(job.get("progress_milestones"))
    if len(milestones) != 1:
        return False
    first = milestones[0] if isinstance(milestones[0], dict) else {}
    if str(first.get("code") or "") != "job_loaded":
        return False

    heartbeat_at = _parse_datetime(job.get("heartbeat_at"))
    started_at = _parse_datetime(job.get("started_at"))
    now = datetime.now(timezone.utc)
    reference_time = heartbeat_at or started_at
    if reference_time is None:
        return False
    return (now - reference_time).total_seconds() >= max(1, stale_after_seconds)


def is_job_loaded_stalled_generation_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    if str(job.get("status") or "") != "running":
        return False
    if job.get("completed_at") is not None:
        return False
    if job.get("stage1_result") is not None:
        return False
    if job.get("final_result") is not None:
        return False
    milestones = _progress_milestones(job.get("progress_milestones"))
    if not milestones:
        return False

    saw_job_loaded_at: datetime | None = None
    blocked_codes = {"request_payload_parsed", "profile_update_started", "stage1_planner_starting", "stage1_planner_invoked"}
    for entry in milestones:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "")
        if code in blocked_codes:
            return False
        if code == "job_loaded":
            parsed = _parse_datetime(entry.get("at"))
            saw_job_loaded_at = parsed or saw_job_loaded_at
    if saw_job_loaded_at is None:
        return False
    age = (datetime.now(timezone.utc) - saw_job_loaded_at).total_seconds()
    return age >= max(1, stale_after_seconds)


def is_startup_stale_generation_job(job: dict[str, Any], *, stale_after_seconds: int = 90) -> bool:
    return is_pre_start_stale_generation_job(
        job,
        stale_after_seconds=stale_after_seconds,
    ) or is_worker_start_stale_generation_job(
        job,
        stale_after_seconds=stale_after_seconds,
    )


def is_stage1_planner_stalled_generation_job(job: dict[str, Any], *, stale_after_seconds: int = 180) -> bool:
    if str(job.get("status") or "") != "running":
        return False
    if job.get("completed_at") is not None or job.get("stage1_result") is not None or job.get("final_result") is not None:
        return False
    milestones = _progress_milestones(job.get("progress_milestones"))
    if not milestones:
        return False
    milestone_invoked_at: datetime | None = None
    saw_planner_finished = False
    for entry in milestones:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "")
        if code == "stage1_planner_finished":
            saw_planner_finished = True
        if code == "stage1_planner_invoked":
            milestone_invoked_at = _parse_datetime(entry.get("at")) or milestone_invoked_at
    if saw_planner_finished or milestone_invoked_at is None:
        return False
    age = (datetime.now(timezone.utc) - milestone_invoked_at).total_seconds()
    return age >= max(1, stale_after_seconds)


def _stage1_stale_after_seconds_for_reads() -> int:
    raw_value = os.getenv("STAGE1_PLANNER_TIMEOUT_SECONDS")
    if raw_value is None:
        raw_value = os.getenv("APP_STAGE1_PLANNER_TIMEOUT_SECONDS", "600")
    raw_value = raw_value.strip()
    if raw_value in {"", "0", "none", "None", "NONE"}:
        return 600
    try:
        parsed = float(raw_value)
    except ValueError:
        return 600
    if parsed <= 0:
        return 600
    return max(1, int(parsed))


def _generation_startup_max_attempts() -> int:
    raw_value = os.getenv("APP_GENERATION_STARTUP_MAX_ATTEMPTS", "2").strip()
    try:
        parsed = int(float(raw_value))
    except ValueError:
        return 2
    return max(1, parsed)


def _job_loaded_milestone(now_iso: str) -> dict[str, Any]:
    return {
        "code": "job_loaded",
        "label": "Generation job loaded",
        "detail": "Worker loaded the persisted generation job.",
        "meta": {},
        "at": now_iso,
    }


@dataclass
class SupabaseAppStore:
    client: Client
    admin_emails: set[str]

    @classmethod
    def from_env(cls) -> "SupabaseAppStore":
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        admin_emails = {
            email.strip().lower()
            for email in os.getenv("UNLXCK_ADMIN_EMAILS", "").split(",")
            if email.strip()
        }
        logger.info(
            "[store] initializing supabase store has_url=%s has_service_role_key=%s admin_emails_count=%s",
            bool(url),
            bool(key),
            len(admin_emails),
        )
        # Disable HTTP/2 to avoid RemoteProtocolError (GOAWAY frames) when
        # Supabase terminates a multiplexed connection after several streams.
        # HTTP/1.1 uses a simple request-per-connection model that is immune
        # to this class of failure.
        http_client = httpx.Client(http2=False)
        return cls(create_client(url, key, options=ClientOptions(httpx_client=http_client)), admin_emails)

    def is_admin_email(self, email: str) -> bool:
        if not email:
            return False
        return email.strip().lower() in self.admin_emails

    def _select_first(self, query) -> dict[str, Any] | None:
        response = query.limit(1).execute()
        rows = getattr(response, "data", None) or []
        return rows[0] if rows else None

    def _classify_running_job_staleness(
        self,
        job: dict[str, Any],
        *,
        stale_after_seconds: int,
        stage1_stale_after_seconds: int | None = None,
    ) -> str:
        if str(job.get("status") or "") != "running":
            return "fresh"
        if is_job_loaded_stalled_generation_job(job, stale_after_seconds=stale_after_seconds):
            return "job_loaded_stalled"
        if is_startup_stale_generation_job(job, stale_after_seconds=stale_after_seconds):
            return "startup_stale"
        stage1_threshold = stale_after_seconds if stage1_stale_after_seconds is None else stage1_stale_after_seconds
        if is_stage1_planner_stalled_generation_job(job, stale_after_seconds=stage1_threshold):
            return "stage1_planner_stalled"
        heartbeat_at = _parse_datetime(job.get("heartbeat_at"))
        started_at = _parse_datetime(job.get("started_at"))
        reference_time = heartbeat_at or started_at
        if reference_time is None:
            return "fresh"
        if (datetime.now(timezone.utc) - reference_time).total_seconds() < max(1, stale_after_seconds):
            return "fresh"
        return "mid_pipeline_stale"

    def _log_profile_event(self, *, operation: str, user: AuthenticatedUser, **fields: Any) -> None:
        details = " ".join(f"{key}=%r" % value for key, value in sorted(fields.items()))
        suffix = f" {details}" if details else ""
        logger.info(
            "[store] profile:%s athlete_id=%s%s",
            operation,
            user.user_id,
            suffix,
            extra={
                "athlete_id": user.user_id,
                "auth_event": f"profile_{operation}",
                "status": fields.get("status") or "ok",
            },
        )

    def _is_transient_profile_error(self, exc: Exception) -> bool:
        return self._is_transient_store_error(exc)

    def _is_transient_store_error(self, exc: Exception) -> bool:
        if isinstance(exc, _TRANSIENT_SUPABASE_ERRORS):
            return True
        if isinstance(exc, PostgrestAPIError):
            text = " ".join(
                str(part)
                for part in (exc.code, exc.message, exc.hint, exc.details)
                if part
            ).lower()
            return any(snippet in text for snippet in _TRANSIENT_POSTGREST_SNIPPETS)
        return False

    def _is_generation_job_schema_error(self, exc: Exception) -> bool:
        if not isinstance(exc, PostgrestAPIError):
            return False
        text = " ".join(
            str(part)
            for part in (exc.code, exc.message, exc.hint, exc.details)
            if part
        ).lower()
        has_generation_job_context = "generation_jobs" in text
        has_schema_mismatch_signal = any(snippet in text for snippet in _GENERATION_JOB_SCHEMA_SNIPPETS)
        return has_generation_job_context and has_schema_mismatch_signal

    def _is_generation_job_conflict_error(self, exc: Exception) -> bool:
        if not isinstance(exc, PostgrestAPIError):
            return False
        text = " ".join(
            str(part)
            for part in (exc.code, exc.message, exc.hint, exc.details)
            if part
        ).lower()
        return any(snippet in text for snippet in _GENERATION_JOB_CONFLICT_SNIPPETS)

    def _is_generation_job_terminal_conflict_error(self, exc: Exception) -> bool:
        if not isinstance(exc, PostgrestAPIError):
            return False
        text = " ".join(
            str(part)
            for part in (exc.code, exc.message, exc.hint, exc.details)
            if part
        ).lower()
        return any(snippet in text for snippet in _GENERATION_JOB_TERMINAL_CONFLICT_SNIPPETS)

    def _is_generation_job_terminal_missing_error(self, exc: Exception) -> bool:
        if not isinstance(exc, PostgrestAPIError):
            return False
        text = " ".join(
            str(part)
            for part in (exc.code, exc.message, exc.hint, exc.details)
            if part
        ).lower()
        return any(snippet in text for snippet in _GENERATION_JOB_TERMINAL_MISSING_SNIPPETS)

    def _is_plan_schema_column_error(self, exc: Exception) -> bool:
        if not isinstance(exc, PostgrestAPIError):
            return False
        text = " ".join(
            str(part)
            for part in (exc.code, exc.message, exc.hint, exc.details)
            if part
        ).lower()
        if "plans" not in text:
            return False
        if not any(snippet in text for snippet in _PLAN_RUNTIME_SCHEMA_ERROR_SNIPPETS):
            return False
        return any(column in text for column in _PLAN_RUNTIME_REQUIRED_COLUMNS_SET)

    def _legacy_plan_schema_fallback_enabled(self) -> bool:
        flag_set = os.getenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "").strip() == "1"
        if not flag_set:
            return False
        if _is_production_environment():
            logger.error(
                "[store] legacy_plan_schema_fallback:blocked_in_production "
                "UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK is ignored in production; "
                "apply the latest Supabase schema and redeploy"
            )
            return False
        logger.warning(
            "[store] Legacy plan schema fallback is enabled. Runtime columns may be "
            "dropped. Do not use in production."
        )
        return True

    def _log_create_plan_postgrest_error(
        self,
        *,
        athlete_id: str,
        intake_id: str,
        payload: dict[str, Any],
        exc: PostgrestAPIError,
    ) -> None:
        logger.error(
            "[store] create_plan:postgrest_error athlete_id=%s intake_id=%s error_type=%s code=%s message=%s details=%s hint=%s payload_keys=%s",
            athlete_id,
            intake_id,
            type(exc).__name__,
            getattr(exc, "code", None),
            getattr(exc, "message", None),
            getattr(exc, "details", None),
            getattr(exc, "hint", None),
            sorted(payload.keys()),
        )

    def _create_plan_error_detail(self, exc: PostgrestAPIError) -> str:
        message = str(getattr(exc, "message", "") or "").lower()
        details = str(getattr(exc, "details", "") or "").lower()
        hint = str(getattr(exc, "hint", "") or "").lower()
        code = str(getattr(exc, "code", "") or "").lower()
        text = " ".join(part for part in (message, details, hint, code) if part)
        if "could not find the" in text and "column" in text and "plans" in text:
            return "missing plans column; apply latest Supabase schema and redeploy"
        if "invalid input" in text or "invalid json" in text or code in {"22p02", "22023"}:
            return _PLAN_INVALID_PAYLOAD_DETAIL
        if "plans" in text and any(snippet in text for snippet in _PLAN_RUNTIME_SCHEMA_ERROR_SNIPPETS):
            return _PLAN_SCHEMA_MISMATCH_DETAIL
        return "plan persistence failed"

    def _validate_generation_job_active_lock(self) -> None:
        try:
            response = self.client.rpc("validate_generation_job_active_lock").execute()
        except _STORE_CLIENT_ERRORS as exc:
            logger.exception("[store] validate_runtime_schema:active_job_lock_check_failed")
            raise RuntimeError(GENERATION_JOB_ACTIVE_LOCK_ERROR_DETAIL) from exc

        lock_present = bool(response.data)

        if not lock_present:
            logger.error("[store] validate_runtime_schema:active_job_lock_missing")
            raise RuntimeError(GENERATION_JOB_ACTIVE_LOCK_ERROR_DETAIL)

    def validate_runtime_schema(self) -> None:
        legacy_fallback_enabled = self._legacy_plan_schema_fallback_enabled()
        logger.info(
            "[store] validate_runtime_schema:start legacy_fallback_enabled=%s",
            legacy_fallback_enabled,
        )
        try:
            (
                self.client.table("plans")
                .select(",".join(PLAN_RUNTIME_REQUIRED_COLUMNS))
                .limit(1)
                .execute()
            )
        except PostgrestAPIError as exc:
            if not self._is_plan_schema_column_error(exc):
                raise
            if legacy_fallback_enabled:
                logger.warning(
                    "[store] validate_runtime_schema:legacy_fallback_enabled; continuing despite schema mismatch"
                )
            else:
                logger.exception("[store] validate_runtime_schema:schema_mismatch")
                raise RuntimeError(PLAN_RUNTIME_SCHEMA_ERROR_DETAIL) from exc

        self._validate_generation_job_active_lock()
        logger.info("[store] validate_runtime_schema:ok")

    def _raise_operation_http_error(
        self,
        *,
        operation: str,
        detail: str,
        exc: Exception,
    ) -> None:
        if self._is_transient_store_error(exc):
            logger.warning(
                "[store] %s:transient_failure error_type=%s",
                operation,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="store service temporarily unavailable",
            ) from exc
        logger.exception("[store] %s:exception", operation)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        ) from exc

    def _run_with_transient_retry(
        self,
        *,
        operation: str,
        fn: Callable[[], Any],
        attempts: int = 3,
        backoff_seconds: float = 0.25,
    ) -> Any:
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except _STORE_CLIENT_ERRORS as exc:
                transient = self._is_transient_store_error(exc)
                logger.warning(
                    "[store] %s:failure attempt=%s transient=%s error_type=%s error=%s",
                    operation,
                    attempt,
                    transient,
                    type(exc).__name__,
                    exc,
                )
                if not transient or attempt >= attempts:
                    raise
                time.sleep(backoff_seconds * attempt)

        raise RuntimeError(f"{operation} exhausted retries")

    def _lookup_generation_job_by_client_request_id(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
    ) -> dict[str, Any] | None:
        return self._select_first(
            self.client.table("generation_jobs")
            .select(GENERATION_JOB_SELECT)
            .eq("athlete_id", athlete_id)
            .eq("client_request_id", client_request_id)
            .order("created_at", desc=True)
        )

    def _read_generation_job(self, job_id: str) -> dict[str, Any] | None:
        return self._select_first(
            self.client.table("generation_jobs").select(GENERATION_JOB_SELECT).eq("id", job_id)
        )

    def _get_profile_by_id(self, athlete_id: str) -> dict[str, Any] | None:
        return self._select_first(self.client.table("profiles").select("*").eq("id", athlete_id))

    def _build_profile_payload(
        self,
        *,
        user: AuthenticatedUser,
        existing: dict[str, Any] | None,
    ) -> dict[str, Any]:
        existing = existing or {}
        return {
            "id": user.user_id,
            "email": user.email,
            "username": existing.get("username"),
            "username_change_history": existing.get("username_change_history") or [],
            "full_name": existing.get("full_name") or user.full_name,
            "role": existing.get("role") or self._default_role_for(user),
            "technical_style": existing.get("technical_style") or [],
            "tactical_style": existing.get("tactical_style") or [],
            "stance": existing.get("stance") or "",
            "professional_status": existing.get("professional_status") or "",
            "record_summary": existing.get("record_summary") or "",
            "athlete_timezone": existing.get("athlete_timezone") or "",
            "athlete_locale": existing.get("athlete_locale") or "",
            "appearance_mode": existing.get("appearance_mode") or "dark",
            "onboarding_draft": existing.get("onboarding_draft"),
            "avatar_url": existing.get("avatar_url"),
        }

    def _upsert_profile_with_retry(
        self,
        *,
        user: AuthenticatedUser,
        payload: dict[str, Any],
        attempts: int = 3,
        backoff_seconds: float = 0.25,
    ) -> None:
        for attempt in range(1, attempts + 1):
            try:
                self._log_profile_event(operation="upsert_attempt", user=user, attempt=attempt)
                self.client.table("profiles").upsert(payload, on_conflict="id").execute()
                self._log_profile_event(operation="upsert_success", user=user, attempt=attempt)
                return
            except _STORE_CLIENT_ERRORS as exc:
                transient = self._is_transient_profile_error(exc)
                logger.warning(
                    "[store] profile:upsert_failure athlete_id=%s attempt=%s transient=%s error_type=%s error=%s error_code=%s",
                    user.user_id,
                    attempt,
                    transient,
                    type(exc).__name__,
                    _sanitize_error_text(exc),
                    "profile_upsert_failure",
                    extra={
                        "athlete_id": user.user_id,
                        "auth_event": "profile_upsert_failure",
                        "status": "failure",
                        "error_code": "profile_upsert_failure",
                    },
                )
                if not transient or attempt >= attempts:
                    raise
                time.sleep(backoff_seconds * attempt)

    def _require_profile(self, athlete_id: str) -> dict[str, Any]:
        profile = self._get_profile_by_id(athlete_id)
        if not profile:
            logger.warning("[store] profile not found athlete_id=%s", athlete_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
        return profile

    def _default_role_for(self, user: AuthenticatedUser) -> str:
        if user.email.lower() in self.admin_emails:
            return "admin"
        return "athlete"

    def ensure_profile(self, user: AuthenticatedUser) -> dict[str, Any]:
        try:
            self._log_profile_event(operation="ensure_start", user=user)
            existing = None
            _last_read_exc: Exception | None = None
            for _attempt in range(2):
                try:
                    existing = self._get_profile_by_id(user.user_id)
                    _last_read_exc = None
                    break
                except _TRANSIENT_SUPABASE_ERRORS as exc:
                    _last_read_exc = exc
                    logger.warning(
                        "[store] ensure_profile:transient_read_error attempt=%d athlete_id=%s error_type=%s",
                        _attempt,
                        user.user_id,
                        type(exc).__name__,
                    )
                    time.sleep(0.5)
            if _last_read_exc is not None:
                raise _last_read_exc
            if existing:
                self._log_profile_event(
                    operation="ensure_existing",
                    user=user,
                    role=existing.get("role"),
                )
                return existing

            payload = self._build_profile_payload(user=user, existing=None)
            try:
                self._upsert_profile_with_retry(user=user, payload=payload)
            except _STORE_CLIENT_ERRORS as exc:
                logger.exception(
                    "[store] profile:ensure_upsert_exception athlete_id=%s error_type=%s error_code=%s",
                    user.user_id,
                    type(exc).__name__,
                    "profile_ensure_upsert_exception",
                    extra={
                        "athlete_id": user.user_id,
                        "auth_event": "profile_ensure_upsert_exception",
                        "status": "failure",
                        "error_code": "profile_ensure_upsert_exception",
                    },
                )
                fallback = self._get_profile_by_id(user.user_id)
                if fallback:
                    self._log_profile_event(operation="ensure_fallback_read_success", user=user)
                    return fallback
                if self._is_transient_profile_error(exc):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="profile service temporarily unavailable",
                    ) from exc
                raise

            profile = self._require_profile(user.user_id)
            self._log_profile_event(operation="ensure_created", user=user, role=profile.get("role"))
            return profile
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            logger.exception(
                "[store] ensure_profile:exception athlete_id=%s error_type=%s error_code=%s",
                user.user_id,
                type(exc).__name__,
                "ensure_profile_exception",
                extra={
                    "athlete_id": user.user_id,
                    "auth_event": "ensure_profile_exception",
                    "status": "failure",
                    "error_code": "ensure_profile_exception",
                },
            )
            if isinstance(exc, _TRANSIENT_SUPABASE_ERRORS):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="profile service temporarily unavailable",
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to ensure profile",
            ) from exc

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict[str, Any]:
        try:
            fields = update.model_dump(mode="json", exclude_none=True)
            if "record" in fields:
                fields["record_summary"] = fields.pop("record")
            for json_field in ("onboarding_draft", "nutrition_profile"):
                if json_field in fields:
                    _guard_persisted_json(
                        fields[json_field],
                        field=json_field,
                        max_bytes=MAX_CLIENT_JSON_BYTES,
                        context=f"athlete_id={athlete_id}",
                    )
            if not fields:
                logger.info("[store] update_profile:no_fields athlete_id=%s", athlete_id)
                return self._require_profile(athlete_id)

            logger.info("[store] update_profile:start athlete_id=%s fields=%s", athlete_id, sorted(fields.keys()))
            self.client.table("profiles").update(fields).eq("id", athlete_id).execute()
            profile = self._require_profile(athlete_id)
            logger.info("[store] update_profile:success athlete_id=%s", athlete_id)
            return profile
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"update_profile athlete_id={athlete_id}",
                detail="failed to update profile",
                exc=exc,
            )

    # ------------------------------------------------------------------
    # Admin role management
    #
    # UNLXCK_ADMIN_EMAILS only *seeds* a profile's role the first time the
    # profile is created (see _default_role_for). After that, profiles.role is
    # authoritative and the env var has no further effect — so removing an email
    # from UNLXCK_ADMIN_EMAILS does NOT demote an existing admin. Grants and
    # revocations after first sign-in must go through here, which updates
    # profiles.role and records the change in public.admin_role_audit. The
    # service-role key bypasses the prevent_self_role_escalation trigger, so the
    # backend is the only sanctioned path for role changes.
    # ------------------------------------------------------------------

    def _get_profile_by_email(self, email: str) -> dict[str, Any] | None:
        normalized = (email or "").strip().lower()
        if not normalized:
            return None
        # Fast path: the indexed unique column, which is lowercase for any
        # profile created after email normalization landed.
        row = self._select_first(
            self.client.table("profiles").select("*").eq("email", normalized)
        )
        if row:
            return row
        # Fallback for legacy rows stored with mixed-case emails. ilike is
        # case-insensitive; `_`/`%` in a local part are treated as wildcards, so
        # the result is a superset that we narrow with an exact lowercase match.
        response = (
            self.client.table("profiles").select("*").ilike("email", normalized).execute()
        )
        for candidate in getattr(response, "data", None) or []:
            if str(candidate.get("email") or "").strip().lower() == normalized:
                return candidate
        return None

    def list_admin_profiles(self) -> list[dict[str, Any]]:
        response = self._run_with_transient_retry(
            operation="list_admin_profiles",
            fn=lambda: (
                self.client.table("profiles")
                .select("id,email,role")
                .eq("role", "admin")
                .execute()
            ),
        )
        return list(getattr(response, "data", None) or [])

    def count_admin_profiles(self) -> int:
        return len(self.list_admin_profiles())

    def set_profile_role(
        self,
        *,
        email: str,
        new_role: str,
        actor: str,
        reason: str | None = None,
        allow_last_admin: bool = False,
    ) -> dict[str, Any]:
        """Grant or revoke admin by email; records an audit row on any change.

        Returns a summary dict with ``changed=False`` when the profile is
        already in the requested role (no write, no audit row). Raises
        ``ValueError`` for an unsupported role, ``LookupError`` when no profile
        matches the email, ``LastAdminError`` when revoking would leave zero
        admins (unless ``allow_last_admin=True``), and ``RuntimeError`` when
        the atomic role+audit transaction fails — in that case neither the
        role change nor the audit row was committed.
        """
        normalized_role = (new_role or "").strip().lower()
        if normalized_role not in {"admin", "athlete"}:
            raise ValueError(f"unsupported role {new_role!r}; expected 'admin' or 'athlete'")
        profile = self._get_profile_by_email(email)
        if not profile:
            raise LookupError(f"no profile found for email {email!r}")

        athlete_id = str(profile["id"])
        previous_role = str(profile.get("role") or "athlete")
        target_email = str(profile.get("email") or email).strip().lower()
        summary = {
            "athlete_id": athlete_id,
            "email": target_email,
            "previous_role": previous_role,
            "new_role": normalized_role,
        }
        if previous_role == normalized_role:
            logger.info(
                "[admin] role:unchanged email=%s role=%s actor=%s",
                target_email, normalized_role, actor,
            )
            return {**summary, "changed": False}

        # Lockout guard: refuse to demote the only remaining admin unless the
        # caller explicitly opts in.
        if previous_role == "admin" and normalized_role != "admin" and not allow_last_admin:
            if self.count_admin_profiles() <= 1:
                raise LastAdminError(
                    f"refusing to revoke {target_email}: they are the only admin. "
                    "Pass allow_last_admin=True to override."
                )

        # Atomic RPC: the role update and the audit insert commit in one
        # database transaction, so a role change can never land without its
        # audit record (and vice versa). The expected previous role is
        # CAS-checked against the locked row so a concurrent change cannot
        # produce a misleading audit trail.
        action = "promote" if normalized_role == "admin" else "revoke"
        try:
            self.client.rpc(
                "set_profile_role_with_audit",
                {
                    "p_athlete_id": athlete_id,
                    "p_new_role": normalized_role,
                    "p_actor": actor,
                    "p_expected_previous_role": previous_role,
                    "p_reason": reason,
                    "p_target_email": target_email,
                },
            ).execute()
        except _STORE_CLIENT_ERRORS as exc:
            logger.error(
                "[admin] role:change_rolled_back action=%s email=%s actor=%s error_type=%s error=%s",
                action, target_email, actor, type(exc).__name__, _sanitize_error_text(exc),
            )
            raise RuntimeError(
                f"admin role change for {target_email} was rolled back "
                f"(role and audit write commit together): {_sanitize_error_text(exc)}"
            ) from exc
        logger.warning(
            "[admin] role:changed action=%s email=%s previous_role=%s new_role=%s actor=%s",
            action, target_email, previous_role, normalized_role, actor,
        )
        return {**summary, "changed": True, "action": action}

    def change_username(self, athlete_id: str, username: str) -> dict[str, Any]:
        try:
            profile = self._require_profile(athlete_id)
            current_username = (profile.get("username") or "").strip().lower() or None
            normalized = validate_username(username)

            if normalized == current_username:
                logger.info(
                    "[store] change_username:noop athlete_id=%s username unchanged",
                    athlete_id,
                )
                return profile

            try:
                logger.info("[store] change_username:start athlete_id=%s", athlete_id)
                self.client.rpc(
                    "change_profile_username",
                    {
                        "p_profile_id": athlete_id,
                        "p_username": normalized,
                    },
                ).execute()
            except PostgrestAPIError as exc:
                message = " ".join(
                    str(part).lower()
                    for part in (
                        getattr(exc, "message", None),
                        getattr(exc, "details", None),
                        getattr(exc, "hint", None),
                        getattr(exc, "code", None),
                        str(exc),
                    )
                    if part
                )
                if "duplicate" in message or "23505" in message or "unique" in message:
                    logger.info(
                        "[store] change_username:duplicate athlete_id=%s username=%s",
                        athlete_id,
                        normalized,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="That username is already taken. Pick another.",
                    ) from exc
                if "username_rate_limit_exceeded" in message:
                    next_available: str | None = None
                    rate_limit_text = str(getattr(exc, "message", "") or "")
                    match = re.search(r"username_rate_limit_exceeded:([0-9T:\-+.\sZ]+)", rate_limit_text)
                    if match:
                        next_available = match.group(1).strip()
                    logger.info(
                        "[store] change_username:rate_limited athlete_id=%s",
                        athlete_id,
                    )
                    detail = (
                        f"You can change your username up to {USERNAME_MAX_CHANGES_PER_WINDOW} times "
                        f"every {USERNAME_CHANGE_WINDOW_DAYS} days."
                    )
                    if next_available:
                        detail = f"{detail} Next change available {next_available}."
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=detail,
                    ) from exc
                raise

            profile = self._require_profile(athlete_id)
            logger.info("[store] change_username:success athlete_id=%s", athlete_id)
            return profile
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"change_username athlete_id={athlete_id}",
                detail="failed to change username",
                exc=exc,
            )

    def get_latest_intake(self, athlete_id: str) -> dict[str, Any] | None:
        return self._select_first(
            self.client.table("athlete_intakes")
            .select("*")
            .eq("athlete_id", athlete_id)
            .order("created_at", desc=True)
        )

    def get_intake(self, intake_id: str) -> dict[str, Any] | None:
        return self._select_first(self.client.table("athlete_intakes").select("*").eq("id", intake_id))

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict[str, Any]:
        payload = {
            "athlete_id": athlete_id,
            "fight_date": None if request.no_scheduled_fight else (request.fight_date.strip() or None),
            "technical_style": request.athlete.technical_style,
            "intake": request.model_dump(mode="json"),
        }
        try:
            logger.info(
                "[store] create_intake:start athlete_id=%s fight_date=%s technical_style=%s",
                athlete_id,
                request.fight_date,
                request.athlete.technical_style,
            )
            response = self.client.table("athlete_intakes").insert(payload).execute()
            rows = getattr(response, "data", None) or []
            if not rows:
                logger.error(
                    "[store] create_intake:no_rows athlete_id=%s response=%r",
                    athlete_id,
                    response,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="failed to persist intake",
                )
            logger.info(
                "[store] create_intake:success athlete_id=%s intake_id=%s",
                athlete_id,
                rows[0].get("id"),
            )
            return rows[0]
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            logger.exception("[store] create_intake:exception athlete_id=%s", athlete_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="create_intake failed",
            ) from exc

    def update_intake(
        self,
        intake_id: str,
        *,
        intake: dict[str, Any],
        fight_date: str | None,
        technical_style: list[str],
    ) -> dict[str, Any]:
        payload = {
            "intake": intake,
            "fight_date": (fight_date or "").strip() or None,
            "technical_style": technical_style,
        }
        try:
            response = self.client.table("athlete_intakes").update(payload).eq("id", intake_id).execute()
            rows = getattr(response, "data", None) or []
            if not rows:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="intake not found")
            return rows[0]
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"update_intake intake_id={intake_id}",
                detail="failed to update intake",
                exc=exc,
            )

    def create_plan(
        self,
        *,
        athlete_id: str,
        intake_id: str,
        request: PlanRequest,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        result_status = str(result.get("status") or "generated").strip().lower()
        if not is_plan_status(result_status):
            raise _status_transition_error(f"unknown plan status: {result_status!r}")
        visible_plan_text = _visible_plan_text_for_status(result, status_value=result_status)
        payload = {
            "athlete_id": athlete_id,
            "intake_id": intake_id,
            "fight_date": request.fight_date.strip() or None,
            "technical_style": request.athlete.technical_style,
            "full_name": request.athlete.full_name,
            "plan_name": "",
            "status": result_status,
            "plan_text": visible_plan_text,
            "draft_plan_text": result.get("draft_plan_text", result.get("plan_text", "")),
            "final_plan_text": result.get("final_plan_text", result.get("plan_text", "")),
            "coach_notes": result.get("coach_notes", ""),
            "pdf_url": result.get("pdf_url"),
            "why_log": result.get("why_log", {}),
            "planning_brief": _encode_structured_text(result.get("planning_brief")),
            "stage2_payload": result.get("stage2_payload"),
            "stage2_handoff_text": result.get("stage2_handoff_text", ""),
            "stage2_retry_text": result.get("stage2_retry_text", ""),
            "stage2_validator_report": result.get("stage2_validator_report", {}),
            "stage2_status": result.get("stage2_status", ""),
            "stage2_attempt_count": result.get("stage2_attempt_count", 0),
            "parsing_metadata": result.get("parsing_metadata"),
        }

        _guard_persisted_json(
            payload.get("stage2_payload"),
            field="stage2_payload",
            max_bytes=MAX_SERVER_JSON_BYTES,
            context=f"athlete_id={athlete_id} intake_id={intake_id}",
        )

        def _insert_plan(insert_payload: dict[str, Any]) -> dict[str, Any]:
            response = self.client.table("plans").insert(insert_payload).execute()
            rows = getattr(response, "data", None) or []
            if not rows:
                logger.error(
                    "[store] create_plan:no_rows athlete_id=%s intake_id=%s response_type=%s response_repr=%r",
                    athlete_id,
                    intake_id,
                    type(response).__name__,
                    response,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="failed to persist plan",
                )
            return rows[0]

        try:
            logger.info(
                "[store] create_plan:start athlete_id=%s intake_id=%s status=%s stage2_status=%s",
                athlete_id,
                intake_id,
                payload["status"],
                payload["stage2_status"],
            )
            try:
                row = _insert_plan(payload)
            except PostgrestAPIError as exc:
                if not self._is_plan_schema_column_error(exc):
                    raise
                if not self._legacy_plan_schema_fallback_enabled():
                    logger.exception(
                        "[store] create_plan:schema_mismatch athlete_id=%s intake_id=%s",
                        athlete_id,
                        intake_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=PLAN_RUNTIME_SCHEMA_ERROR_DETAIL,
                    ) from exc
                compatibility_payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in _PLAN_RUNTIME_REQUIRED_COLUMNS_SET
                }
                logger.warning(
                    "[store] create_plan:legacy_schema_fallback athlete_id=%s intake_id=%s dropped_columns=%s",
                    athlete_id,
                    intake_id,
                    sorted(_PLAN_RUNTIME_REQUIRED_COLUMNS_SET),
                )
                row = _insert_plan(compatibility_payload)
            logger.info(
                "[store] create_plan:success athlete_id=%s intake_id=%s plan_id=%s",
                athlete_id,
                intake_id,
                row.get("id"),
            )
            return row
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            if isinstance(exc, PostgrestAPIError):
                self._log_create_plan_postgrest_error(
                    athlete_id=athlete_id,
                    intake_id=intake_id,
                    payload=payload,
                    exc=exc,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=self._create_plan_error_detail(exc),
                ) from exc
            logger.exception("[store] create_plan:exception athlete_id=%s intake_id=%s", athlete_id, intake_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="plan persistence failed",
            ) from exc

    def list_user_plans(self, athlete_id: str) -> list[dict[str, Any]]:
        try:
            response = self._run_with_transient_retry(
                operation="list_user_plans",
                fn=lambda: (
                    self.client.table("plans")
                    .select(PLAN_SUMMARY_SELECT)
                    .eq("athlete_id", athlete_id)
                    .order("created_at", desc=True)
                    .execute()
                ),
            )
            return getattr(response, "data", None) or []
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation="list_user_plans",
                detail="failed to list plans",
                exc=exc,
            )

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        try:
            return self._run_with_transient_retry(
                operation=f"get_plan plan_id={plan_id}",
                fn=lambda: self._select_first(self.client.table("plans").select("*").eq("id", plan_id)),
            )
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"get_plan plan_id={plan_id}",
                detail="failed to read plan",
                exc=exc,
            )

    def get_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict[str, Any] | None:
        """Read a plan scoped to its owner.

        Scoping the query by both ``id`` and ``athlete_id`` means a plan owned by
        another athlete is indistinguishable from a missing one (returns
        ``None``), so callers cannot accidentally leak or mutate it.
        """
        try:
            return self._run_with_transient_retry(
                operation=f"get_plan_for_athlete plan_id={plan_id} athlete_id={athlete_id}",
                fn=lambda: self._select_first(
                    self.client.table("plans")
                    .select("*")
                    .eq("id", plan_id)
                    .eq("athlete_id", athlete_id)
                ),
            )
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"get_plan_for_athlete plan_id={plan_id} athlete_id={athlete_id}",
                detail="failed to read plan",
                exc=exc,
            )

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any] | None:
        try:
            return self._run_with_transient_retry(
                operation=f"get_latest_plan athlete_id={athlete_id}",
                fn=lambda: self._select_first(
                    self.client.table("plans")
                    .select("*")
                    .eq("athlete_id", athlete_id)
                    .order("created_at", desc=True)
                ),
            )
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"get_latest_plan athlete_id={athlete_id}",
                detail="failed to read latest plan",
                exc=exc,
            )

    def create_or_get_generation_job(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict[str, Any],
        plan_id: str | None = None,
        intake_id: str | None = None,
        stale_after_seconds: int = 90,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        _guard_persisted_json(
            request_payload,
            field="request_payload",
            max_bytes=MAX_SERVER_JSON_BYTES,
            context=f"athlete_id={athlete_id} client_request_id={client_request_id}",
        )
        payload_hash = _stable_payload_hash(request_payload)

        try:
            existing = self._run_with_transient_retry(
                operation="create_or_get_generation_job:lookup_existing",
                fn=lambda: self._lookup_generation_job_by_client_request_id(
                    athlete_id=athlete_id,
                    client_request_id=client_request_id,
                ),
            )
        except _STORE_CLIENT_ERRORS as exc:
            if not self._is_transient_store_error(exc):
                if self._is_generation_job_schema_error(exc):
                    logger.exception(
                        "[store] create_or_get_generation_job:schema_mismatch athlete_id=%s client_request_id=%s",
                        athlete_id,
                        client_request_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=GENERATION_JOB_SCHEMA_DETAIL,
                    ) from exc
                logger.exception(
                    "[store] create_or_get_generation_job:lookup_exception athlete_id=%s client_request_id=%s",
                    athlete_id,
                    client_request_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="failed to read generation job",
                ) from exc
            last_error = exc
            existing = None
        if existing:
            _raise_client_request_payload_mismatch_if_known(existing, payload_hash)
            if is_startup_stale_generation_job(existing, stale_after_seconds=stale_after_seconds):
                reset_payload = {
                    "status": "queued",
                    "source": (source or "").strip() or "self_serve",
                    "request_payload": request_payload,
                    "payload_hash": payload_hash,
                    "error": None,
                    "heartbeat_at": None,
                    "started_at": None,
                    "completed_at": None,
                    "stage1_result": None,
                    "final_result": None,
                    "progress_milestones": [],
                    # Back to the queue means back to unowned; the next claim
                    # records the new owner.
                    "claimed_by": None,
                    "claimed_at": None,
                }

                if plan_id is not None:
                    reset_payload["plan_id"] = plan_id
                if intake_id is not None:
                    reset_payload["intake_id"] = intake_id

                self._run_with_transient_retry(
                    operation="create_or_get_generation_job:reset_startup_stale",
                    fn=lambda: self.client.table("generation_jobs")
                    .update(reset_payload)
                    .eq("id", str(existing["id"]))
                    .eq("status", "running")
                    .execute(),
                )
                refreshed = self.get_generation_job(str(existing["id"]))
                if refreshed:
                    return refreshed
            return existing
        active_job = self.get_active_generation_job_for_athlete(
            athlete_id,
            stale_after_seconds=stale_after_seconds,
        )
        if active_job and str(active_job.get("status") or "") in {"queued", "running"}:
            if str(active_job.get("client_request_id") or "") == client_request_id:
                _raise_client_request_payload_mismatch_if_known(active_job, payload_hash)
                return active_job
            raise generation_already_in_flight_error()

        payload = {
            "athlete_id": athlete_id,
            "client_request_id": client_request_id,
            "source": (source or "").strip() or "self_serve",
            "request_payload": request_payload,
            "payload_hash": payload_hash,
            "status": "queued",
            "attempt_count": 0,
            "heartbeat_at": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "intake_id": intake_id,
            "stage1_result": None,
            "final_result": None,
            "plan_id": plan_id,
        }
        try:
            response = self._run_with_transient_retry(
                operation="create_or_get_generation_job:insert",
                fn=lambda: self.client.table("generation_jobs").insert(payload).execute(),
            )
            rows = getattr(response, "data", None) or []
            if rows:
                return rows[0]
        except _STORE_CLIENT_ERRORS as exc:
            last_error = exc
            if self._is_generation_job_conflict_error(exc):
                logger.info(
                    "[store] create_or_get_generation_job:insert_conflict athlete_id=%s client_request_id=%s",
                    athlete_id,
                    client_request_id,
                )
            else:
                logger.exception(
                    "[store] create_or_get_generation_job:insert_exception athlete_id=%s client_request_id=%s",
                    athlete_id,
                    client_request_id,
                )

        try:
            existing = self._run_with_transient_retry(
                operation="create_or_get_generation_job:lookup_after_insert",
                fn=lambda: self._lookup_generation_job_by_client_request_id(
                    athlete_id=athlete_id,
                    client_request_id=client_request_id,
                ),
            )
        except _STORE_CLIENT_ERRORS as exc:
            if not self._is_transient_store_error(exc):
                if self._is_generation_job_schema_error(exc):
                    logger.exception(
                        "[store] create_or_get_generation_job:schema_mismatch_after_insert athlete_id=%s client_request_id=%s",
                        athlete_id,
                        client_request_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=GENERATION_JOB_SCHEMA_DETAIL,
                    ) from exc
                logger.exception(
                    "[store] create_or_get_generation_job:lookup_after_insert_exception athlete_id=%s client_request_id=%s",
                    athlete_id,
                    client_request_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="failed to read generation job",
                ) from exc
            last_error = exc
            existing = None
        if existing:
            _raise_client_request_payload_mismatch_if_known(existing, payload_hash)
            return existing
        active_job = self.get_active_generation_job_for_athlete(
            athlete_id,
            stale_after_seconds=stale_after_seconds,
        )
        if active_job and str(active_job.get("status") or "") in {"queued", "running"}:
            if str(active_job.get("client_request_id") or "") == client_request_id:
                _raise_client_request_payload_mismatch_if_known(active_job, payload_hash)
                return active_job
            raise generation_already_in_flight_error()
        if last_error and self._is_transient_store_error(last_error):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
            ) from last_error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to persist generation job",
        )

    def create_or_get_generation_job_with_daily_limit(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict[str, Any],
        daily_limit: int,
        day_start_iso: str,
        limit_reached_detail: str,
        counted_sources: set[str],
        plan_id: str | None = None,
        intake_id: str | None = None,
        stale_after_seconds: int = 90,
    ) -> dict[str, Any]:
        if daily_limit <= 0:
            return self.create_or_get_generation_job(
                athlete_id=athlete_id,
                client_request_id=client_request_id,
                source=source,
                request_payload=request_payload,
                plan_id=plan_id,
                intake_id=intake_id,
                stale_after_seconds=stale_after_seconds,
            )

        _guard_persisted_json(
            request_payload,
            field="request_payload",
            max_bytes=MAX_SERVER_JSON_BYTES,
            context=f"athlete_id={athlete_id} client_request_id={client_request_id}",
        )
        payload_hash = _stable_payload_hash(request_payload)

        # Recover stale `running` jobs before the atomic RPC runs. The RPC's
        # in-flight guard checks `status in ('queued', 'running')` purely at the
        # SQL level and has no staleness awareness, so without this a stale
        # `running` row left by a crashed worker would raise
        # `generation_job_in_flight` and permanently block new generation
        # requests. This mirrors the recovery that create_or_get_generation_job
        # performs via get_active_generation_job_for_athlete; the requeue/fail
        # mutations land before the RPC re-checks in-flight state atomically.
        self.get_active_generation_job_for_athlete(
            athlete_id,
            stale_after_seconds=stale_after_seconds,
        )

        try:
            response = self._run_with_transient_retry(
                operation=f"create_or_get_generation_job_with_daily_limit athlete_id={athlete_id}",
                fn=lambda: self.client.rpc(
                    "create_generation_job_with_daily_limit",
                    {
                        "p_athlete_id": athlete_id,
                        "p_client_request_id": client_request_id,
                        "p_source": source,
                        "p_request_payload": request_payload,
                        "p_payload_hash": payload_hash,
                        "p_daily_limit": daily_limit,
                        "p_day_start": day_start_iso,
                        "p_counted_sources": sorted(counted_sources),
                        "p_plan_id": plan_id,
                        "p_intake_id": intake_id,
                    },
                ).execute(),
            )
        except _STORE_CLIENT_ERRORS as exc:
            error_text = _sanitize_error_text(exc)
            if "generation_job_in_flight" in error_text:
                raise generation_already_in_flight_error() from exc
            if self._is_generation_job_schema_error(exc):
                logger.exception(
                    "[store] create_or_get_generation_job_with_daily_limit:schema_mismatch athlete_id=%s client_request_id=%s",
                    athlete_id,
                    client_request_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            if self._is_generation_job_conflict_error(exc):
                raise generation_already_in_flight_error() from exc
            self._raise_operation_http_error(
                operation=f"create_or_get_generation_job_with_daily_limit athlete_id={athlete_id}",
                detail="failed to persist generation job",
                exc=exc,
            )

        payload = getattr(response, "data", None)
        if isinstance(payload, list):
            payload = payload[0] if payload else {}
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="invalid daily generation limit response",
            )
        if payload.get("limit_exceeded") is True:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=limit_reached_detail,
            )
        job = payload.get("job")
        if not isinstance(job, dict):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="invalid daily generation limit response",
            )
        _raise_client_request_payload_mismatch_if_known(job, payload_hash)
        return job

    def count_generation_jobs_for_athlete_since(
        self,
        athlete_id: str,
        since_timestamp: str,
        *,
        sources: set[str] | None = None,
    ) -> int:
        try:
            query = self.client.table("generation_jobs").select("id", count="exact").eq("athlete_id", athlete_id).gte("created_at", since_timestamp).limit(0)
            if sources:
                query = query.in_("source", sorted(sources))
            response = self._run_with_transient_retry(
                operation=f"count_generation_jobs_for_athlete_since athlete_id={athlete_id}",
                fn=lambda: query.execute(),
            )
            count = getattr(response, "count", None)
            return int(count or 0)
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_generation_job_schema_error(exc):
                logger.exception(
                    "[store] count_generation_jobs_for_athlete_since:schema_mismatch athlete_id=%s",
                    athlete_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            self._raise_operation_http_error(
                operation=f"count_generation_jobs_for_athlete_since athlete_id={athlete_id}",
                detail="failed to count generation jobs",
                exc=exc,
            )

    def check_plan_generation_short_window_limit(
        self,
        athlete_id: str,
        max_requests: int,
        window_seconds: float,
    ) -> tuple[bool, int]:
        try:
            response = self._run_with_transient_retry(
                operation=f"check_plan_generation_short_window_limit athlete_id={athlete_id}",
                fn=lambda: self.client.rpc(
                    "check_plan_generation_short_window_limit",
                    {
                        "p_athlete_id": athlete_id,
                        "p_max_requests": max_requests,
                        "p_window_seconds": window_seconds,
                    },
                ).execute(),
            )
            payload = getattr(response, "data", None)
            if isinstance(payload, list):
                payload = payload[0] if payload else {}
            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="invalid short-window rate limit response",
                )
            allowed = payload.get("allowed")
            retry_after_seconds = payload.get("retry_after_seconds")
            if not isinstance(allowed, bool) or not isinstance(retry_after_seconds, int):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="invalid short-window rate limit response",
                )
            return allowed, max(0, retry_after_seconds)
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"check_plan_generation_short_window_limit athlete_id={athlete_id}",
                detail="failed to enforce short-window rate limit",
                exc=exc,
            )

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        """Pure read. Never mutates job state.

        Stale ``running`` jobs are recovered separately via
        :meth:`recover_generation_job_if_stale` so that callers performing a
        plain lookup (including read-after-write refreshes) cannot trigger
        hidden status changes.
        """
        try:
            return self._run_with_transient_retry(
                operation="get_generation_job:select",
                fn=lambda: self._read_generation_job(job_id),
            )
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] get_generation_job:transient_failure job_id=%s error_type=%s",
                    job_id,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                logger.exception("[store] get_generation_job:schema_mismatch job_id=%s", job_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            logger.exception("[store] get_generation_job:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to load generation job",
            ) from exc

    def recover_generation_job_if_stale(self, job: dict[str, Any] | None) -> dict[str, Any] | None:
        """Requeue, fail, or recover a stale ``running`` job and return it refreshed.

        This is the explicit, mutating counterpart to :meth:`get_generation_job`.
        Non-running jobs (and ``None``) are returned unchanged.
        """
        if not job or str(job.get("status") or "") != "running":
            return job
        job_id = str(job.get("id") or "")
        try:
            staleness = self._classify_running_job_staleness(
                job,
                stale_after_seconds=generation_job_stale_after_seconds(),
                stage1_stale_after_seconds=_stage1_stale_after_seconds_for_reads(),
            )
            if staleness == "job_loaded_stalled":
                attempt_count = int(job.get("attempt_count") or 0)
                now_iso = _utc_now_iso()
                milestones = _progress_milestones(job.get("progress_milestones"))
                if attempt_count < _generation_startup_max_attempts():
                    milestones.append(
                        {
                            "code": "worker_claim_stalled_requeued",
                            "label": "Worker claim stalled",
                            "detail": "Worker loaded the generation job but did not reach request parsing; job was requeued for recovery.",
                            "meta": {},
                            "at": now_iso,
                        }
                    )
                    self._run_with_transient_retry(
                        operation="recover_generation_job_if_stale:requeue_job_loaded_stalled",
                        fn=lambda: self.client.table("generation_jobs")
                        .update(
                            {
                                "status": "queued",
                                "error": None,
                                "started_at": None,
                                "heartbeat_at": None,
                                "completed_at": None,
                                "progress_milestones": milestones,
                                # Back to the queue means back to unowned; the
                                # next claim records the new owner.
                                "claimed_by": None,
                                "claimed_at": None,
                            }
                        )
                        .eq("id", str(job.get("id") or ""))
                        .eq("status", "running")
                        .execute(),
                    )
                else:
                    milestones.append(
                        {
                            "code": "worker_claim_stalled_failed",
                            "label": "Worker stalled after loading job",
                            "detail": "Worker loaded the generation job but did not reach request parsing after retry.",
                            "meta": {},
                            "at": now_iso,
                        }
                    )
                    self._run_with_transient_retry(
                        operation="recover_generation_job_if_stale:fail_job_loaded_stalled",
                        fn=lambda: self.client.table("generation_jobs")
                        .update(
                            {
                                "status": "failed",
                                "error": "Generation worker stalled after loading the job.",
                                "completed_at": now_iso,
                                "heartbeat_at": now_iso,
                                "progress_milestones": milestones,
                            }
                        )
                        .eq("id", str(job.get("id") or ""))
                        .eq("status", "running")
                        .execute(),
                    )
                return self._read_generation_job(job_id)
            if staleness == "stage1_planner_stalled":
                now_iso = _utc_now_iso()
                milestones = _progress_milestones(job.get("progress_milestones"))
                if not _has_milestone_code(milestones, "stage1_planner_timeout"):
                    milestones.append(
                        {
                            "code": "stage1_planner_timeout",
                            "label": "Stage 1 planner timed out",
                            "detail": "Planner did not return after invocation and the job was failed for recovery.",
                            "meta": {},
                            "at": now_iso,
                        }
                    )
                recovered_plan_id = _plan_id_from_terminal_milestones(job)
                recovered_status = "review_required" if _should_recover_stalled_job(job) else "failed"
                if recovered_status == "review_required":
                    milestones.append(
                        {
                            "code": "stalled_job_recovered",
                            "label": "Stalled job recovered",
                            "detail": "Recovered as review required because usable output was already persisted.",
                            "meta": {"recovery_reason": "persisted_output"},
                            "at": now_iso,
                        }
                    )
                self._run_with_transient_retry(
                    operation="recover_generation_job_if_stale:resolve_stage1_stalled",
                    fn=lambda: self.client.table("generation_jobs")
                    .update(
                        {
                            "status": recovered_status,
                            "error": None if recovered_status == "review_required" else "Stage 1 planner stalled after planner invocation.",
                            "completed_at": now_iso,
                            "heartbeat_at": now_iso,
                            "progress_milestones": milestones,
                            "plan_id": recovered_plan_id or str(job.get("plan_id") or "") or None,
                        }
                    )
                    .eq("id", str(job.get("id") or ""))
                    .eq("status", "running")
                    .execute(),
                )
                return self._read_generation_job(job_id)
            return job
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] recover_generation_job_if_stale:transient_failure job_id=%s error_type=%s",
                    job_id,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                logger.exception("[store] recover_generation_job_if_stale:schema_mismatch job_id=%s", job_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            logger.exception("[store] recover_generation_job_if_stale:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to recover generation job",
            ) from exc

    def get_generation_job_by_client_request_id(self, *, athlete_id: str, client_request_id: str) -> dict[str, Any] | None:
        try:
            return self._run_with_transient_retry(
                operation=f"get_generation_job_by_client_request_id athlete_id={athlete_id}",
                fn=lambda: self._lookup_generation_job_by_client_request_id(
                    athlete_id=athlete_id,
                    client_request_id=client_request_id,
                ),
            )
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to load generation job",
            ) from exc

    def get_visible_active_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any] | None:
        """Pure read of the latest queued/running generation job for polling endpoints."""
        try:
            response = self._run_with_transient_retry(
                operation=f"get_visible_active_generation_job_for_athlete athlete_id={athlete_id}",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("athlete_id", athlete_id)
                .in_("status", ["queued", "running"])
                .order("created_at", desc=True)
                .limit(1)
                .execute(),
            )
            rows = [row for row in (getattr(response, "data", None) or []) if isinstance(row, dict)]
            return rows[0] if rows else None
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to load generation job",
            ) from exc

    def get_active_generation_job_for_athlete(
        self,
        athlete_id: str,
        *,
        stale_after_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        if stale_after_seconds is None:
            stale_after_seconds = generation_job_stale_after_seconds()
        try:
            response = self._run_with_transient_retry(
                operation=f"get_active_generation_job_for_athlete athlete_id={athlete_id}",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("athlete_id", athlete_id)
                .in_("status", ["queued", "running"])
                .order("created_at", desc=True)
                .limit(10)
                .execute(),
            )
            rows = [row for row in (getattr(response, "data", None) or []) if isinstance(row, dict)]
            for row in rows:
                if str(row.get("status") or "") == "queued":
                    return row
                if str(row.get("status") or "") != "running":
                    continue
                staleness = self._classify_running_job_staleness(
                    row,
                    stale_after_seconds=stale_after_seconds,
                    stage1_stale_after_seconds=_stage1_stale_after_seconds_for_reads(),
                )
                if staleness == "fresh":
                    return row
                if staleness == "startup_stale":
                    self._run_with_transient_retry(
                        operation="get_active_generation_job_for_athlete:reset_startup_stale",
                        fn=lambda: self.client.table("generation_jobs")
                        .update(
                            {
                                "status": "queued",
                                "error": None,
                                "heartbeat_at": None,
                                "started_at": None,
                                "completed_at": None,
                                "stage1_result": None,
                                "final_result": None,
                                "progress_milestones": [],
                            }
                        )
                        .eq("id", str(row.get("id") or ""))
                        .eq("status", "running")
                        .execute(),
                    )
                elif staleness == "job_loaded_stalled":
                    attempt_count = int(row.get("attempt_count") or 0)
                    now_iso = _utc_now_iso()
                    milestones = _progress_milestones(row.get("progress_milestones"))
                    if attempt_count < _generation_startup_max_attempts():
                        milestones.append(
                            {
                                "code": "worker_claim_stalled_requeued",
                                "label": "Worker claim stalled",
                                "detail": "Worker loaded the generation job but did not reach request parsing; job was requeued for recovery.",
                                "meta": {},
                                "at": now_iso,
                            }
                        )
                        self._run_with_transient_retry(
                            operation="get_active_generation_job_for_athlete:requeue_job_loaded_stalled",
                            fn=lambda: self.client.table("generation_jobs")
                            .update(
                                {
                                    "status": "queued",
                                    "error": None,
                                    "heartbeat_at": None,
                                    "started_at": None,
                                    "completed_at": None,
                                    "progress_milestones": milestones,
                                }
                            )
                            .eq("id", str(row.get("id") or ""))
                            .eq("status", "running")
                            .execute(),
                        )
                    else:
                        milestones.append(
                            {
                                "code": "worker_claim_stalled_failed",
                                "label": "Worker stalled after loading job",
                                "detail": "Worker loaded the generation job but did not reach request parsing after retry.",
                                "meta": {},
                                "at": now_iso,
                            }
                        )
                        self._run_with_transient_retry(
                            operation="get_active_generation_job_for_athlete:fail_job_loaded_stalled",
                            fn=lambda: self.client.table("generation_jobs")
                            .update(
                                {
                                    "status": "failed",
                                    "error": "Generation worker stalled after loading the job.",
                                    "completed_at": now_iso,
                                    "heartbeat_at": now_iso,
                                    "progress_milestones": milestones,
                                }
                            )
                            .eq("id", str(row.get("id") or ""))
                            .eq("status", "running")
                            .execute(),
                        )
                elif staleness == "stage1_planner_stalled":
                    now_iso = _utc_now_iso()
                    milestones = _progress_milestones(row.get("progress_milestones"))
                    if not _has_milestone_code(milestones, "stage1_planner_timeout"):
                        milestones.append(
                            {
                                "code": "stage1_planner_timeout",
                                "label": "Stage 1 planner timed out",
                                "detail": "Planner did not return after invocation and the job was failed for recovery.",
                                "meta": {},
                            "at": now_iso,
                            }
                        )
                    recovered_plan_id = _plan_id_from_terminal_milestones(row)
                    recovered_status = "review_required" if _should_recover_stalled_job(row) else "failed"
                    if recovered_status == "review_required":
                        milestones.append(
                            {
                                "code": "stalled_job_recovered",
                                "label": "Stalled job recovered",
                                "detail": "Recovered as review required because usable output was already persisted.",
                                "meta": {"recovery_reason": "persisted_output"},
                                "at": now_iso,
                            }
                        )
                    self._run_with_transient_retry(
                        operation="get_active_generation_job_for_athlete:resolve_stage1_stalled",
                        fn=lambda: self.client.table("generation_jobs")
                        .update(
                            {
                                "status": recovered_status,
                                "error": None if recovered_status == "review_required" else "Stage 1 planner stalled after planner invocation.",
                                "completed_at": now_iso,
                                "heartbeat_at": now_iso,
                                "progress_milestones": milestones,
                                "plan_id": recovered_plan_id or str(row.get("plan_id") or "") or None,
                            }
                        )
                        .eq("id", str(row.get("id") or ""))
                        .eq("status", "running")
                        .execute(),
                    )
                else:
                    now_iso = _utc_now_iso()
                    milestones = _progress_milestones(row.get("progress_milestones"))
                    recovered_plan_id = _plan_id_from_terminal_milestones(row)
                    recovered_status = "review_required" if _should_recover_stalled_job(row) else "failed"
                    if recovered_status == "review_required":
                        milestones.append(
                            {
                                "code": "stalled_job_recovered",
                                "label": "Stalled job recovered",
                                "detail": "Recovered as review required because usable output was already persisted.",
                                "meta": {"recovery_reason": "persisted_output"},
                                "at": now_iso,
                            }
                        )
                    self._run_with_transient_retry(
                        operation="get_active_generation_job_for_athlete:resolve_mid_pipeline_stale",
                        fn=lambda: self.client.table("generation_jobs")
                        .update(
                            {
                                "status": recovered_status,
                                "error": None if recovered_status == "review_required" else "Generation job stalled mid-pipeline and was failed for recovery.",
                                "completed_at": now_iso,
                                "heartbeat_at": now_iso,
                                "progress_milestones": milestones,
                                "plan_id": recovered_plan_id or str(row.get("plan_id") or "") or None,
                            }
                        )
                        .eq("id", str(row.get("id") or ""))
                        .eq("status", "running")
                        .execute(),
                    )
                refreshed = self.get_generation_job(str(row.get("id") or ""))
                if refreshed and str(refreshed.get("status") or "") in {"queued", "failed", "review_required"}:
                    return refreshed
            return None
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to load generation job",
            ) from exc

    def get_generation_job_by_plan_id(self, plan_id: str) -> dict[str, Any] | None:
        # Soft-fails to None so plan detail loads even if generation_jobs is unavailable —
        # the plan_source field is non-critical (banner-only).
        try:
            return self._select_first(
                self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("plan_id", plan_id)
                .order("completed_at", desc=True)
            )
        except _STORE_CLIENT_ERRORS:
            logger.exception("[store] get_generation_job_by_plan_id:exception plan_id=%s", plan_id)
            return None

    def get_latest_generation_job_for_athlete(self, athlete_id: str) -> dict[str, Any] | None:
        try:
            response = self._run_with_transient_retry(
                operation=f"get_latest_generation_job_for_athlete athlete_id={athlete_id}",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("athlete_id", athlete_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute(),
            )
            rows = response.data or []
            if not rows:
                return None
            row = rows[0]
            return row if isinstance(row, dict) else None
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to load generation job",
            ) from exc

    def has_active_generation_job_for_plan(self, plan_id: str) -> bool:
        try:
            response = self._run_with_transient_retry(
                operation=f"has_active_generation_job_for_plan plan_id={plan_id}",
                fn=lambda: self.client.table("generation_jobs")
                .select("id")
                .eq("plan_id", plan_id)
                .in_("status", ["queued", "running"])
                .limit(1)
                .execute(),
            )
            return bool(response.data)
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"has_active_generation_job_for_plan plan_id={plan_id}",
                detail="failed to check active generation jobs",
                exc=exc,
            )

    def list_generation_jobs_for_athlete(self, athlete_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
        try:
            response = self._run_with_transient_retry(
                operation=f"list_generation_jobs_for_athlete athlete_id={athlete_id}",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_ADMIN_LIST_SELECT)
                .eq("athlete_id", athlete_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute(),
            )
            return [row for row in (response.data or []) if isinstance(row, dict)]
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            self._raise_operation_http_error(
                operation=f"list_generation_jobs_for_athlete athlete_id={athlete_id}",
                detail="failed to list generation jobs",
                exc=exc,
            )
        return []

    def list_admin_triage_generation_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        try:
            response = self._run_with_transient_retry(
                operation=f"list_admin_triage_generation_jobs limit={limit}",
                fn=lambda: self.client.table("generation_jobs")
                .select(f"{GENERATION_JOB_ADMIN_LIST_SELECT}, profiles!generation_jobs_athlete_id_fkey(email, full_name)")
                .eq("status", "review_required")
                .is_("plan_id", "null")
                .order("created_at", desc=True)
                .limit(limit)
                .execute(),
            )
            return [row for row in (response.data or []) if isinstance(row, dict)]
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            self._raise_operation_http_error(
                operation=f"list_admin_triage_generation_jobs limit={limit}",
                detail="failed to list triage generation jobs",
                exc=exc,
            )
        return []

    def list_admin_active_generation_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        try:
            response = self._run_with_transient_retry(
                operation=f"list_admin_active_generation_jobs limit={limit}",
                fn=lambda: self.client.table("generation_jobs")
                .select(f"{GENERATION_JOB_ADMIN_LIST_SELECT}, profiles!generation_jobs_athlete_id_fkey(email, full_name)")
                .in_("status", ["queued", "running"])
                .order("created_at", desc=True)
                .limit(limit)
                .execute(),
            )
            return [row for row in (response.data or []) if isinstance(row, dict)]
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_generation_job_schema_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            self._raise_operation_http_error(
                operation=f"list_admin_active_generation_jobs limit={limit}",
                detail="failed to list active generation jobs",
                exc=exc,
            )
        return []

    def list_orphaned_terminal_generation_jobs(self, *, limit: int = 500) -> list[dict[str, Any]]:
        try:
            response = self._run_with_transient_retry(
                operation=f"list_orphaned_terminal_generation_jobs limit={limit}",
                fn=lambda: self.client.table("generation_jobs")
                .select("id, athlete_id, status, source, plan_id, plans!left(id)")
                .in_("status", ["completed", "review_required"])
                .is_("plans.id", "null")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute(),
            )
            rows = [row for row in (response.data or []) if isinstance(row, dict)]
            orphaned: list[dict[str, Any]] = []
            for row in rows:
                plan_ref = row.get("plans")
                has_plan = isinstance(plan_ref, dict) and bool(str(plan_ref.get("id") or "").strip())
                if not has_plan:
                    orphaned.append(
                        {
                            "job_id": str(row.get("id") or ""),
                            "athlete_id": str(row.get("athlete_id") or ""),
                            "status": str(row.get("status") or ""),
                            "source": str(row.get("source") or ""),
                            "plan_id": str(row.get("plan_id") or ""),
                        }
                    )
            return orphaned
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"list_orphaned_terminal_generation_jobs limit={limit}",
                detail="failed to list orphaned terminal generation jobs",
                exc=exc,
            )
        return []

    def list_failed_triage_resume_jobs_with_approved_marker(self, *, limit: int = 500) -> list[dict[str, Any]]:
        try:
            response = self._run_with_transient_retry(
                operation=f"list_failed_triage_resume_jobs_with_approved_marker limit={limit}",
                fn=lambda: self.client.table("generation_jobs")
                .select("id, athlete_id, status, source, plan_id, plans!inner(id,stage2_status)")
                .eq("status", "failed")
                .eq("source", "admin_triage_resume")
                .eq("plans.stage2_status", "triage_resume_approved")
                .order("updated_at", desc=True)
                .limit(limit)
                .execute(),
            )
            rows = [row for row in (response.data or []) if isinstance(row, dict)]
            findings: list[dict[str, Any]] = []
            for row in rows:
                linked_plan = row.get("plans") if isinstance(row.get("plans"), dict) else {}
                findings.append(
                    {
                        "job_id": str(row.get("id") or ""),
                        "plan_id": str(linked_plan.get("id") or row.get("plan_id") or ""),
                        "athlete_id": str(row.get("athlete_id") or ""),
                    }
                )
            return findings
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"list_failed_triage_resume_jobs_with_approved_marker limit={limit}",
                detail="failed to list failed triage resume jobs with approved marker",
                exc=exc,
            )
        return []

    def list_claimable_generation_jobs(self, *, limit: int = 20, stale_after_seconds: int | None = None) -> list[dict[str, Any]]:
        if stale_after_seconds is None:
            stale_after_seconds = generation_job_stale_after_seconds()
        try:
            cutoff_iso = (
                datetime.now(timezone.utc) - timedelta(seconds=max(1, stale_after_seconds))
            ).isoformat()
            queued_response = self._run_with_transient_retry(
                operation="list_claimable_generation_jobs:select_queued",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("status", "queued")
                .order("created_at", desc=False)
                .limit(limit)
                .execute(),
            )
            legacy_status_responses: list[Any] = []
            if _claim_legacy_blank_status_jobs_enabled():
                legacy_status_responses = [
                    self._run_with_transient_retry(
                        operation="list_claimable_generation_jobs:select_null_status",
                        fn=lambda: self.client.table("generation_jobs")
                        .select(GENERATION_JOB_SELECT)
                        .is_("status", "null")
                        .order("created_at", desc=False)
                        .limit(limit)
                        .execute(),
                    ),
                    self._run_with_transient_retry(
                        operation="list_claimable_generation_jobs:select_blank_status",
                        fn=lambda: self.client.table("generation_jobs")
                        .select(GENERATION_JOB_SELECT)
                        .eq("status", "")
                        .order("created_at", desc=False)
                        .limit(limit)
                        .execute(),
                    ),
                ]
            stale_heartbeat_response = self._run_with_transient_retry(
                operation="list_claimable_generation_jobs:select_running_stale_heartbeat",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("status", "running")
                .lte("heartbeat_at", cutoff_iso)
                .order("created_at", desc=False)
                .limit(limit)
                .execute(),
            )
            stale_without_heartbeat_response = self._run_with_transient_retry(
                operation="list_claimable_generation_jobs:select_running_stale_started",
                fn=lambda: self.client.table("generation_jobs")
                .select(GENERATION_JOB_SELECT)
                .eq("status", "running")
                .is_("heartbeat_at", "null")
                .lte("started_at", cutoff_iso)
                .order("created_at", desc=False)
                .limit(limit)
                .execute(),
            )

            merged_rows: dict[str, dict[str, Any]] = {}

            # Queued jobs are always claimable. Legacy blank/null status scans
            # are opt-in only; the migration normalizes old rows and the hot
            # worker loop should stay on indexed canonical statuses.
            for response in (queued_response, *legacy_status_responses):
                for row in response.data or []:
                    if not isinstance(row, dict):
                        continue
                    row_id = str(row.get("id") or "")
                    if not row_id:
                        continue
                    merged_rows[row_id] = dict(row)

            # Running jobs are only claimable if they are startup-stale.
            for response in (stale_heartbeat_response, stale_without_heartbeat_response):
                for row in response.data or []:
                    if not isinstance(row, dict):
                        continue
                    row_id = str(row.get("id") or "")
                    if not row_id:
                        continue
                    if not is_startup_stale_generation_job(
                        row,
                        stale_after_seconds=stale_after_seconds,
                    ):
                        continue
                    merged_rows[row_id] = dict(row)
            return sorted(merged_rows.values(), key=lambda row: str(row.get("created_at") or ""))[:limit]
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] list_claimable_generation_jobs:transient_failure error_type=%s",
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                logger.exception("[store] list_claimable_generation_jobs:schema_mismatch")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            logger.exception("[store] list_claimable_generation_jobs:exception")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to list generation jobs",
            ) from exc

    def _fail_stalled_job_loaded_job(
        self, job_id: str, job: dict[str, Any], now_iso: str
    ) -> None:
        """Mark a ``job_loaded``-stalled job failed once its retry budget is spent.

        Mirrors the read-side recovery in ``recover_generation_job_if_stale`` so the
        terminal status, error, and milestone are identical regardless of which path
        observes the exhausted attempt budget.
        """
        milestones = _progress_milestones(job.get("progress_milestones"))
        milestones.append(
            {
                "code": "worker_claim_stalled_failed",
                "label": "Worker stalled after loading job",
                "detail": "Worker loaded the generation job but did not reach request parsing after retry.",
                "meta": {},
                "at": now_iso,
            }
        )
        # Optimistic lock: only fail the exact row we read. Guarding on
        # attempt_count blocks a concurrent worker that re-claimed the job (the
        # claim bumps attempt_count), and guarding on heartbeat_at blocks a job
        # whose heartbeat advanced after our read — i.e. a worker that is in fact
        # alive. Either change means the row moved on, so the update no-ops and the
        # next pass re-evaluates instead of clobbering live state.
        expected_attempt_count = int(job.get("attempt_count") or 0)

        self.fail_generation_job(
            job_id,
            expected_status="running",
            expected_attempt_count=expected_attempt_count,
            error="Generation worker stalled after loading the job.",
            progress_milestones=milestones,
            failed_at=now_iso,
            heartbeat_at=now_iso,
            # The stalled job is owned by a dead worker, not this process; the
            # status + attempt_count guards above are the protection here.
            enforce_worker_ownership=False,
        )

    def claim_generation_job_start(self, job_id: str, *, stale_after_seconds: int | None = None, worker_id: str | None = None) -> dict[str, Any] | None:
        if stale_after_seconds is None:
            stale_after_seconds = generation_job_stale_after_seconds()
        try:
            job = self.get_generation_job(job_id)
            if not job:
                return None

            current_status = str(job.get("status") or "").strip().lower() or "queued"
            current_attempt_count = int(job.get("attempt_count") or 0)
            now_iso = _utc_now_iso()

            if current_status not in {"queued", "running"}:
                return None
            if current_status == "running" and not is_startup_stale_generation_job(
                job,
                stale_after_seconds=stale_after_seconds,
            ):
                return None
            # The worker reclaims startup-stale ``running`` jobs directly through this
            # path. Jobs stalled at ``job_loaded`` (claimed, then dead before request
            # parsing) are retry-capped by the read-side recovery; enforce the same cap
            # here so a repeatedly-dying worker cannot re-grab the job forever, bumping
            # attempt_count without bound. Once the budget is spent, fail the job
            # instead of reclaiming it.
            if (
                current_status == "running"
                and current_attempt_count >= _generation_startup_max_attempts()
                and is_job_loaded_stalled_generation_job(
                    job,
                    stale_after_seconds=stale_after_seconds,
                )
            ):
                self._fail_stalled_job_loaded_job(job_id, job, now_iso)
                return None
            try:
                require_generation_job_transition(current_status, "running")
            except ValueError:
                return None

            # Atomic claim RPC: the status/attempt guards and the
            # running/ownership write happen in one statement, so two workers
            # racing for the same row cannot both win. A null result means the
            # row moved on (claimed elsewhere or finished) — not an error.
            payload = {
                "p_job_id": job_id,
                "p_worker_id": (worker_id or "").strip() or generation_worker_id(),
                "p_expected_status": current_status,
                "p_expected_attempt_count": current_attempt_count,
                "p_progress_milestones": [_job_loaded_milestone(now_iso)],
                "p_claimed_at": now_iso,
            }
            response = self._run_with_transient_retry(
                operation="claim_generation_job_start:rpc",
                fn=lambda: self.client.rpc("claim_generation_job", payload).execute(),
            )
            return self._terminal_generation_job_rpc_result(response)
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] claim_generation_job_start:transient_failure job_id=%s error_type=%s",
                    job_id,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            logger.exception("[store] claim_generation_job_start:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to claim generation job",
            ) from exc

    def claim_generation_job(self, job_id: str, *, stale_after_seconds: int | None = None, worker_id: str | None = None) -> dict[str, Any] | None:
        return self.claim_generation_job_start(job_id, stale_after_seconds=stale_after_seconds, worker_id=worker_id)

    def count_active_generation_jobs(self, *, stale_after_seconds: int | None = None) -> int:
        if stale_after_seconds is None:
            stale_after_seconds = generation_job_stale_after_seconds()
        try:
            cutoff_iso = (
                datetime.now(timezone.utc) - timedelta(seconds=max(1, stale_after_seconds))
            ).isoformat()
            response = self._run_with_transient_retry(
                operation="count_active_generation_jobs:select_running",
                fn=lambda: self.client.table("generation_jobs")
                .select("id", count="exact")
                .eq("status", "running")
                .or_(f"heartbeat_at.gt.{cutoff_iso},and(heartbeat_at.is.null,started_at.gt.{cutoff_iso})")
                .execute(),
            )
            count_value = getattr(response, "count", None)
            return int(count_value or 0)
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] count_active_generation_jobs:transient_failure error_type=%s",
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            if self._is_generation_job_schema_error(exc):
                logger.exception("[store] count_active_generation_jobs:schema_mismatch")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=GENERATION_JOB_SCHEMA_DETAIL,
                ) from exc
            logger.exception("[store] count_active_generation_jobs:exception")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to count active generation jobs",
            ) from exc

    def _terminal_generation_job_rpc_result(self, response: Any) -> dict[str, Any] | None:
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return None

    def _handle_terminal_generation_job_error(
        self,
        *,
        exc: Exception,
        operation: str,
        job_id: str,
    ) -> None:
        if self._is_transient_store_error(exc):
            logger.warning(
                "[store] %s:transient_failure job_id=%s error_type=%s",
                operation,
                job_id,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
            ) from exc
        if self._is_generation_job_terminal_missing_error(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="generation job not found",
            ) from exc
        if self._is_generation_job_terminal_conflict_error(exc):
            raise _status_transition_error(_sanitize_error_text(exc)) from exc
        if self._is_generation_job_schema_error(exc):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=GENERATION_JOB_SCHEMA_DETAIL,
            ) from exc

    def complete_generation_job(
        self,
        job_id: str,
        *,
        expected_attempt_count: int,
        final_status: str,
        final_result: dict[str, Any] | None = None,
        plan_id: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
        heartbeat_at: str | None = None,
        expected_status: str = "running",
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict[str, Any]:
        next_status = str(final_status or "").strip().lower()
        if next_status not in {"completed", "review_required"}:
            raise _status_transition_error(f"invalid terminal generation job status: {final_status!r}")
        try:
            payload = {
                "p_job_id": job_id,
                "p_expected_status": expected_status,
                "p_expected_attempt_count": int(expected_attempt_count),
                "p_final_status": next_status,
                "p_final_result": final_result,
                "p_plan_id": plan_id,
                "p_error": error,
                "p_completed_at": completed_at,
                "p_heartbeat_at": heartbeat_at,
                "p_expected_worker_id": (
                    ((expected_worker_id or "").strip() or generation_worker_id())
                    if enforce_worker_ownership
                    else None
                ),
            }
            response = self._run_with_transient_retry(
                operation="complete_generation_job:rpc",
                fn=lambda: self.client.rpc("complete_generation_job", payload).execute(),
            )
            updated = self._terminal_generation_job_rpc_result(response)
            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="generation job completion returned no row",
                )
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._handle_terminal_generation_job_error(
                exc=exc,
                operation="complete_generation_job",
                job_id=job_id,
            )
            logger.exception("[store] complete_generation_job:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to complete generation job",
            ) from exc

    def fail_generation_job(
        self,
        job_id: str,
        *,
        expected_attempt_count: int,
        error: str,
        final_result: dict[str, Any] | None = None,
        plan_id: str | None = None,
        progress_milestones: list[Any] | None = None,
        failed_at: str | None = None,
        heartbeat_at: str | None = None,
        expected_status: str = "running",
        expected_worker_id: str | None = None,
        enforce_worker_ownership: bool = True,
    ) -> dict[str, Any]:
        try:
            payload = {
                "p_job_id": job_id,
                "p_expected_status": expected_status,
                "p_expected_attempt_count": int(expected_attempt_count),
                "p_error": str(error or "Generation job failed."),
                "p_final_result": final_result,
                "p_plan_id": plan_id,
                "p_progress_milestones": progress_milestones,
                "p_failed_at": failed_at,
                "p_heartbeat_at": heartbeat_at,
                "p_expected_worker_id": (
                    ((expected_worker_id or "").strip() or generation_worker_id())
                    if enforce_worker_ownership
                    else None
                ),
            }
            response = self._run_with_transient_retry(
                operation="fail_generation_job:rpc",
                fn=lambda: self.client.rpc("fail_generation_job", payload).execute(),
            )
            updated = self._terminal_generation_job_rpc_result(response)
            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="generation job failure returned no row",
                )
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._handle_terminal_generation_job_error(
                exc=exc,
                operation="fail_generation_job",
                job_id=job_id,
            )
            logger.exception("[store] fail_generation_job:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to fail generation job",
            ) from exc

    def update_generation_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        try:
            payload = dict(changes)
            if "status" in payload:
                next_status = str(payload.get("status") or "").strip().lower()
                if not is_generation_job_status(next_status):
                    raise _status_transition_error(f"unknown generation job status: {next_status!r}")
                existing = self._read_generation_job(job_id)
                if not existing:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="generation job not found",
                    )
                try:
                    payload["status"] = require_generation_job_transition(existing.get("status") or "queued", next_status)
                except ValueError as exc:
                    raise _status_transition_error(str(exc)) from exc
            self._run_with_transient_retry(
                operation="update_generation_job:update",
                fn=lambda: self.client.table("generation_jobs").update(payload).eq("id", job_id).execute(),
            )
            updated = self.get_generation_job(job_id)
            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="generation job not found",
                )
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] update_generation_job:transient_failure job_id=%s error_type=%s",
                    job_id,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            logger.exception("[store] update_generation_job:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to update generation job",
            ) from exc

    def record_stage2_cost(self, job_id: str, metadata: dict[str, Any]) -> None:
        """Best-effort persistence of Stage 2 token/cost telemetry to generation_jobs.

        Telemetry only — this NEVER raises. The canonical generation outcome
        (status, plan, final_result) is already persisted via
        update_generation_job before this is called, so a schema gap (migration
        not yet applied) or a transient store error here must not fail or roll
        back the job. Only the known Stage 2 cost columns are written; any stray
        keys in ``metadata`` are dropped so the payload can never carry plan text
        or other unrelated fields into the database.
        """
        if not isinstance(metadata, dict):
            return
        payload = {
            column: metadata[column]
            for column in GENERATION_JOB_STAGE2_COST_COLUMNS
            if column in metadata
        }
        if not payload:
            return
        try:
            self.client.table("generation_jobs").update(payload).eq("id", job_id).execute()
            logger.info(
                "[store] record_stage2_cost:ok job_id=%s model=%s total_tokens=%s estimated_cost_usd=%s",
                job_id,
                payload.get("stage2_model"),
                payload.get("stage2_total_tokens"),
                payload.get("stage2_estimated_cost_usd"),
            )
        except Exception as exc:  # noqa: BLE001 - telemetry write must never break generation
            logger.warning(
                "[store] record_stage2_cost:skipped job_id=%s error_type=%s error=%s",
                job_id,
                type(exc).__name__,
                _sanitize_error_text(exc),
            )

    def rename_plan(self, plan_id: str, plan_name: str) -> dict[str, Any]:
        try:
            logger.info("[store] rename_plan:start plan_id=%s", plan_id)
            self.client.table("plans").update({"plan_name": plan_name}).eq("id", plan_id).execute()
            updated = self.get_plan(plan_id)
            if not updated:
                logger.warning("[store] rename_plan:plan_missing_after_update plan_id=%s", plan_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] rename_plan:success plan_id=%s", plan_id)
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"rename_plan plan_id={plan_id}",
                detail="failed to rename plan",
                exc=exc,
            )

    def rename_plan_for_athlete(self, plan_id: str, athlete_id: str, plan_name: str) -> dict[str, Any]:
        """Rename a plan only if it belongs to ``athlete_id``.

        The update is scoped by both ``id`` and ``athlete_id`` so another
        athlete's plan is untouched; the scoped re-read then yields ``None`` and
        we surface a 404 rather than leaking that the plan exists.
        """
        try:
            logger.info("[store] rename_plan_for_athlete:start plan_id=%s athlete_id=%s", plan_id, athlete_id)
            self.client.table("plans").update({"plan_name": plan_name}).eq("id", plan_id).eq(
                "athlete_id", athlete_id
            ).execute()
            updated = self.get_plan_for_athlete(plan_id, athlete_id)
            if not updated:
                logger.warning(
                    "[store] rename_plan_for_athlete:not_found plan_id=%s athlete_id=%s", plan_id, athlete_id
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] rename_plan_for_athlete:success plan_id=%s athlete_id=%s", plan_id, athlete_id)
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"rename_plan_for_athlete plan_id={plan_id} athlete_id={athlete_id}",
                detail="failed to rename plan",
                exc=exc,
            )

    def archive_plan(self, plan_id: str) -> dict[str, Any]:
        try:
            existing = self.get_plan(plan_id)
            if not existing:
                logger.warning("[store] archive_plan:not_found plan_id=%s", plan_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            try:
                next_status = require_plan_transition(existing.get("status") or "generated", "archived")
            except ValueError as exc:
                raise _status_transition_error(str(exc)) from exc
            logger.info("[store] archive_plan:start plan_id=%s", plan_id)
            self.client.table("plans").update({"status": next_status}).eq("id", plan_id).execute()
            updated = self.get_plan(plan_id)
            if not updated:
                logger.warning("[store] archive_plan:plan_missing_after_update plan_id=%s", plan_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] archive_plan:success plan_id=%s", plan_id)
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"archive_plan plan_id={plan_id}",
                detail="failed to archive plan",
                exc=exc,
            )

    def archive_plan_for_athlete(self, plan_id: str, athlete_id: str) -> dict[str, Any]:
        """Archive a plan only if it belongs to ``athlete_id`` (404 otherwise)."""
        try:
            existing = self.get_plan_for_athlete(plan_id, athlete_id)
            if not existing:
                logger.warning(
                    "[store] archive_plan_for_athlete:not_found plan_id=%s athlete_id=%s", plan_id, athlete_id
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            try:
                next_status = require_plan_transition(existing.get("status") or "generated", "archived")
            except ValueError as exc:
                raise _status_transition_error(str(exc)) from exc
            logger.info("[store] archive_plan_for_athlete:start plan_id=%s athlete_id=%s", plan_id, athlete_id)
            self.client.table("plans").update({"status": next_status}).eq("id", plan_id).eq(
                "athlete_id", athlete_id
            ).execute()
            updated = self.get_plan_for_athlete(plan_id, athlete_id)
            if not updated:
                logger.warning(
                    "[store] archive_plan_for_athlete:plan_missing_after_update plan_id=%s athlete_id=%s",
                    plan_id,
                    athlete_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] archive_plan_for_athlete:success plan_id=%s athlete_id=%s", plan_id, athlete_id)
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"archive_plan_for_athlete plan_id={plan_id} athlete_id={athlete_id}",
                detail="failed to archive plan",
                exc=exc,
            )

    def delete_plan(self, plan_id: str) -> None:
        try:
            existing = self.get_plan(plan_id)
            if not existing:
                logger.warning("[store] delete_plan:not_found plan_id=%s", plan_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] delete_plan:start plan_id=%s", plan_id)
            self.client.table("plans").delete().eq("id", plan_id).execute()
            logger.info("[store] delete_plan:success plan_id=%s", plan_id)
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"delete_plan plan_id={plan_id}",
                detail="failed to delete plan",
                exc=exc,
            )

    def delete_plan_for_athlete(self, plan_id: str, athlete_id: str) -> None:
        """Delete a plan only if it belongs to ``athlete_id`` (404 otherwise)."""
        try:
            existing = self.get_plan_for_athlete(plan_id, athlete_id)
            if not existing:
                logger.warning(
                    "[store] delete_plan_for_athlete:not_found plan_id=%s athlete_id=%s", plan_id, athlete_id
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] delete_plan_for_athlete:start plan_id=%s athlete_id=%s", plan_id, athlete_id)
            self.client.table("plans").delete().eq("id", plan_id).eq("athlete_id", athlete_id).execute()
            logger.info("[store] delete_plan_for_athlete:success plan_id=%s athlete_id=%s", plan_id, athlete_id)
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"delete_plan_for_athlete plan_id={plan_id} athlete_id={athlete_id}",
                detail="failed to delete plan",
                exc=exc,
            )

    def update_plan_stage2(self, plan_id: str, result: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_plan(plan_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="plan not found",
            )
        try:
            current_status = existing.get("status") or "generated"
            next_status_input = result.get("status") or current_status
            next_status = require_plan_transition(current_status, next_status_input)
        except ValueError as exc:
            raise _status_transition_error(str(exc)) from exc
        visible_plan_text = _visible_plan_text_for_status(result, status_value=next_status)
        payload = {
            "status": next_status,
            "plan_text": visible_plan_text,
            "draft_plan_text": result.get("draft_plan_text", result.get("plan_text", "")),
            "final_plan_text": result.get("final_plan_text", result.get("plan_text", "")),
            "pdf_url": result.get("pdf_url"),
            "stage2_retry_text": result.get("stage2_retry_text", ""),
            "stage2_validator_report": result.get("stage2_validator_report", {}),
            "stage2_status": result.get("stage2_status", ""),
            "stage2_attempt_count": result.get("stage2_attempt_count", 0),
        }
        for optional_field in (
            "coach_notes",
            "why_log",
            "planning_brief",
            "stage2_payload",
            "parsing_metadata",
            "stage2_handoff_text",
        ):
            if optional_field in result:
                value = result.get(optional_field)
                if optional_field == "planning_brief":
                    value = _encode_structured_text(value)
                payload[optional_field] = value
        if "stage2_payload" in payload:
            _guard_persisted_json(
                payload.get("stage2_payload"),
                field="stage2_payload",
                max_bytes=MAX_SERVER_JSON_BYTES,
                context=f"plan_id={plan_id}",
            )
        try:
            logger.info("[store] update_plan_stage2:start plan_id=%s status=%s", plan_id, payload["status"])
            self.client.table("plans").update(payload).eq("id", plan_id).execute()
            updated = self.get_plan(plan_id)
            if not updated:
                logger.warning("[store] update_plan_stage2:plan_missing_after_update plan_id=%s", plan_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] update_plan_stage2:success plan_id=%s", plan_id)
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"update_plan_stage2 plan_id={plan_id}",
                detail="failed to update plan stage 2",
                exc=exc,
            )

    def update_plan_triage_approval(
        self,
        plan_id: str,
        *,
        why_log: dict[str, Any],
        stage2_status: str,
    ) -> dict[str, Any]:
        payload = {"why_log": why_log, "stage2_status": stage2_status}
        try:
            logger.info("[store] update_plan_triage_approval:start plan_id=%s", plan_id)
            self.client.table("plans").update(payload).eq("id", plan_id).execute()
            updated = self.get_plan(plan_id)
            if not updated:
                logger.warning("[store] update_plan_triage_approval:plan_missing_after_update plan_id=%s", plan_id)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="plan not found",
                )
            logger.info("[store] update_plan_triage_approval:success plan_id=%s", plan_id)
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"update_plan_triage_approval plan_id={plan_id}",
                detail="failed to update triage approval",
                exc=exc,
            )

    def list_admin_plans(
        self, *, limit: int = 50, offset: int = 0, q: str | None = None
    ) -> list[dict[str, Any]]:
        query = self.client.table("plans").select(
            "id, athlete_id, full_name, fight_date, technical_style, plan_name, status, "
            "pdf_url, created_at, profiles!plans_athlete_id_fkey(email, full_name)"
        )
        clause = _admin_search_clause(("plan_name", "full_name", "status"), q)
        if clause:
            query = query.or_(clause)
        response = (
            query.order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return getattr(response, "data", None) or []

    def list_admin_athletes(
        self, *, limit: int = 50, offset: int = 0, q: str | None = None
    ) -> list[dict[str, Any]]:
        query = self.client.table("admin_athlete_rollups").select("*")
        clause = _admin_search_clause(
            ("email", "full_name", "username", "professional_status", "record_summary"), q
        )
        if clause:
            query = query.or_(clause)
        response = (
            query.order("updated_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return getattr(response, "data", None) or []

    def get_admin_athlete(self, athlete_id: str) -> dict[str, Any] | None:
        return self._select_first(
            self.client.table("admin_athlete_rollups").select("*").eq("id", athlete_id)
        )

    def clear_onboarding_draft(self, athlete_id: str) -> None:
        try:
            logger.info("[store] clear_onboarding_draft:start athlete_id=%s", athlete_id)
            self.client.table("profiles").update({"onboarding_draft": None}).eq("id", athlete_id).execute()
            logger.info("[store] clear_onboarding_draft:success athlete_id=%s", athlete_id)
        except _STORE_CLIENT_ERRORS as exc:
            self._raise_operation_http_error(
                operation=f"clear_onboarding_draft athlete_id={athlete_id}",
                detail="failed to clear onboarding draft",
                exc=exc,
            )
