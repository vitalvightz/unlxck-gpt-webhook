from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from api.store import SupabaseAppStore


def _response() -> dict:
    return {
        "state": {
            "total_xp": 10,
            "last_daily_login_date": "2026-08-01",
            "recent_awards": [],
        },
        "previous_total_xp": 0,
        "awarded": True,
        "award": None,
    }


def test_store_awards_xp_through_atomic_rpc():
    client = MagicMock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=_response())
    store = SupabaseAppStore(client=client, admin_emails=set())

    result = store.award_xp(
        "11111111-1111-1111-1111-111111111111",
        action="daily_login",
        idempotency_key="daily-login:2026-08-01",
        calendar_date="2026-08-01",
    )

    assert result["state"]["total_xp"] == 10
    client.rpc.assert_called_once_with(
        "award_athlete_xp",
        {
            "p_athlete_id": "11111111-1111-1111-1111-111111111111",
            "p_action": "daily_login",
            "p_idempotency_key": "daily-login:2026-08-01",
            "p_calendar_date": "2026-08-01",
        },
    )


@pytest.mark.parametrize("payload", [None, [], "not-an-object"])
def test_store_rejects_invalid_rpc_payloads(payload):
    client = MagicMock()
    client.rpc.return_value.execute.return_value = SimpleNamespace(data=payload)
    store = SupabaseAppStore(client=client, admin_emails=set())

    with pytest.raises(HTTPException) as raised:
        store.award_xp(
            "11111111-1111-1111-1111-111111111111",
            action="daily_login",
            idempotency_key="daily-login:2026-08-01",
            calendar_date="2026-08-01",
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == "XP service temporarily unavailable"
