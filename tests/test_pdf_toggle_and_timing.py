"""Tests for PDF-toggle default-off behavior and Stage 2 unblocking.

Covers:
1. Default generation path returns plan text and Stage 2 outputs with PDF disabled.
2. pdf_url is None when PDF export is off (default).
3. Enabling PDF export (generate_pdf=True) calls the export path.
4. Stage 2 outputs are built regardless of PDF toggle.
5. No regression in API response key compatibility.
6. UNLXCK_ENABLE_PLAN_PDF env var controls the default.
"""
from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import fightcamp.plan_pipeline as plan_pipeline
import fightcamp.plan_pipeline_rendering as _rendering_module
from fightcamp import main as main_module
from fightcamp.main import generate_plan

_DATA_PATH = Path(__file__).resolve().parents[1] / "test_data.json"


def _load_data() -> dict:
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1 & 2 – default path: PDF off, pdf_url is None
# ---------------------------------------------------------------------------

def test_default_generate_pdf_is_false_and_pdf_url_is_none(monkeypatch):
    """generate_plan() with no explicit flag should skip PDF and return pdf_url=None."""
    monkeypatch.setattr(main_module, "_PDF_ENABLED_BY_DEFAULT", False)

    called = []

    def _spy_html_to_pdf(html, output_path):  # pragma: no cover
        called.append(output_path)
        return "/tmp/plan.pdf"

    # Patch both the rendering module and the pipeline re-assignment point.
    monkeypatch.setattr(plan_pipeline, "html_to_pdf", _spy_html_to_pdf)
    monkeypatch.setattr(_rendering_module, "html_to_pdf", _spy_html_to_pdf)

    data = _load_data()
    result = asyncio.run(generate_plan(data))

    assert result["pdf_url"] is None, "pdf_url must be None when PDF is disabled"
    assert not called, "html_to_pdf must not be called when PDF is disabled"


def test_generate_plan_default_returns_plan_text_and_stage2(monkeypatch):
    """Default path (PDF off) still returns plan_text and all Stage 2 artifacts."""
    monkeypatch.setattr(main_module, "_PDF_ENABLED_BY_DEFAULT", False)

    data = _load_data()
    result = asyncio.run(generate_plan(data))

    assert result.get("plan_text"), "plan_text must be non-empty"
    assert result.get("stage2_payload") is not None, "stage2_payload must be present"
    assert result.get("planning_brief") is not None, "planning_brief must be present"
    assert result.get("stage2_handoff_text"), "stage2_handoff_text must be non-empty"


# ---------------------------------------------------------------------------
# 3 – explicit generate_pdf=True calls the export path
# ---------------------------------------------------------------------------

def test_generate_pdf_true_calls_export(monkeypatch):
    """Passing generate_pdf=True must invoke html_to_pdf (the PDF generation path)."""
    called = []

    def _stub_html_to_pdf(html: str, output_path: str):
        called.append(output_path)
        return "/tmp/plan.pdf"

    def _stub_upload_to_supabase(pdf_path: str, **kwargs):
        return "https://example.com/uploaded.pdf"

    # plan_pipeline.export_plan_pdf injects these into the rendering module at
    # call time, so we must patch the plan_pipeline namespace (same pattern used
    # by the golden-snapshot tests).
    monkeypatch.setattr(plan_pipeline, "html_to_pdf", _stub_html_to_pdf)
    monkeypatch.setattr(plan_pipeline, "upload_to_supabase", _stub_upload_to_supabase)

    data = _load_data()
    result = asyncio.run(generate_plan(data, generate_pdf=True))

    assert called, "html_to_pdf must be called when generate_pdf=True"
    assert result["pdf_url"] == "https://example.com/uploaded.pdf"


# ---------------------------------------------------------------------------
# 4 – Stage 2 outputs built regardless of PDF toggle
# ---------------------------------------------------------------------------

def test_stage2_outputs_present_when_pdf_disabled(monkeypatch):
    monkeypatch.setattr(main_module, "_PDF_ENABLED_BY_DEFAULT", False)
    data = _load_data()
    result = asyncio.run(generate_plan(data))
    assert result["stage2_payload"] is not None
    assert result["planning_brief"] is not None
    assert result["stage2_handoff_text"]


def test_stage2_outputs_present_when_pdf_enabled(monkeypatch):
    # Simulate PDF generation failure (html_to_pdf returns None); Stage 2 must
    # still be populated.
    monkeypatch.setattr(plan_pipeline, "html_to_pdf", lambda html, output_path: None)

    data = _load_data()
    result = asyncio.run(generate_plan(data, generate_pdf=True))

    assert result["stage2_payload"] is not None
    assert result["planning_brief"] is not None
    assert result["stage2_handoff_text"]


# ---------------------------------------------------------------------------
# 5 – API response key compatibility
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = {
    "pdf_url",
    "why_log",
    "coach_notes",
    "plan_text",
    "stage2_payload",
    "planning_brief",
    "stage2_handoff_text",
}


def test_response_schema_keys_unchanged(monkeypatch):
    """All expected response keys must be present regardless of PDF toggle."""
    monkeypatch.setattr(main_module, "_PDF_ENABLED_BY_DEFAULT", False)
    data = _load_data()
    result = asyncio.run(generate_plan(data))
    assert _EXPECTED_KEYS.issubset(result.keys()), (
        f"Missing keys: {_EXPECTED_KEYS - result.keys()}"
    )


# ---------------------------------------------------------------------------
# 6 – UNLXCK_ENABLE_PLAN_PDF env var controls the module default
# ---------------------------------------------------------------------------

def test_env_var_enables_pdf_default(monkeypatch):
    """_PDF_ENABLED_BY_DEFAULT should be True when env var is set to '1'."""
    monkeypatch.setenv("UNLXCK_ENABLE_PLAN_PDF", "1")
    importlib.reload(main_module)
    try:
        assert main_module._PDF_ENABLED_BY_DEFAULT is True
    finally:
        monkeypatch.delenv("UNLXCK_ENABLE_PLAN_PDF", raising=False)
        importlib.reload(main_module)


def test_env_var_disabled_pdf_default(monkeypatch):
    """_PDF_ENABLED_BY_DEFAULT should be False when env var is '0' or unset."""
    monkeypatch.delenv("UNLXCK_ENABLE_PLAN_PDF", raising=False)
    importlib.reload(main_module)
    assert main_module._PDF_ENABLED_BY_DEFAULT is False

