"""Tests for the athlete-local training day resolver (Block 4 §3)."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from api.contracts.training_day import (
    DAY_ROLLOVER_HOUR,
    current_training_day,
    resolve_timezone,
    resolve_training_day,
    resolve_training_day_str,
)

NY = "America/New_York"


class TestRollover:
    def test_0259_local_maps_to_previous_training_day(self):
        # 02:59 local is before the 03:00 rollover -> previous training day.
        ts = datetime(2026, 6, 18, 2, 59, tzinfo=ZoneInfo(NY))
        assert resolve_training_day(ts, athlete_timezone=NY) == date(2026, 6, 17)

    def test_0300_local_maps_to_current_training_day(self):
        # 03:00 local is exactly the rollover -> current training day.
        ts = datetime(2026, 6, 18, 3, 0, tzinfo=ZoneInfo(NY))
        assert resolve_training_day(ts, athlete_timezone=NY) == date(2026, 6, 18)

    def test_just_before_midnight_is_same_training_day(self):
        ts = datetime(2026, 6, 18, 23, 30, tzinfo=ZoneInfo(NY))
        assert resolve_training_day(ts, athlete_timezone=NY) == date(2026, 6, 18)


class TestTimezoneDefinesDay:
    def test_utc_instant_alone_does_not_define_training_day(self):
        # Same instant, two timezones -> two different training days. The UTC
        # calendar day does not define the athlete-facing training day.
        ts = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        assert resolve_training_day(ts, athlete_timezone=NY) == date(2026, 6, 17)
        assert resolve_training_day(ts) == date(2026, 6, 18)  # UTC fallback

    def test_naive_timestamp_treated_as_utc(self):
        naive = datetime(2026, 6, 18, 6, 0)
        aware = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        assert resolve_training_day(naive, athlete_timezone=NY) == resolve_training_day(
            aware, athlete_timezone=NY
        )


class TestSafeFallback:
    def test_missing_timezone_falls_back_without_crashing(self):
        ts = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        # None and an unknown timezone both fall back to the UTC default.
        assert resolve_training_day(ts, athlete_timezone=None) == date(2026, 6, 18)
        assert resolve_training_day(ts, athlete_timezone="Not/AZone") == date(2026, 6, 18)

    def test_blank_timezone_falls_back(self):
        ts = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        assert resolve_training_day(ts, athlete_timezone="   ") == date(2026, 6, 18)

    def test_default_timezone_is_used_when_athlete_missing(self):
        ts = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)
        assert resolve_training_day(
            ts, athlete_timezone=None, default_timezone=NY
        ) == date(2026, 6, 17)

    def test_resolve_timezone_falls_back_to_utc(self):
        assert resolve_timezone("Not/AZone", default_timezone="Also/Bad") == timezone.utc


class TestHelpers:
    def test_rollover_hour_constant_is_three(self):
        assert DAY_ROLLOVER_HOUR == 3

    def test_str_helper_matches_iso(self):
        ts = datetime(2026, 6, 18, 3, 0, tzinfo=ZoneInfo(NY))
        assert resolve_training_day_str(ts, athlete_timezone=NY) == "2026-06-18"

    def test_current_training_day_accepts_injected_now(self):
        now = datetime(2026, 6, 18, 2, 59, tzinfo=ZoneInfo(NY))
        assert current_training_day(now=now, athlete_timezone=NY) == date(2026, 6, 17)
