from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from .auth import AuthenticatedUser
from .models import PlanRequest, ProfileUpdateRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DemoAuthService:
    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        normalized = token.strip().lower()
        if normalized == "demo-admin":
            return AuthenticatedUser(
                user_id="demo-admin",
                email="ops@unlxck.test",
                full_name="Demo Admin",
                metadata={"mode": "demo"},
            )
        if normalized in {"demo-athlete", "demo"}:
            return AuthenticatedUser(
                user_id="demo-athlete",
                email="athlete@example.com",
                full_name="Demo Athlete",
                metadata={"mode": "demo"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid demo authentication token",
        )


class DemoStore:
    def __init__(self):
        self._lock = Lock()
        self.profiles: dict[str, dict[str, Any]] = {}
        self.intakes: dict[str, list[dict[str, Any]]] = {}
        self.plans: dict[str, dict[str, Any]] = {}

    def ensure_profile(self, user: AuthenticatedUser) -> dict[str, Any]:
        with self._lock:
            existing = self.profiles.get(user.user_id)
            if existing:
                return dict(existing)
            role = "admin" if user.email.endswith("@unlxck.test") else "athlete"
            profile = {
                "id": user.user_id,
                "email": user.email,
                "role": role,
                "full_name": user.full_name,
                "technical_style": [],
                "tactical_style": [],
                "stance": "",
                "professional_status": "",
                "record_summary": "",
                "athlete_timezone": "",
                "athlete_locale": "",
                "onboarding_draft": None,
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.profiles[user.user_id] = profile
            return dict(profile)

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict[str, Any]:
        with self._lock:
            profile = self.profiles[athlete_id]
            fields = update.model_dump(mode="json", exclude_none=True)
            if "record" in fields:
                fields["record_summary"] = fields.pop("record")
            profile.update(fields)
            profile["updated_at"] = _now()
            return dict(profile)

    def get_latest_intake(self, athlete_id: str) -> dict[str, Any] | None:
        with self._lock:
            items = self.intakes.get(athlete_id, [])
            return dict(items[-1]) if items else None

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict[str, Any]:
        with self._lock:
            intake = {
                "id": str(uuid4()),
                "athlete_id": athlete_id,
                "fight_date": request.fight_date,
                "technical_style": request.athlete.technical_style,
                "intake": request.model_dump(mode="json"),
                "created_at": _now(),
            }
            self.intakes.setdefault(athlete_id, []).append(intake)
            return dict(intake)

    def create_plan(
        self,
        *,
        athlete_id: str,
        intake_id: str,
        request: PlanRequest,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            profile = self.profiles[athlete_id]
            plan_id = str(uuid4())
            row = {
                "id": plan_id,
                "athlete_id": athlete_id,
                "intake_id": intake_id,
                "fight_date": request.fight_date,
                "technical_style": request.athlete.technical_style,
                "status": result.get("status", "generated"),
                "plan_text": result.get("plan_text", ""),
                "draft_plan_text": result.get("draft_plan_text", result.get("plan_text", "")),
                "final_plan_text": result.get("final_plan_text", result.get("plan_text", "")),
                "coach_notes": result.get("coach_notes", ""),
                "pdf_url": result.get("pdf_url"),
                "why_log": result.get("why_log", {}),
                "planning_brief": result.get("planning_brief"),
                "stage2_payload": result.get("stage2_payload"),
                "stage2_handoff_text": result.get("stage2_handoff_text", ""),
                "stage2_retry_text": result.get("stage2_retry_text", ""),
                "stage2_validator_report": result.get("stage2_validator_report", {}),
                "stage2_status": result.get("stage2_status", ""),
                "stage2_attempt_count": result.get("stage2_attempt_count", 0),
                "created_at": _now(),
                "full_name": request.athlete.full_name or profile.get("full_name", ""),
            }
            self.plans[plan_id] = row
            return dict(row)

    def list_user_plans(self, athlete_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(plan) for plan in self.plans.values() if plan["athlete_id"] == athlete_id]
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.plans.get(plan_id)
            return dict(row) if row else None

    def update_plan_stage2(self, plan_id: str, result: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = self.plans.get(plan_id)
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
            row.update(
                {
                    "status": result.get("status", row.get("status", "generated")),
                    "plan_text": result.get("plan_text", row.get("plan_text", "")),
                    "draft_plan_text": result.get("draft_plan_text", row.get("draft_plan_text", row.get("plan_text", ""))),
                    "final_plan_text": result.get("final_plan_text", row.get("final_plan_text", row.get("plan_text", ""))),
                    "pdf_url": result.get("pdf_url"),
                    "stage2_retry_text": result.get("stage2_retry_text", ""),
                    "stage2_validator_report": result.get("stage2_validator_report", {}),
                    "stage2_status": result.get("stage2_status", ""),
                    "stage2_attempt_count": result.get("stage2_attempt_count", row.get("stage2_attempt_count", 0)),
                }
            )
            return dict(row)

    def list_admin_plans(self) -> list[dict[str, Any]]:
        with self._lock:
            rows: list[dict[str, Any]] = []
            for plan in self.plans.values():
                profile = self.profiles[plan["athlete_id"]]
                rows.append(
                    {
                        **plan,
                        "profiles": {
                            "email": profile["email"],
                            "full_name": profile["full_name"],
                        },
                    }
                )
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def list_admin_athletes(self) -> list[dict[str, Any]]:
        with self._lock:
            rows: list[dict[str, Any]] = []
            for profile in self.profiles.values():
                plans = sorted(
                    [plan for plan in self.plans.values() if plan["athlete_id"] == profile["id"]],
                    key=lambda row: row["created_at"],
                    reverse=True,
                )
                rows.append(
                    {
                        **profile,
                        "plan_count": len(plans),
                        "latest_plan_created_at": plans[0]["created_at"] if plans else None,
                    }
                )
        return sorted(rows, key=lambda row: row["updated_at"], reverse=True)

    def get_admin_athlete(self, athlete_id: str) -> dict[str, Any] | None:
        with self._lock:
            profile = self.profiles.get(athlete_id)
            if not profile:
                return None
            plans = sorted(
                [plan for plan in self.plans.values() if plan["athlete_id"] == athlete_id],
                key=lambda row: row["created_at"],
                reverse=True,
            )
            return {
                **profile,
                "plan_count": len(plans),
                "latest_plan_created_at": plans[0]["created_at"] if plans else None,
            }

    def clear_onboarding_draft(self, athlete_id: str) -> None:
        with self._lock:
            self.profiles[athlete_id]["onboarding_draft"] = None
            self.profiles[athlete_id]["updated_at"] = _now()


_DEMO_STORE = DemoStore()


def get_demo_store() -> DemoStore:
    return _DEMO_STORE
