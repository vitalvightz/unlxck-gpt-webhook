from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import create_app
from api.auth import AuthenticatedUser
from api.models import PlanRequest, ProfileUpdateRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FakeAuthService:
    users_by_token: dict[str, AuthenticatedUser]

    def get_user_from_token(self, token: str) -> AuthenticatedUser:
        user = self.users_by_token.get(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="authentication required",
            )
        return user


class FakeStore:
    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.intakes: dict[str, list[dict]] = {}
        self.plans: dict[str, dict] = {}
        self.generation_jobs: dict[str, dict] = {}

    def validate_runtime_schema(self) -> None:
        return None

    def ensure_profile(self, user: AuthenticatedUser) -> dict:
        existing = self.profiles.get(user.user_id)
        if existing:
            return existing
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
            "appearance_mode": "dark",
            "onboarding_draft": None,
            "nutrition_profile": {},
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.profiles[user.user_id] = profile
        return profile

    def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict:
        profile = self.profiles[athlete_id]
        data = update.model_dump(mode="json", exclude_none=True)
        if "record" in data:
            data["record_summary"] = data.pop("record")
        profile.update(data)
        profile["updated_at"] = _now()
        return profile

    def get_latest_intake(self, athlete_id: str) -> dict | None:
        items = self.intakes.get(athlete_id, [])
        return items[-1] if items else None

    def create_intake(self, athlete_id: str, request: PlanRequest) -> dict:
        intake = {
            "id": f"intake_{uuid4().hex[:10]}",
            "athlete_id": athlete_id,
            "fight_date": request.fight_date,
            "technical_style": request.athlete.technical_style,
            "intake": request.model_dump(mode="json"),
            "created_at": _now(),
        }
        self.intakes.setdefault(athlete_id, []).append(intake)
        return intake

    def update_intake(
        self,
        intake_id: str,
        *,
        intake: dict,
        fight_date: str | None,
        technical_style: list[str],
    ) -> dict:
        for athlete_intakes in self.intakes.values():
            for row in athlete_intakes:
                if row["id"] != intake_id:
                    continue
                row["intake"] = intake
                row["fight_date"] = fight_date
                row["technical_style"] = technical_style
                row["updated_at"] = _now()
                return row
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="intake not found")

    def create_plan(self, *, athlete_id: str, intake_id: str, request: PlanRequest, result: dict) -> dict:
        profile = self.profiles[athlete_id]
        plan_id = f"plan_{uuid4().hex[:10]}"
        row = {
            "id": plan_id,
            "athlete_id": athlete_id,
            "intake_id": intake_id,
            "fight_date": request.fight_date,
            "technical_style": request.athlete.technical_style,
            "plan_name": "",
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
            "full_name": profile["full_name"],
        }
        self.plans[plan_id] = row
        return row

    def list_user_plans(self, athlete_id: str) -> list[dict]:
        rows = [plan for plan in self.plans.values() if plan["athlete_id"] == athlete_id]
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def get_plan(self, plan_id: str) -> dict | None:
        return self.plans.get(plan_id)

    def get_latest_plan(self, athlete_id: str) -> dict | None:
        plans = self.list_user_plans(athlete_id)
        return plans[0] if plans else None

    def rename_plan(self, plan_id: str, plan_name: str) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        row["plan_name"] = plan_name
        return row

    def delete_plan(self, plan_id: str) -> None:
        if plan_id not in self.plans:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        del self.plans[plan_id]

    def create_or_get_generation_job(
        self,
        *,
        athlete_id: str,
        client_request_id: str,
        source: str,
        request_payload: dict,
    ) -> dict:
        for job in self.generation_jobs.values():
            if job["athlete_id"] == athlete_id and job["client_request_id"] == client_request_id:
                return dict(job)
        now = _now()
        job_id = f"job_{uuid4().hex[:10]}"
        job = {
            "id": job_id,
            "athlete_id": athlete_id,
            "client_request_id": client_request_id,
            "source": source,
            "request_payload": request_payload,
            "status": "queued",
            "error": None,
            "intake_id": None,
            "stage1_result": None,
            "final_result": None,
            "plan_id": None,
            "attempt_count": 0,
            "heartbeat_at": None,
            "started_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.generation_jobs[job_id] = job
        return dict(job)

    def get_generation_job(self, job_id: str) -> dict | None:
        job = self.generation_jobs.get(job_id)
        return dict(job) if job else None

    def list_claimable_generation_jobs(self, *, limit: int = 20, stale_after_seconds: int = 90) -> list[dict]:
        now = datetime.now(timezone.utc)
        rows = []
        for job in self.generation_jobs.values():
            status_value = str(job.get("status") or "")
            if status_value == "queued":
                rows.append(dict(job))
                continue
            if status_value != "running":
                continue
            heartbeat_raw = job.get("heartbeat_at")
            started_raw = job.get("started_at")
            heartbeat = (
                datetime.fromisoformat(str(heartbeat_raw).replace("Z", "+00:00"))
                if isinstance(heartbeat_raw, str) and heartbeat_raw
                else None
            )
            started_at = (
                datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
                if isinstance(started_raw, str) and started_raw
                else None
            )
            last_progress_at = heartbeat or started_at
            if last_progress_at and (now - last_progress_at).total_seconds() >= stale_after_seconds:
                rows.append(dict(job))
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
        return rows[:limit]

    def claim_generation_job(self, job_id: str, *, stale_after_seconds: int = 90) -> dict | None:
        job = self.generation_jobs.get(job_id)
        if not job:
            return None
        heartbeat_raw = job.get("heartbeat_at")
        heartbeat = None
        if isinstance(heartbeat_raw, str) and heartbeat_raw:
            heartbeat = datetime.fromisoformat(heartbeat_raw.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        is_stale_running = job["status"] == "running" and (
            heartbeat is None or (now - heartbeat).total_seconds() >= stale_after_seconds
        )
        if job["status"] not in {"queued", "running"}:
            return None
        if job["status"] == "running" and not is_stale_running:
            return None
        now_iso = _now()
        job["status"] = "running"
        job["heartbeat_at"] = now_iso
        job["started_at"] = job["started_at"] or now_iso
        job["attempt_count"] = int(job.get("attempt_count") or 0) + 1
        job["error"] = None
        job["updated_at"] = now_iso
        return dict(job)

    def update_generation_job(self, job_id: str, **changes: dict) -> dict:
        job = self.generation_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generation job not found")
        job.update(changes)
        job["updated_at"] = _now()
        return dict(job)

    def update_plan_stage2(self, plan_id: str, result: dict) -> dict:
        row = self.plans.get(plan_id)
        if not row:
            return None
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
        return row

    def list_admin_plans(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = []
        for plan in self.plans.values():
            profile = self.profiles[plan["athlete_id"]]
            rows.append({**plan, "profiles": {"email": profile["email"], "full_name": profile["full_name"]}})
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return rows[offset:offset + limit]

    def list_admin_athletes(self, *, limit: int = 50, offset: int = 0) -> list[dict]:
        rows = []
        for profile in self.profiles.values():
            plans = self.list_user_plans(profile["id"])
            rows.append({
                **profile,
                "plan_count": len(plans),
                "latest_plan_created_at": plans[-1]["created_at"] if plans else None,
            })
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        return rows[offset:offset + limit]

    def get_admin_athlete(self, athlete_id: str) -> dict | None:
        profile = self.profiles.get(athlete_id)
        if not profile:
            return None
        plans = self.list_user_plans(athlete_id)
        return {
            **profile,
            "plan_count": len(plans),
            "latest_plan_created_at": plans[-1]["created_at"] if plans else None,
        }

    def clear_onboarding_draft(self, athlete_id: str) -> None:
        self.profiles[athlete_id]["onboarding_draft"] = None


@dataclass
class FakeStage2Automator:
    result: dict | None = None
    error: Exception | None = None
    calls: list[dict] = field(default_factory=list)

    async def finalize(self, *, stage1_result: dict) -> dict:
        self.calls.append(stage1_result)
        if self.error:
            raise self.error
        return {**stage1_result, **(self.result or {})}


def _build_request(overrides: dict | None = None) -> PlanRequest:
    payload = {
        "athlete": {
            "full_name": "Ari Mensah",
            "age": 27,
            "weight_kg": 72.5,
            "target_weight_kg": 70.0,
            "height_cm": 178,
            "technical_style": ["boxing"],
            "tactical_style": ["pressure_fighter"],
            "professional_status": "amateur",
            "record": "5-1",
            "athlete_timezone": "Europe/London",
        },
        "fight_date": "2026-04-18",
        "weekly_training_frequency": 4,
        "training_availability": ["Monday", "Tuesday", "Thursday", "Saturday"],
        "hard_sparring_days": ["Tuesday", "Saturday"],
        "technical_skill_days": ["Monday"],
        "equipment_access": ["barbell", "heavy_bag"],
        "key_goals": ["power", "conditioning"],
        "weak_areas": ["gas_tank"],
        "injuries": "mild left shoulder irritation",
        "rounds_format": "3 x 3",
        "fatigue_level": "moderate",
    }
    if overrides:
        merged = copy.deepcopy(overrides)
        athlete_overrides = merged.pop("athlete", None)
        if athlete_overrides:
            payload["athlete"].update(athlete_overrides)
        payload.update(merged)
    return PlanRequest.model_validate(payload)


def stage1_result() -> dict:
    return {
        "plan_text": "# Stage 1 Draft",
        "coach_notes": "### Coach Review",
        "pdf_url": "https://example.com/stage1.pdf",
        "why_log": {"strength": {}},
        "stage2_payload": {"ok": True},
        "planning_brief": {"schema_version": "planning_brief.v1", "main_limiter": "conditioning"},
        "stage2_handoff_text": "handoff",
    }


def finalized_result(**overrides: object) -> dict:
    base = {
        **stage1_result(),
        "status": "ready",
        "plan_text": "# Final Plan",
        "draft_plan_text": "# Stage 1 Draft",
        "final_plan_text": "# Final Plan",
        "pdf_url": None,
        "stage2_status": "stage2_pass",
        "stage2_validator_report": {"errors": [], "warnings": []},
        "stage2_retry_text": "",
        "stage2_attempt_count": 1,
    }
    return {**base, **overrides}


def advisory_planning_brief(
    *,
    phase: str = "TAPER",
    stage_key: str = "fight_week_survival_rhythm",
    days_until_fight: int = 6,
    fatigue: str = "low",
    readiness_flags: list[str] | None = None,
    injuries: list[str] | None = None,
    weight_cut_pct: float = 0.0,
    hard_sparring_days: list[str] | None = None,
) -> dict:
    hard_days = hard_sparring_days or ["Tuesday", "Thursday"]
    return {
        "schema_version": "planning_brief.v1",
        "athlete_snapshot": {
            "sport": "boxing",
            "days_until_fight": days_until_fight,
            "fatigue": fatigue,
            "short_notice": days_until_fight <= 14,
            "readiness_flags": readiness_flags or [],
            "injuries": injuries or [],
            "weight_cut_pct": weight_cut_pct,
            "hard_sparring_days": hard_days,
            "technical_skill_days": ["Monday"],
        },
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": phase,
                    "week_index": 1,
                    "phase_week_index": 1,
                    "phase_week_total": 1,
                    "stage_key": stage_key,
                    "declared_hard_sparring_days": hard_days,
                    "declared_technical_skill_days": ["Monday"],
                    "declared_training_days": ["Monday", "Tuesday", "Thursday", "Saturday"],
                    "session_roles": [],
                    "suppressed_roles": [],
                }
            ]
        },
    }


def _presentation_ready_plan(*, heading: str, support_note: str) -> str:
    return (
        f"## {heading}\n"
        "### Week 1\n"
        "#### Strength\n"
        "- Trap Bar Deadlift - 4x3\n"
        "#### Recovery\n"
        f"- {support_note}\n"
        "#### Fight-pace conditioning\n"
        "- Bag Rounds - 5 x 3 min\n"
    )


def _review_required_result(*, final_plan_text: str, warning_code: str) -> dict:
    return finalized_result(
        status="review_required",
        plan_text="",
        final_plan_text=final_plan_text,
        stage2_status="stage2_failed",
        stage2_retry_text="repair prompt",
        stage2_validator_report={"errors": [], "warnings": [{"code": warning_code}]},
        stage2_attempt_count=2,
    )


@dataclass(frozen=True)
class SystemScenario:
    key: str
    request_overrides: dict
    automator_result: dict
    expected_status: str
    expected_review_code: str | None
    expected_resolution: str | None
    support_marker: str


SYSTEM_SCENARIOS = [
    SystemScenario(
        key="high_fatigue",
        request_overrides={
            "fatigue_level": "high",
            "weekly_training_frequency": 5,
            "training_availability": ["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"],
        },
        automator_result=finalized_result(
            plan_text=_presentation_ready_plan(
                heading="PHASE 2: SPP",
                support_note="High fatigue this week, so keep the recovery day obvious and trim optional density first.",
            ),
            final_plan_text=_presentation_ready_plan(
                heading="PHASE 2: SPP",
                support_note="High fatigue this week, so keep the recovery day obvious and trim optional density first.",
            ),
        ),
        expected_status="ready",
        expected_review_code=None,
        expected_resolution=None,
        support_marker="High fatigue this week",
    ),
    SystemScenario(
        key="messy_injury_input",
        request_overrides={
            "injuries": "none / right shoulder cranky after pads + left wrist sore on hooks",
            "equipment_access": ["bands", "heavy_bag", "bodyweight"],
        },
        automator_result=finalized_result(
            plan_text=_presentation_ready_plan(
                heading="PHASE 1: GPP",
                support_note="Shoulder and wrist management stay in the week, but the main session remains decisive.",
            ),
            final_plan_text=_presentation_ready_plan(
                heading="PHASE 1: GPP",
                support_note="Shoulder and wrist management stay in the week, but the main session remains decisive.",
            ),
        ),
        expected_status="ready",
        expected_review_code=None,
        expected_resolution=None,
        support_marker="Shoulder and wrist management",
    ),
    SystemScenario(
        key="severe_cut_pressure",
        request_overrides={
            "athlete": {"weight_kg": 72.0, "target_weight_kg": 66.0},
            "fatigue_level": "moderate",
            "fight_date": "2026-04-05",
        },
        automator_result=finalized_result(
            plan_text=(
                "## Camp Summary\n"
                "- Active weight-cut stress is part of this camp, so protect freshness and avoid optional fatigue.\n"
                "## Nutrition\n"
                "- Prioritize carbs, fluids, and sodium around key sessions to preserve strength expression and conditioning tolerance.\n"
            ),
            final_plan_text=(
                "## Camp Summary\n"
                "- Active weight-cut stress is part of this camp, so protect freshness and avoid optional fatigue.\n"
                "## Nutrition\n"
                "- Prioritize carbs, fluids, and sodium around key sessions to preserve strength expression and conditioning tolerance.\n"
            ),
        ),
        expected_status="ready",
        expected_review_code=None,
        expected_resolution=None,
        support_marker="Active weight-cut stress",
    ),
    SystemScenario(
        key="limited_equipment_hold",
        request_overrides={
            "equipment_access": ["bands", "bodyweight"],
            "weekly_training_frequency": 3,
            "training_availability": ["Tuesday", "Thursday", "Saturday"],
        },
        automator_result=_review_required_result(
            final_plan_text="## PHASE 2: SPP\n- Heavy Bag Sprint Rounds - 6 x 15 sec",
            warning_code="equipment_incongruent_selection",
        ),
        expected_status="review_required",
        expected_review_code="equipment_incongruent_selection",
        expected_resolution="approve",
        support_marker="Heavy Bag Sprint Rounds",
    ),
    SystemScenario(
        key="short_notice_contradictory",
        request_overrides={
            "fight_date": "2026-03-24",
            "weekly_training_frequency": 6,
            "training_availability": ["Monday", "Wednesday"],
            "equipment_access": ["assault_bike", "bands", "bodyweight"],
        },
        automator_result=_review_required_result(
            final_plan_text="## PHASE 3: TAPER\n### Week 5\n#### Strength\n- Dead Bug - 2x8",
            warning_code="late_camp_session_incomplete",
        ),
        expected_status="review_required",
        expected_review_code="late_camp_session_incomplete",
        expected_resolution="manual_stage2",
        support_marker="Dead Bug - 2x8",
    ),
]


def _planner(payload: dict) -> dict:
    return stage1_result()


def _start_generation(client: TestClient, request: PlanRequest | None = None) -> tuple[dict, dict]:
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=(request or _build_request()).model_dump(mode="json"),
    )
    assert response.status_code == 202
    job_body = response.json()
    job_response = client.get(
        f"/api/generation-jobs/{job_body['job_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert job_response.status_code == 200
    return job_body, job_response.json()


def _build_client(automator: FakeStage2Automator | None = None) -> tuple[TestClient, FakeStore, FakeStage2Automator]:
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    admin = AuthenticatedUser(
        user_id="admin-1",
        email="ops@unlxck.test",
        full_name="Ops Admin",
        metadata={},
    )
    store = FakeStore()
    stage2 = automator or FakeStage2Automator(result=finalized_result())
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=stage2,
        )
    )
    return client, store, stage2
