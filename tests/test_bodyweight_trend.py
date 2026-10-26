from __future__ import annotations

from datetime import date

from api.bodyweight_trend import daily_readings, seven_day_average, smoothed_trend, weekly_pace
from api.models import NutritionBodyweightLogEntry


def _entry(day: str, weight: float, time: str | None = "07:00", fasted: bool | None = True) -> NutritionBodyweightLogEntry:
    return NutritionBodyweightLogEntry(date=day, weight_kg=weight, time=time, is_fasted=fasted)


def test_one_reading_per_day_prefers_the_earliest_fasted_weigh_in():
    readings = daily_readings([
        _entry("2026-10-02", 73.9, "18:30", False),
        _entry("2026-10-02", 73.1, "07:10", True),
        _entry("2026-10-02", 72.6, "12:00", False),
        _entry("2026-10-01", 74.0, None, None),
        _entry("2026-10-01", 74.4, "09:00", False),
    ])
    assert readings == [(date(2026, 10, 1), 74.4), (date(2026, 10, 2), 73.1)]


def test_trend_smooths_a_one_day_spike_and_counts_gaps():
    trend = smoothed_trend([(date(2026, 10, 1), 74.0), (date(2026, 10, 2), 75.0), (date(2026, 10, 3), 74.0)])
    assert [point.trend_weight_kg for point in trend] == [74.0, 74.2, 74.16]
    assert trend[1].scale_weight_kg == 75.0

    gap = smoothed_trend([(date(2026, 10, 1), 74.0), (date(2026, 10, 4), 73.0)])
    # Three days apart moves the trend as far as three logged days would.
    assert gap[1].trend_weight_kg == round(74.0 - (1 - 0.8 ** 3), 2)


def test_seven_day_average_uses_calendar_days_not_entries():
    readings = [(date(2026, 10, day), 70.0 + day / 10) for day in (1, 2, 20, 24, 26)]
    assert seven_day_average(readings, date(2026, 10, 26)) == (72.3, 3)
    assert seven_day_average(readings, date(2026, 11, 10)) == (None, 0)


def test_weekly_pace_needs_two_weeks_of_recent_readings():
    steady = [(date(2026, 10, day), 75.0 - (day - 1) / 7 * 0.6) for day in range(1, 26, 3)]
    assert weekly_pace(steady, date(2026, 10, 26)) == -0.6
    # Under two weeks between first and last reading.
    assert weekly_pace(steady[-5:], date(2026, 10, 26)) is None
    # Too few readings.
    assert weekly_pace(steady[::2], date(2026, 10, 26)) is None
    # Latest reading over a week old.
    assert weekly_pace(steady, date(2026, 11, 5)) is None


def test_latest_calendar_day_is_already_tomorrow_east_of_the_date_line():
    from datetime import datetime, timezone

    from api.nutrition_workspace import latest_calendar_day

    assert latest_calendar_day(datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)) == date(2026, 10, 26)
    assert latest_calendar_day(datetime(2026, 10, 26, 11, 0, tzinfo=timezone.utc)) == date(2026, 10, 27)
