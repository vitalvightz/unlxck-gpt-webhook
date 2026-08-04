"""Production-path regression for intake wound-safety persistence."""

from __future__ import annotations

from typing import Any

from api.auth import AuthenticatedUser
from api.contracts.readiness_message import classify_injury_surface
from api.services.intake_injury_sync import sync_intake_injuries_for_plan
from tests.support import FakeStore, _build_request, finalized_result

ATHLETE = "athlete-wound-rpc"


class _RpcResponse:
    def __init__(self, data: object):
        self.data = data

    def execute(self) -> "_RpcResponse":
        return self


class _WoundRpcClient:
    """Minimal Supabase client double that persists the RPC payload."""

    def __init__(self, store: FakeStore):
        self.store = store
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> _RpcResponse:
        self.calls.append((name, dict(params)))
        row = self.store.create_injury_flag(
            params["p_athlete_id"],
            {
                "plan_id": params["p_plan_id"],
                "source": "intake",
                "source_key": params["p_source_key"],
                "body_area": params["p_body_area"],
                "description": params["p_description"],
                "severity": params["p_severity"],
                "status": params["p_status"],
                "resolved_at": params["p_resolved_at"],
                "skin_integrity": params["p_skin_integrity"],
                "bleeding_status": params["p_bleeding_status"],
                "infection_signs": params["p_infection_signs"],
                "coverable": params["p_coverable"],
                "drainage": params["p_drainage"],
            },
        )
        return _RpcResponse(row)


def _seed_surface_wound(store: FakeStore) -> dict[str, Any]:
    store.ensure_profile(
        AuthenticatedUser(
            user_id=ATHLETE,
            email="wound-rpc@example.com",
            full_name="Wound RPC",
            metadata={},
        )
    )
    plan = store.create_plan(
        athlete_id=ATHLETE,
        intake_id="intake-wound-rpc",
        request=_build_request(),
        result=finalized_result(),
    )
    store.intakes.setdefault(ATHLETE, []).append(
        {
            "id": "intake-wound-rpc",
            "athlete_id": ATHLETE,
            "intake": {
                "guided_injuries": [
                    {
                        "area": "Right shoulder",
                        "zone": "r_shoulder",
                        "severity": "moderate",
                        "trend": "stable",
                        "injury_type": "surface_injury",
                        "surface_type": "cut",
                        "injury_subtypes": ["surface_injury:cut"],
                        "timeframe": "recent",
                        "cleared": "yes",
                        "open_wound": "yes",
                        "bleeding_status": "wont_stop",
                        "infection_signs": ["pus"],
                        "coverable": "no",
                        "drainage": "present",
                    }
                ]
            },
            "created_at": "2026-08-04T00:00:00+00:00",
        }
    )
    return plan


def test_production_rpc_preserves_wound_fields_and_medical_review() -> None:
    store = FakeStore()
    plan = _seed_surface_wound(store)
    rpc_client = _WoundRpcClient(store)
    store.client = rpc_client

    active = sync_intake_injuries_for_plan(
        store,
        athlete_id=ATHLETE,
        plan_row=plan,
    )

    assert len(rpc_client.calls) == 1
    rpc_name, params = rpc_client.calls[0]
    assert rpc_name == "adopt_or_create_intake_injury_flag_with_wound_fields"
    assert params["p_skin_integrity"] == "open"
    assert params["p_bleeding_status"] == "uncontrolled"
    assert params["p_infection_signs"] == ["pus"]
    assert params["p_coverable"] == "no"
    assert params["p_drainage"] == "present"

    assert len(active) == 1
    assert active[0]["skin_integrity"] == "open"
    assert active[0]["bleeding_status"] == "uncontrolled"
    assert active[0]["infection_signs"] == ["pus"]
    assert classify_injury_surface(active[0]) == "surface_medical_review"
