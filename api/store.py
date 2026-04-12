from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

import httpx
from fastapi import HTTPException, status
from postgrest.exceptions import APIError as PostgrestAPIError
from supabase import Client, create_client

from .auth import AuthenticatedUser
from .models import PlanRequest, ProfileUpdateRequest

logger = logging.getLogger(__name__)

PLAN_SUMMARY_SELECT = "id, athlete_id, full_name, fight_date, technical_style, plan_name, status, pdf_url, created_at"
GENERATION_JOB_SELECT = "*"

_TRANSIENT_SUPABASE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
)
_STORE_CLIENT_ERRORS = (PostgrestAPIError, httpx.HTTPError)
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
)
_PLAN_OPTIONAL_SCHEMA_COLUMNS = {
    "draft_plan_text",
    "final_plan_text",
    "planning_brief",
    "stage2_payload",
    "stage2_handoff_text",
    "stage2_retry_text",
    "stage2_validator_report",
    "stage2_status",
    "stage2_attempt_count",
    "parsing_metadata",
}
GENERATION_JOB_UNAVAILABLE_DETAIL = "generation job service temporarily unavailable"
GENERATION_JOB_SCHEMA_DETAIL = "generation job store is not ready; apply the latest Supabase schema and redeploy"


class AppStore(Protocol):
    def ensure_profile(self, user: AuthenticatedUser) -> dict[str, Any]: ...

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict[str, Any]: ...

    def get_latest_intake(self, athlete_id: str) -> dict[str, Any] | None: ...

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict[str, Any]: ...

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

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any] | None: ...

    def rename_plan(self, plan_id: str, plan_name: str) -> dict[str, Any]: ...

    def delete_plan(self, plan_id: str) -> None: ...

    def create_or_get_generation_job(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]: ...

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None: ...

    def claim_generation_job(self, job_id: str, *, stale_after_seconds: int = 90) -> dict[str, Any] | None: ...

    def update_generation_job(self, job_id: str, **changes: Any) -> dict[str, Any]: ...

    def update_plan_stage2(self, plan_id: str, result: dict[str, Any]) -> dict[str, Any]: ...

    def list_admin_plans(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_admin_athletes(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]: ...

    def get_admin_athlete(self, athlete_id: str) -> dict[str, Any] | None: ...

    def clear_onboarding_draft(self, athlete_id: str) -> None: ...


def _encode_structured_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


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
        return cls(create_client(url, key), admin_emails)

    def _select_first(self, query) -> dict[str, Any] | None:
        response = query.limit(1).execute()
        rows = getattr(response, "data", None) or []
        return rows[0] if rows else None

    def _log_profile_event(self, *, operation: str, user: AuthenticatedUser, **fields: Any) -> None:
        details = " ".join(f"{key}=%r" % value for key, value in sorted(fields.items()))
        suffix = f" {details}" if details else ""
        logger.info(
            "[store] profile:%s user_id=%s email=%s%s",
            operation,
            user.user_id,
            user.email,
            suffix,
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
        if not any(snippet in text for snippet in ("schema cache", "column", "does not exist")):
            return False
        return any(column in text for column in _PLAN_OPTIONAL_SCHEMA_COLUMNS)

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
                    "[store] profile:upsert_failure user_id=%s email=%s attempt=%s transient=%s error_type=%s error=%s",
                    user.user_id,
                    user.email,
                    attempt,
                    transient,
                    type(exc).__name__,
                    exc,
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
            existing = self._get_profile_by_id(user.user_id)
            if existing:
                self._log_profile_event(
                    operation="ensure_existing",
                    user=user,
                    role=existing.get("role") or self._default_role_for(user),
                )
                return existing

            payload = self._build_profile_payload(user=user, existing=None)
            try:
                self._upsert_profile_with_retry(user=user, payload=payload)
            except _STORE_CLIENT_ERRORS as exc:
                logger.exception(
                    "[store] profile:ensure_upsert_exception user_id=%s email=%s error_type=%s",
                    user.user_id,
                    user.email,
                    type(exc).__name__,
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
                "[store] ensure_profile:exception athlete_id=%s email=%s error_type=%s",
                user.user_id,
                user.email,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to ensure profile",
            ) from exc

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict[str, Any]:
        try:
            fields = update.model_dump(mode="json", exclude_none=True)
            if "record" in fields:
                fields["record_summary"] = fields.pop("record")
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

    def get_latest_intake(self, athlete_id: str) -> dict[str, Any] | None:
        return self._select_first(
            self.client.table("athlete_intakes")
            .select("*")
            .eq("athlete_id", athlete_id)
            .order("created_at", desc=True)
        )

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict[str, Any]:
        payload = {
            "athlete_id": athlete_id,
            "fight_date": request.fight_date,
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

    def create_plan(
        self,
        *,
        athlete_id: str,
        intake_id: str,
        request: PlanRequest,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "athlete_id": athlete_id,
            "intake_id": intake_id,
            "fight_date": request.fight_date,
            "technical_style": request.athlete.technical_style,
            "full_name": request.athlete.full_name,
            "plan_name": "",
            "status": result.get("status", "generated"),
            "plan_text": result.get("plan_text", ""),
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
            "parsing_metadata": result.get("parsing_metadata", {}),
        }

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
                compatibility_payload = {
                    key: value
                    for key, value in payload.items()
                    if key not in _PLAN_OPTIONAL_SCHEMA_COLUMNS
                }
                logger.warning(
                    "[store] create_plan:legacy_schema_fallback athlete_id=%s intake_id=%s dropped_columns=%s",
                    athlete_id,
                    intake_id,
                    sorted(_PLAN_OPTIONAL_SCHEMA_COLUMNS),
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
            logger.exception("[store] create_plan:exception athlete_id=%s intake_id=%s", athlete_id, intake_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="create_plan failed",
            ) from exc

    def list_user_plans(self, athlete_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("plans")
            .select(PLAN_SUMMARY_SELECT)
            .eq("athlete_id", athlete_id)
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(response, "data", None) or []

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._select_first(self.client.table("plans").select("*").eq("id", plan_id))

    def get_latest_plan(self, athlete_id: str) -> dict[str, Any] | None:
        return self._select_first(
            self.client.table("plans")
            .select("*")
            .eq("athlete_id", athlete_id)
            .order("created_at", desc=True)
        )

    def create_or_get_generation_job(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        last_error: Exception | None = None

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
            return existing

        payload = {
            "athlete_id": athlete_id,
            "client_request_id": client_request_id,
            "request_payload": request_payload,
            "status": "queued",
            "attempt_count": 0,
            "heartbeat_at": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "intake_id": None,
            "stage1_result": None,
            "final_result": None,
            "plan_id": None,
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
            return existing
        if last_error and self._is_transient_store_error(last_error):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
            ) from last_error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to persist generation job",
        )

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
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

    def claim_generation_job(self, job_id: str, *, stale_after_seconds: int = 90) -> dict[str, Any] | None:
        try:
            job = self.get_generation_job(job_id)
            if not job:
                return None

            current_status = str(job.get("status") or "")
            current_attempt_count = int(job.get("attempt_count") or 0)
            now_iso = _utc_now_iso()
            now_dt = _parse_datetime(now_iso)
            heartbeat = _parse_datetime(job.get("heartbeat_at"))
            started_at = _parse_datetime(job.get("started_at"))
            last_progress_at = heartbeat or started_at
            is_stale_running = (
                current_status == "running"
                and now_dt is not None
                and last_progress_at is not None
                and (now_dt - last_progress_at).total_seconds() >= stale_after_seconds
            )

            if current_status not in {"queued", "running"}:
                return None
            if current_status == "running" and not is_stale_running:
                return None

            next_attempt_count = current_attempt_count + 1
            next_started_at = job.get("started_at") or now_iso
            payload = {
                "status": "running",
                "heartbeat_at": now_iso,
                "started_at": next_started_at,
                "error": None,
                "attempt_count": next_attempt_count,
            }
            self._run_with_transient_retry(
                operation="claim_generation_job:update",
                fn=lambda: self.client.table("generation_jobs")
                .update(payload)
                .eq("id", job_id)
                .eq("status", current_status)
                .eq("attempt_count", current_attempt_count)
                .execute(),
            )
            updated = self.get_generation_job(job_id)
            if not updated:
                return None
            if str(updated.get("status") or "") != "running":
                return None
            if int(updated.get("attempt_count") or 0) != next_attempt_count:
                return None
            if str(updated.get("heartbeat_at") or "") != now_iso:
                return None
            if str(updated.get("started_at") or "") != str(next_started_at):
                return None
            return updated
        except HTTPException:
            raise
        except _STORE_CLIENT_ERRORS as exc:
            if self._is_transient_store_error(exc):
                logger.warning(
                    "[store] claim_generation_job:transient_failure job_id=%s error_type=%s",
                    job_id,
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=GENERATION_JOB_UNAVAILABLE_DETAIL,
                ) from exc
            logger.exception("[store] claim_generation_job:exception job_id=%s", job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to claim generation job",
            ) from exc

    def update_generation_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        try:
            payload = dict(changes)
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

    def update_plan_stage2(self, plan_id: str, result: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "status": result.get("status", "generated"),
            "plan_text": result.get("plan_text", ""),
            "draft_plan_text": result.get("draft_plan_text", result.get("plan_text", "")),
            "final_plan_text": result.get("final_plan_text", result.get("plan_text", "")),
            "pdf_url": result.get("pdf_url"),
            "stage2_retry_text": result.get("stage2_retry_text", ""),
            "stage2_validator_report": result.get("stage2_validator_report", {}),
            "stage2_status": result.get("stage2_status", ""),
            "stage2_attempt_count": result.get("stage2_attempt_count", 0),
        }
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

    def list_admin_plans(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        response = (
            self.client.table("plans")
            .select(
                "id, athlete_id, full_name, fight_date, technical_style, plan_name, status, "
                "pdf_url, created_at, profiles!plans_athlete_id_fkey(email, full_name)"
            )
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return getattr(response, "data", None) or []

    def list_admin_athletes(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        response = (
            self.client.table("admin_athlete_rollups")
            .select("*")
            .order("updated_at", desc=True)
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
