from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from fastapi import HTTPException, status
from supabase import Client, create_client

from .auth import AuthenticatedUser
from .models import PlanRequest, ProfileUpdateRequest

logger = logging.getLogger(__name__)

_TRANSIENT_SUPABASE_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
)


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

    def update_plan_stage2(self, plan_id: str, result: dict[str, Any]) -> dict[str, Any]: ...

    def list_admin_plans(self) -> list[dict[str, Any]]: ...

    def list_admin_athletes(self) -> list[dict[str, Any]]: ...

    def get_admin_athlete(self, athlete_id: str) -> dict[str, Any] | None: ...

    def clear_onboarding_draft(self, athlete_id: str) -> None: ...


def _encode_structured_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


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
        return isinstance(exc, _TRANSIENT_SUPABASE_ERRORS)

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
            except Exception as exc:
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
            except Exception as exc:
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
        except Exception as exc:
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
        except Exception:
            logger.exception("[store] update_profile:exception athlete_id=%s", athlete_id)
            raise

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
        except Exception as exc:
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
        }
        try:
            logger.info(
                "[store] create_plan:start athlete_id=%s intake_id=%s status=%s stage2_status=%s",
                athlete_id,
                intake_id,
                payload["status"],
                payload["stage2_status"],
            )
            response = self.client.table("plans").insert(payload).execute()
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
            logger.info(
                "[store] create_plan:success athlete_id=%s intake_id=%s plan_id=%s",
                athlete_id,
                intake_id,
                rows[0].get("id"),
            )
            return rows[0]
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("[store] create_plan:exception athlete_id=%s intake_id=%s", athlete_id, intake_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="create_plan failed",
            ) from exc

    def list_user_plans(self, athlete_id: str) -> list[dict[str, Any]]:
        response = (
            self.client.table("plans")
            .select("*")
            .eq("athlete_id", athlete_id)
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(response, "data", None) or []

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._select_first(self.client.table("plans").select("*").eq("id", plan_id))

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
        except Exception:
            logger.exception("[store] update_plan_stage2:exception plan_id=%s", plan_id)
            raise

    def list_admin_plans(self) -> list[dict[str, Any]]:
        response = (
            self.client.table("plans")
            .select("*, profiles!plans_athlete_id_fkey(email, full_name)")
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(response, "data", None) or []

    def list_admin_athletes(self) -> list[dict[str, Any]]:
        response = (
            self.client.table("profiles")
            .select("*")
            .order("updated_at", desc=True)
            .execute()
        )
        athletes = getattr(response, "data", None) or []
        for athlete in athletes:
            plans = self.list_user_plans(str(athlete["id"]))
            athlete["plan_count"] = len(plans)
            athlete["latest_plan_created_at"] = plans[0]["created_at"] if plans else None
        return athletes

    def get_admin_athlete(self, athlete_id: str) -> dict[str, Any] | None:
        profile = self._select_first(self.client.table("profiles").select("*").eq("id", athlete_id))
        if not profile:
            return None
        plans = self.list_user_plans(athlete_id)
        profile["plan_count"] = len(plans)
        profile["latest_plan_created_at"] = plans[0]["created_at"] if plans else None
        return profile

    def clear_onboarding_draft(self, athlete_id: str) -> None:
        try:
            logger.info("[store] clear_onboarding_draft:start athlete_id=%s", athlete_id)
            self.client.table("profiles").update({"onboarding_draft": None}).eq("id", athlete_id).execute()
            logger.info("[store] clear_onboarding_draft:success athlete_id=%s", athlete_id)
        except Exception:
            logger.exception("[store] clear_onboarding_draft:exception athlete_id=%s", athlete_id)
            raise
