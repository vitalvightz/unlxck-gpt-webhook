import importlib
import logging
from pathlib import Path

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


def test_md_to_html_escapes_raw_html():
    rendered = build_block._md_to_html("Hello <script>alert(1)</script>")

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_build_html_document_escapes_inline_user_fields():
    rendered = build_block.build_html_document(
        full_name="<img src=x onerror=alert(1)>",
        sport="boxing<script>",
        phase_split="2 / 2 / 1",
        status="active",
    )

    assert "<img" not in rendered
    assert "<script>" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "boxing&lt;script&gt;" in rendered


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


# ── Auth config hardening tests ──────────────────────────────────────────────

def test_supabase_auth_service_raises_when_url_missing(monkeypatch):
    """from_env() must raise immediately if SUPABASE_URL is not set."""
    from api.auth import SupabaseAuthService

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        SupabaseAuthService.from_env()


def test_supabase_auth_service_raises_when_both_keys_missing(monkeypatch):
    """from_env() must raise when neither service-role nor anon key is set."""
    from api.auth import SupabaseAuthService

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        SupabaseAuthService.from_env()


def test_supabase_auth_service_warns_when_using_anon_key_fallback(monkeypatch, caplog):
    """from_env() succeeds with only SUPABASE_ANON_KEY but logs a warning."""
    from unittest.mock import MagicMock, patch
    from api.auth import SupabaseAuthService

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = MagicMock()
    with patch("api.auth.create_client", return_value=fake_client), caplog.at_level(logging.WARNING, logger="api.auth"):
        service = SupabaseAuthService.from_env()

    assert service.client is fake_client
    assert "SUPABASE_ANON_KEY" in caplog.text
    assert "SUPABASE_SERVICE_ROLE_KEY" in caplog.text


def test_supabase_auth_service_uses_service_role_key_when_both_set(monkeypatch):
    """from_env() prefers SUPABASE_SERVICE_ROLE_KEY over SUPABASE_ANON_KEY."""
    from unittest.mock import MagicMock, call, patch
    from api.auth import SupabaseAuthService

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = MagicMock()
    with patch("api.auth.create_client", return_value=fake_client) as mock_create:
        SupabaseAuthService.from_env()

    mock_create.assert_called_once_with("https://example.supabase.co", "service-role-key")


def test_supabase_app_store_raises_when_url_missing(monkeypatch):
    """SupabaseAppStore.from_env() must raise immediately if SUPABASE_URL is not set."""
    from api.store import SupabaseAppStore

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "key")

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        SupabaseAppStore.from_env()


def test_supabase_app_store_raises_when_service_role_key_missing(monkeypatch):
    """SupabaseAppStore.from_env() must raise if SUPABASE_SERVICE_ROLE_KEY is missing."""
    from api.store import SupabaseAppStore

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        SupabaseAppStore.from_env()


# ── Stage 2 artifact path tests ───────────────────────────────────────────────

def test_stage2_default_artifact_paths_are_under_artifacts_dir(monkeypatch):
    """Default artifact paths should live under .artifacts/stage2/, not the repo root."""
    import sys
    from run_stage2_validation import _DEFAULT_ARTIFACTS_DIR, parse_args

    monkeypatch.setattr(sys, "argv", ["run_stage2_validation.py"])
    args = parse_args()

    assert Path(args.handoff).parent == _DEFAULT_ARTIFACTS_DIR
    assert Path(args.final).parent == _DEFAULT_ARTIFACTS_DIR
    assert Path(args.retry).parent == _DEFAULT_ARTIFACTS_DIR
    assert str(_DEFAULT_ARTIFACTS_DIR).startswith(".artifacts")


def test_stage2_artifact_parent_dir_is_created_automatically(tmp_path, monkeypatch):
    """The script must create parent directories before writing artifact files."""
    import asyncio
    import json
    import sys
    from unittest.mock import AsyncMock, patch

    artifact_dir = tmp_path / ".artifacts" / "stage2"
    handoff_path = artifact_dir / "stage2_handoff.txt"
    assert not artifact_dir.exists()

    fake_stage1 = {
        "plan_text": "plan",
        "planning_brief": {},
        "stage2_payload": {},
        "stage2_handoff_text": "",
    }
    fake_package = {
        "handoff_text": "HANDOFF",
        "summary": "summary",
        "planning_brief": {},
        "draft_plan_text": "draft",
    }

    input_json = tmp_path / "input.json"
    input_json.write_text(json.dumps({"data": {"fields": []}}), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_stage2_validation.py",
            "--input",
            str(input_json),
            "--handoff",
            str(handoff_path),
            "--final",
            str(artifact_dir / "final_plan.txt"),
            "--retry",
            str(artifact_dir / "stage2_retry.txt"),
        ],
    )
    with (
        patch("run_stage2_validation.generate_plan", new=AsyncMock(return_value=fake_stage1)),
        patch("run_stage2_validation.build_stage2_package", return_value=fake_package),
    ):
        from run_stage2_validation import main as run_main

        exit_code = asyncio.run(run_main())

    assert artifact_dir.exists(), "Parent directory was not created"
    assert handoff_path.exists(), "Handoff file was not written"
    assert handoff_path.read_text(encoding="utf-8") == "HANDOFF"


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


def test_md_to_html_escapes_raw_html():
    rendered = build_block._md_to_html("Hello <script>alert(1)</script>")

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_build_html_document_escapes_inline_user_fields():
    rendered = build_block.build_html_document(
        full_name="<img src=x onerror=alert(1)>",
        sport="boxing<script>",
        phase_split="2 / 2 / 1",
        status="active",
    )

    assert "<img" not in rendered
    assert "<script>" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "boxing&lt;script&gt;" in rendered


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

