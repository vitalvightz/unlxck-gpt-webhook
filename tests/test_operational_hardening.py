import importlib
import logging

from fightcamp import build_block


def test_optional_import_loader_logs_non_import_failure(monkeypatch, caplog):
    def _boom(module_name: str):
        raise RuntimeError(f"bad import side effect for {module_name}")

    monkeypatch.setattr(build_block.importlib, "import_module", _boom)

    with caplog.at_level(logging.ERROR):
        result = build_block._load_optional_module("fake.optional.module")

    assert result is None
    assert "[optional-import-failed] module=fake.optional.module" in caplog.text


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


def test_build_html_document_sanitizes_raw_html_fragments():
    rendered = build_block.build_html_document(
        full_name="Ari Mensah",
        sport="boxing",
        phase_split="2 / 2 / 1",
        status="active",
        athlete_profile_html='''<p onclick="alert(1)">Safe</p><script>alert(1)</script><a href="javascript:alert(1)">bad</a><a href="https://example.com">ok</a>''',
        selection_rationale_html='<iframe src="https://example.com"></iframe><p>Selection</p>',
    )

    assert "<script>" not in rendered
    assert "<iframe" not in rendered
    assert "onclick=" not in rendered
    assert 'href="javascript:alert(1)"' not in rendered
    assert '<a href="https://example.com">ok</a>' in rendered
    assert "<p>Selection</p>" in rendered


def test_plan_banks_start_lazy_and_prime_on_demand():
    conditioning_mod = importlib.reload(importlib.import_module("fightcamp.conditioning"))
    strength_mod = importlib.reload(importlib.import_module("fightcamp.strength"))
    rehab_mod = importlib.reload(importlib.import_module("fightcamp.rehab_protocols"))

    assert conditioning_mod._conditioning_bank_cache is None
    assert conditioning_mod._style_conditioning_bank_cache is None
    assert conditioning_mod._format_weights_cache is None
    assert strength_mod._exercise_bank_cache is None
    assert rehab_mod._REHAB_BANK_CACHE is None

    conditioning_mod.prime_conditioning_banks()
    strength_mod.prime_strength_banks()
    rehab_mod.prime_rehab_bank()

    assert conditioning_mod._conditioning_bank_cache is not None
    assert conditioning_mod._style_conditioning_bank_cache is not None
    assert conditioning_mod._format_weights_cache is not None
    assert strength_mod._exercise_bank_cache is not None
    assert rehab_mod._REHAB_BANK_CACHE is not None
