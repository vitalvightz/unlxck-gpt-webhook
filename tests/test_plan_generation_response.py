"""Tests for in-app plan generation response compatibility.

PDF export has been removed. The API still returns ``pdf_url`` as ``None`` so
old saved plans and frontend contracts remain compatible.
"""
from __future__ import annotations

import asyncio

from fightcamp.main import generate_plan
from support import _build_request


def _load_data() -> dict:
    return _build_request().to_payload()


def test_generate_plan_returns_plan_text_stage2_and_null_pdf_url():
    data = _load_data()
    result = asyncio.run(generate_plan(data))

    assert result["pdf_url"] is None
    assert result.get("plan_text"), "plan_text must be non-empty"
    assert result.get("stage2_payload") is not None, "stage2_payload must be present"
    assert result.get("planning_brief") is not None, "planning_brief must be present"
    assert result.get("stage2_handoff_text"), "stage2_handoff_text must be non-empty"
    assert result["parsing_metadata"] == result["stage2_payload"]["input_parsing_metadata"]


_EXPECTED_KEYS = {
    "pdf_url",
    "why_log",
    "coach_notes",
    "plan_text",
    "stage2_payload",
    "planning_brief",
    "stage2_handoff_text",
}


def test_response_schema_keeps_pdf_url_key_for_compatibility():
    data = _load_data()
    result = asyncio.run(generate_plan(data))

    assert _EXPECTED_KEYS.issubset(result.keys()), (
        f"Missing keys: {_EXPECTED_KEYS - result.keys()}"
    )
    assert result["pdf_url"] is None
