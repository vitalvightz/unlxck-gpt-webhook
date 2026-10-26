"""Read an athlete's weigh-in log as one scale reading per day.

A fighter often weighs in more than once a day (morning, before and after
training). Those readings are not comparable, so every summary here starts from
one reading per calendar day: the day's earliest fasted weigh-in, else its
earliest weigh-in. Summaries are descriptive only; nothing here forecasts a date
or prescribes a cut.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from api.datetimes import parse_calendar_date
from api.models import NutritionBodyweightLogEntry, NutritionBodyweightTrendPoint

# Share of each new day's reading the trend moves toward. 0.2 smooths
# day-to-day water swings while lagging a steady 1 kg/week loss by ~0.5 kg.
TREND_SMOOTHING = 0.2
PACE_WINDOW_DAYS = 28
PACE_MIN_SPAN_DAYS = 14
PACE_MIN_READINGS = 6
PACE_MAX_STALENESS_DAYS = 7


def daily_readings(entries: Iterable[NutritionBodyweightLogEntry]) -> list[tuple[date, float]]:
    """One scale reading per day, oldest first."""
    chosen: dict[date, tuple[tuple[bool, str], float]] = {}
    for entry in entries:
        day = parse_calendar_date(entry.date)
        if day is None or not entry.weight_kg or entry.weight_kg <= 0:
            continue
        # Fasted before fed; then earliest time, with an unknown time last.
        rank = (entry.is_fasted is not True, (entry.time or "").strip() or "99:99")
        if day not in chosen or rank < chosen[day][0]:
            chosen[day] = (rank, float(entry.weight_kg))
    return [(day, weight) for day, (_, weight) in sorted(chosen.items())]


def smoothed_trend(readings: list[tuple[date, float]]) -> list[NutritionBodyweightTrendPoint]:
    """An exponentially smoothed trend through the daily readings.

    A gap of several days moves the trend as far as that many logged days would,
    so irregular logging is not over- or under-weighted.
    """
    points: list[NutritionBodyweightTrendPoint] = []
    trend: float | None = None
    previous: date | None = None
    for day, weight in readings:
        if trend is None or previous is None:
            trend = weight
        else:
            gap = max(1, (day - previous).days)
            trend += (1 - (1 - TREND_SMOOTHING) ** gap) * (weight - trend)
        previous = day
        points.append(
            NutritionBodyweightTrendPoint(
                date=day.isoformat(),
                scale_weight_kg=round(weight, 1),
                trend_weight_kg=round(trend, 2),
            )
        )
    return points


def seven_day_average(readings: list[tuple[date, float]], today: date) -> tuple[float | None, int]:
    """Mean daily reading over today and the six days before it, with the day count."""
    window = [weight for day, weight in readings if today - timedelta(days=6) <= day <= today]
    if not window:
        return None, 0
    return round(sum(window) / len(window), 1), len(window)


def weekly_pace(readings: list[tuple[date, float]], today: date) -> float | None:
    """Least-squares change in kg per week over the last four weeks.

    Only reported with enough evidence: at least six daily readings spanning two
    weeks, the latest within the past week. Negative means losing.
    """
    window = [(day, weight) for day, weight in readings if today - timedelta(days=PACE_WINDOW_DAYS - 1) <= day <= today]
    if len(window) < PACE_MIN_READINGS:
        return None
    first, last = window[0][0], window[-1][0]
    if (last - first).days < PACE_MIN_SPAN_DAYS or (today - last).days >= PACE_MAX_STALENESS_DAYS:
        return None
    xs = [(day - first).days for day, _ in window]
    ys = [weight for _, weight in window]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if not spread:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread
    return round(slope * 7, 1) + 0.0
