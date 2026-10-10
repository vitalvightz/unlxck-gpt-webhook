"""Ensure service-role writes stay owner scoped and retries never overwrite."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from api.store import SupabaseAppStore


def store_query():
    client = MagicMock()
    query = client.table.return_value
    for method in ("select", "eq", "is_", "order", "limit", "upsert", "update"):
        getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "entry", "athlete_id": "owner"}])
    return SupabaseAppStore(client=client, admin_emails=set()), query


def test_atomic_insert_does_not_overwrite_an_edit_or_trust_client_owner():
    store, query = store_query()
    fields = {"client_request_id": "request", "athlete_id": "attacker", "duration_minutes": 60}
    assert store.create_external_training_session("owner", fields)["id"] == "entry"
    query.upsert.assert_called_once_with({**fields, "athlete_id": "owner"},
        on_conflict="athlete_id,client_request_id", ignore_duplicates=True)
    assert ("athlete_id", "owner") in [call.args for call in query.eq.call_args_list]


def test_update_whitelist_cannot_move_date_owner_or_idempotency_key():
    store, query = store_query()
    fields = {"activity": "boxing", "duration_minutes": 45, "effort": "easy",
              "athlete_id": "other", "training_day": "2027-01-01", "client_request_id": "changed"}
    store.update_external_training_session("owner", "entry", fields)
    query.update.assert_called_once_with({key: fields[key] for key in ("activity", "duration_minutes", "effort")})
    assert [call.args for call in query.eq.call_args_list] == [("athlete_id", "owner"), ("id", "entry")]
    query.is_.assert_called_once_with("deleted_at", "null")


def test_list_excludes_tombstones_and_other_owners():
    store, query = store_query()
    store.list_external_training_sessions("owner", limit=20)
    query.eq.assert_called_once_with("athlete_id", "owner")
    query.is_.assert_called_once_with("deleted_at", "null")
    query.limit.assert_called_once_with(20)


def test_internal_refresh_can_see_tombstones_without_losing_owner_scope():
    store, query = store_query()
    store.list_external_training_sessions("owner", include_deleted=True)
    query.eq.assert_called_once_with("athlete_id", "owner")
    query.is_.assert_not_called()


def test_delete_is_scoped_even_with_privileged_client():
    store, query = store_query()
    assert store.delete_external_training_session("owner", "entry")
    assert [call.args for call in query.eq.call_args_list] == [("athlete_id", "owner"), ("id", "entry")] * 2
    assert set(query.update.call_args.args[0]) == {"deleted_at"}
