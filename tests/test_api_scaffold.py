from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from api.app import create_app
from api.auth import AuthenticatedUser
from api.models import ManualStage2SubmissionRequest, PlanRequest, ProfileUpdateRequest
from api.stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError


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
            "onboarding_draft": None,
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

    def create_plan(self, *, athlete_id: str, intake_id: str, request: PlanRequest, result: dict) -> dict:
        profile = self.profiles[athlete_id]
        plan_id = f"plan_{uuid4().hex[:10]}"
        row = {
            "id": plan_id,
            "athlete_id": athlete_id,
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
            "full_name": profile["full_name"],
        }
        self.plans[plan_id] = row
        return row

    def list_user_plans(self, athlete_id: str) -> list[dict]:
        return [plan for plan in self.plans.values() if plan["athlete_id"] == athlete_id]

    def get_plan(self, plan_id: str) -> dict | None:
        return self.plans.get(plan_id)

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

    def list_admin_plans(self) -> list[dict]:
        rows = []
        for plan in self.plans.values():
            profile = self.profiles[plan["athlete_id"]]
            rows.append({**plan, "profiles": {"email": profile["email"], "full_name": profile["full_name"]}})
        return rows

    def list_admin_athletes(self) -> list[dict]:
        rows = []
        for profile in self.profiles.values():
            plans = self.list_user_plans(profile["id"])
            rows.append({
                **profile,
                "plan_count": len(plans),
                "latest_plan_created_at": plans[-1]["created_at"] if plans else None,
            })
        return rows

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


def _build_request() -> PlanRequest:
    return PlanRequest(
        athlete={
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
        fight_date="2026-04-18",
        weekly_training_frequency=4,
        training_availability=["Monday", "Tuesday", "Thursday", "Saturday"],
        equipment_access=["barbell", "heavy_bag"],
        key_goals=["power", "conditioning"],
        weak_areas=["gas_tank"],
        injuries="mild left shoulder irritation",
        rounds_format="3 x 3",
        fatigue_level="moderate",
    )


async def _planner(payload: dict) -> dict:
    return stage1_result()


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


def test_plan_request_to_payload_uses_existing_parser_labels():
    payload = _build_request().to_payload()
    labels = {field["label"] for field in payload["data"]["fields"]}

    assert "Full name" in labels
    assert "When is your next fight?" in labels
    assert "Training Availability" in labels
    assert "Athlete Time Zone" in labels
    assert "Sessions per Week" in labels


def test_record_format_validation_rejects_invalid_values():
    try:
        PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
                "record": "five and one",
            },
            fight_date="2026-04-18",
        )
    except Exception as exc:
        assert "x-x or x-x-x" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("invalid record format should be rejected")


def test_auth_is_required_for_me_route():
    client, _, _ = _build_client()

    response = client.get("/api/me")

    assert response.status_code == 401


def test_generate_plan_persists_validated_final_plan_and_history():
    client, store, stage2 = _build_client()
    payload = _build_request().model_dump(mode="json")

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["outputs"]["plan_text"] == "# Final Plan"
    assert body["outputs"]["pdf_url"] is None
    assert body["status"] == "ready"
    assert body["admin_outputs"] is None
    assert store.get_latest_intake("athlete-1")["intake"]["fight_date"] == "2026-04-18"
    assert len(store.list_user_plans("athlete-1")) == 1
    saved = next(iter(store.plans.values()))
    assert saved["draft_plan_text"] == "# Stage 1 Draft"
    assert saved["final_plan_text"] == "# Final Plan"
    assert saved["stage2_status"] == "stage2_pass"
    assert saved["pdf_url"] is None
    assert stage2.calls[0]["stage2_handoff_text"] == "handoff"


def test_generate_plan_persists_retry_pass_result():
    client, store, _ = _build_client(
        FakeStage2Automator(
            result=finalized_result(
                plan_text="# Final Retry Plan",
                final_plan_text="# Final Retry Plan",
                stage2_status="stage2_retry_pass",
                stage2_retry_text="repair prompt",
                stage2_attempt_count=2,
            )
        )
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 201
    saved = next(iter(store.plans.values()))
    assert saved["plan_text"] == "# Final Retry Plan"
    assert saved["stage2_status"] == "stage2_retry_pass"
    assert saved["stage2_retry_text"] == "repair prompt"
    assert saved["stage2_attempt_count"] == 2


def test_generate_plan_returns_review_required_when_stage2_needs_manual_review():
    client, store, _ = _build_client(
        FakeStage2Automator(
            result=finalized_result(
                status="review_required",
                plan_text="",
                final_plan_text="# Failed Stage 2 Output",
                stage2_status="stage2_failed",
                stage2_retry_text="repair prompt",
                stage2_validator_report={"errors": [{"code": "restriction_violation"}], "warnings": []},
                stage2_attempt_count=2,
            )
        )
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "review_required"
    assert body["outputs"]["plan_text"] == ""
    saved = next(iter(store.plans.values()))
    assert saved["final_plan_text"] == "# Failed Stage 2 Output"
    assert saved["stage2_status"] == "stage2_failed"


def test_stage2_unavailable_returns_503_without_persisting_plan():
    client, store, _ = _build_client(
        FakeStage2Automator(
            error=Stage2AutomationUnavailableError("OPENAI_API_KEY is required for automated Stage 2 finalization.")
        )
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 503
    assert len(store.plans) == 0


def test_stage2_gateway_failure_returns_502_without_persisting_plan():
    client, store, _ = _build_client(
        FakeStage2Automator(error=Stage2AutomationError("Stage 2 model request failed"))
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 502
    assert len(store.plans) == 0


def test_athlete_cannot_read_another_athlete_plan():
    client, store, _ = _build_client()
    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    store.ensure_profile(other_user)
    plan = store.create_plan(
        athlete_id="athlete-2",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 403


def test_admin_can_view_internal_plan_outputs():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            stage2_retry_text="repair prompt",
            planning_brief={"schema_version": "planning_brief.v1"},
        ),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    admin_outputs = response.json()["admin_outputs"]
    assert admin_outputs["stage2_payload"] == {"ok": True}
    assert admin_outputs["draft_plan_text"] == "# Stage 1 Draft"
    assert admin_outputs["stage2_retry_text"] == "repair prompt"
    assert admin_outputs["stage2_status"] == "stage2_pass"


def test_admin_endpoints_require_admin_role():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)

    forbidden = client.get("/api/admin/athletes", headers={"Authorization": "Bearer athlete-token"})
    allowed = client.get("/api/admin/athletes", headers={"Authorization": "Bearer admin-token"})

    assert forbidden.status_code == 403
    assert allowed.status_code == 200


def test_legacy_rows_with_only_plan_text_remain_readable():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    legacy = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=stage1_result(),
    )

    response = client.get(
        f"/api/plans/{legacy['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 200
    assert response.json()["outputs"]["plan_text"] == "# Stage 1 Draft"


def test_manual_stage2_submission_publishes_validated_admin_result():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="",
            stage2_status="stage2_failed",
            stage2_retry_text="repair prompt",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(final_plan_text="# Manual GPT Final").model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["outputs"]["plan_text"] == "# Manual GPT Final"
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_retry_pass"
    saved = store.get_plan(plan["id"])
    assert saved["plan_text"] == "# Manual GPT Final"
    assert saved["stage2_retry_text"] == ""


def test_manual_stage2_submission_generates_retry_prompt_when_output_needs_revision():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="",
            stage2_status="stage2_failed",
            stage2_retry_text="",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(
            final_plan_text="## PHASE 2: SPP\n- Bike sprint or bag sprint depending on access"
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["outputs"]["plan_text"] == ""
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_retry_required"
    assert body["admin_outputs"]["stage2_retry_text"]


def test_manual_stage2_submission_requires_admin_role():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer athlete-token"},
        json=ManualStage2SubmissionRequest(final_plan_text="# Manual GPT Final").model_dump(mode="json"),
    )

    assert response.status_code == 403


def test_admin_can_approve_review_required_plan_for_release():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    store.ensure_profile(athlete)
    plan = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(
            status="review_required",
            plan_text="",
            final_plan_text="# Held Stage 2 Output",
            stage2_status="stage2_failed",
            stage2_retry_text="repair prompt",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/approve",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["outputs"]["plan_text"] == "# Held Stage 2 Output"
    assert body["admin_outputs"]["stage2_status"] == "admin_review_approved"

