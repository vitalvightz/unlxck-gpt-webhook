from __future__ import annotations

import copy
import importlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import create_app
from api.auth import AuthenticatedUser
from api.models import ManualStage2SubmissionRequest, PlanRequest, ProfileUpdateRequest
from api.stage2_automation import Stage2AutomationError, Stage2AutomationUnavailableError
from conftest import RENDER_BACKEND_URL


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

    def get_latest_plan(self, athlete_id: str) -> dict | None:
        plans = self.list_user_plans(athlete_id)
        return plans[0] if plans else None

    def delete_plan(self, plan_id: str) -> None:
        row = self.plans.pop(plan_id, None)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")

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


def test_record_format_validation_accepts_valid_formats():
    for record in ("5-1", "12-2-1", "0-0", "10-0-3"):
        req = PlanRequest(
            athlete={
                "full_name": "Ari Mensah",
                "technical_style": ["boxing"],
                "record": record,
            },
            fight_date="2026-04-18",
        )
        assert req.athlete.record == record


def test_record_format_validation_accepts_empty_record():
    req = PlanRequest(
        athlete={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "record": "",
        },
        fight_date="2026-04-18",
    )
    assert req.athlete.record == ""


def test_record_format_validation_rejects_partial_format():
    for bad in ("5-", "-1", "5", "5-1-2-3"):
        try:
            PlanRequest(
                athlete={
                    "full_name": "Ari Mensah",
                    "technical_style": ["boxing"],
                    "record": bad,
                },
                fight_date="2026-04-18",
            )
        except Exception as exc:
            assert "x-x or x-x-x" in str(exc)
        else:  # pragma: no cover - explicit failure path
            raise AssertionError(f"record '{bad}' should be rejected")


def test_auth_is_required_for_me_route():
    client, _, _ = _build_client()

    response = client.get("/api/me")

    assert response.status_code == 401


def test_request_id_header_is_attached_to_error_responses():
    client, _, _ = _build_client()

    response = client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert len(response.headers["x-request-id"]) == 8


def test_request_middleware_returns_json_request_id_for_unhandled_exceptions():
    app = create_app(
        store=FakeStore(),
        auth_service=FakeAuthService({}),
        planner=_planner,
        stage2_automator=FakeStage2Automator(result=finalized_result()),
    )

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert len(response.json()["request_id"]) == 8


def test_admin_athlete_profile_includes_latest_intake_details():
    client, store, _ = _build_client()

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json={
            "full_name": "Ari Mensah",
            "technical_style": ["boxing"],
            "tactical_style": ["pressure_fighter"],
            "stance": "orthodox",
            "professional_status": "amateur",
            "record": "5-1",
            "athlete_timezone": "Europe/London",
            "athlete_locale": "en-GB",
        },
    )
    assert response.status_code == 200

    generate_response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json={
            "athlete": {
                "full_name": "Ari Mensah",
                "age": 29,
                "height_cm": 178,
                "weight_kg": 74,
                "target_weight_kg": 72,
                "technical_style": ["boxing"],
                "tactical_style": ["pressure_fighter"],
                "stance": "orthodox",
                "professional_status": "amateur",
                "record": "5-1",
                "athlete_timezone": "Europe/London",
                "athlete_locale": "en-GB",
            },
            "fight_date": "2026-04-18",
            "rounds_format": "3 x 3",
            "weekly_training_frequency": 5,
            "fatigue_level": "moderate",
            "equipment_access": ["heavy_bag", "weights"],
            "training_availability": ["Monday", "Wednesday"],
            "hard_sparring_days": ["Friday"],
            "technical_skill_days": ["Tuesday"],
            "injuries": "Left shoulder management",
            "key_goals": ["conditioning", "fight_sharpness"],
            "weak_areas": ["defense", "gas_tank"],
            "training_preference": "Short, intense pads and bag rounds.",
            "mindset_challenges": "Starts too fast in the first round.",
            "notes": "Loved reactive defense work in the last camp.",
        },
    )
    assert generate_response.status_code == 202

    admin_response = client.get(
        "/api/admin/athletes/athlete-1",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert admin_response.status_code == 200
    payload = admin_response.json()
    assert payload["technical_style"] == ["boxing"]
    assert payload["tactical_style"] == ["pressure_fighter"]
    assert payload["stance"] == "orthodox"
    assert payload["professional_status"] == "amateur"
    assert payload["record"] == "5-1"
    assert payload["athlete_locale"] == "en-GB"
    assert payload["latest_intake"]["athlete"]["age"] == 29
    assert payload["latest_intake"]["equipment_access"] == ["heavy_bag", "weights"]
    assert payload["latest_intake"]["training_preference"] == "Short, intense pads and bag rounds."


def test_runtime_app_falls_back_to_health_endpoint_when_supabase_config_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UNLXCK_DEMO_MODE", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    reloaded = importlib.reload(app_module)

    client = TestClient(reloaded.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "app": "unlxck-fight-camp-api",
        "detail": "missing supabase configuration",
    }


def test_cors_allows_normalized_production_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://unlxck-gpt-webhook.vercel.app/onboarding/")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": "https://unlxck-gpt-webhook.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://unlxck-gpt-webhook.vercel.app"


def test_cors_allows_regex_configured_preview_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": "https://unlxck-gpt-webhook-git-feature-branch.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://unlxck-gpt-webhook-git-feature-branch.vercel.app"
    )


def test_cors_allows_host_only_origin_configuration(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGINS", "unlxck-gpt-webhook.vercel.app")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": "https://unlxck-gpt-webhook.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://unlxck-gpt-webhook.vercel.app"


def test_cors_does_not_allow_render_origin_when_only_vercel_origin_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_CORS_ORIGINS", "https://unlxck-gpt-webhook.vercel.app")
    client, _, _ = _build_client()

    response = client.options(
        "/api/plans/generate",
        headers={
            "Origin": RENDER_BACKEND_URL,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_auth_is_required_for_draft_save():
    client, _, _ = _build_client()

    response = client.put(
        "/api/me",
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            onboarding_draft={"current_step": 5, "injuries": "left shoulder"},
        ).model_dump(mode="json"),
    )

    assert response.status_code == 401


def test_review_stage_draft_save_persists_step_and_form():
    """Saving a draft at step 5 (Review) must persist the full form and correct step index."""
    client, store, _ = _build_client()
    request = _build_request()
    draft_payload = {
        **request.model_dump(mode="json"),
        "current_step": 5,
    }

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name=request.athlete.full_name,
            technical_style=request.athlete.technical_style,
            record=request.athlete.record,
            onboarding_draft=draft_payload,
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["onboarding_draft"]["current_step"] == 5
    assert profile["onboarding_draft"]["fight_date"] == request.fight_date
    assert store.profiles["athlete-1"]["onboarding_draft"]["current_step"] == 5


def test_review_stage_invalid_record_returns_422_not_network_error():
    """Invalid record submitted during draft save at review stage must return 422, not a network error."""
    client, _, _ = _build_client()

    for bad_record in ("5-", "-1", "5", "5-1-2-3", "abc"):
        response = client.put(
            "/api/me",
            headers={"Authorization": "Bearer athlete-token"},
            json={"record": bad_record},
        )
        assert response.status_code == 422, f"expected 422 for record={bad_record!r}"


def test_review_stage_empty_record_is_accepted_during_draft_save():
    """Empty record must be accepted when saving a draft (partial completion is allowed)."""
    client, _, _ = _build_client()

    response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            record="",
            onboarding_draft={"current_step": 5},
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200


def test_saved_onboarding_draft_round_trips_through_me_and_clears_after_generation():
    client, store, _ = _build_client()

    draft_response = client.put(
        "/api/me",
        headers={"Authorization": "Bearer athlete-token"},
        json=ProfileUpdateRequest(
            full_name="Ari Mensah",
            technical_style=["boxing"],
            onboarding_draft={"current_step": 4, "injuries": "heel soreness"},
        ).model_dump(mode="json"),
    )

    assert draft_response.status_code == 200
    assert draft_response.json()["profile"]["onboarding_draft"]["current_step"] == 4

    me_response = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert me_response.status_code == 200
    assert me_response.json()["profile"]["onboarding_draft"]["injuries"] == "heel soreness"

    generate_response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert generate_response.status_code == 202
    assert store.profiles["athlete-1"]["onboarding_draft"] is None
    refreshed_me = client.get("/api/me", headers={"Authorization": "Bearer athlete-token"})
    assert refreshed_me.json()["profile"]["onboarding_draft"] is None
    assert refreshed_me.json()["latest_intake"]["fight_date"] == "2026-04-18"


def test_generate_plan_persists_validated_final_plan_and_history():
    client, store, stage2 = _build_client()
    payload = _build_request().model_dump(mode="json")

    _, job = _start_generation(client, PlanRequest.model_validate(payload))
    detail = client.get(
        f"/api/plans/{job['plan_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert detail.status_code == 200
    body = detail.json()
    assert job["status"] == "completed"
    saved = store.get_plan(job["plan_id"])
    assert saved["plan_text"] == "# Final Plan"
    assert saved["pdf_url"] is None
    assert saved["status"] == "ready"
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

    assert response.status_code == 202
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

    _, job = _start_generation(client)

    assert job["status"] == "review_required"
    saved = next(iter(store.plans.values()))
    assert saved["final_plan_text"] == "# Failed Stage 2 Output"
    assert saved["stage2_status"] == "stage2_failed"


@pytest.mark.parametrize("scenario", SYSTEM_SCENARIOS, ids=lambda scenario: scenario.key)
def test_curated_system_scenarios_cover_generation_and_hold_behavior(scenario: SystemScenario):
    client, store, _ = _build_client(
        FakeStage2Automator(result=scenario.automator_result)
    )
    request = _build_request(scenario.request_overrides)

    _, job = _start_generation(client, request)

    saved = next(iter(store.plans.values()))
    latest_intake = store.get_latest_intake("athlete-1")["intake"]

    assert job["status"] == ("completed" if scenario.expected_status == "ready" else scenario.expected_status)
    assert latest_intake["fight_date"] == request.fight_date
    assert latest_intake["injuries"] == request.injuries
    assert latest_intake["equipment_access"] == request.equipment_access
    assert latest_intake["training_availability"] == request.training_availability
    assert latest_intake["hard_sparring_days"] == request.hard_sparring_days
    assert latest_intake["technical_skill_days"] == request.technical_skill_days
    assert store.profiles["athlete-1"]["onboarding_draft"] is None

    if scenario.expected_status == "ready":
        assert scenario.support_marker in saved["plan_text"]
        assert "Primary:" not in saved["plan_text"]
        assert "Fallback:" not in saved["plan_text"]
        assert saved["stage2_status"] == "stage2_pass"
    else:
        assert saved["plan_text"] == ""
        warning_codes = [warning["code"] for warning in saved["stage2_validator_report"]["warnings"]]
        assert scenario.expected_review_code in warning_codes
        assert saved["stage2_status"] == "stage2_failed"
        assert saved["stage2_retry_text"] == "repair prompt"


def test_stage2_unavailable_returns_failed_job_without_persisting_plan():
    client, store, _ = _build_client(
        FakeStage2Automator(
            error=Stage2AutomationUnavailableError("OPENAI_API_KEY is required for automated Stage 2 finalization.")
        )
    )

    _, job = _start_generation(client)

    assert job["status"] == "failed"
    assert "OPENAI_API_KEY" in job["error"]
    assert len(store.plans) == 0


def test_stage2_gateway_failure_returns_failed_job_without_persisting_plan():
    client, store, _ = _build_client(
        FakeStage2Automator(error=Stage2AutomationError("Stage 2 model request failed"))
    )

    _, job = _start_generation(client)

    assert job["status"] == "failed"
    assert "Stage 2 model request failed" in job["error"]
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


def test_athlete_can_delete_own_plan():
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

    response = client.delete(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 204
    assert store.get_plan(plan["id"]) is None


def test_athlete_cannot_delete_another_users_plan():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-1",
        email="ari@example.com",
        full_name="Ari Mensah",
        metadata={},
    )
    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    store.ensure_profile(athlete)
    store.ensure_profile(other_user)
    plan = store.create_plan(
        athlete_id="athlete-2",
        intake_id="intake_x",
        request=_build_request(),
        result=finalized_result(),
    )

    response = client.delete(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 403
    assert store.get_plan(plan["id"]) is not None


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


def test_admin_get_athlete_by_id_returns_profile():
    client, store, _ = _build_client()
    athlete = AuthenticatedUser(
        user_id="athlete-profile-1",
        email="solo@example.com",
        full_name="Solo Fighter",
        metadata={},
    )
    store.ensure_profile(athlete)

    forbidden = client.get(
        "/api/admin/athletes/athlete-profile-1",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert forbidden.status_code == 403

    not_found = client.get(
        "/api/admin/athletes/nonexistent-id",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert not_found.status_code == 404

    response = client.get(
        "/api/admin/athletes/athlete-profile-1",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["athlete_id"] == "athlete-profile-1"
    assert data["email"] == "solo@example.com"
    assert data["full_name"] == "Solo Fighter"
    assert data["plan_count"] == 0


def test_admin_can_list_and_open_review_required_plan_for_resolution():
    review_result = _review_required_result(
        final_plan_text="## PHASE 2: SPP\n- Heavy Bag Sprint Rounds - 6 x 15 sec",
        warning_code="equipment_incongruent_selection",
    )
    client, store, _ = _build_client(FakeStage2Automator(result=review_result))

    _, job = _start_generation(client, _build_request(
            {
                "equipment_access": ["bands", "bodyweight"],
                "training_availability": ["Tuesday", "Thursday", "Saturday"],
            }
        ))
    plan_id = job["plan_id"]

    admin_list = client.get("/api/admin/plans", headers={"Authorization": "Bearer admin-token"})
    assert admin_list.status_code == 200
    listed_plan = next(plan for plan in admin_list.json() if plan["plan_id"] == plan_id)
    assert listed_plan["status"] == "review_required"

    admin_detail = client.get(f"/api/plans/{plan_id}", headers={"Authorization": "Bearer admin-token"})
    assert admin_detail.status_code == 200
    assert admin_detail.json()["admin_outputs"]["stage2_retry_text"] == "repair prompt"


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
            planning_brief={
                "phase_strategy": {"SPP": {"must_keep": ["rehab"]}},
                "candidate_pools": {
                    "SPP": {
                        "strength_slots": [],
                        "conditioning_slots": [],
                        "rehab_slots": [
                            {
                                "role": "rehab_ankle",
                                "selected": {"name": "Heel Raise"},
                                "alternates": [],
                            }
                        ],
                    }
                },
            },
            stage2_status="stage2_failed",
            stage2_retry_text="",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(
            final_plan_text="## PHASE 2: SPP\n- Air Bike Sprint - 6 x 6 sec"
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["outputs"]["plan_text"] == ""
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_retry_required"
    assert body["admin_outputs"]["stage2_retry_text"]


def test_manual_stage2_submission_publishes_when_only_non_blocking_review_flags_exist():
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
            planning_brief={"athlete_model": {"sport": "boxing"}},
            stage2_status="stage2_failed",
            stage2_retry_text="",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/manual-stage2",
        headers={"Authorization": "Bearer admin-token"},
        json=ManualStage2SubmissionRequest(
            final_plan_text=(
                "## PHASE 2: SPP\n"
                "- Double-leg sprint entry - 6 x 6 sec\n"
            )
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["outputs"]["plan_text"]
    assert body["admin_outputs"]["stage2_status"] == "manual_stage2_pass"
    assert body["admin_outputs"]["stage2_validator_report"]["review_flag_count"] >= 1


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


def test_admin_can_reject_approved_plan_back_to_review():
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
            status="ready",
            plan_text="# Released Stage 2 Output",
            final_plan_text="# Released Stage 2 Output",
            stage2_status="admin_review_approved",
            stage2_retry_text="repair prompt",
            stage2_attempt_count=2,
        ),
    )

    response = client.post(
        f"/api/admin/plans/{plan['id']}/reject",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["outputs"]["plan_text"] == ""
    assert body["admin_outputs"]["final_plan_text"] == "# Released Stage 2 Output"
    assert body["admin_outputs"]["stage2_status"] == "admin_review_rejected"


def test_curated_review_required_scenarios_are_fast_for_admin_to_resolve():
    for scenario in [item for item in SYSTEM_SCENARIOS if item.expected_resolution]:
        client, store, _ = _build_client(
            FakeStage2Automator(result=scenario.automator_result)
        )
        _, job = _start_generation(client, _build_request(scenario.request_overrides))
        plan_id = job["plan_id"]

        if scenario.expected_resolution == "approve":
            resolved = client.post(
                f"/api/admin/plans/{plan_id}/approve",
                headers={"Authorization": "Bearer admin-token"},
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "ready"
            assert resolved.json()["admin_outputs"]["stage2_status"] == "admin_review_approved"
        elif scenario.expected_resolution == "manual_stage2":
            resolved = client.post(
                f"/api/admin/plans/{plan_id}/manual-stage2",
                headers={"Authorization": "Bearer admin-token"},
                json=ManualStage2SubmissionRequest(
                    final_plan_text=(
                        "## PHASE 3: TAPER\n"
                        "### Week 5\n"
                        "#### Neural primer\n"
                        "- Assault Bike Sprint - 4 x 6 sec\n"
                        "#### Recovery\n"
                        "- Walk + mobility\n"
                    )
                ).model_dump(mode="json"),
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "ready"
            assert resolved.json()["admin_outputs"]["stage2_status"] == "manual_stage2_retry_pass"
        else:  # pragma: no cover - explicit safety branch
            raise AssertionError(f"Unexpected resolution strategy: {scenario.expected_resolution}")

        assert store.get_plan(plan_id)["status"] == "ready"


# ---------------------------------------------------------------------------
# Deferred non-essential write tests
# ---------------------------------------------------------------------------

def test_generate_plan_returns_existing_active_job_for_same_athlete():
    client, store, _ = _build_client()

    existing_job = {
        "job_id": "job_existing123",
        "athlete_id": "athlete-1",
        "status": "running",
        "created_at": _now(),
        "updated_at": _now(),
        "error": None,
        "plan_id": None,
        "latest_plan_id": None,
    }
    client.app.state.generation_jobs[existing_job["job_id"]] = app_module.GenerationJobState(**existing_job)

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    assert response.json() == existing_job
    assert store.get_latest_intake("athlete-1") is None
    assert len(store.plans) == 0


def test_generate_plan_response_shape_is_preserved_with_deferred_writes():
    """Response schema must be unchanged after moving non-essential writes to background tasks."""
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("job_")
    assert body["status"] in {"queued", "running", "completed"}
    assert body["athlete_id"] == "athlete-1"


def test_generate_plan_essential_writes_happen_synchronously():
    """create_intake and create_plan must be persisted before the response is returned."""
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    # Intake must exist.
    assert store.get_latest_intake("athlete-1") is not None
    # Plan must exist and match the returned plan_id.
    job_body = response.json()
    assert job_body["job_id"].startswith("job_")
    assert len(store.plans) == 1
    plan_id = next(iter(store.plans.values()))["id"]
    assert store.get_plan(plan_id) is not None


def test_generate_plan_deferred_writes_run_but_do_not_block_response():
    """update_profile and clear_onboarding_draft are run as background tasks.

    With FastAPI's TestClient, background tasks execute synchronously before
    the call returns, so we can assert their side-effects are visible here.
    The structural assertion is that a failure in either task does NOT
    prevent the 201 response from being delivered.
    """
    client, store, _ = _build_client()

    # Pre-set an onboarding draft so we can verify it gets cleared by the
    # deferred background task.
    store.profiles.setdefault("athlete-1", {})
    store.ensure_profile(AuthenticatedUser(
        user_id="athlete-1", email="ari@example.com", full_name="Ari Mensah", metadata={}
    ))
    store.profiles["athlete-1"]["onboarding_draft"] = {"current_step": 3}

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    # Deferred update_profile side-effect: profile full_name refreshed.
    assert store.profiles["athlete-1"]["full_name"] == "Ari Mensah"
    # Deferred clear_onboarding_draft side-effect: draft cleared.
    assert store.profiles["athlete-1"]["onboarding_draft"] is None


def test_generate_plan_deferred_write_failure_does_not_fail_main_response():
    """A failure in a deferred (background) write must not retroactively fail the plan generation.

    We subclass FakeStore so that update_profile and clear_onboarding_draft raise,
    simulating a transient backend failure in those non-essential writes.
    The essential writes (create_intake, create_plan) succeed, and the caller
    must still receive a 201 with the generated plan.
    """

    class FailingNonEssentialStore(FakeStore):
        def update_profile(self, athlete_id: str, update: ProfileUpdateRequest) -> dict:
            raise RuntimeError("simulated update_profile failure")

        def clear_onboarding_draft(self, athlete_id: str) -> None:
            raise RuntimeError("simulated clear_onboarding_draft failure")

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
    store = FailingNonEssentialStore()
    stage2 = FakeStage2Automator(result=finalized_result())
    # raise_server_exceptions=False so background-task exceptions do not
    # propagate into the test; the response is still the one already sent.
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
            stage2_automator=stage2,
        ),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    # Main response must succeed despite deferred-write failures.
    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("job_")
    job_response = client.get(
        f"/api/generation-jobs/{body['job_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert job_response.status_code == 200
    assert job_response.json()["status"] == "completed"
    # Essential writes must still have persisted.
    assert store.get_latest_intake("athlete-1") is not None
    assert len(store.plans) == 1


def test_generate_plan_returns_job_payload_and_status_endpoint_resolves_completed_plan():
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"].startswith("job_")

    job_response = client.get(
        f"/api/generation-jobs/{body['job_id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert job_response.status_code == 200
    job_body = job_response.json()
    assert job_body["status"] == "completed"
    assert job_body["plan_id"]
    assert job_body["latest_plan_id"] == job_body["plan_id"]
    assert store.get_plan(job_body["plan_id"]) is not None


def test_generation_job_status_reports_review_required_result():
    client, _, _ = _build_client(
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

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job_response = client.get(
        f"/api/generation-jobs/{job_id}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert job_response.status_code == 200
    assert job_response.json()["status"] == "review_required"


def test_latest_plan_endpoint_returns_latest_saved_plan():
    client, store, _ = _build_client()

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )

    assert response.status_code == 202
    latest = client.get("/api/plans/latest", headers={"Authorization": "Bearer athlete-token"})

    assert latest.status_code == 200
    assert latest.json()["plan_id"] == next(iter(store.plans.values()))["id"]


def test_generation_job_endpoint_requires_same_athlete_or_admin():
    client, _, _ = _build_client()
    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=_build_request().model_dump(mode="json"),
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    other_user = AuthenticatedUser(
        user_id="athlete-2",
        email="other@example.com",
        full_name="Other Athlete",
        metadata={},
    )
    app_store = client.app.state.store
    client.app.state.auth_service.users_by_token["other-token"] = other_user
    app_store.ensure_profile(other_user)

    forbidden = client.get(
        f"/api/generation-jobs/{job_id}",
        headers={"Authorization": "Bearer other-token"},
    )
    allowed = client.get(
        f"/api/generation-jobs/{job_id}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert forbidden.status_code == 403
    assert allowed.status_code == 200
