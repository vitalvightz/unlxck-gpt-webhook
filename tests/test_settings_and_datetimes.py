"""api/settings.py and api/datetimes.py: the one reading of env settings and of timestamps."""

from datetime import date, datetime, timedelta, timezone

import pytest

from api import app as app_module
from api.datetimes import parse_calendar_date, parse_utc_datetime
from api.generation import scheduler
from api.settings import env_csv, env_flag, env_float, env_int


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 5), ("", 5), ("  ", 5), ("7", 7), (" 7 ", 7), ("0", 1), ("99", 10), ("abc", 5), ("2.5", 5)],
)
def test_env_int(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("X_INT", raising=False)
    else:
        monkeypatch.setenv("X_INT", raw)

    assert env_int("X_INT", 5, minimum=1, maximum=10) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 6.0), ("2.5", 2.5), ("0.2", 1.0), ("0", 6.0), ("-3", 6.0), ("inf", 6.0), ("nan", 6.0), ("x", 6.0)],
)
def test_env_float_positive(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("X_FLOAT", raising=False)
    else:
        monkeypatch.setenv("X_FLOAT", raw)

    assert env_float("X_FLOAT", 6.0, minimum=1.0, positive=True) == expected


@pytest.mark.parametrize(
    ("raw", "default", "expected"),
    [
        (None, False, False),
        (None, True, True),
        ("1", False, True),
        ("TRUE", False, True),
        ("yes", False, True),
        ("0", True, False),
        ("off", True, False),
        ("maybe", True, True),
    ],
)
def test_env_flag(monkeypatch, raw, default, expected):
    if raw is None:
        monkeypatch.delenv("X_FLAG", raising=False)
    else:
        monkeypatch.setenv("X_FLAG", raw)

    assert env_flag("X_FLAG", default) is expected


def test_env_csv(monkeypatch):
    monkeypatch.setenv("X_CSV", " A@x.com, ,b@Y.com ")

    assert env_csv("X_CSV", lower=True) == ("a@x.com", "b@y.com")


def test_settings_are_read_when_used(monkeypatch):
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "3")
    assert app_module._plan_generate_daily_limit_per_user() == 3
    monkeypatch.setenv("APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER", "8")
    assert app_module._plan_generate_daily_limit_per_user() == 8


def test_in_process_generation_is_one_flag(monkeypatch):
    # The API and the worker used to read this flag with different rules.
    for raw in ("1", "true", "yes", "0", "false", ""):
        monkeypatch.setenv("UNLXCK_ENABLE_IN_PROCESS_GENERATION", raw)
        assert app_module.is_in_process_generation_enabled() is scheduler.is_in_process_generation_enabled(), raw


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-01T09:00:00Z", datetime(2026, 8, 1, 9, tzinfo=timezone.utc)),
        ("2026-08-01T11:00:00+02:00", datetime(2026, 8, 1, 9, tzinfo=timezone.utc)),
        ("2026-08-01T09:00:00", datetime(2026, 8, 1, 9, tzinfo=timezone.utc)),
        (" 2026-08-01T09:00:00Z ", datetime(2026, 8, 1, 9, tzinfo=timezone.utc)),
        (datetime(2026, 8, 1, 4, tzinfo=timezone(timedelta(hours=-5))), datetime(2026, 8, 1, 9, tzinfo=timezone.utc)),
        ("not a time", None),
        ("", None),
        (None, None),
        (date(2026, 8, 1), None),
    ],
)
def test_parse_utc_datetime(value, expected):
    parsed = parse_utc_datetime(value)

    assert parsed == expected
    if parsed is not None:
        assert parsed.tzinfo is timezone.utc


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-01", date(2026, 8, 1)),
        ("2026-08-01T23:30:00Z", date(2026, 8, 1)),
        (" 2026-08-01 ", date(2026, 8, 1)),
        (date(2026, 8, 1), date(2026, 8, 1)),
        ("2026-02-30", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_calendar_date(value, expected):
    assert parse_calendar_date(value) == expected
