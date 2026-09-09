"""Size and depth guards for large JSON fields persisted to Supabase."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.json_limits import (
    MAX_CLIENT_JSON_BYTES,
    MAX_JSON_DEPTH,
    MAX_SERVER_JSON_BYTES,
    MAX_STAGE2_PAYLOAD_BYTES,
    json_byte_size,
    validate_json_field,
)
from api.models import (
    NutritionProfileInput,
    OnboardingDraftSaveRequest,
    ProfileUpdateRequest,
)
from api.store import SupabaseAppStore
from support import _build_request


def _oversized_dict() -> dict[str, str]:
    return {"blob": "a" * (MAX_CLIENT_JSON_BYTES + 100)}


def _oversized_server_dict() -> dict[str, str]:
    return {"blob": "a" * (MAX_SERVER_JSON_BYTES + 100)}


def _stage2_payload_of_approximate_size(size: int) -> dict[str, str]:
    return {"blob": "a" * size}


def _too_deep_dict(depth: int) -> dict:
    root: dict = {}
    cur = root
    for _ in range(depth):
        cur["x"] = {}
        cur = cur["x"]
    return root


# --- helper -----------------------------------------------------------------

def test_validate_json_field_allows_none_and_small_payloads():
    assert validate_json_field(None, field="f") is None
    payload = {"a": 1, "b": ["x", "y"]}
    assert validate_json_field(payload, field="f") is payload


def test_validate_json_field_rejects_oversized():
    with pytest.raises(ValueError):
        validate_json_field(_oversized_dict(), field="f", max_bytes=MAX_CLIENT_JSON_BYTES)


def test_validate_json_field_rejects_too_deep():
    with pytest.raises(ValueError):
        validate_json_field(_too_deep_dict(MAX_JSON_DEPTH + 5), field="f", max_depth=MAX_JSON_DEPTH)


def test_validate_json_field_allows_exactly_max_depth():
    # depth == limit is allowed; only deeper is rejected
    validate_json_field(_too_deep_dict(MAX_JSON_DEPTH - 1), field="f", max_depth=MAX_JSON_DEPTH)


def test_json_byte_size_handles_non_serializable_via_default():
    # default=str keeps the helper from blowing up on odd values
    assert json_byte_size({"k": object()}) > 0


# --- Pydantic validators (HTTP 422 boundary) --------------------------------

def test_profile_update_rejects_oversized_onboarding_draft():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(onboarding_draft=_oversized_dict())


def test_profile_update_rejects_too_deep_onboarding_draft():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(onboarding_draft=_too_deep_dict(MAX_JSON_DEPTH + 5))


def test_profile_update_accepts_in_bounds_onboarding_draft():
    req = ProfileUpdateRequest(onboarding_draft={"goals": ["power"]})
    assert req.onboarding_draft == {"goals": ["power"]}


def test_onboarding_draft_save_request_rejects_oversized():
    with pytest.raises(ValidationError):
        OnboardingDraftSaveRequest(onboarding_draft=_oversized_dict())


def test_nutrition_profile_rejects_oversized_payload():
    huge_list = ["item" + str(i) for i in range(MAX_CLIENT_JSON_BYTES)]
    with pytest.raises(ValidationError):
        NutritionProfileInput(dietary_restrictions=huge_list)


# --- store-side guards (HTTP 413 defense in depth) --------------------------

def _make_store() -> SupabaseAppStore:
    return SupabaseAppStore(client=MagicMock(), admin_emails=set())


def test_create_or_get_generation_job_rejects_oversized_request_payload():
    store = _make_store()
    with pytest.raises(HTTPException) as exc_info:
        store.create_or_get_generation_job(
            athlete_id="athlete-1",
            client_request_id="cli-1",
            source="self_serve",
            request_payload=_oversized_server_dict(),
        )
    assert exc_info.value.status_code == 413
    # rejected before touching the database
    store.client.table.assert_not_called()


def test_update_profile_rejects_oversized_onboarding_draft_at_store_layer():
    store = _make_store()
    # Bypass the Pydantic validator to exercise the store backstop directly.
    update = ProfileUpdateRequest()
    object.__setattr__(update, "onboarding_draft", _oversized_dict())
    with pytest.raises(HTTPException) as exc_info:
        store.update_profile("athlete-1", update)
    assert exc_info.value.status_code == 413
    store.client.table.assert_not_called()


def test_json_limit_constants_keep_stage2_headroom_field_specific():
    assert MAX_CLIENT_JSON_BYTES == 100 * 1024
    assert MAX_SERVER_JSON_BYTES == 256 * 1024
    assert MAX_STAGE2_PAYLOAD_BYTES == 384 * 1024
    assert MAX_JSON_DEPTH == 32


def test_create_plan_accepts_stage2_payload_above_generic_server_limit():
    store = _make_store()
    persisted = {"id": "plan-1"}
    store.client.table.return_value.insert.return_value.execute.return_value.data = [persisted]
    payload = _stage2_payload_of_approximate_size(311 * 1024)

    result = store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-1",
        request=_build_request(),
        result={"status": "generated", "stage2_payload": payload},
    )

    assert result == persisted
    inserted = store.client.table.return_value.insert.call_args.args[0]
    assert inserted["stage2_payload"] is payload
    assert MAX_SERVER_JSON_BYTES < json_byte_size(payload) < MAX_STAGE2_PAYLOAD_BYTES


def test_create_plan_accepts_large_candidate_pools_for_20_plus_equipment_selections():
    store = _make_store()
    store.client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "plan-1"}]
    equipment = [f"equipment_{index}" for index in range(24)]
    candidates = [
        {"name": f"Exercise {index}", "equipment": equipment[index % len(equipment)], "notes": "x" * 900}
        for index in range(340)
    ]
    payload = {"athlete_model": {"equipment_access": equipment}, "candidate_pools": candidates}

    store.create_plan(
        athlete_id="athlete-1",
        intake_id="intake-1",
        request=_build_request(),
        result={"status": "generated", "stage2_payload": payload},
    )

    inserted = store.client.table.return_value.insert.call_args.args[0]["stage2_payload"]
    assert inserted["athlete_model"]["equipment_access"] == equipment
    assert inserted["candidate_pools"] == candidates
    assert MAX_SERVER_JSON_BYTES < json_byte_size(payload) < MAX_STAGE2_PAYLOAD_BYTES


def test_create_plan_rejects_stage2_payload_above_dedicated_limit():
    store = _make_store()
    with pytest.raises(HTTPException) as exc_info:
        store.create_plan(
            athlete_id="athlete-1",
            intake_id="intake-1",
            request=_build_request(),
            result={
                "status": "generated",
                "stage2_payload": _stage2_payload_of_approximate_size(MAX_STAGE2_PAYLOAD_BYTES + 100),
            },
        )
    assert exc_info.value.status_code == 413
    store.client.table.assert_not_called()
