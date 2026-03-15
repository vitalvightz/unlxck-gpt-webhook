from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import HTTPException, status
from supabase import Client, create_client

from .auth import AuthenticatedUser
from .models import PlanRequest, ProfileUpdateRequest


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
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url:
            raise RuntimeError(
                "SUPABASE_URL is required but not set. "
                "Set it in your .env file or environment before starting the server."
            )
        if not key:
            raise RuntimeError(
                "SUPABASE_SERVICE_ROLE_KEY is required for store operations but not set. "
                "This key is used for privileged writes and must not be replaced by SUPABASE_ANON_KEY. "
                "Set it in your .env file or environment before starting the server."
            )
        admin_emails = {
            email.strip().lower()
            for email in os.getenv("UNLXCK_ADMIN_EMAILS", "").split(",")
            if email.strip()
        }
        return cls(create_client(url, key), admin_emails)

    def _select_first(self, query) -> dict[str, Any] | None:
        response = query.limit(1).execute()
        rows = getattr(response, "data", None) or []
        return rows[0] if rows else None

    def _require_profile(self, athlete_id: str) -> dict[str, Any]:
        profile = self._select_first(self.client.table("profiles").select("*").eq("id", athlete_id))
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
        return profile

    def _default_role_for(self, user: AuthenticatedUser) -> str:
        return "admin" if user.email.lower() in self.admin_emails else "athlete"

    def ensure_profile(self, user: AuthenticatedUser) -> dict[str, Any]:
        existing = self._select_first(self.client.table("profiles").select("*").eq("id", user.user_id))
        payload = {
            "id": user.user_id,
            "email": user.email,
            "full_name": (existing or {}).get("full_name") or user.full_name,
            "role": (existing or {}).get("role") or self._default_role_for(user),
            "technical_style": (existing or {}).get("technical_style") or [],
            "tactical_style": (existing or {}).get("tactical_style") or [],
            "stance": (existing or {}).get("stance") or "",
            "professional_status": (existing or {}).get("professional_status") or "",
            "record_summary": (existing or {}).get("record_summary") or "",
            "athlete_timezone": (existing or {}).get("athlete_timezone") or "",
            "athlete_locale": (existing or {}).get("athlete_locale") or "",
            "onboarding_draft": (existing or {}).get("onboarding_draft"),
        }
        self.client.table("profiles").upsert(payload, on_conflict="id").execute()
        return self._require_profile(user.user_id)

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict[str, Any]:
        fields = update.model_dump(mode="json", exclude_none=True)
        if "record" in fields:
            fields["record_summary"] = fields.pop("record")
        if not fields:
            return self._require_profile(athlete_id)
        self.client.table("profiles").update(fields).eq("id", athlete_id).execute()
        return self._require_profile(athlete_id)

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
        response = self.client.table("athlete_intakes").insert(payload).execute()
        rows = getattr(response, "data", None) or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to persist intake",
            )
        return rows[0]

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
        response = self.client.table("plans").insert(payload).execute()
        rows = getattr(response, "data", None) or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to persist plan",
            )
        return rows[0]

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
        self.client.table("plans").update(payload).eq("id", plan_id).execute()
        updated = self.get_plan(plan_id)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="plan not found",
            )
        return updated

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

    def clear_onboarding_draft(self, athlete_id: str) -> None:
        self.client.table("profiles").update({"onboarding_draft": None}).eq("id", athlete_id).execute()
