from datetime import datetime, timezone

from api.performance_focus import get_performance_focus_cap


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
