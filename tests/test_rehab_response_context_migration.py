from pathlib import Path

from api.schema_requirements import REQUIRED_SESSION_COMPLETIONS_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260820180000_persist_rehab_response_contexts.sql"
SQL = MIGRATION.read_text(encoding="utf-8").lower()


def test_completion_context_is_nullable_json_array_with_no_new_access_grant():
    assert "add column if not exists rehab_response_contexts jsonb" in SQL
    assert "rehab_response_contexts is null" in SQL
    assert "jsonb_typeof(rehab_response_contexts) = 'array'" in SQL
    assert "\ngrant " not in SQL
    assert "\ncreate policy" not in SQL


def test_runtime_schema_gate_requires_the_context_column():
    assert "rehab_response_contexts" in REQUIRED_SESSION_COMPLETIONS_COLUMNS
