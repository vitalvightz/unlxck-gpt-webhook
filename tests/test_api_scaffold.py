from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

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
            "coach_notes": result.get("coach_notes", ""),
            "pdf_url": result.get("pdf_url"),
            "why_log": result.get("why_log", {}),
            "planning_brief": result.get("planning_brief"),
            "stage2_payload": result.get("stage2_payload"),
            "stage2_handoff_text": result.get("stage2_handoff_text", ""),
            "created_at": _now(),
            "full_name": profile["full_name"],
        }
        self.plans[plan_id] = row
        return row

    def list_user_plans(self, athlete_id: str) -> list[dict]:
        return [plan for plan in self.plans.values() if plan["athlete_id"] == athlete_id]

    def get_plan(self, plan_id: str) -> dict | None:
        return self.plans.get(plan_id)

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
    return {
        "plan_text": "# Plan",
        "coach_notes": "### Coach Review",
        "pdf_url": None,
        "why_log": {"strength": {}},
        "stage2_payload": {"ok": True},
        "planning_brief": "brief",
        "stage2_handoff_text": "handoff",
    }


def _build_client() -> tuple[TestClient, FakeStore]:
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
    client = TestClient(
        create_app(
            store=store,
            auth_service=FakeAuthService({"athlete-token": athlete, "admin-token": admin}),
            planner=_planner,
        )
    )
    return client, store


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
    client, _ = _build_client()

    response = client.get("/api/me")

    assert response.status_code == 401


def test_generate_plan_persists_profile_intake_and_history():
    client, store = _build_client()
    payload = _build_request().model_dump(mode="json")

    response = client.post(
        "/api/plans/generate",
        headers={"Authorization": "Bearer athlete-token"},
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["outputs"]["plan_text"] == "# Plan"
    assert body["admin_outputs"] is None
    assert store.get_latest_intake("athlete-1")["intake"]["fight_date"] == "2026-04-18"
    assert len(store.list_user_plans("athlete-1")) == 1


def test_athlete_cannot_read_another_athlete_plan():
    client, store = _build_client()
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
        result=awaitable_result(),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer athlete-token"},
    )

    assert response.status_code == 403


def test_admin_can_view_internal_plan_outputs():
    client, store = _build_client()
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
        result=awaitable_result(),
    )

    response = client.get(
        f"/api/plans/{plan['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.json()["admin_outputs"]["stage2_payload"] == {"ok": True}


def test_admin_endpoints_require_admin_role():
    client, store = _build_client()
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


def awaitable_result() -> dict:
    return {
        "plan_text": "# Plan",
        "coach_notes": "### Coach Review",
        "pdf_url": None,
        "why_log": {"strength": {}},
        "stage2_payload": {"ok": True},
        "planning_brief": "brief",
        "stage2_handoff_text": "handoff",
    }