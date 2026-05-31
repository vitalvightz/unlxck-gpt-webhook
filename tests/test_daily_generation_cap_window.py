from __future__ import annotations

from datetime import datetime, timezone

from api.generation_job_helpers import (
    _DAILY_LIMIT_DETAIL_TZ_AWARE,
    _DAILY_LIMIT_DETAIL_UTC,
    daily_generation_cap_window,
)

# Fixed reference instant: 2026-05-31T02:00:00Z.
_NOW = datetime(2026, 5, 31, 2, 0, 0, tzinfo=timezone.utc)


def test_explicit_utc_timezone_is_tz_aware():
    # A valid "UTC" zone is honoured as the athlete's timezone (not a fallback),
    # so the reset window is UTC midnight and the message is the tz-aware one.
    cutoff, detail = daily_generation_cap_window("UTC", now=_NOW)
    assert cutoff == "2026-05-31T00:00:00+00:00"
    assert detail == _DAILY_LIMIT_DETAIL_TZ_AWARE


def test_non_utc_timezone_west_of_utc():
    # America/New_York is UTC-4 during May (DST). 02:00Z is 22:00 the previous
    # local day, so the local day starts at 2026-05-30T00:00-04:00 == 04:00Z.
    cutoff, detail = daily_generation_cap_window("America/New_York", now=_NOW)
    assert cutoff == "2026-05-30T04:00:00+00:00"
    assert detail == _DAILY_LIMIT_DETAIL_TZ_AWARE


def test_non_utc_timezone_east_of_utc():
    # Pacific/Auckland is UTC+12 in May. 02:00Z is 14:00 local same day, so the
    # local day starts at 2026-05-31T00:00+12:00 == 2026-05-30T12:00Z.
    cutoff, detail = daily_generation_cap_window("Pacific/Auckland", now=_NOW)
    assert cutoff == "2026-05-30T12:00:00+00:00"
    assert detail == _DAILY_LIMIT_DETAIL_TZ_AWARE


def test_invalid_timezone_falls_back_to_utc():
    cutoff, detail = daily_generation_cap_window("Not/AZone", now=_NOW)
    assert cutoff == "2026-05-31T00:00:00+00:00"
    assert detail == _DAILY_LIMIT_DETAIL_UTC


def test_missing_timezone_falls_back_to_utc():
    for value in ("", "   ", None):
        cutoff, detail = daily_generation_cap_window(value, now=_NOW)
        assert cutoff == "2026-05-31T00:00:00+00:00"
        assert detail == _DAILY_LIMIT_DETAIL_UTC


def test_naive_reference_is_treated_as_utc():
    # A naive reference is assumed to be UTC; with no athlete timezone this
    # falls back to the UTC reset window and message.
    naive_now = datetime(2026, 5, 31, 2, 0, 0)
    cutoff, detail = daily_generation_cap_window(None, now=naive_now)
    assert cutoff == "2026-05-31T00:00:00+00:00"
    assert detail == _DAILY_LIMIT_DETAIL_UTC
