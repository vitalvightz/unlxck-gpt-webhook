import importlib
import logging

import pytest

from fightcamp import build_block


def test_optional_import_loader_logs_non_import_failure(monkeypatch, caplog):
    def _boom(module_name: str):
        raise RuntimeError(f"bad import side effect for {module_name}")

    monkeypatch.setattr(build_block.importlib, "import_module", _boom)

    with caplog.at_level(logging.ERROR):
        result = build_block._load_optional_module("fake.optional.module")

    assert result is None
    assert "[optional-import-failed] module=fake.optional.module" in caplog.text


def test_html_to_pdf_logs_when_pdfkit_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(build_block, "pdfkit", None)

    with caplog.at_level(logging.ERROR):
        result = build_block.html_to_pdf("<p>hi</p>", "out.pdf")

    assert result is None
    assert "code=pdfkit_unavailable" in caplog.text
    assert "stage=pdf_export" in caplog.text


def test_resolve_supabase_url_requires_explicit_override(monkeypatch, caplog):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("ALLOW_DEFAULT_SUPABASE_URL", raising=False)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="Missing SUPABASE_URL"):
        build_block._resolve_supabase_url()

    assert "code=supabase_url_missing" in caplog.text


def test_resolve_supabase_url_allows_default_only_with_flag(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("ALLOW_DEFAULT_SUPABASE_URL", "1")

    assert build_block._resolve_supabase_url() == build_block.DEFAULT_SUPABASE_URL


def test_upload_to_supabase_logs_missing_credentials(tmp_path, monkeypatch, caplog):
    pdf_path = tmp_path / "plan.pdf"
    pdf_path.write_bytes(b"pdf")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("ALLOW_DEFAULT_SUPABASE_URL", "1")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="Missing Supabase credentials"):
        build_block.upload_to_supabase(str(pdf_path))

    assert "code=supabase_credentials_missing" in caplog.text
    assert "bucket=fight-plans" in caplog.text


def test_plan_banks_start_lazy_and_prime_on_demand():
    conditioning_mod = importlib.reload(importlib.import_module("fightcamp.conditioning"))
    strength_mod = importlib.reload(importlib.import_module("fightcamp.strength"))
    rehab_mod = importlib.reload(importlib.import_module("fightcamp.rehab_protocols"))

    assert conditioning_mod._conditioning_bank_cache is None
    assert conditioning_mod._style_conditioning_bank_cache is None
    assert conditioning_mod._format_weights_cache is None
    assert strength_mod._exercise_bank_cache is None
    assert strength_mod._style_exercises_cache is None
    assert rehab_mod._REHAB_BANK_CACHE is None

    conditioning_mod.prime_conditioning_banks()
    strength_mod.prime_strength_banks()
    rehab_mod.prime_rehab_bank()

    assert conditioning_mod._conditioning_bank_cache is not None
    assert conditioning_mod._style_conditioning_bank_cache is not None
    assert conditioning_mod._format_weights_cache is not None
    assert strength_mod._exercise_bank_cache is not None
    assert strength_mod._style_exercises_cache is not None
    assert rehab_mod._REHAB_BANK_CACHE is not None
