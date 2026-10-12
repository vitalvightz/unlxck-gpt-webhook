"""Pin the production 23502 failure and distinguish it from missing columns."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError

from api.store import PLAN_RUNTIME_SCHEMA_ERROR_DETAIL, SupabaseAppStore
from tests.support import _build_request


def error(code, message, details=None, hint=None):
    return APIError(dict(code=code, message=message, details=details, hint=hint))


@pytest.mark.parametrize("metadata", [None, {}, {"source": "stage1", "warnings": ["review"]}])
def test_create_plan_normalizes_only_null_parsing_metadata(metadata):
    client = MagicMock()
    client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "plan"}]
    store = SupabaseAppStore(client=client, admin_emails=set())
    store.create_plan(athlete_id="athlete", intake_id="intake", request=_build_request(),
                      result={"parsing_metadata": metadata})
    assert client.table.return_value.insert.call_args.args[0]["parsing_metadata"] == (
        {} if metadata is None else metadata
    )


@pytest.mark.parametrize("code,message", [
    ("23502", 'null value in column "parsing_metadata" of relation "plans" violates not-null constraint'),
    ("23503", 'insert or update on table "plans" violates foreign key constraint "plans_intake_id_fkey"'),
    ("23514", 'new row for relation "plans" violates check constraint "plans_status_check"'),
    ("23505", 'duplicate key value violates unique constraint "plans_pkey"'),
    ("22P02", 'invalid input syntax for type json'),
    ("22023", 'invalid parameter value for plans.structured_plan'),
    ("42501", 'new row violates row-level security policy for table "plans"'),
    ("PGRST102", 'Empty or invalid json'),
])
def test_unrelated_errors_never_trigger_schema_fallback_or_schema_response(code, message, monkeypatch, caplog):
    monkeypatch.setenv("UNLXCK_ALLOW_LEGACY_PLAN_SCHEMA_FALLBACK", "1")
    client = MagicMock()
    exc = error(code, message, "Failing row contains (private athlete prescription, plans, parsing_metadata).",
                "Private hint: plans column structured_plan could not find schema cache")
    client.table.return_value.insert.return_value.execute.side_effect = exc
    store = SupabaseAppStore(client=client, admin_emails=set())
    assert not store._is_plan_schema_column_error(exc)
    with pytest.raises(HTTPException) as rejected:
        store.create_plan(athlete_id="athlete", intake_id="intake", request=_build_request(), result={})
    assert "schema" not in rejected.value.detail and "missing" not in rejected.value.detail
    assert client.table.return_value.insert.call_count == 1
    assert f"code={code}" in caplog.text
    assert message in caplog.text
    assert "private athlete prescription" not in caplog.text
    assert "Private hint" not in caplog.text


@pytest.mark.parametrize("code,message,column", [
    ("PGRST204", "Could not find the 'structured_plan' column of 'plans' in the schema cache", "structured_plan"),
    ("42703", 'column plans.parsing_metadata does not exist', "parsing_metadata"),
    ("42703", 'column "planning_brief" of relation "plans" does not exist', "planning_brief"),
    ("42703", 'column public.plans."structured_plan" does not exist', "structured_plan"),
])
def test_genuine_runtime_column_errors_are_classified_and_logged(code, message, column, caplog):
    client = MagicMock()
    exc = error(code, message)
    client.table.return_value.insert.return_value.execute.side_effect = exc
    store = SupabaseAppStore(client=client, admin_emails=set())
    assert store._missing_plan_column(exc) == column
    assert store._is_plan_schema_column_error(exc)
    with pytest.raises(HTTPException) as rejected:
        store.create_plan(athlete_id="athlete", intake_id="intake", request=_build_request(), result={})
    assert rejected.value.detail == PLAN_RUNTIME_SCHEMA_ERROR_DETAIL
    assert f"code={code}" in caplog.text and "create_plan:postgrest_error" in caplog.text


def test_hint_cannot_turn_another_tables_missing_column_into_plans_schema_error():
    store = SupabaseAppStore(client=MagicMock(), admin_emails=set())
    exc = error("42703", "column athlete_intakes.parsing_metadata does not exist",
                hint="Perhaps you meant plans.structured_plan")
    assert not store._is_plan_schema_column_error(exc)
    assert store._create_plan_error_detail(exc) == "plan persistence failed"


def test_startup_validation_preserves_non_column_error():
    client = MagicMock()
    exc = error("23502", 'null value in column "parsing_metadata" of relation "plans" violates not-null constraint')
    client.table.return_value.select.return_value.limit.return_value.execute.side_effect = exc
    store = SupabaseAppStore(client=client, admin_emails=set())
    with pytest.raises(APIError) as rejected:
        store.validate_runtime_schema()
    assert rejected.value is exc
