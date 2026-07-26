import math
from datetime import datetime, timezone

from api.performance_focus import (
    get_performance_focus_cap,
    validate_performance_focus_selections,
)


def _cap(days_until_fight: int) -> int:
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)
    fight_date = (now.date()).fromordinal(now.date().toordinal() + days_until_fight).isoformat()
    cap = get_performance_focus_cap(fight_date, now=now, time_zone="UTC")
    assert cap is not None
    return cap.max_selections


def test_backend_fight_week_cap_is_2():
    assert _cap(2) == 2


def test_backend_ultra_short_cap_is_3():
    assert _cap(14) == 3


def test_backend_short_camp_cap_is_4():
    assert _cap(35) == 4


def test_backend_mid_length_cap_is_5():
    assert _cap(56) == 5


def test_backend_long_camp_cap_is_6():
    assert _cap(120) == 6


def test_backend_past_fight_date_has_no_cap():
    now = datetime(2026, 5, 25, tzinfo=timezone.utc)
    assert get_performance_focus_cap("2026-05-01", now=now, time_zone="UTC") is None


# Open plans are capped too. Mirrors OPEN_PLAN_FOCUS_CAP in
# web/lib/performance-focus-cap.ts: without this the server accepted unlimited
# focus picks whenever there was no fight date to band on.
def test_backend_open_plan_cap_is_5():
    for fight_date in ("", None, "   "):
        cap = get_performance_focus_cap(fight_date, time_zone="UTC")
        assert cap is not None, fight_date
        assert cap.max_selections == 5
        assert cap.window_label == "Open plan"
        assert cap.days_until_fight == math.inf


def test_backend_unparseable_fight_date_falls_back_to_open_plan_cap():
    for fight_date in ("not-a-date", "2026-02-31", "20260525"):
        cap = get_performance_focus_cap(fight_date, time_zone="UTC")
        assert cap is not None, fight_date
        assert cap.max_selections == 5


def test_backend_open_plan_blocks_selections_over_the_cap():
    validation = validate_performance_focus_selections(
        "",
        key_goals=["power", "conditioning", "mobility"],
        weak_areas=["gas_tank", "defense", "timing"],
        time_zone="UTC",
    )
    assert validation.is_over_cap is True
    assert validation.excess_selections == 1
    assert validation.error_message == (
        "This camp allows 5 total focus picks. Remove 1 goal or weak-area selection before generating."
    )


def test_backend_open_plan_allows_selections_at_the_cap():
    validation = validate_performance_focus_selections(
        "",
        key_goals=["power", "conditioning", "mobility"],
        weak_areas=["gas_tank", "defense"],
        time_zone="UTC",
    )
    assert validation.is_over_cap is False
    assert validation.error_message is None
