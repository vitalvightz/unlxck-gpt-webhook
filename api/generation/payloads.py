"""Request-payload helpers for the generation runtime.

Kept dependency-light (stdlib + fastapi + models) so other generation modules
(e.g. admin_linkage) can import these without pulling in the runtime shim.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from ..models import PlanRequest


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    try:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        normalized = json.dumps(str(payload), ensure_ascii=False)
    return normalized


def parse_plan_request(value: Any) -> PlanRequest:
    if isinstance(value, PlanRequest):
        return value
    if isinstance(value, dict):
        return PlanRequest.model_validate(value)
    if isinstance(value, str):
        return PlanRequest.model_validate(json.loads(value))
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="generation job payload is invalid",
    )
