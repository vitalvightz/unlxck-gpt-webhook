"""SupabaseAppStore.upsert_exercise_logs: a batch is one atomic statement."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.store import SupabaseAppStore

ROWS = [
    {"plan_id": "p", "training_day": "2026-10-07", "block_id": "a", "status": "as_prescribed"},
    {"plan_id": "p", "training_day": "2026-10-07", "block_id": "b", "status": "skipped"},
]


def _store(data):
    client = MagicMock()
    query = client.table.return_value.upsert.return_value
    query.execute.return_value = SimpleNamespace(data=data)
    return SupabaseAppStore(client=client, admin_emails=set()), client


@pytest.mark.parametrize("keep_existing", [False, True])
def test_the_whole_batch_goes_in_one_upsert_request(keep_existing):
    store, client = _store([{**row, "athlete_id": "ath"} for row in ROWS])

    written = store.upsert_exercise_logs("ath", ROWS, keep_existing=keep_existing)

    client.table.assert_called_once_with("exercise_logs")
    client.table.return_value.upsert.assert_called_once_with(
        [{"athlete_id": "ath", **row} for row in ROWS],
        on_conflict="athlete_id,plan_id,training_day,block_id",
        # keep_existing is ON CONFLICT DO NOTHING, decided in the same statement.
        ignore_duplicates=keep_existing,
    )
    assert [row["block_id"] for row in written] == ["a", "b"]


def test_a_short_write_without_keep_existing_is_an_error():
    store, _client = _store([{**ROWS[0], "athlete_id": "ath"}])

    with pytest.raises(HTTPException) as caught:
        store.upsert_exercise_logs("ath", ROWS)

    assert caught.value.status_code == 500


def test_keep_existing_returns_only_the_rows_it_inserted():
    store, _client = _store([{**ROWS[1], "athlete_id": "ath"}])

    assert [row["block_id"] for row in store.upsert_exercise_logs("ath", ROWS, keep_existing=True)] == ["b"]


def test_an_empty_batch_makes_no_request():
    store, client = _store([])

    assert store.upsert_exercise_logs("ath", []) == []
    client.table.assert_not_called()
