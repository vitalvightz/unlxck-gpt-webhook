"""Credit writes must preserve a concurrent independent report in the DB."""
from types import SimpleNamespace

from tests.test_store_external_training import store_query


def test_credit_write_is_insert_only_then_conditionally_updates_owned_credit():
    store, query = store_query()
    fields = {"plan_id": "plan", "session_id": "session", "training_day": "2026-10-18",
              "status": "done", "completion_origin": "day_credit"}
    store.upsert_session_completion("owner", fields)
    query.upsert.assert_called_once_with({**fields, "athlete_id": "owner"},
        on_conflict="athlete_id,session_id,training_day", ignore_duplicates=True)
    assert [call.args for call in query.eq.call_args_list] == [
        ("athlete_id", "owner"), ("session_id", "session"), ("training_day", "2026-10-18"),
        ("plan_id", "plan"), ("completion_origin", "day_credit")]


def test_report_winning_credit_race_is_returned_without_an_unconditional_retry():
    store, query = store_query()
    winner = {"id": "existing", "completion_origin": "reported", "session_rpe": 9}
    query.execute.side_effect = [SimpleNamespace(data=[]), SimpleNamespace(data=[]), SimpleNamespace(data=[winner])]
    assert store.upsert_session_completion("owner", {"plan_id": "plan", "session_id": "session",
        "training_day": "2026-10-18", "status": "done", "completion_origin": "day_credit"}) == winner
    assert query.upsert.call_count == 1
    assert query.update.call_count == 1
